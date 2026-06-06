"""Dashboard server for Aegis."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from aegis_agent.agent import run_aegis_game_day
from aegis_agent.agent import run_with_adk
from aegis_agent.config import get_config
from aegis_agent.dynatrace import fetch_burn_rate
from aegis_agent.events import event_bus


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
config = get_config()

app = FastAPI(title="Aegis Dashboard", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "demo_app_url": config.demo_app_url,
        "dynatrace_configured": config.has_dynatrace,
        "github_configured": config.has_github,
        "slack_configured": config.has_slack,
    }


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
