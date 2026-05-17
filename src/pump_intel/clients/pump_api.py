from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import TracebackType
from typing import Any

import httpx

from pump_intel.config import get_settings
from pump_intel.http import with_retry

log = logging.getLogger(__name__)


class PumpAPIError(RuntimeError):
    """Raised when the Pump.fun API returns an unrecoverable error."""


class PumpFunClient:
    """Read-only client for Pump.fun frontend API (analytics only).

    Use as an async context manager so the underlying httpx connection pool is
    reused for the lifetime of the pipeline:

        async with PumpFunClient() as client:
            sol = await client.get_sol_price()
            async for page in client.iter_coins_pages():
                ...
    """

    def __init__(self) -> None:
        s = get_settings()
        self._base = s.pump_api_base.rstrip("/")
        self._headers = {
            "User-Agent": s.pump_user_agent,
            "Accept": "application/json",
            "Origin": s.pump_origin,
        }
        self._timeout = httpx.Timeout(30.0, connect=10.0)
        self._retry_attempts = s.http_retry_attempts
        self._retry_base = s.http_retry_base_delay_s
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> PumpFunClient:
        self._client = httpx.AsyncClient(headers=self._headers, timeout=self._timeout)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("PumpFunClient must be used as an async context manager")
        return self._client

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    async def _get(self, path: str, *, params: dict[str, Any] | None = None) -> httpx.Response:
        client = self._ensure_client()

        @with_retry(attempts=self._retry_attempts, base_delay=self._retry_base, op_name=f"GET {path}")
        async def _do() -> httpx.Response:
            return await client.get(self._url(path), params=params)

        return await _do()

    async def get_sol_price(self) -> float:
        r = await self._get("/sol-price")
        if r.status_code >= 400:
            raise PumpAPIError(f"sol-price returned {r.status_code}: {r.text[:200]}")
        data = r.json()
        return float(data["solPrice"])

    async def iter_coins_pages(self) -> AsyncIterator[list[dict[str, Any]]]:
        s = get_settings()
        offset = 0
        pages = 0
        while pages < s.ingest_max_pages:
            params = {
                "limit": s.ingest_page_size,
                "offset": offset,
                "sort": s.ingest_sort,
                "order": s.ingest_order,
                "includeNsfw": str(s.include_nsfw).lower(),
                "creator": "",
                "complete": "",
                "meta": "",
            }
            r = await self._get("/coins", params=params)
            if r.status_code == 404:
                log.info("coins endpoint 404 at offset=%d — stopping pagination", offset)
                return
            if r.status_code >= 400:
                raise PumpAPIError(
                    f"coins page failed offset={offset} status={r.status_code} body={r.text[:200]}"
                )
            batch = r.json()
            if not isinstance(batch, list) or not batch:
                return
            yield batch
            pages += 1
            offset += len(batch)
            if len(batch) < s.ingest_page_size:
                return

    async def get_coin(self, mint: str, *, sync: bool = True) -> dict[str, Any] | None:
        r = await self._get(f"/coins/{mint}", params={"sync": str(sync).lower()})
        if r.status_code == 404:
            return None
        if r.status_code >= 400:
            raise PumpAPIError(f"coin {mint} returned {r.status_code}: {r.text[:200]}")
        return r.json()


def ms_to_utc(ms: int | float | None) -> datetime | None:
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(float(ms) / 1000.0, tz=UTC)
    except (OSError, ValueError, OverflowError, TypeError):
        return None


__all__ = ["PumpAPIError", "PumpFunClient", "ms_to_utc"]
