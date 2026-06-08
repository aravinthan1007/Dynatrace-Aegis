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
from aegis_agent.dynatrace_skills import build_post_onboarding_queries
from aegis_agent.dynatrace import fetch_burn_rate
from aegis_agent.events import event_bus
from aegis_agent.onboarding.gke import onboard_gke_autopilot


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
config = get_config()

app = FastAPI(title="Aegis Dashboard", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _metadata_value(path: str, timeout: float = 3.0) -> str:
    md = {"Metadata-Flavor": "Google"}
    base = "http://metadata.google.internal/computeMetadata/v1"
    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.get(f"{base}/{path}", headers=md)
            if r.status_code == 200:
                return r.text.strip()
    except Exception:
        return ""
    return ""


def _current_project() -> str:
    return os.getenv("GOOGLE_CLOUD_PROJECT", "").strip() or _metadata_value("project/project-id")


def _current_region() -> str:
    region = os.getenv("GOOGLE_CLOUD_LOCATION", "").strip()
    if region and region != "global":
        return region
    metadata_region = _metadata_value("instance/region")
    if metadata_region:
        return metadata_region.rsplit("/", 1)[-1]
    return os.getenv("GOOGLE_CLOUD_REGION", "us-central1").strip() or "us-central1"


def _github_status() -> dict:
    target_path = os.getenv("AEGIS_PR_TARGET_PATH", "demo_app/payment_client.py")
    result = {
        "configured": config.has_github,
        "repo": config.github_repo,
        "base_branch": config.github_base_branch,
        "target_path": target_path,
        "repo_read": False,
        "base_ref_read": False,
        "target_file_read": False,
        "permissions": {},
    }
    if not config.has_github:
        result["detail"] = "GITHUB_TOKEN and GITHUB_REPO must be configured."
        return result
    try:
        owner, repo = config.github_repo.split("/", 1)
    except ValueError:
        result["detail"] = "GITHUB_REPO must be owner/repo."
        return result
    headers = {
        "Authorization": f"Bearer {config.github_token}",
        "Accept": "application/vnd.github+json",
    }
    try:
        with httpx.Client(base_url="https://api.github.com", headers=headers, timeout=20) as client:
            repo_resp = client.get(f"/repos/{owner}/{repo}")
            result["repo_read"] = repo_resp.status_code == 200
            if repo_resp.status_code == 200:
                repo_json = repo_resp.json()
                result["default_branch"] = repo_json.get("default_branch")
                result["permissions"] = repo_json.get("permissions") or {}
            base = config.github_base_branch or result.get("default_branch") or "main"
            ref_resp = client.get(f"/repos/{owner}/{repo}/git/ref/heads/{base}")
            result["base_ref_read"] = ref_resp.status_code == 200
            file_resp = client.get(f"/repos/{owner}/{repo}/contents/{target_path}", params={"ref": base})
            result["target_file_read"] = file_resp.status_code == 200
            result["ok"] = result["repo_read"] and result["base_ref_read"] and result["target_file_read"]
            if not result["ok"]:
                result["detail"] = (
                    f"repo={repo_resp.status_code}, ref={ref_resp.status_code}, "
                    f"target_file={file_resp.status_code}"
                )
    except Exception as exc:
        result["ok"] = False
        result["detail"] = str(exc)[:200]
    return result


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


@app.get("/environment-status")
async def environment_status() -> dict:
    project = _current_project()
    service = os.getenv("AEGIS_ONBOARD_SERVICE", "aegis-demo-app")
    cluster = os.getenv("AEGIS_GKE_CLUSTER", "dynatrace-gcp-monitor")
    return {
        "project": project,
        "region": _current_region(),
        "service": service,
        "cluster": cluster,
        "dashboard_url": config.dashboard_url,
        "demo_app_url": config.demo_app_url,
        "dynatrace_environment": config.dt_environment,
        "dynatrace_configured": config.has_dynatrace,
        "github": _github_status(),
        "execution_model": {
            "gemini_adk": "Gemini ADK selects and calls tools.",
            "mutations": "Deterministic Python tools run gcloud/GitHub actions.",
            "default_mode": "GKE onboarding starts as dry-run unless live execution is explicitly selected.",
        },
    }


@app.get("/github-status")
async def github_status() -> dict:
    return await asyncio.to_thread(_github_status)


@app.get("/post-onboarding-checks")
async def post_onboarding_checks() -> dict:
    project = _current_project()
    service = os.getenv("AEGIS_ONBOARD_SERVICE", "aegis-demo-app")
    cluster = os.getenv("AEGIS_GKE_CLUSTER", "dynatrace-gcp-monitor")
    return build_post_onboarding_queries(
        project_id=project or "<PROJECT>",
        cloud_run_service=service,
        cluster_name=cluster,
        service_name=service,
    )


def _gcp_list_projects() -> dict:
    """List the project + available GCP projects via the Cloud Run SA (no gcloud)."""
    md = {"Metadata-Flavor": "Google"}
    base = "http://metadata.google.internal/computeMetadata/v1"
    out: dict = {"projects": [], "current": _current_project(), "dt_environment": config.dt_environment,
                 "region": _current_region(), "services": os.getenv("AEGIS_ONBOARD_SERVICE", "aegis-demo-app")}
    token = ""
    try:
        with httpx.Client(timeout=5) as c:
            metadata_project = c.get(f"{base}/project/project-id", headers=md).text.strip()
            out["current"] = out["current"] or metadata_project
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
    project = _current_project()
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
