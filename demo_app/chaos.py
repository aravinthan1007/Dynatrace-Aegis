"""Chaos controls and recent request metrics for the demo app."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
import os
import random
import threading
from typing import Any

from fastapi import HTTPException


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


_hardened_lock = threading.Lock()
_hardened = _as_bool(os.getenv("PAYMENT_HARDENED"), False)


def get_hardened() -> bool:
    with _hardened_lock:
        return _hardened


def set_hardened(enabled: bool) -> bool:
    global _hardened
    with _hardened_lock:
        _hardened = bool(enabled)
        return _hardened


@dataclass(slots=True)
class ChaosState:
    target: str = "payment->store"
    latency_ms: int = 0
    error_rate: float = 0.0


@dataclass(slots=True)
class RequestSample:
    service: str
    started_at: datetime
    duration_ms: float
    ok: bool


_chaos_lock = threading.Lock()
_chaos_state = ChaosState()
_samples_lock = threading.Lock()
_recent_samples: deque[RequestSample] = deque(maxlen=5000)


def get_chaos_state() -> dict[str, Any]:
    with _chaos_lock:
        return asdict(_chaos_state)


def set_chaos_state(target: str, latency_ms: int, error_rate: float) -> dict[str, Any]:
    with _chaos_lock:
        _chaos_state.target = target
        _chaos_state.latency_ms = max(latency_ms, 0)
        _chaos_state.error_rate = min(max(error_rate, 0.0), 1.0)
        return asdict(_chaos_state)


async def apply_payment_to_store_chaos() -> None:
    with _chaos_lock:
        state = ChaosState(
            target=_chaos_state.target,
            latency_ms=_chaos_state.latency_ms,
            error_rate=_chaos_state.error_rate,
        )

    if state.target != "payment->store":
        return

    if state.latency_ms > 0:
        import asyncio

        await asyncio.sleep(state.latency_ms / 1000.0)

    if state.error_rate > 0.0 and random.random() < state.error_rate:
        raise HTTPException(status_code=503, detail="Injected dependency failure")


def reset_samples() -> dict[str, Any]:
    """Clear the recent-request buffer so the burn window starts clean.

    Used before the verify-after-fix run so its burn reflects only the hardened
    behavior, not leftover bad samples from the abort run still inside the window.
    """

    with _samples_lock:
        cleared = len(_recent_samples)
        _recent_samples.clear()
    return {"cleared": cleared}


def record_request(service: str, duration_ms: float, ok: bool) -> None:
    with _samples_lock:
        _recent_samples.append(
            RequestSample(
                service=service,
                started_at=datetime.now(UTC),
                duration_ms=duration_ms,
                ok=ok,
            )
        )


def summarize_recent(service: str, window_seconds: int, threshold_ms: int) -> dict[str, Any]:
    cutoff = datetime.now(UTC).timestamp() - window_seconds
    with _samples_lock:
        samples = [
            sample
            for sample in list(_recent_samples)
            if sample.service == service and sample.started_at.timestamp() >= cutoff
        ]

    total = len(samples)
    bad = 0
    for sample in samples:
        if (not sample.ok) or sample.duration_ms > threshold_ms:
            bad += 1

    durations = sorted(sample.duration_ms for sample in samples)
    avg_ms = (sum(durations) / total) if total else 0.0
    if durations:
        idx = min(len(durations) - 1, int(round(0.95 * (len(durations) - 1))))
        p95_ms = durations[idx]
    else:
        p95_ms = 0.0

    bad_ratio = (bad / total) if total else 0.0
    return {
        "service": service,
        "window_seconds": window_seconds,
        "threshold_ms": threshold_ms,
        "total": total,
        "bad": bad,
        "bad_ratio": bad_ratio,
        "avg_ms": round(avg_ms, 1),
        "p95_ms": round(p95_ms, 1),
        "hardened": get_hardened(),
    }
