"""ADK root agent and orchestration helpers for Aegis."""

from __future__ import annotations

import json
import os
import shutil
import time
from textwrap import dedent
from typing import Any

from google.adk.apps import App
from google.adk.tools.function_tool import FunctionTool

try:
    from google.adk.agents import LlmAgent as BaseAgent
except ImportError:  # pragma: no cover - depends on ADK version
    from google.adk.agents import Agent as BaseAgent

from .actions import create_dynatrace_notebook
from .actions import get_service_metrics
from .actions import open_github_pr
from .actions import post_slack
from .actions import reset_metrics
from .actions import set_hardening
from .actions import write_scorecard
from .config import get_config
from .dynatrace import create_notebook
from .dynatrace import list_dynatrace_tools
from .dynatrace import query_dql
from .events import event_bus
from .experiment import run_experiment


config = get_config()


# Known dependency edges in the demo topology. The downstream `service` is the
# one whose live request metrics we measure; `hardened` reflects whether that
# call path currently has timeout/retry protection.
_CANDIDATE_EDGES = [
    {"edge": "frontend->payment", "service": "payment", "on_request_path": True, "hardened": True},
    {"edge": "payment->store", "service": "store", "on_request_path": True, "hardened": False},
]


def _score_candidate(stats: dict[str, Any], edge: dict[str, Any], config) -> float:
    """Deterministic risk score from measured stats + structural risk factors."""

    bad_ratio = float(stats.get("bad_ratio", 0.0))
    p95_ms = float(stats.get("p95_ms", 0.0))
    latency_pressure = min(p95_ms / max(config.latency_threshold_ms, 1), 1.5)
    hardening_gap = 0.0 if edge.get("hardened") else 1.0
    path_weight = 1.0 if edge.get("on_request_path") else 0.4
    # Weighted blend: measured failure ratio, latency headroom used, and the
    # structural fact that an unhardened request-path dependency is fragile.
    return round(
        (3.0 * bad_ratio + 1.0 * latency_pressure + 2.0 * hardening_gap) * path_weight, 3
    )


def _discover_candidates(config) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for edge in _CANDIDATE_EDGES:
        stats = get_service_metrics(edge["service"], config=config)
        candidates.append(
            {
                "edge": edge["edge"],
                "service": edge["service"],
                "hardened": edge["hardened"],
                "bad_ratio": round(float(stats.get("bad_ratio", 0.0)), 4),
                "p95_ms": float(stats.get("p95_ms", 0.0)),
                "samples": int(stats.get("total", 0)),
                "risk_score": _score_candidate(stats, edge, config),
            }
        )
    candidates.sort(key=lambda c: c["risk_score"], reverse=True)
    return candidates


def _choose_target_with_gemini(candidates: list[dict[str, Any]], config) -> dict[str, Any] | None:
    """Ask Gemini to pick the target + latency from measured candidates.

    Returns a validated decision dict, or None to fall back to deterministic
    ranking (no API key, library missing, or an unparseable / invalid reply).
    """

    if not config.google_api_key:
        return None
    try:
        from google import genai

        client = genai.Client(api_key=config.google_api_key)
        prompt = dedent(
            f"""
            You are a site-reliability engineer planning a chaos game-day.
            Here are candidate service dependencies with live measured stats:

            {json.dumps(candidates, indent=2)}

            SLO target is {config.slo_target} of requests under
            {config.latency_threshold_ms}ms. The burn-rate abort threshold is
            {config.burn_abort}.

            Choose the single riskiest dependency to test and the latency in ms to
            inject (200-900). Respond ONLY as JSON with keys:
            target (must equal one candidate's "edge"), latency_ms (int),
            rationale (one sentence citing the numbers), hypothesis (one sentence).
            """
        ).strip()
        response = client.models.generate_content(
            model=config.gemini_model,
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )
        data = json.loads(response.text)
        valid_edges = {c["edge"] for c in candidates}
        if data.get("target") not in valid_edges:
            return None
        latency = int(data.get("latency_ms", 0))
        if not 100 <= latency <= 1500:
            return None
        return {
            "target": data["target"],
            "recommended_latency_ms": latency,
            "rationale": str(data.get("rationale", "")).strip(),
            "hypothesis": str(data.get("hypothesis", "")).strip(),
            "selected_by": "gemini",
        }
    except Exception as exc:
        event_bus.publish(
            {
                "type": "message",
                "level": "warning",
                "source": "gemini",
                "text": f"Gemini selection unavailable, using deterministic ranking: {exc}",
            }
        )
        return None


def gather_dynatrace_context() -> dict[str, Any]:
    """Discover dependency candidates from live data and choose a target.

    The choice is made by Gemini over measured candidate stats when an API key is
    available, and falls back to a deterministic risk ranking otherwise. Either
    way the target is derived from real numbers rather than hardcoded.
    """

    # Note: we intentionally do NOT open the Dynatrace MCP here — that connect can
    # be slow and would delay the approval prompt. Candidates come from live demo
    # metrics; the MCP is used during the experiment (burn) and for the notebook.
    tool_names: list[str] = []
    candidates = _discover_candidates(config)

    ranking_text = "; ".join(
        f"{c['edge']} (risk {c['risk_score']}, bad {c['bad_ratio']:.1%}, "
        f"p95 {c['p95_ms']:.0f}ms, hardened={c['hardened']})"
        for c in candidates
    )
    event_bus.publish(
        {"type": "reasoning", "phase": "rank", "text": f"Ranked dependency candidates: {ranking_text}."}
    )
    event_bus.publish({"type": "candidates", "candidates": candidates})

    decision = _choose_target_with_gemini(candidates, config)
    if decision is None:
        top = candidates[0]
        decision = {
            "target": top["edge"],
            "recommended_latency_ms": 650,
            "rationale": (
                f"{top['edge']} ranks highest (risk {top['risk_score']}): "
                f"measured bad-ratio {top['bad_ratio']:.1%}, p95 {top['p95_ms']:.0f}ms, "
                f"hardening={'yes' if top['hardened'] else 'no'}."
            ),
            "hypothesis": (
                f"Injecting 650ms latency on {top['edge']} will push the burn rate over "
                f"the {config.burn_abort} abort threshold."
            ),
            "selected_by": "deterministic-ranking",
        }

    event_bus.publish(
        {"type": "reasoning", "phase": "select",
         "text": f"Target chosen ({decision['selected_by']}): {decision['target']}. {decision['rationale']}"}
    )
    event_bus.publish({"type": "reasoning", "phase": "hypothesis", "text": decision["hypothesis"]})

    return {
        "target": decision["target"],
        "rationale": decision["rationale"],
        "hypothesis": decision["hypothesis"],
        "recommended_latency_ms": decision["recommended_latency_ms"],
        "recommended_burn_abort": config.burn_abort,
        "selected_by": decision["selected_by"],
        "candidates": candidates,
        "dynatrace_tools": tool_names,
    }


def request_human_approval(plan_summary: str, timeout_seconds: int | None = None) -> dict[str, Any]:
    timeout_seconds = timeout_seconds or config.approval_timeout_s
    event_bus.request_approval(
        {
            "source": "aegis",
            "text": plan_summary,
            "timeout_seconds": timeout_seconds,
        }
    )
    approved = event_bus.wait_for_approval(timeout_seconds)
    return {"approved": approved, "timeout_seconds": timeout_seconds}


def run_experiment_tool(
    target: str,
    latency_ms: int,
    burn_abort: float | None = None,
    error_rate: float = 0.0,
    poll_seconds: float = 3,
    max_duration_s: float = 120,
) -> dict[str, Any]:
    return run_experiment(
        target=target,
        latency_ms=latency_ms,
        burn_abort=burn_abort or config.burn_abort,
        error_rate=error_rate,
        poll_seconds=poll_seconds,
        max_duration_s=max_duration_s,
        config=config,
    )


def _render_timeline(timeline: list[dict[str, float]]) -> str:
    if not timeline:
        return "_No samples recorded._"
    rows = ["| t (s) | burn |", "| --- | --- |"]
    for sample in timeline:
        rows.append(f"| {sample.get('t', 0)} | {round(float(sample.get('burn', 0)), 2)} |")
    return "\n".join(rows)


def create_game_day_scorecard(
    experiment_result: dict[str, Any],
    label: str = "game-day",
) -> dict[str, Any]:
    verdict = "ABORTED" if experiment_result["aborted"] else "PASSED"
    title = f"Aegis Game Day Scorecard ({label})"
    markdown = dedent(
        f"""
        # {title}

        - Verdict: {verdict}
        - Target: {experiment_result['target']}
        - Injected latency: {experiment_result['latency_ms']}ms
        - Injected error rate: {experiment_result.get('error_rate', 0.0)}
        - Peak burn: {experiment_result['peak_burn']}
        - Abort threshold: {experiment_result['burn_abort']}
        - Duration: {experiment_result['duration_s']}s

        ## Burn timeline

        {_render_timeline(experiment_result['timeline'])}
        """
    ).strip()
    path = write_scorecard(f"aegis-scorecard-{label}", markdown, config=config)
    notebook = create_notebook(title, markdown, config=config)
    event_bus.publish({"type": "reasoning", "phase": "scorecard", "text": f"Scorecard ({label}) stored at {path}."})
    return {"local_path": str(path), "notebook": notebook, "markdown": markdown, "verdict": verdict}


def apply_hardening_fix() -> dict[str, Any]:
    """Enable the demo app's timeout+retry hardening (simulates merging the PR)."""

    result = set_hardening(True, config=config)
    event_bus.publish(
        {
            "type": "reasoning",
            "phase": "harden",
            "text": f"Applied timeout+retry hardening to the live service (status: {result['status']}).",
        }
    )
    return result


def verify_after_fix(context: dict[str, Any], scenario: str = "pass") -> dict[str, Any]:
    """Re-run the experiment against the hardened service.

    scenario="pass": inject transient dependency *failures* — timeout+retry absorbs
    them, so burn stays low = PASSED (the fix holds).
    scenario="fail": inject sustained *latency* — timeout+retry does NOT mitigate
    latency, so burn climbs and the run aborts = fix NOT confirmed. This shows
    Aegis honestly catching an insufficient fix.
    """

    if scenario == "fail":
        latency_ms, error_rate = context.get("recommended_latency_ms", 650), 0.0
        fault_desc = f"latency={latency_ms}ms (which timeout+retry cannot mitigate)"
    else:
        latency_ms, error_rate = 0, config.verify_error_rate
        fault_desc = f"error_rate={error_rate} (which timeout+retry absorbs)"

    # Clear the burn window so verify reflects only the hardened behavior.
    reset = reset_metrics(config=config)
    event_bus.publish(
        {
            "type": "reasoning",
            "phase": "verify",
            "text": (
                f"Cleared burn window ({reset.get('status')}). Re-running {context['target']} "
                f"with injected {fault_desc} against the hardened client [{scenario} scenario]."
            ),
        }
    )
    time.sleep(config.verify_warmup_seconds)
    result = run_experiment_tool(
        target=context["target"],
        latency_ms=latency_ms,
        burn_abort=config.burn_abort,
        error_rate=error_rate,
        poll_seconds=2,
        max_duration_s=16,
    )
    result["scenario"] = scenario
    event_bus.publish(
        {
            "type": "reasoning",
            "phase": "verify",
            "text": (
                f"Verify result: {'STILL FAILING' if result['aborted'] else 'PASSED'} "
                f"(peak burn {result['peak_burn']} vs threshold {result['burn_abort']})."
            ),
        }
    )
    return result


def open_hardening_pr(experiment_result: dict[str, Any]) -> dict[str, Any]:
    title = "feat: harden payment client after Aegis game day"
    body = dedent(
        f"""
        Aegis detected that `payment->store` is vulnerable to latency amplification.

        Experiment summary:
        - aborted: {experiment_result['aborted']}
        - peak burn: {experiment_result['peak_burn']}
        - latency injected: {experiment_result['latency_ms']}ms

        This PR adds a timeout and simple retry policy to the payment dependency client.
        """
    ).strip()
    result = open_github_pr(title=title, body=body, config=config)
    event_bus.publish(
        {
            "type": "reasoning",
            "phase": "harden",
            "text": f"GitHub hardening action status: {result['status']}.",
        }
    )
    return result


def post_summary_to_slack(summary: str) -> dict[str, Any]:
    return post_slack(summary, config=config)


def _gemini_notebook_narrative(payload: dict[str, Any]) -> str | None:
    """Have Gemini (ADK model, on Vertex) write the notebook analysis dynamically."""
    try:
        from google import genai

        use_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in {"1", "true", "yes", "on"}
        if use_vertex:
            client = genai.Client(
                vertexai=True,
                project=os.getenv("GOOGLE_CLOUD_PROJECT"),
                location=os.getenv("GOOGLE_CLOUD_LOCATION", "global"),
            )
        elif config.google_api_key:
            client = genai.Client(api_key=config.google_api_key)
        else:
            return None
        prompt = (
            "You are a senior Site Reliability Engineer writing a Dynatrace notebook "
            "after an automated chaos game day. Using ONLY the JSON data below, write a "
            "clear, specific Markdown report with these sections: '## Executive summary', "
            "'## Why this dependency was targeted', '## What happened', '## The fix and why', "
            "'## Verification & verdict', and '## What the live Dynatrace metrics show'. "
            "Cite the actual numbers (peak burn, threshold, latency, p95, request count). "
            "Be concise and concrete. Do not invent data not present.\n\n"
            f"DATA:\n{json.dumps(payload, indent=2)}"
        )
        resp = client.models.generate_content(model=config.gemini_model, contents=prompt)
        text = (getattr(resp, "text", "") or "").strip()
        return text or None
    except Exception as exc:
        event_bus.publish(
            {"type": "message", "level": "warning", "source": "gemini",
             "text": f"Gemini notebook narrative unavailable, using template: {exc}"}
        )
        return None


def _build_and_publish_notebook(
    context, experiment_result, scorecard, verify_result, verify_scorecard, fix_confirmed, scenario
) -> dict[str, Any]:
    """Create a Dynatrace notebook: Gemini-written narrative + real Grail metric graphs."""

    svc = config.otel_service_name
    summary_q = (
        f'fetch spans, from:now()-1h | filter service.name == "{svc}" '
        f"| summarize requests = count(), avg_ms = avg(duration)/1000000, "
        f"p95_ms = percentile(duration, 95)/1000000"
    )
    by_ep_q = (
        f'fetch spans, from:now()-1h | filter service.name == "{svc}" '
        f"| summarize requests = count(), by:{{span.name}} | sort requests desc"
    )

    metrics_row = None
    try:
        rows = query_dql(summary_q, config)
        metrics_row = rows[0] if rows else None
    except Exception:
        metrics_row = None

    def _fmt(value, suffix=""):
        try:
            return f"{float(value):,.1f}{suffix}"
        except (TypeError, ValueError):
            return "n/a"

    if metrics_row:
        live = (
            f"- **Requests (last 1h):** {_fmt(metrics_row.get('requests'))}\n"
            f"- **Avg latency:** {_fmt(metrics_row.get('avg_ms'), ' ms')}\n"
            f"- **p95 latency:** {_fmt(metrics_row.get('p95_ms'), ' ms')}\n"
        )
    else:
        live = "_No spans in Grail for the last hour yet (ingest lag); the DQL cells below will populate shortly._\n"

    cand_lines = "\n".join(
        f"- `{c['edge']}` — risk {c['risk_score']}, bad {c['bad_ratio'] * 100:.1f}%, "
        f"p95 {c['p95_ms']:.0f}ms, hardened={'yes' if c['hardened'] else 'no'}"
        for c in context.get("candidates", [])
    )
    fault = (
        f"{experiment_result['latency_ms']}ms latency"
        if experiment_result.get("latency_ms")
        else f"error_rate {experiment_result.get('error_rate')}"
    )
    verify_fault = (
        "sustained latency (which timeout+retry cannot mitigate)"
        if scenario == "fail"
        else "transient dependency failures (which timeout+retry absorbs)"
    )
    # Graph-friendly timeseries queries — these render as line charts in the notebook.
    ts_requests = (
        f'fetch spans, from:now()-1h | filter service.name == "{svc}" '
        f"| makeTimeseries request_count = count(), interval:1m"
    )
    ts_latency = (
        f'fetch spans, from:now()-1h | filter service.name == "{svc}" '
        f"| makeTimeseries p95_latency_ms = percentile(duration, 95)/1000000, interval:1m"
    )

    payload = {
        "target": context["target"],
        "rationale": context.get("rationale"),
        "hypothesis": context.get("hypothesis"),
        "candidates": context.get("candidates"),
        "scenario": scenario,
        "pre_fix": {
            "verdict": scorecard["verdict"],
            "peak_burn": experiment_result["peak_burn"],
            "abort_threshold": experiment_result["burn_abort"],
            "fault_injected": fault,
        },
        "post_fix": {
            "verdict": verify_scorecard["verdict"],
            "peak_burn": verify_result["peak_burn"],
            "verify_fault": verify_fault,
        },
        "fix": "timeout 2s + 3 retries on the dependency client",
        "fix_confirmed": fix_confirmed,
        "live_metrics_last_1h": metrics_row or {},
    }

    template_md = f"""## Verdict
| Phase | Result | Peak burn | Abort threshold |
|---|---|---|---|
| Pre-fix (unhardened) | {scorecard['verdict']} | {experiment_result['peak_burn']} | {experiment_result['burn_abort']} |
| Post-fix ({scenario}) | {verify_scorecard['verdict']} | {verify_result['peak_burn']} | {verify_result['burn_abort']} |

**Fix confirmed: {fix_confirmed}**

## Why this dependency
{context['rationale']}

Ranked candidates:
{cand_lines}

## What happened
- **Hypothesis:** {context['hypothesis']}
- **Fault injected:** {fault} on `{context['target']}`; burn climbed to **{experiment_result['peak_burn']}** (threshold {experiment_result['burn_abort']}) and the deterministic loop auto-aborted.

## The fix & verification ({scenario})
Timeout (2s) + 3 retries; re-ran with {verify_fault} → **{verify_scorecard['verdict']}** (peak burn {verify_result['peak_burn']})."""

    narrative = _gemini_notebook_narrative(payload)
    authored_by = "Gemini (Google ADK, Vertex AI)" if narrative else "Aegis (deterministic template)"
    body = narrative or template_md
    md = (
        f"# Aegis Game Day — {context['target']}\n"
        f"_Authored by **{authored_by}** • validated against Dynatrace ({config.dt_environment})._\n\n"
        f"{body}\n\n"
        f"## Live Dynatrace metrics — `{svc}` (last 1h)\n{live}\n"
        f"The charts below query Grail live — request rate and p95 latency over time:\n"
    )

    notebook = create_dynatrace_notebook(
        f"Aegis Game Day — {context['target']} ({scenario})",
        md,
        [ts_requests, ts_latency, by_ep_q],
        config=config,
    )
    event_bus.publish(
        {
            "type": "link",
            "kind": "dynatrace_notebook",
            "label": "Dynatrace notebook",
            "url": notebook.get("url"),
            "status": notebook.get("status"),
        }
    )
    event_bus.publish(
        {
            "type": "reasoning",
            "phase": "notebook",
            "text": f"Dynatrace notebook {notebook.get('status')}"
            + (f": {notebook['url']}" if notebook.get("url") else ""),
        }
    )
    return notebook


def run_aegis_game_day(scenario: str = "pass") -> dict[str, Any]:
    # Start from a clean, unhardened state so the demo is repeatable.
    set_hardening(False, config=config)

    context = gather_dynatrace_context()
    approval = request_human_approval(
        (
            f"Planned test target: {context['target']}. "
            f"Hypothesis: {context['hypothesis']} "
            f"Inject {context['recommended_latency_ms']}ms latency with abort threshold {context['recommended_burn_abort']}."
        )
    )
    if not approval["approved"]:
        return {
            "status": "cancelled",
            "detail": "Approval was not granted before the timeout.",
            "context": context,
        }

    # 1) Hero run: prove the vulnerability against the unhardened service.
    experiment_result = run_experiment_tool(
        target=context["target"],
        latency_ms=context["recommended_latency_ms"],
        burn_abort=context["recommended_burn_abort"],
    )
    scorecard = create_game_day_scorecard(experiment_result, label="pre-fix")

    # 2) Propose the fix as a real PR.
    pr_result = open_hardening_pr(experiment_result)

    # 3) Apply the fix and verify it actually holds (closed loop).
    hardening = apply_hardening_fix()
    verify_result = verify_after_fix(context, scenario=scenario)
    verify_scorecard = create_game_day_scorecard(verify_result, label="post-fix")

    fix_confirmed = experiment_result["aborted"] and not verify_result["aborted"]

    # Surface the GitHub PR link to the UI (real url when configured, else dry-run).
    event_bus.publish(
        {
            "type": "link",
            "kind": "github_pr",
            "label": "Hardening PR",
            "url": pr_result.get("url"),
            "status": pr_result.get("status"),
        }
    )

    notebook = _build_and_publish_notebook(
        context, experiment_result, scorecard, verify_result, verify_scorecard, fix_confirmed, scenario
    )

    slack_result = post_summary_to_slack(
        f"Aegis game day on {context['target']}: pre-fix peak burn "
        f"{experiment_result['peak_burn']} ({scorecard['verdict']}), post-fix peak burn "
        f"{verify_result['peak_burn']} ({verify_scorecard['verdict']}). "
        f"Fix confirmed: {fix_confirmed}."
    )
    event_bus.publish(
        {
            "type": "reasoning",
            "phase": "done",
            "text": (
                "Closed loop complete: vulnerability proven, PR opened, fix applied, re-run "
                f"{'PASSED — fix confirmed.' if fix_confirmed else 'did not confirm the fix.'}"
            ),
        }
    )
    return {
        "status": "completed",
        "context": context,
        "experiment_result": experiment_result,
        "scorecard": scorecard,
        "pull_request": pr_result,
        "hardening": hardening,
        "verify_result": verify_result,
        "verify_scorecard": verify_scorecard,
        "fix_confirmed": fix_confirmed,
        "notebook": notebook,
        "slack": slack_result,
    }


def run_with_adk() -> dict[str, Any]:
    """Execute the game day through the Google ADK Runner (Gemini drives the tools).

    Gemini, running on Vertex AI, decides to call the `run_aegis_game_day` tool; the
    deterministic safety loop still lives inside that tool. If ADK/Vertex is not
    available at runtime, we fall back to the deterministic workflow so the live demo
    never breaks.
    """

    import asyncio

    try:
        from google.genai import types

        try:
            from google.adk.runners import InMemoryRunner

            runner = InMemoryRunner(agent=root_agent, app_name="aegis")
        except Exception:
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService

            runner = Runner(
                agent=root_agent, app_name="aegis", session_service=InMemorySessionService()
            )

        event_bus.publish(
            {
                "type": "reasoning",
                "phase": "adk",
                "text": "Starting Aegis via the Google ADK Runner — Gemini (Vertex AI) is now driving the tools.",
            }
        )

        async def _go() -> None:
            session = await runner.session_service.create_session(
                app_name="aegis", user_id="dashboard"
            )
            message = types.Content(
                role="user",
                parts=[
                    types.Part(
                        text=(
                            "Run a complete Aegis resilience game day now by calling the "
                            "run_aegis_game_day tool, then briefly summarize the pre-fix and "
                            "post-fix verdicts."
                        )
                    )
                ],
            )
            final_text = None
            async for ev in runner.run_async(
                user_id="dashboard", session_id=session.id, new_message=message
            ):
                try:
                    if ev.content and ev.content.parts:
                        for part in ev.content.parts:
                            fc = getattr(part, "function_call", None)
                            if fc is not None:
                                event_bus.publish(
                                    {
                                        "type": "reasoning",
                                        "phase": "adk",
                                        "text": f"Gemini (ADK) → calling tool: {fc.name}",
                                    }
                                )
                            if getattr(part, "text", None):
                                final_text = part.text
                except Exception:
                    pass
            if final_text:
                event_bus.publish(
                    {"type": "reasoning", "phase": "adk", "text": f"Gemini (ADK) summary: {final_text[:400]}"}
                )

        asyncio.run(_go())
        return {"status": "completed", "engine": "google-adk"}
    except Exception as exc:  # pragma: no cover - depends on runtime creds
        event_bus.publish(
            {
                "type": "message",
                "level": "warning",
                "source": "adk",
                "text": f"ADK Runner unavailable ({exc}); running the deterministic workflow instead.",
            }
        )
        return run_aegis_game_day()


INSTRUCTION = dedent(
    """
    You are Aegis, an autonomous resilience game-day agent for Dynatrace.

    Follow this order:
    1. Call `gather_dynatrace_context` to rank live dependency candidates and pick the riskiest target.
    2. Call `request_human_approval` before any mutating action.
    3. After approval, call `run_experiment_tool`. This tool is the deterministic safety core.
    4. Call `create_game_day_scorecard` to capture the verdict and notebook/report.
    5. Call `open_hardening_pr` to propose timeout and retry hardening.
    6. Call `apply_hardening_fix`, then `verify_after_fix` to prove the fix holds (closed loop).
    7. Optionally call `post_summary_to_slack`.

    Never improvise your own abort logic. The safety stop must stay inside `run_experiment_tool`.
    If Dynatrace is unavailable, be honest and continue with the local fallback burn signal.

    If Dynatrace MCP tools are available (e.g. execute_dql, list_problems,
    find_entity_by_name), you may call them to enrich the report with live
    observability data, but never let them gate or replace the deterministic abort.
    """
).strip()


def _dynatrace_mcp_toolset():
    """Attach the live Dynatrace MCP server as an ADK toolset (Method 2).

    When enabled, Gemini can call Dynatrace tools directly during the game day
    (execute_dql, list_problems, find_entity_by_name, ...). Opt-in via
    AEGIS_DT_MCP_TOOLS=true so it doesn't break headless Cloud Run, where the
    npx/OAuth handshake can't complete without a platform token.
    """

    enabled = os.getenv("AEGIS_DT_MCP_TOOLS", "").strip().lower() in {"1", "true", "yes", "on"}
    if not (enabled and config.has_dynatrace):
        return None
    try:
        from google.adk.tools.mcp_tool import McpToolset
        from google.adk.tools.mcp_tool import StdioConnectionParams
        from mcp import StdioServerParameters
    except Exception:
        return None

    npx_path = shutil.which("npx.cmd") or shutil.which("npx") or "npx"
    env = {"DT_ENVIRONMENT": config.dt_environment}
    if config.dt_platform_token:
        env["DT_PLATFORM_TOKEN"] = config.dt_platform_token
    if config.dt_api_token:
        env["DT_API_TOKEN"] = config.dt_api_token
    if config.dt_oauth_client_id and config.dt_oauth_client_secret:
        env["OAUTH_CLIENT_ID"] = config.dt_oauth_client_id
        env["OAUTH_CLIENT_SECRET"] = config.dt_oauth_client_secret
    if config.dt_disable_telemetry:
        env["DT_MCP_DISABLE_TELEMETRY"] = "true"
    try:
        return McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=npx_path,
                    args=["-y", f"@dynatrace-oss/dynatrace-mcp-server@{config.dt_mcp_server_version}"],
                    env=env,
                ),
                timeout=config.mcp_timeout_seconds,
            )
        )
    except Exception:
        return None


_AEGIS_TOOLS = [
    FunctionTool(gather_dynatrace_context),
    FunctionTool(request_human_approval),
    FunctionTool(run_experiment_tool),
    FunctionTool(create_game_day_scorecard),
    FunctionTool(open_hardening_pr),
    FunctionTool(apply_hardening_fix),
    FunctionTool(verify_after_fix),
    FunctionTool(post_summary_to_slack),
    FunctionTool(run_aegis_game_day),
]
_dt_toolset = _dynatrace_mcp_toolset()
if _dt_toolset is not None:
    _AEGIS_TOOLS.append(_dt_toolset)


root_agent = BaseAgent(
    name="aegis_root_agent",
    model=config.gemini_model,
    description="Autonomous resilience game-day agent with deterministic safety aborts.",
    instruction=INSTRUCTION,
    tools=_AEGIS_TOOLS,
)

app = App(root_agent=root_agent, name="aegis")
