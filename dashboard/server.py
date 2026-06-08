"""Dashboard server for Aegis."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import httpx

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from aegis_agent.agent import run_aegis_game_day
from aegis_agent.agent import run_with_adk
from aegis_agent.config import get_config
from aegis_agent.dynatrace import fetch_burn_rate
from aegis_agent.events import event_bus
from aegis_agent.onboarding.gke import onboard_gke_autopilot


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
config = get_config()

app = FastAPI(title="Aegis Dashboard", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/onboard")
async def onboard_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "onboard.html")


@app.post("/onboard-gke")
async def onboard_gke(request: Request) -> dict:
    """Kick off the self-healing GKE Autopilot onboarding (dry-run unless execute=true)."""
    body = await request.json()
    kwargs = dict(
        project_id=(body.get("project_id") or "").strip(),
        dynatrace_url=(body.get("dynatrace_url") or config.dt_environment).strip(),
        dynatrace_access_key=(body.get("dynatrace_access_key") or config.dt_api_token).strip(),
        cluster_name=(body.get("cluster_name") or "dynatrace-gcp-monitor").strip(),
        region=(body.get("region") or "us-central1").strip(),
        topic_name=(body.get("topic_name") or "dynatrace-gcp-logs").strip(),
        subscription_name=(body.get("subscription_name") or "dynatrace-gcp-logs-sub").strip(),
        deployment_type=(body.get("deployment_type") or "all").strip(),
        log_filter=(body.get("log_filter") or "").strip(),
        execute=bool(body.get("execute", False)),
    )
    if not kwargs["project_id"]:
        return {"status": "error", "detail": "project_id is required"}
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, lambda: onboard_gke_autopilot(**kwargs))
    return {"status": "started", "execute": kwargs["execute"], "mode": "live" if kwargs["execute"] else "dry-run"}


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "demo_app_url": config.demo_app_url,
        "dynatrace_configured": config.has_dynatrace,
        "github_configured": config.has_github,
        "slack_configured": config.has_slack,
    }


def _gcp_list_projects() -> dict:
    """List the project + available GCP projects via the Cloud Run SA (no gcloud)."""
    md = {"Metadata-Flavor": "Google"}
    base = "http://metadata.google.internal/computeMetadata/v1"
    out: dict = {"projects": [], "current": "", "dt_environment": config.dt_environment,
                 "region": "us-central1", "services": os.getenv("AEGIS_ONBOARD_SERVICE", "aegis-demo-app")}
    token = ""
    try:
        with httpx.Client(timeout=5) as c:
            out["current"] = c.get(f"{base}/project/project-id", headers=md).text.strip()
            token = c.get(f"{base}/instance/service-accounts/default/token", headers=md).json().get("access_token", "")
    except Exception as exc:
        out["error"] = f"metadata: {exc}"[:160]
    if token:
        try:
            with httpx.Client(timeout=15) as c:
                r = c.get(
                    "https://cloudresourcemanager.googleapis.com/v1/projects",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"filter": "lifecycleState:ACTIVE"},
                )
            if r.status_code == 200:
                out["projects"] = [p["projectId"] for p in r.json().get("projects", [])][:50]
            else:
                out["error"] = f"resourcemanager {r.status_code}"
        except Exception as exc:
            out["error"] = f"resourcemanager: {exc}"[:160]
    if not out["projects"] and out["current"]:
        out["projects"] = [out["current"]]
    return out


@app.get("/gcp-projects")
async def gcp_projects() -> dict:
    return await asyncio.to_thread(_gcp_list_projects)


@app.get("/onboard-status")
async def onboard_status() -> dict:
    """Onboarding plan + a live Dynatrace MCP verification for the demo service.

    Provisioning (enable APIs, Secret Manager, Cloud Run OTLP, infra-metrics bridge)
    runs via the onboarding agent where gcloud is available; the deployed dashboard
    container has no gcloud, so here we surface the plan + run the live verify.
    """
    project = os.getenv("GOOGLE_CLOUD_PROJECT", "")
    service = os.getenv("AEGIS_ONBOARD_SERVICE", "aegis-demo-app")
    plan = [
        {"step": "enable_gcp_apis", "detail": "run, cloudbuild, monitoring, secretmanager, aiplatform"},
        {"step": "store_token_secret", "detail": "Dynatrace OTLP token -> GCP Secret Manager (+ grant runtime SA)"},
        {"step": "configure_cloud_run_otlp", "detail": f"{service}: OTLP endpoint + token-from-secret + delta metrics"},
        {"step": "bridge_gcp_metrics", "detail": "Cloud Run platform metrics -> Dynatrace Metrics v2 (no Helm)"},
        {"step": "verify_dynatrace_ingest", "detail": "DQL via Dynatrace MCP"},
    ]
    cli = (
        "python -m aegis_agent.onboarding.agent "
        f"--project {project or '<PROJECT>'} --region {config.demo_app_url and 'us-central1'} "
        f"--services {service} --dt-environment {config.dt_environment or '<TENANT_URL>'} "
        "--dt-otlp-token <INGEST_TOKEN> --runtime-sa <SA> "
        "--oauth-client-id <DT0S02_ID> --oauth-client-secret <SECRET>"
    )
    verify: dict = {"configured": config.has_dynatrace}
    if config.has_dynatrace:
        try:
            from aegis_agent.onboarding.agent import verify_dynatrace_ingest

            verify = await asyncio.to_thread(
                verify_dynatrace_ingest,
                config.dt_environment,
                config.dt_oauth_client_id,
                config.dt_oauth_client_secret,
                service,
            )
        except Exception as exc:
            verify = {"ok": False, "error": str(exc)[:300]}
    return {"project": project, "service": service, "plan": plan, "cli": cli, "verify": verify}


@app.get("/dt-check")
async def dt_check() -> dict:
    """Validate cloud -> Dynatrace connectivity (MCP tools + a trivial DQL)."""
    auth = (
        "oauth-client"
        if (config.dt_oauth_client_id and config.dt_oauth_client_secret)
        else ("platform-token" if config.dt_platform_token else ("api-token" if config.dt_api_token else "none"))
    )
    result = {
        "dt_environment": config.dt_environment,
        "configured": config.has_dynatrace,
        "auth_method": auth,
    }
    if not config.has_dynatrace:
        result["connected"] = False
        result["detail"] = "DT_ENVIRONMENT not set on this service."
        return result
    try:
        from aegis_agent.dynatrace import DynatraceMcpClient

        async with DynatraceMcpClient(config) as client:
            tools = await client.list_tools()
            result["connected"] = True
            result["tool_count"] = len(tools)
            result["tools"] = [t["name"] for t in tools][:20]
            dql = await client.execute_dql("fetch spans, from:now()-30m | summarize total = count()")
            result["dql_ok"] = not dql.is_error
            result["dql_detail"] = (dql.text or "")[:200]
    except Exception as exc:
        result["connected"] = False
        result["error"] = str(exc)[:400]
    return result


@app.get("/events")
async def events() -> StreamingResponse:
    subscriber, history = event_bus.subscribe()

    async def stream():
        try:
            for event in history:
                yield f"data: {json.dumps(event)}\n\n"
            while True:
                event = await asyncio.to_thread(event_bus.next_event, subscriber, 1.0)
                if event is None:
                    yield ": keep-alive\n\n"
                else:
                    yield f"data: {json.dumps(event)}\n\n"
        finally:
            event_bus.unsubscribe(subscriber)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/sli")
async def sli() -> dict:
    current_burn = await fetch_burn_rate(config)
    return {
        "current_burn": current_burn,
        "threshold": config.burn_abort,
        "samples": event_bus.burn_samples(),
    }


@app.get("/approval")
async def approval() -> dict:
    return event_bus.approval_state()


@app.post("/approve")
async def approve() -> dict:
    event_bus.approve()
    return {"status": "approved"}


@app.post("/run-demo")
async def run_demo() -> dict:
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, run_aegis_game_day)
    event_bus.publish(
        {
            "type": "reasoning",
            "phase": "init",
            "text": "Aegis game day started. Waiting for approval before fault injection.",
        }
    )
    return {"status": "started"}


@app.post("/run-fail")
async def run_fail() -> dict:
    """Run the game day in the FAIL scenario (the fix does not hold)."""
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, lambda: run_aegis_game_day("fail"))
    event_bus.publish(
        {
            "type": "reasoning",
            "phase": "init",
            "text": "Aegis game day started in FAIL scenario. Waiting for approval before fault injection.",
        }
    )
    return {"status": "started", "scenario": "fail"}


@app.post("/run-agent")
async def run_agent() -> dict:
    """Run the game day through the Google ADK Runner (Gemini drives the tools)."""
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, run_with_adk)
    event_bus.publish(
        {
            "type": "reasoning",
            "phase": "init",
            "text": "Aegis game day started via Google ADK. Waiting for approval before fault injection.",
        }
    )
    return {"status": "started", "engine": "google-adk"}
