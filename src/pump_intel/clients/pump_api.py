from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from pump_intel.config import get_settings

log = logging.getLogger(__name__)


class PumpFunClient:
    """Read-only client for Pump.fun frontend API (analytics only)."""

    def __init__(self) -> None:
        s = get_settings()
        self._base = s.pump_api_base.rstrip("/")
        self._headers = {
            "User-Agent": s.pump_user_agent,
            "Accept": "application/json",
            "Origin": s.pump_origin,
        }
        self._timeout = httpx.Timeout(30.0, connect=10.0)

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    async def get_sol_price(self) -> float:
        async with httpx.AsyncClient(headers=self._headers, timeout=self._timeout) as client:
            r = await client.get(self._url("/sol-price"))
            r.raise_for_status()
            data = r.json()
            return float(data["solPrice"])

    async def iter_coins_pages(self):
        s = get_settings()
        offset = 0
        pages = 0
        async with httpx.AsyncClient(headers=self._headers, timeout=self._timeout) as client:
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
                r = await client.get(self._url("/coins"), params=params)
                if r.status_code >= 400:
                    log.warning("coins page failed: %s %s", r.status_code, r.text[:200])
                    break
                batch = r.json()
                if not isinstance(batch, list) or not batch:
                    break
                yield batch
                pages += 1
                offset += len(batch)
                if len(batch) < s.ingest_page_size:
                    break

    async def get_coin(self, mint: str, *, sync: bool = True) -> dict[str, Any] | None:
        async with httpx.AsyncClient(headers=self._headers, timeout=self._timeout) as client:
            r = await client.get(self._url(f"/coins/{mint}"), params={"sync": str(sync).lower()})
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()


def ms_to_utc(ms: int | float | None) -> datetime | None:
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc)
    except (OSError, ValueError, OverflowError):
        return None
