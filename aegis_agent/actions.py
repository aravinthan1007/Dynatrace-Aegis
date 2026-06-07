"""Demo app and outbound actions for Aegis."""

from __future__ import annotations

import base64
from datetime import UTC
from datetime import datetime
import json
import os
from pathlib import Path
import re
from typing import Any

import httpx

from .config import AegisConfig
from .config import get_config


def _slugify(value: str) -> str:
    lowered = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return lowered or "aegis-report"


def set_chaos(
    target: str,
    latency_ms: int,
    error_rate: float = 0.0,
    *,
    config: AegisConfig | None = None,
) -> dict[str, Any]:
    config = config or get_config()
    payload = {
        "target": target,
        "latency_ms": latency_ms,
        "error_rate": error_rate,
    }
    with httpx.Client(timeout=10) as client:
        response = client.post(f"{config.demo_app_url}/chaos", json=payload)
        response.raise_for_status()
        return response.json()


def get_chaos(*, config: AegisConfig | None = None) -> dict[str, Any]:
    config = config or get_config()
    with httpx.Client(timeout=10) as client:
        response = client.get(f"{config.demo_app_url}/chaos")
        response.raise_for_status()
        return response.json()


def set_hardening(enabled: bool, *, config: AegisConfig | None = None) -> dict[str, Any]:
    """Toggle the demo app's runtime timeout+retry hardening.

    Used after the hardening PR is opened so the verify-after-fix re-run exercises
    the fixed code path. Returns a dry-run payload if the demo app is unreachable.
    """

    config = config or get_config()
    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(f"{config.demo_app_url}/harden", json={"enabled": enabled})
            response.raise_for_status()
            return {"status": "applied", **response.json()}
    except Exception as exc:
        return {"status": "dry-run", "detail": str(exc), "hardened": enabled}


def reset_metrics(*, config: AegisConfig | None = None) -> dict[str, Any]:
    """Clear the demo app's recent-request window (best-effort)."""

    config = config or get_config()
    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(f"{config.demo_app_url}/metrics/reset")
            response.raise_for_status()
            return {"status": "reset", **response.json()}
    except Exception as exc:
        return {"status": "dry-run", "detail": str(exc)}


def get_service_metrics(service: str, *, config: AegisConfig | None = None) -> dict[str, Any]:
    """Fetch recent measured stats for a demo-app service (best-effort)."""

    config = config or get_config()
    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(
                f"{config.demo_app_url}/metrics/recent",
                params={
                    "service": service,
                    "window_seconds": config.burn_window_seconds,
                    "threshold_ms": config.latency_threshold_ms,
                },
            )
            response.raise_for_status()
            return response.json()
    except Exception:
        return {
            "service": service,
            "total": 0,
            "bad_ratio": 0.0,
            "avg_ms": 0.0,
            "p95_ms": 0.0,
            "hardened": False,
        }


def _build_hardened_payment_client() -> str:
    return '''"""Payment dependency client with basic timeout and retry hardening."""

from __future__ import annotations

import asyncio

import httpx

from .chaos import apply_payment_to_store_chaos


class PaymentClient:
    def __init__(self, base_url: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(2.0, connect=0.5),
        )

    async def fetch_store_inventory(self, order_id: str) -> dict:
        last_error = None
        for attempt in range(3):
            try:
                await apply_payment_to_store_chaos()
                response = await self._client.get(
                    "/store/inventory",
                    params={"order_id": order_id},
                )
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.HTTPError) as exc:
                last_error = exc
                if attempt == 2:
                    break
                await asyncio.sleep(0.15 * (attempt + 1))
        raise RuntimeError(f"store dependency failed after retries: {last_error}") from last_error

    async def aclose(self) -> None:
        await self._client.aclose()
'''


def _dt_oauth_bearer(config: AegisConfig, scope: str) -> str | None:
    """Exchange the Dynatrace OAuth client for a short-lived bearer token."""
    if not (config.dt_oauth_client_id and config.dt_oauth_client_secret):
        return None
    with httpx.Client(timeout=30) as client:
        resp = client.post(
            "https://sso.dynatrace.com/sso/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": config.dt_oauth_client_id,
                "client_secret": config.dt_oauth_client_secret,
                "scope": scope,
            },
        )
        resp.raise_for_status()
        return resp.json().get("access_token")


def create_dynatrace_notebook(
    title: str,
    markdown_summary: str,
    dql_queries: list[str] | None = None,
    *,
    config: AegisConfig | None = None,
) -> dict[str, Any]:
    """Create a Dynatrace notebook (platform document) with an LLM/summary + DQL.

    Uses the OAuth client-credentials flow, so it works headless from Cloud Run.
    Returns a dict with the notebook URL, or a dry-run/error status.
    """

    config = config or get_config()
    if not (config.dt_environment and config.dt_oauth_client_id and config.dt_oauth_client_secret):
        return {"status": "dry-run", "detail": "Dynatrace OAuth client not configured."}
    try:
        bearer = _dt_oauth_bearer(config, "document:documents:read document:documents:write")
        if not bearer:
            return {"status": "dry-run", "detail": "Could not obtain Dynatrace bearer token."}
        sections: list[dict[str, Any]] = [
            {"id": "summary", "type": "markdown", "markdown": markdown_summary}
        ]
        for i, query in enumerate(dql_queries or []):
            sections.append({"id": f"dql{i}", "type": "dql", "dql": query})
        content = {"version": "1", "kind": "notebook", "sections": sections}
        with httpx.Client(timeout=40) as client:
            resp = client.post(
                f"{config.dt_environment}/platform/document/v1/documents",
                headers={"Authorization": f"Bearer {bearer}"},
                files={"content": ("aegis.notebook", json.dumps(content), "application/json")},
                data={"name": title, "type": "notebook"},
            )
            resp.raise_for_status()
            doc_id = resp.json().get("id")
        url = f"{config.dt_environment}/ui/apps/dynatrace.notebooks/notebook/{doc_id}"
        return {"status": "created", "id": doc_id, "url": url}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)[:300]}


def open_github_pr(
    title: str,
    body: str,
    *,
    branch_hint: str = "aegis-hardening",
    config: AegisConfig | None = None,
) -> dict[str, Any]:
    config = config or get_config()
    target_path = os.getenv("AEGIS_PR_TARGET_PATH", "demo_app/payment_client.py")
    new_content = _build_hardened_payment_client()

    if not config.has_github:
        return {
            "status": "dry-run",
            "title": title,
            "detail": (
                "GitHub credentials are not configured. Generated hardened "
                f"content for {target_path} but did not open a PR."
            ),
            "file_path": target_path,
            "preview": new_content[:400],
        }

    owner, repo = config.github_repo.split("/", 1)
    branch = f"{branch_hint}-{datetime.now(UTC).strftime('%H%M%S')}"
    headers = {
        "Authorization": f"Bearer {config.github_token}",
        "Accept": "application/vnd.github+json",
    }

    # A PR failure (e.g. token missing Contents/Pull-requests write) must never crash
    # the game day — return a status dict instead of raising.
    try:
        with httpx.Client(base_url="https://api.github.com", headers=headers, timeout=30) as client:
            repo_resp = client.get(f"/repos/{owner}/{repo}")
            repo_resp.raise_for_status()
            repo_json = repo_resp.json()
            base_branch = config.github_base_branch or repo_json["default_branch"]

            ref_resp = client.get(f"/repos/{owner}/{repo}/git/ref/heads/{base_branch}")
            ref_resp.raise_for_status()
            base_sha = ref_resp.json()["object"]["sha"]

            create_ref = client.post(
                f"/repos/{owner}/{repo}/git/refs",
                json={"ref": f"refs/heads/{branch}", "sha": base_sha},
            )
            if create_ref.status_code not in {201, 422}:
                create_ref.raise_for_status()

            existing = client.get(f"/repos/{owner}/{repo}/contents/{target_path}", params={"ref": base_branch})
            existing.raise_for_status()
            existing_json = existing.json()

            put_content = client.put(
                f"/repos/{owner}/{repo}/contents/{target_path}",
                json={
                    "message": "feat: harden payment client timeout and retry policy",
                    "content": base64.b64encode(new_content.encode("utf-8")).decode("utf-8"),
                    "sha": existing_json["sha"],
                    "branch": branch,
                },
            )
            put_content.raise_for_status()

            pr_resp = client.post(
                f"/repos/{owner}/{repo}/pulls",
                json={"title": title, "head": branch, "base": base_branch, "body": body},
            )
            pr_resp.raise_for_status()
            pr_json = pr_resp.json()
        return {
            "status": "opened",
            "url": pr_json.get("html_url"),
            "branch": branch,
            "file_path": target_path,
        }
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        hint = ""
        if code == 403:
            hint = " (the fine-grained token needs Contents: write + Pull requests: write on this repo)"
        return {"status": "error", "detail": f"GitHub {code}{hint}", "file_path": target_path}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)[:200], "file_path": target_path}


def post_slack(message: str, *, config: AegisConfig | None = None) -> dict[str, Any]:
    config = config or get_config()
    if not config.has_slack:
        return {
            "status": "dry-run",
            "detail": "SLACK_WEBHOOK is not configured.",
            "message": message,
        }

    with httpx.Client(timeout=15) as client:
        response = client.post(config.slack_webhook, json={"text": message})
        response.raise_for_status()
    return {"status": "sent"}


def write_scorecard(title: str, markdown_body: str, *, config: AegisConfig | None = None) -> Path:
    config = config or get_config()
    config.reports_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{_slugify(title)}.md"
    path = config.reports_dir / filename
    path.write_text(markdown_body, encoding="utf-8")
    return path
