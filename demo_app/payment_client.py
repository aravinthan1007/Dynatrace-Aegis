"""Payment dependency client.

By default this client has NO timeout or retry hardening, which is the
vulnerability Aegis exercises. When the runtime hardening flag is enabled
(via POST /harden, set by Aegis after opening the PR), the same client adds a
per-attempt timeout and a small retry policy so the verify-after-fix re-run can
demonstrate that the fix actually works.
"""

from __future__ import annotations

import asyncio

import httpx

from .chaos import apply_payment_to_store_chaos
from .chaos import get_hardened


class PaymentClient:
    def __init__(self, base_url: str) -> None:
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=None)

    async def fetch_store_inventory(self, order_id: str) -> dict:
        if get_hardened():
            return await self._fetch_hardened(order_id)
        await apply_payment_to_store_chaos()
        response = await self._client.get("/store/inventory", params={"order_id": order_id})
        response.raise_for_status()
        return response.json()

    async def _fetch_hardened(self, order_id: str) -> dict:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                await apply_payment_to_store_chaos()
                response = await self._client.get(
                    "/store/inventory",
                    params={"order_id": order_id},
                    timeout=httpx.Timeout(2.0, connect=0.5),
                )
                response.raise_for_status()
                return response.json()
            except Exception as exc:  # absorb injected failures and transient errors
                last_error = exc
                if attempt == 2:
                    break
                await asyncio.sleep(0.05 * (attempt + 1))
        raise RuntimeError(f"store dependency failed after retries: {last_error}") from last_error

    async def aclose(self) -> None:
        await self._client.aclose()
