"""Steady async traffic generator for the Aegis demo app."""

from __future__ import annotations

import argparse
import asyncio
from collections import deque
import statistics
import time

import httpx


async def worker(client: httpx.AsyncClient, base_url: str, results: deque[tuple[bool, float]]) -> None:
    started = time.perf_counter()
    ok = False
    try:
        response = await client.get(f"{base_url.rstrip('/')}/frontend/checkout")
        response.raise_for_status()
        ok = True
    except Exception:
        ok = False
    finally:
        duration_ms = (time.perf_counter() - started) * 1000
        results.append((ok, duration_ms))


async def run_loadgen(base_url: str, rps: float, duration_s: int | None) -> None:
    results: deque[tuple[bool, float]] = deque(maxlen=500)
    started = time.perf_counter()
    last_report = started

    async with httpx.AsyncClient(timeout=10) as client:
        while True:
            now = time.perf_counter()
            if duration_s is not None and now - started >= duration_s:
                break
            asyncio.create_task(worker(client, base_url, results))
            await asyncio.sleep(max(1.0 / max(rps, 0.1), 0.001))

            if now - last_report >= 5:
                sample = list(results)
                success_rate = (sum(1 for ok, _ in sample if ok) / len(sample)) if sample else 0.0
                p95 = statistics.quantiles([lat for _, lat in sample], n=20)[-1] if len(sample) >= 20 else (
                    max((lat for _, lat in sample), default=0.0)
                )
                print(
                    f"[loadgen] requests={len(sample)} success_rate={success_rate:.2%} p95_ms={p95:.1f}",
                    flush=True,
                )
                last_report = now


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aegis demo load generator")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--rps", type=float, default=20.0)
    parser.add_argument("--duration-s", type=int, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run_loadgen(args.base_url, args.rps, args.duration_s))
