"""Dynatrace MCP helpers and burn-rate accessors."""

from __future__ import annotations

import asyncio
import concurrent.futures
from dataclasses import dataclass
import shutil
from typing import Any

import httpx

from .actions import write_scorecard
from .config import AegisConfig
from .config import get_config
from .dql import build_burn_rate_query
from .events import event_bus

_VERIFIED_QUERIES: set[str] = set()


def _run_blocking(coro: Any) -> Any:
    """Run a coroutine even if an event loop is already running (e.g. under ADK)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


@dataclass(slots=True)
class DynatraceToolResult:
    tool_name: str
    is_error: bool
    text: str
    structured_content: dict[str, Any] | list[Any] | None
    raw: dict[str, Any]


class DynatraceMcpClient:
    def __init__(self, config: AegisConfig):
        self._config = config
        self._toolset = None
        self._session = None
        self._tool_schemas: dict[str, dict[str, Any]] = {}

    async def __aenter__(self) -> "DynatraceMcpClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def connect(self) -> None:
        if self._session is not None:
            return
        if not self._config.has_dynatrace:
            raise RuntimeError("DT_ENVIRONMENT is not configured.")

        try:
            from google.adk.tools.mcp_tool import McpToolset
            from google.adk.tools.mcp_tool import StdioConnectionParams
            from mcp import StdioServerParameters
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Dynatrace MCP dependencies are not installed. Install the `mcp` package to enable live Dynatrace access."
            ) from exc

        env = {"DT_ENVIRONMENT": self._config.dt_environment}
        if self._config.dt_platform_token:
            env["DT_PLATFORM_TOKEN"] = self._config.dt_platform_token
        if self._config.dt_api_token:
            env["DT_API_TOKEN"] = self._config.dt_api_token
        # Headless OAuth client-credentials flow (works without a browser, e.g. Cloud Run).
        if self._config.dt_oauth_client_id and self._config.dt_oauth_client_secret:
            env["OAUTH_CLIENT_ID"] = self._config.dt_oauth_client_id
            env["OAUTH_CLIENT_SECRET"] = self._config.dt_oauth_client_secret
        if self._config.dt_disable_telemetry:
            env["DT_MCP_DISABLE_TELEMETRY"] = "true"

        npx_path = (
            shutil.which("npx.cmd")
            or shutil.which("npx")
            or shutil.which("npx.ps1")
            or "npx"
        )
        params = StdioServerParameters(
            command=npx_path,
            args=[
                "-y",
                f"@dynatrace-oss/dynatrace-mcp-server@{self._config.dt_mcp_server_version}",
            ],
            env=env,
        )
        self._toolset = McpToolset(
            connection_params=StdioConnectionParams(
                server_params=params,
                timeout=self._config.mcp_timeout_seconds,
            )
        )
        self._session = await self._toolset._mcp_session_manager.create_session()

    async def close(self) -> None:
        if self._toolset is not None:
            await self._toolset.close()
        self._toolset = None
        self._session = None
        self._tool_schemas = {}

    async def list_tools(self) -> list[dict[str, Any]]:
        await self.connect()
        result = await self._session.list_tools()
        tools = []
        for tool in result.tools:
            dumped = tool.model_dump(mode="json")
            self._tool_schemas[tool.name] = dumped.get("inputSchema") or {}
            tools.append(dumped)
        return tools

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> DynatraceToolResult:
        await self.connect()
        result = await self._session.call_tool(name, arguments or {})
        text = []
        for item in result.content:
            if hasattr(item, "text") and item.text:
                text.append(item.text)
            else:
                text.append(str(item))
        return DynatraceToolResult(
            tool_name=name,
            is_error=result.isError,
            text="\n".join(text).strip(),
            structured_content=result.structuredContent,
            raw=result.model_dump(mode="json"),
        )

    async def verify_dql(self, query: str) -> DynatraceToolResult:
        tool_name, args = await self._build_query_call("verify_dql", query)
        return await self.call_tool(tool_name, args)

    async def execute_dql(self, query: str) -> DynatraceToolResult:
        tool_name, args = await self._build_query_call("execute_dql", query)
        return await self.call_tool(tool_name, args)

    async def create_notebook(self, title: str, markdown_body: str) -> dict[str, Any]:
        await self.list_tools()
        for tool_name in ("create_dynatrace_notebook", "create_document"):
            if tool_name in self._tool_schemas:
                schema = self._tool_schemas.get(tool_name, {})
                properties = schema.get("properties", {})
                args: dict[str, Any] = {}
                for candidate in ("title", "name"):
                    if candidate in properties:
                        args[candidate] = title
                        break
                for candidate in ("markdown", "content", "body", "text"):
                    if candidate in properties:
                        args[candidate] = markdown_body
                        break
                result = await self.call_tool(tool_name, args)
                return {
                    "status": "created" if not result.is_error else "failed",
                    "tool": tool_name,
                    "detail": result.text,
                }

        local_path = write_scorecard(title, markdown_body, config=self._config)
        return {
            "status": "dry-run",
            "detail": "No notebook creation tool was found in the live MCP tool list.",
            "local_path": str(local_path),
        }

    async def send_event(self, title: str, properties: dict[str, Any] | None = None) -> None:
        await self.list_tools()
        if "send_event" not in self._tool_schemas:
            return
        schema = self._tool_schemas["send_event"]
        props = schema.get("properties", {})
        args: dict[str, Any] = {}
        if "title" in props:
            args["title"] = title
        elif "name" in props:
            args["name"] = title
        if "properties" in props:
            args["properties"] = properties or {}
        elif "payload" in props:
            args["payload"] = properties or {}
        await self.call_tool("send_event", args)

    async def _build_query_call(self, tool_name: str, query: str) -> tuple[str, dict[str, Any]]:
        await self.list_tools()
        schema = self._tool_schemas.get(tool_name, {})
        properties = schema.get("properties", {})
        args: dict[str, Any] = {}
        # dynatrace-mcp-server uses `dqlStatement`; keep older names as fallbacks.
        for candidate in ("dqlStatement", "query", "dql", "statement", "text"):
            if candidate in properties:
                args[candidate] = query
                break
        if not args:
            # Last resort: if there is exactly one required string property, use it.
            required = schema.get("required") or []
            string_props = [p for p in required if properties.get(p, {}).get("type") == "string"]
            args[string_props[0] if len(string_props) == 1 else "dqlStatement"] = query
        if "from" in properties and "from" not in args:
            args["from"] = f"-{self._config.burn_window_seconds}s"
        if "to" in properties and "to" not in args:
            args["to"] = "now"
        return tool_name, args


def extract_rows(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        if payload and all(isinstance(item, dict) for item in payload):
            return payload
        for item in payload:
            rows = extract_rows(item)
            if rows:
                return rows
        return []
    if isinstance(payload, dict):
        for key in ("records", "rows", "items", "data", "result", "values", "tables"):
            if key in payload:
                rows = extract_rows(payload[key])
                if rows:
                    return rows
        if payload and all(
            isinstance(value, (str, int, float, bool, type(None))) for value in payload.values()
        ):
            return [payload]
    return []


async def fetch_burn_rate(config: AegisConfig | None = None) -> float:
    config = config or get_config()
    if config.has_dynatrace:
        query = build_burn_rate_query(config)
        try:
            async with DynatraceMcpClient(config) as client:
                if query not in _VERIFIED_QUERIES:
                    verify = await client.verify_dql(query)
                    if verify.is_error:
                        raise RuntimeError(verify.text or "verify_dql failed")
                    _VERIFIED_QUERIES.add(query)
                result = await client.execute_dql(query)
                rows = extract_rows(result.structured_content) or extract_rows(result.raw)
                if rows:
                    row = rows[0]
                    if "burn_rate" in row:
                        return float(row["burn_rate"])
                    if "bad_ratio" in row:
                        bad_ratio = float(row["bad_ratio"])
                        return bad_ratio / max(1.0 - config.slo_target, 0.000001)
        except Exception as exc:
            event_bus.publish(
                {
                    "type": "message",
                    "level": "warning",
                    "source": "dynatrace",
                    "text": f"Falling back to local SLI because Dynatrace burn query failed: {exc}",
                }
            )
    return await fetch_local_burn_rate(config)


async def fetch_local_burn_rate(config: AegisConfig) -> float:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{config.demo_app_url}/metrics/recent",
                params={
                    "service": "frontend",
                    "window_seconds": config.burn_window_seconds,
                    "threshold_ms": config.latency_threshold_ms,
                },
            )
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        event_bus.publish(
            {
                "type": "message",
                "level": "warning",
                "source": "local-sli",
                "text": f"Local SLI query failed: {exc}",
            }
        )
        return 0.0
    bad_ratio = float(data.get("bad_ratio", 0.0))
    return bad_ratio / max(1.0 - config.slo_target, 0.000001)


class BurnRateSampler:
    """Polls burn rate while reusing a single MCP session and httpx client.

    Opens at most one Dynatrace MCP subprocess for the whole experiment instead
    of spawning a fresh `npx` process on every poll. Applies EWMA smoothing so
    the displayed signal ramps over a couple of polls rather than snapping.
    """

    def __init__(self, config: AegisConfig, alpha: float | None = None):
        self.config = config
        self._query = build_burn_rate_query(config)
        self._dt: DynatraceMcpClient | None = None
        self._http: httpx.AsyncClient | None = None
        self._verified = False
        self._ewma: float | None = None
        self._alpha = alpha if alpha is not None else config.burn_smoothing_alpha

    async def __aenter__(self) -> "BurnRateSampler":
        if self.config.has_dynatrace:
            try:
                client = DynatraceMcpClient(self.config)
                await client.connect()
                self._dt = client
            except Exception as exc:
                event_bus.publish(
                    {
                        "type": "message",
                        "level": "warning",
                        "source": "dynatrace",
                        "text": f"Could not open Dynatrace MCP session, using local SLI: {exc}",
                    }
                )
                self._dt = None
        self._http = httpx.AsyncClient(timeout=10)
        # Seed from a healthy baseline so the first faulted sample ramps in.
        self._ewma = 0.0
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._dt is not None:
            try:
                await self._dt.close()
            except Exception:
                pass
            self._dt = None
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def _raw_sample(self) -> float:
        if self._dt is not None:
            try:
                if not self._verified:
                    verify = await self._dt.verify_dql(self._query)
                    if verify.is_error:
                        raise RuntimeError(verify.text or "verify_dql failed")
                    self._verified = True
                result = await self._dt.execute_dql(self._query)
                rows = extract_rows(result.structured_content) or extract_rows(result.raw)
                if rows:
                    row = rows[0]
                    if "burn_rate" in row:
                        return float(row["burn_rate"])
                    if "bad_ratio" in row:
                        return float(row["bad_ratio"]) / max(1.0 - self.config.slo_target, 0.000001)
            except Exception as exc:
                event_bus.publish(
                    {
                        "type": "message",
                        "level": "warning",
                        "source": "dynatrace",
                        "text": f"Falling back to local SLI because Dynatrace burn query failed: {exc}",
                    }
                )
        return await self._sample_local()

    async def _sample_local(self) -> float:
        assert self._http is not None
        try:
            response = await self._http.get(
                f"{self.config.demo_app_url}/metrics/recent",
                params={
                    "service": "frontend",
                    "window_seconds": self.config.burn_window_seconds,
                    "threshold_ms": self.config.latency_threshold_ms,
                },
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            event_bus.publish(
                {
                    "type": "message",
                    "level": "warning",
                    "source": "local-sli",
                    "text": f"Local SLI query failed: {exc}",
                }
            )
            return 0.0
        return float(data.get("bad_ratio", 0.0)) / max(1.0 - self.config.slo_target, 0.000001)

    async def sample(self) -> float:
        raw = await self._raw_sample()
        if self._alpha >= 1.0 or self._ewma is None:
            self._ewma = raw
        else:
            self._ewma = self._alpha * raw + (1.0 - self._alpha) * self._ewma
        return round(self._ewma, 3)

    async def send_event(self, title: str, properties: dict[str, Any] | None = None) -> None:
        if self._dt is None:
            return
        try:
            await self._dt.send_event(title, properties or {})
        except Exception:
            pass


def make_burn_sampler(config: AegisConfig) -> BurnRateSampler:
    return BurnRateSampler(config)


def get_burn_rate(config: AegisConfig | None = None) -> float:
    return _run_blocking(fetch_burn_rate(config))


def list_dynatrace_tools(config: AegisConfig | None = None) -> list[str]:
    async def _run() -> list[str]:
        cfg = config or get_config()
        if not cfg.has_dynatrace:
            return []
        async with DynatraceMcpClient(cfg) as client:
            return [tool["name"] for tool in await client.list_tools()]

    return _run_blocking(_run())


def create_notebook(title: str, markdown_body: str, config: AegisConfig | None = None) -> dict[str, Any]:
    async def _run() -> dict[str, Any]:
        cfg = config or get_config()
        if not cfg.has_dynatrace:
            local_path = write_scorecard(title, markdown_body, config=cfg)
            return {
                "status": "dry-run",
                "detail": "Dynatrace is not configured. Wrote the report locally instead.",
                "local_path": str(local_path),
            }
        async with DynatraceMcpClient(cfg) as client:
            return await client.create_notebook(title, markdown_body)

    return _run_blocking(_run())


def send_event(title: str, properties: dict[str, Any] | None = None, config: AegisConfig | None = None) -> None:
    async def _run() -> None:
        cfg = config or get_config()
        if not cfg.has_dynatrace:
            return
        async with DynatraceMcpClient(cfg) as client:
            await client.send_event(title, properties)

    try:
        _run_blocking(_run())
    except Exception:
        return
