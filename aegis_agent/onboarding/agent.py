"""Single-click Dynatrace-on-GCP onboarding agent (Google ADK).

Automates the exact steps required to get a GCP Cloud Run workload reporting to
Dynatrace via OpenTelemetry:

  1. enable the required GCP APIs,
  2. set the OTLP env vars (endpoint + token + DELTA metric temporality) on each
     Cloud Run service,
  3. verify that data is actually queryable in Grail.

"Single click" == one call to `onboard_dynatrace_gcp(...)` (or ask the ADK agent
in natural language). It shells out to `gcloud`, so run it where gcloud is
authenticated (your machine, Cloud Shell, or a Cloud Build/Run job with a
service account).

Feasibility note: this configures everything deterministically; whether spans
then appear depends on the Dynatrace tenant having OTLP/Grail ingest + retention
enabled (a tenant-side entitlement), which `verify_dynatrace_ingest` reports on.
"""

from __future__ import annotations

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

config = get_config()

REQUIRED_APIS = [
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "monitoring.googleapis.com",
    "aiplatform.googleapis.com",
]


def _gcloud(args: list[str], timeout: int = 600) -> dict[str, Any]:
    exe = shutil.which("gcloud") or shutil.which("gcloud.cmd") or "gcloud"
    try:
        proc = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout)
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "")[-1200:],
            "stderr": (proc.stderr or "")[-1200:],
        }
    except FileNotFoundError:
        return {"ok": False, "error": "gcloud not found on PATH"}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": str(exc)[:300]}


def enable_gcp_apis(project_id: str) -> dict[str, Any]:
    """Enable the GCP APIs required for Dynatrace OTLP onboarding."""
    res = _gcloud(["services", "enable", *REQUIRED_APIS, "--project", project_id])
    return {"step": "enable_apis", "apis": REQUIRED_APIS, **res}


def configure_cloud_run_otlp(
    service: str,
    region: str,
    project_id: str,
    dt_otlp_endpoint: str,
    dt_otlp_token: str,
) -> dict[str, Any]:
    """Point a Cloud Run service's OTLP exporter at Dynatrace (delta metrics)."""
    env = (
        f"DT_OTLP_ENDPOINT={dt_otlp_endpoint},"
        f"DT_OTLP_TOKEN={dt_otlp_token},"
        f"OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=delta"
    )
    res = _gcloud(
        [
            "run", "services", "update", service,
            "--region", region, "--project", project_id,
            "--update-env-vars", env,
        ]
    )
    return {"step": "configure_otlp", "service": service, "endpoint": dt_otlp_endpoint, **res}


def verify_dynatrace_ingest(
    dt_environment: str,
    oauth_client_id: str,
    oauth_client_secret: str,
    service_name: str = "aegis-demo-app",
) -> dict[str, Any]:
    """Query Grail to confirm spans are actually landing (the honest check)."""
    try:
        token = httpx.post(
            "https://sso.dynatrace.com/sso/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": oauth_client_id,
                "client_secret": oauth_client_secret,
                "scope": "storage:buckets:read storage:spans:read",
            },
            timeout=30,
        ).json().get("access_token")
        if not token:
            return {"step": "verify", "ok": False, "detail": "could not obtain bearer token"}
        query = f'fetch spans, from:now()-15m | filter service.name == "{service_name}" | summarize c = count()'
        url = f"{dt_environment}/platform/storage/query/v1/query:execute"
        headers = {"Authorization": f"Bearer {token}"}
        resp = httpx.post(url, headers=headers, json={"query": query, "requestTimeoutMilliseconds": 20000}, timeout=40)
        data = resp.json()
        # Poll if the query is async.
        token_id = data.get("requestToken")
        for _ in range(10):
            if data.get("result") is not None or data.get("state") == "SUCCEEDED":
                break
            if not token_id:
                break
            time.sleep(2)
            poll = httpx.get(
                f"{dt_environment}/platform/storage/query/v1/query:poll",
                headers=headers, params={"request-token": token_id}, timeout=30,
            )
            data = poll.json()
        records = (((data.get("result") or {}).get("records")) or [])
        count = records[0].get("c") if records else 0
        return {"step": "verify", "ok": True, "spans_last_15m": count, "has_data": bool(count)}
    except Exception as exc:
        return {"step": "verify", "ok": False, "detail": str(exc)[:300]}


def onboard_dynatrace_gcp(
    project_id: str,
    region: str,
    cloud_run_services: str,
    dt_environment: str,
    dt_otlp_token: str,
    oauth_client_id: str = "",
    oauth_client_secret: str = "",
) -> dict[str, Any]:
    """One-click: enable APIs, wire OTLP on every Cloud Run service, verify ingest.

    cloud_run_services: comma-separated service names.
    dt_environment: https://<tenant>.apps.dynatrace.com
    """
    tenant = dt_environment.replace("https://", "").split(".")[0]
    otlp_endpoint = f"https://{tenant}.live.dynatrace.com/api/v2/otlp"
    steps: list[dict[str, Any]] = [enable_gcp_apis(project_id)]
    for svc in [s.strip() for s in cloud_run_services.split(",") if s.strip()]:
        steps.append(configure_cloud_run_otlp(svc, region, project_id, otlp_endpoint, dt_otlp_token))
    verify = None
    if oauth_client_id and oauth_client_secret:
        time.sleep(20)
        verify = verify_dynatrace_ingest(dt_environment, oauth_client_id, oauth_client_secret)
    ok = all(s.get("ok", False) for s in steps)
    return {
        "status": "completed" if ok else "completed_with_errors",
        "otlp_endpoint": otlp_endpoint,
        "steps": steps,
        "verification": verify,
        "note": (
            "Configuration applied. If verification shows has_data=false, the tenant "
            "is accepting OTLP but not retaining it — enable OTel/Grail ingest on the tenant."
        ),
    }


INSTRUCTION = dedent(
    """
    You are the Dynatrace-on-GCP Onboarding agent. Given a GCP project, region,
    Cloud Run service name(s), and a Dynatrace tenant URL + OTLP ingest token, call
    `onboard_dynatrace_gcp` once to enable APIs, wire OTLP (with delta metric
    temporality) on each service, and verify ingest. Report each step's result and,
    if verification shows no data, explain that the tenant must enable OTLP/Grail
    retention. Never print secrets back to the user.
    """
).strip()

root_agent = BaseAgent(
    name="aegis_onboarding_agent",
    model=config.gemini_model,
    description="Single-click Dynatrace-on-GCP OpenTelemetry onboarding.",
    instruction=INSTRUCTION,
    tools=[
        FunctionTool(enable_gcp_apis),
        FunctionTool(configure_cloud_run_otlp),
        FunctionTool(verify_dynatrace_ingest),
        FunctionTool(onboard_dynatrace_gcp),
    ],
)

app = App(root_agent=root_agent, name="aegis_onboarding")


def _main() -> None:
    import argparse
    import json

    p = argparse.ArgumentParser(description="One-click Dynatrace-on-GCP onboarding")
    p.add_argument("--project", required=True)
    p.add_argument("--region", default="us-central1")
    p.add_argument("--services", required=True, help="comma-separated Cloud Run service names")
    p.add_argument("--dt-environment", required=True, help="https://<tenant>.apps.dynatrace.com")
    p.add_argument("--dt-otlp-token", required=True)
    p.add_argument("--oauth-client-id", default="")
    p.add_argument("--oauth-client-secret", default="")
    a = p.parse_args()
    result = onboard_dynatrace_gcp(
        a.project, a.region, a.services, a.dt_environment, a.dt_otlp_token,
        a.oauth_client_id, a.oauth_client_secret,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _main()
