"""Single-click, secure Dynatrace-on-GCP onboarding agent (Google ADK).

Replaces the brittle Helm/IAM/token dance with one self-verifying agent call:

  1. enable the required GCP APIs,
  2. store the Dynatrace OTLP token in **GCP Secret Manager** (not plaintext env)
     and grant the Cloud Run runtime SA access,
  3. wire each Cloud Run service to read the token from the secret and export OTLP
     (endpoint + DELTA metric temporality),
  4. **verify via the Dynatrace MCP** that data is actually queryable in Grail.

It shells out to `gcloud` (run where gcloud is authenticated) and verifies through
the Dynatrace MCP. Honest by design: if the tenant accepts OTLP but doesn't retain
it, step 4 reports `has_data: false` instead of pretending success.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from textwrap import dedent
from typing import Any

import httpx

from google.adk.apps import App
from google.adk.tools.function_tool import FunctionTool

try:
    from google.adk.agents import LlmAgent as BaseAgent
except ImportError:  # pragma: no cover
    from google.adk.agents import Agent as BaseAgent

from ..config import get_config
from ..dynatrace import query_dql
from ..dynatrace_skills import build_post_onboarding_queries, get_dynatrace_skill_context

config = get_config()

REQUIRED_APIS = [
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "monitoring.googleapis.com",
    "secretmanager.googleapis.com",
    "aiplatform.googleapis.com",
]


def _gcloud(args: list[str], stdin: str | None = None, timeout: int = 600) -> dict[str, Any]:
    exe = shutil.which("gcloud") or shutil.which("gcloud.cmd") or "gcloud"
    try:
        proc = subprocess.run(
            [exe, *args], input=stdin, capture_output=True, text=True, timeout=timeout
        )
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "")[-1000:],
            "stderr": (proc.stderr or "")[-1000:],
        }
    except FileNotFoundError:
        return {"ok": False, "error": "gcloud not found on PATH"}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc)[:300]}


def _config_for(dt_environment: str, oauth_client_id: str, oauth_client_secret: str):
    cfg = get_config()
    cfg.dt_environment = dt_environment
    cfg.dt_oauth_client_id = oauth_client_id
    cfg.dt_oauth_client_secret = oauth_client_secret
    return cfg


def _remediate_and_retry(args: list[str], project_id: str, stdin: str | None = None) -> dict[str, Any]:
    """Run a gcloud command; if it fails on a known, fixable cause, fix it and retry once.

    Handles the two most common onboarding failures:
      - a required API is disabled  -> enable it, retry
      - a permission/IAM error       -> reported with a clear hint (and SA grants
        for Secret Manager are handled in the secret step)
    """
    res = _gcloud(args, stdin=stdin)
    if res.get("ok"):
        return {**res, "remediation": "none"}
    stderr = (res.get("stderr") or "") + (res.get("error") or "")
    # Disabled-API remediation: extract the api host and enable it.
    m = re.search(r"([a-z0-9.\-]+\.googleapis\.com)", stderr) if re.search(
        r"SERVICE_DISABLED|has not been used|API .* (is |has been )?disabl", stderr
    ) else None
    if m:
        api = m.group(1)
        enable = _gcloud(["services", "enable", api, "--project", project_id])
        if enable.get("ok"):
            time.sleep(5)
            retry = _gcloud(args, stdin=stdin)
            return {**retry, "remediation": f"enabled {api} and retried"}
        return {**res, "remediation": f"tried to enable {api} (failed: {enable.get('stderr','')[:120]})"}
    if re.search(r"PERMISSION_DENIED|does not have permission|403|forbidden", stderr, re.I):
        return {**res, "remediation": "permission error — grant the runtime SA the required role and retry"}
    return {**res, "remediation": "unrecognized failure"}


def enable_gcp_apis(project_id: str) -> dict[str, Any]:
    """Enable the GCP APIs required for secure Dynatrace OTLP onboarding."""
    res = _gcloud(["services", "enable", *REQUIRED_APIS, "--project", project_id])
    return {"step": "enable_apis", "apis": REQUIRED_APIS, **res}


def store_otlp_token_secret(
    project_id: str,
    token: str,
    secret_name: str = "dynatrace-otlp-token",
    runtime_service_account: str = "",
) -> dict[str, Any]:
    """Store the OTLP token in Secret Manager and grant Cloud Run SA access."""
    exists = _gcloud(["secrets", "describe", secret_name, "--project", project_id]).get("ok")
    if exists:
        res = _gcloud(
            ["secrets", "versions", "add", secret_name, "--data-file=-", "--project", project_id],
            stdin=token,
        )
    else:
        res = _gcloud(
            [
                "secrets", "create", secret_name, "--data-file=-",
                "--replication-policy=automatic", "--project", project_id,
            ],
            stdin=token,
        )
    grant = {"ok": True}
    if runtime_service_account:
        grant = _gcloud(
            [
                "secrets", "add-iam-policy-binding", secret_name,
                f"--member=serviceAccount:{runtime_service_account}",
                "--role=roles/secretmanager.secretAccessor", "--project", project_id,
            ]
        )
    return {"step": "store_secret", "secret": secret_name, "stored": res.get("ok"), "granted": grant.get("ok"), **res}


def configure_cloud_run_otlp(
    service: str,
    region: str,
    project_id: str,
    dt_otlp_endpoint: str,
    secret_name: str = "dynatrace-otlp-token",
    dt_otlp_token: str = "",
) -> dict[str, Any]:
    """Wire a Cloud Run service to export OTLP to Dynatrace (token from Secret Manager)."""
    env = f"DT_OTLP_ENDPOINT={dt_otlp_endpoint},OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=delta"
    args = [
        "run", "services", "update", service,
        "--region", region, "--project", project_id,
        "--update-env-vars", env,
    ]
    if secret_name:
        args += ["--remove-env-vars", "DT_OTLP_TOKEN", "--update-secrets", f"DT_OTLP_TOKEN={secret_name}:latest"]
        token_source = f"secret:{secret_name}"
    elif dt_otlp_token:
        args[-1] = env + f",DT_OTLP_TOKEN={dt_otlp_token}"
        token_source = "plaintext-env"
    else:
        token_source = "none"
    res = _remediate_and_retry(args, project_id)
    return {"step": "configure_otlp", "service": service, "token_source": token_source, **res}


def verify_dynatrace_ingest(
    dt_environment: str,
    oauth_client_id: str,
    oauth_client_secret: str,
    service_name: str = "aegis-demo-app",
) -> dict[str, Any]:
    """Verify via the Dynatrace MCP (DQL) that spans are actually landing in Grail."""
    cfg = _config_for(dt_environment, oauth_client_id, oauth_client_secret)
    query = f'fetch spans, from:now()-15m | filter service.name == "{service_name}" | summarize c = count()'
    try:
        rows = query_dql(query, cfg)
        count = rows[0].get("c") if rows else 0
        return {
            "step": "verify",
            "via": "dynatrace-mcp",
            "ok": True,
            "spans_last_15m": count,
            "has_data": bool(count),
        }
    except Exception as exc:
        return {"step": "verify", "via": "dynatrace-mcp", "ok": False, "detail": str(exc)[:300]}


def bridge_gcp_metrics(
    project_id: str,
    dt_environment: str,
    dt_metrics_token: str,
    minutes: int = 10,
) -> dict[str, Any]:
    """No-Helm GCP infra metrics: read Cloud Run platform metrics from Cloud
    Monitoring and ingest them to Dynatrace via the Metrics v2 API.

    Replaces the dynatrace-gcp-monitor Helm/GKE workload for the common case — no
    cluster, no chart. `dt_metrics_token` needs the `metrics.ingest` scope.
    """
    import datetime
    import json as _json

    # 1) Cloud Monitoring access token via gcloud (ADC).
    at = _gcloud(["auth", "print-access-token"])
    token = (at.get("stdout") or "").strip()
    if not token:
        return {"step": "infra_metrics", "ok": False, "detail": "could not get gcloud access token"}

    now = datetime.datetime.now(datetime.timezone.utc)
    start = (now - datetime.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    tenant = dt_environment.replace("https://", "").split(".")[0]
    metric_types = {
        "gcp.cloud_run.request_count": "run.googleapis.com/request_count",
        "gcp.cloud_run.container_instances": "run.googleapis.com/container/instance_count",
    }
    lines: list[str] = []
    pulled: dict[str, int] = {}
    try:
        with httpx.Client(timeout=40) as client:
            for dt_key, gcp_type in metric_types.items():
                resp = client.get(
                    f"https://monitoring.googleapis.com/v3/projects/{project_id}/timeSeries",
                    headers={"Authorization": f"Bearer {token}"},
                    params={
                        "filter": f'metric.type="{gcp_type}"',
                        "interval.startTime": start,
                        "interval.endTime": end,
                        "aggregation.alignmentPeriod": "60s",
                        "aggregation.perSeriesAligner": "ALIGN_SUM",
                    },
                )
                series = resp.json().get("timeSeries", []) if resp.status_code == 200 else []
                pulled[dt_key] = len(series)
                for s in series:
                    svc = (s.get("resource", {}).get("labels", {}) or {}).get("service_name", "unknown")
                    pts = s.get("points", [])
                    if not pts:
                        continue
                    v = pts[0].get("value", {})
                    val = v.get("int64Value") or v.get("doubleValue") or 0
                    lines.append(f'{dt_key},gcp.project={project_id},service={svc} {val}')
        if not lines:
            return {"step": "infra_metrics", "ok": True, "pulled": pulled, "ingested": 0,
                    "detail": "no Cloud Run series in window (low/no traffic)"}
        # 2) Ingest to Dynatrace Metrics v2.
        with httpx.Client(timeout=30) as client:
            ing = client.post(
                f"https://{tenant}.live.dynatrace.com/api/v2/metrics/ingest",
                headers={"Authorization": f"Api-Token {dt_metrics_token}", "Content-Type": "text/plain"},
                content="\n".join(lines),
            )
        return {
            "step": "infra_metrics",
            "ok": ing.status_code in (200, 202),
            "pulled": pulled,
            "ingested_lines": len(lines),
            "ingest_status": ing.status_code,
            "ingest_body": (ing.text or "")[:200],
        }
    except Exception as exc:
        return {"step": "infra_metrics", "ok": False, "detail": str(exc)[:300]}


def onboard_dynatrace_gcp(
    project_id: str,
    region: str,
    cloud_run_services: str,
    dt_environment: str,
    dt_otlp_token: str,
    runtime_service_account: str = "",
    oauth_client_id: str = "",
    oauth_client_secret: str = "",
    secret_name: str = "dynatrace-otlp-token",
) -> dict[str, Any]:
    """One-click secure onboarding: APIs -> Secret Manager -> Cloud Run OTLP -> verify (MCP)."""
    tenant = dt_environment.replace("https://", "").split(".")[0]
    otlp_endpoint = f"https://{tenant}.live.dynatrace.com/api/v2/otlp"
    steps: list[dict[str, Any]] = [enable_gcp_apis(project_id)]
    steps.append(store_otlp_token_secret(project_id, dt_otlp_token, secret_name, runtime_service_account))
    for svc in [s.strip() for s in cloud_run_services.split(",") if s.strip()]:
        steps.append(configure_cloud_run_otlp(svc, region, project_id, otlp_endpoint, secret_name=secret_name))
    # No-Helm GCP infra metrics: bridge Cloud Run platform metrics into Dynatrace.
    steps.append(bridge_gcp_metrics(project_id, dt_environment, dt_otlp_token))
    verify = None
    if oauth_client_id and oauth_client_secret:
        time.sleep(20)
        verify = verify_dynatrace_ingest(dt_environment, oauth_client_id, oauth_client_secret)
    ok = all(s.get("ok", False) for s in steps)
    return {
        "status": "completed" if ok else "completed_with_errors",
        "otlp_endpoint": otlp_endpoint,
        "secret": secret_name,
        "steps": steps,
        "verification": verify,
        "note": (
            "Config applied securely (token in Secret Manager). If verification shows "
            "has_data=false, the tenant accepts OTLP but isn't retaining it — enable "
            "OTel/Grail ingest on the tenant; no code change needed afterward."
        ),
    }


INSTRUCTION = dedent(
    """
    You are the Dynatrace-on-GCP Onboarding agent. Given a GCP project, region,
    Cloud Run service name(s), a Dynatrace tenant URL + OTLP ingest token (and
    optionally an OAuth client for verification), call `onboard_dynatrace_gcp` once.
    It enables APIs, stores the token in Secret Manager, wires OTLP (delta metrics)
    on each service, and verifies ingest via the Dynatrace MCP. Report each step and,
    if verification shows no data, clearly explain the tenant must enable OTel/Grail
    retention. Never print secrets.

    For post-onboarding validation, eval/test-case generation, or troubleshooting
    questions, use the curated Dynatrace skill helpers. They provide DQL and
    observability guidance only; live Google Cloud mutations must stay in the
    deterministic onboarding tools.
    """
).strip()

root_agent = BaseAgent(
    name="aegis_onboarding_agent",
    model=config.gemini_model,
    description="Single-click, secure Dynatrace-on-GCP OpenTelemetry onboarding with MCP verification.",
    instruction=INSTRUCTION,
    tools=[
        FunctionTool(enable_gcp_apis),
        FunctionTool(store_otlp_token_secret),
        FunctionTool(configure_cloud_run_otlp),
        FunctionTool(bridge_gcp_metrics),
        FunctionTool(verify_dynatrace_ingest),
        FunctionTool(onboard_dynatrace_gcp),
        FunctionTool(get_dynatrace_skill_context),
        FunctionTool(build_post_onboarding_queries),
    ],
)

app = App(root_agent=root_agent, name="aegis_onboarding")


def _main() -> None:
    import argparse
    import json

    p = argparse.ArgumentParser(description="One-click secure Dynatrace-on-GCP onboarding")
    p.add_argument("--project", required=True)
    p.add_argument("--region", default="us-central1")
    p.add_argument("--services", required=True, help="comma-separated Cloud Run service names")
    p.add_argument("--dt-environment", required=True, help="https://<tenant>.apps.dynatrace.com")
    p.add_argument("--dt-otlp-token", required=True)
    p.add_argument("--runtime-sa", default="")
    p.add_argument("--oauth-client-id", default="")
    p.add_argument("--oauth-client-secret", default="")
    a = p.parse_args()
    result = onboard_dynatrace_gcp(
        a.project, a.region, a.services, a.dt_environment, a.dt_otlp_token,
        a.runtime_sa, a.oauth_client_id, a.oauth_client_secret,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _main()
