"""FastAPI demo app with frontend, payment, store, and chaos controls."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
import time
import uuid

from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel

from .chaos import get_chaos_state
from .chaos import get_hardened
from .chaos import record_request
from .chaos import reset_samples
from .chaos import set_chaos_state
from .chaos import set_hardened
from .chaos import summarize_recent
from .otel_setup import configure_telemetry
from .payment_client import PaymentClient


class ChaosPayload(BaseModel):
    target: str = "payment->store"
    latency_ms: int = 0
    error_rate: float = 0.0


class HardenPayload(BaseModel):
    enabled: bool = True


payment_client: PaymentClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global payment_client
    configure_telemetry(app)
    base_url = os.getenv("DEMO_APP_BASE_URL", "http://127.0.0.1:8001")
    payment_client = PaymentClient(base_url=base_url)
    try:
        yield
    finally:
        if payment_client is not None:
            await payment_client.aclose()
        payment_client = None


app = FastAPI(title="Aegis Demo App", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "aegis-demo-app"}


@app.get("/frontend/checkout")
async def frontend_checkout(order_id: str | None = None) -> dict:
    started = time.perf_counter()
    chosen_order_id = order_id or str(uuid.uuid4())
    ok = False
    try:
        response = await payment_charge(chosen_order_id)
        ok = True
        return {
            "service": "frontend",
            "order_id": chosen_order_id,
            "payment": response,
        }
    finally:
        duration_ms = (time.perf_counter() - started) * 1000
        record_request("frontend", duration_ms, ok)


@app.post("/payment/charge")
async def payment_charge(order_id: str) -> dict:
    started = time.perf_counter()
    ok = False
    try:
        if payment_client is None:
            raise HTTPException(status_code=500, detail="payment client is not initialized")
        store_response = await payment_client.fetch_store_inventory(order_id)
        ok = True
        return {
            "service": "payment",
            "approved": True,
            "order_id": order_id,
            "inventory": store_response,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        duration_ms = (time.perf_counter() - started) * 1000
        record_request("payment", duration_ms, ok)


@app.get("/store/inventory")
async def store_inventory(order_id: str) -> dict:
    started = time.perf_counter()
    ok = False
    try:
        base_latency_ms = int(os.getenv("STORE_BASE_LATENCY_MS", "40"))
        import asyncio

        await asyncio.sleep(base_latency_ms / 1000.0)
        ok = True
        return {
            "service": "store",
            "order_id": order_id,
            "inventory_ok": True,
            "sku": "premium-plan",
        }
    finally:
        duration_ms = (time.perf_counter() - started) * 1000
        record_request("store", duration_ms, ok)


@app.get("/chaos")
async def get_chaos() -> dict:
    return get_chaos_state()


@app.post("/chaos")
async def post_chaos(payload: ChaosPayload) -> dict:
    return set_chaos_state(payload.target, payload.latency_ms, payload.error_rate)


@app.get("/harden")
async def get_harden() -> dict:
    return {"hardened": get_hardened()}


@app.post("/harden")
async def post_harden(payload: HardenPayload) -> dict:
    return {"hardened": set_hardened(payload.enabled)}


@app.get("/metrics/recent")
async def recent_metrics(
    service: str = "frontend",
    window_seconds: int = 90,
    threshold_ms: int = 500,
) -> dict:
    return summarize_recent(service, window_seconds, threshold_ms)


@app.post("/metrics/reset")
async def metrics_reset() -> dict:
    return reset_samples()
