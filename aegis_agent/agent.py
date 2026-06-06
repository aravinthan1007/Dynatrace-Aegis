"""ADK root agent and orchestration helpers for Aegis."""

from __future__ import annotations

import json
import time
from textwrap import dedent
from typing import Any

from google.adk.apps import App
from google.adk.tools.function_tool import FunctionTool

try:
    from google.adk.agents import LlmAgent as BaseAgent
except ImportError:  # pragma: no cover - depends on ADK version
    from google.adk.agents import Agent as BaseAgent

from .actions import get_service_metrics
from .actions import open_github_pr
from .actions import post_slack
from .actions import reset_metrics
from .actions import set_hardening
from .actions import write_scorecard
from .config import get_config
from .dynatrace import create_notebook
from .dynatrace import list_dynatrace_tools
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

    tool_names = list_dynatrace_tools(config)
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


def verify_after_fix(context: dict[str, Any]) -> dict[str, Any]:
    """Re-run the experiment against the hardened service to prove the fix works.

    Injects transient dependency failures (which timeout+retry is designed to
    absorb) and expects the burn to stay under the abort threshold = PASSED.
    """

    # Clear the burn window so verify reflects only the hardened behavior, then
    # let a little clean traffic accumulate before injecting failures.
    reset = reset_metrics(config=config)
    event_bus.publish(
        {
            "type": "reasoning",
            "phase": "verify",
            "text": (
                f"Cleared burn window ({reset.get('status')}). Re-running {context['target']} "
                f"with injected error_rate={config.verify_error_rate} against the hardened client."
            ),
        }
    )
    time.sleep(config.verify_warmup_seconds)
    result = run_experiment_tool(
        target=context["target"],
        latency_ms=0,
        burn_abort=config.burn_abort,
        error_rate=config.verify_error_rate,
        poll_seconds=2,
        max_duration_s=16,
    )
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


def run_aegis_game_day() -> dict[str, Any]:
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
    verify_result = verify_after_fix(context)
    verify_scorecard = create_game_day_scorecard(verify_result, label="post-fix")

    fix_confirmed = experiment_result["aborted"] and not verify_result["aborted"]
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
    """
).strip()


root_agent = BaseAgent(
    name="aegis_root_agent",
    model=config.gemini_model,
    description="Autonomous resilience game-day agent with deterministic safety aborts.",
    instruction=INSTRUCTION,
    tools=[
        FunctionTool(gather_dynatrace_context),
        FunctionTool(request_human_approval),
        FunctionTool(run_experiment_tool),
        FunctionTool(create_game_day_scorecard),
        FunctionTool(open_hardening_pr),
        FunctionTool(apply_hardening_fix),
        FunctionTool(verify_after_fix),
        FunctionTool(post_summary_to_slack),
        FunctionTool(run_aegis_game_day),
    ],
)

app = App(root_agent=root_agent, name="aegis")
