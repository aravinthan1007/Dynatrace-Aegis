"""Shared configuration for Aegis."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class AegisConfig:
    gemini_model: str
    google_api_key: str
    dt_environment: str
    dt_platform_token: str
    dt_api_token: str
    dt_mcp_server_version: str
    dt_disable_telemetry: bool
    dt_otlp_endpoint: str
    dt_otlp_token: str
    demo_app_url: str
    dashboard_url: str
    github_token: str
    github_repo: str
    github_base_branch: str
    slack_webhook: str
    slo_target: float
    burn_abort: float
    burn_window_seconds: int
    latency_threshold_ms: int
    burn_smoothing_alpha: float
    verify_error_rate: float
    approval_timeout_s: int
    mcp_timeout_seconds: float
    reports_dir: Path

    @property
    def has_dynatrace(self) -> bool:
        return bool(self.dt_environment)

    @property
    def has_dt_otlp(self) -> bool:
        return bool(self.dt_otlp_endpoint and self.dt_otlp_token)

    @property
    def has_github(self) -> bool:
        return bool(self.github_token and self.github_repo)

    @property
    def has_slack(self) -> bool:
        return bool(self.slack_webhook)


def get_config() -> AegisConfig:
    package_root = Path(__file__).resolve().parents[1]
    load_dotenv()
    load_dotenv(package_root / ".env")
    return AegisConfig(
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
        google_api_key=os.getenv("GOOGLE_API_KEY", "").strip(),
        dt_environment=os.getenv("DT_ENVIRONMENT", "").strip(),
        dt_platform_token=os.getenv("DT_PLATFORM_TOKEN", "").strip(),
        dt_api_token=os.getenv("DT_API_TOKEN", "").strip(),
        dt_mcp_server_version=os.getenv("DT_MCP_SERVER_VERSION", "0.13.0").strip(),
        dt_disable_telemetry=_as_bool(os.getenv("DT_MCP_DISABLE_TELEMETRY"), True),
        dt_otlp_endpoint=os.getenv("DT_OTLP_ENDPOINT", "").strip(),
        dt_otlp_token=os.getenv("DT_OTLP_TOKEN", "").strip(),
        demo_app_url=os.getenv("AEGIS_DEMO_APP_URL", "http://127.0.0.1:8001").rstrip("/"),
        dashboard_url=os.getenv("AEGIS_DASHBOARD_URL", "http://127.0.0.1:8000").rstrip("/"),
        github_token=os.getenv("GITHUB_TOKEN", "").strip(),
        github_repo=os.getenv("GITHUB_REPO", "").strip(),
        github_base_branch=os.getenv("GITHUB_BASE_BRANCH", "main").strip(),
        slack_webhook=os.getenv("SLACK_WEBHOOK", "").strip(),
        slo_target=float(os.getenv("SLO_TARGET", "0.995")),
        burn_abort=float(os.getenv("BURN_ABORT", "10")),
        burn_window_seconds=int(os.getenv("BURN_WINDOW_SECONDS", "90")),
        latency_threshold_ms=int(os.getenv("LATENCY_THRESHOLD_MS", "500")),
        burn_smoothing_alpha=float(os.getenv("BURN_SMOOTHING_ALPHA", "0.5")),
        verify_error_rate=float(os.getenv("VERIFY_ERROR_RATE", "0.25")),
        approval_timeout_s=int(os.getenv("AEGIS_APPROVAL_TIMEOUT_S", "900")),
        mcp_timeout_seconds=float(os.getenv("AEGIS_MCP_TIMEOUT_SECONDS", "90")),
        reports_dir=Path(os.getenv("AEGIS_REPORTS_DIR", "runtime_artifacts")),
    )
