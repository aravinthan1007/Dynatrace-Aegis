"""Deterministic experiment runner for Aegis.

The safety-critical loop (inject -> poll burn -> abort) is plain, auditable code
with a numeric threshold. Gemini never participates in the abort decision.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import time
from typing import Any, Callable

from .actions import set_chaos
from .config import AegisConfig
from .config import get_config
from .dynatrace import make_burn_sampler
from .events import event_bus

SamplerFactory = Callable[[AegisConfig], Any]


def run_coro_blocking(coro: Any) -> Any:
    """Run a coroutine to completion even if a loop is already running.

    ADK executes sync tools inside its event loop, so a bare `asyncio.run()`
    would raise "cannot be called from a running event loop". When that happens
    we offload to a dedicated worker thread that owns its own loop.
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def _run_experiment_async(
    target: str,
    latency_ms: int,
    burn_abort: float,
    poll_seconds: float,
    max_duration_s: float,
    error_rate: float,
    config: AegisConfig,
    sampler_factory: SamplerFactory,
) -> dict[str, Any]:
    start = time.monotonic()
    peak = 0.0
    aborted = False
    timeline: list[dict[str, float]] = []

    sampler = sampler_factory(config)
    async with sampler:
        await sampler.send_event(
            "Aegis experiment START",
            {"target": target, "latency_ms": latency_ms, "error_rate": error_rate},
        )
        event_bus.publish(
            {
                "type": "reasoning",
                "phase": "run",
                "text": (
                    f"Injecting latency={latency_ms}ms error_rate={error_rate} on {target} "
                    f"and watching burn every {poll_seconds}s (abort at {burn_abort})."
                ),
            }
        )
        set_chaos(target=target, latency_ms=latency_ms, error_rate=error_rate, config=config)

        try:
            while time.monotonic() - start < max_duration_s:
                burn = await sampler.sample()
                elapsed = round(time.monotonic() - start, 1)
                peak = max(peak, burn)
                timeline.append({"t": elapsed, "burn": burn})
                event_bus.publish({"type": "burn", "burn": burn, "t": elapsed, "threshold": burn_abort})
                if burn >= burn_abort:
                    aborted = True
                    set_chaos(target=target, latency_ms=0, error_rate=0.0, config=config)
                    await sampler.send_event(
                        "Aegis ABORT",
                        {"target": target, "burn": round(burn, 2), "threshold": burn_abort},
                    )
                    event_bus.publish(
                        {
                            "type": "abort",
                            "burn": burn,
                            "threshold": burn_abort,
                            "text": f"Abort triggered because burn {burn:.2f} exceeded threshold {burn_abort:.2f}.",
                        }
                    )
                    break
                await asyncio.sleep(poll_seconds)
        finally:
            set_chaos(target=target, latency_ms=0, error_rate=0.0, config=config)
            if not aborted:
                await sampler.send_event(
                    "Aegis experiment END", {"target": target, "peak_burn": round(peak, 2)}
                )
                event_bus.publish(
                    {
                        "type": "reasoning",
                        "phase": "scorecard",
                        "text": f"Experiment completed without abort. Peak burn was {peak:.2f}.",
                    }
                )

    return {
        "aborted": aborted,
        "peak_burn": round(peak, 3),
        "duration_s": round(time.monotonic() - start, 1),
        "timeline": timeline,
        "target": target,
        "latency_ms": latency_ms,
        "error_rate": error_rate,
        "burn_abort": burn_abort,
    }


def run_experiment(
    target: str,
    latency_ms: int,
    burn_abort: float = 10.0,
    poll_seconds: float = 3,
    max_duration_s: float = 120,
    error_rate: float = 0.0,
    *,
    config: AegisConfig | None = None,
    sampler_factory: SamplerFactory | None = None,
) -> dict[str, Any]:
    """Inject a fault, poll burn rate, and abort in deterministic code.

    A single burn sampler (one MCP session) is opened for the whole run, so we
    no longer spawn an `npx` subprocess on every poll. `sampler_factory` is
    injectable so tests can drive scripted burn values.
    """

    config = config or get_config()
    sampler_factory = sampler_factory or make_burn_sampler
    return run_coro_blocking(
        _run_experiment_async(
            target=target,
            latency_ms=latency_ms,
            burn_abort=burn_abort,
            poll_seconds=poll_seconds,
            max_duration_s=max_duration_s,
            error_rate=error_rate,
            config=config,
            sampler_factory=sampler_factory,
        )
    )
