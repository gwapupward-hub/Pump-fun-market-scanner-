from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from pump_intel.config import Settings, get_settings
from pump_intel.schemas.coin import NormalizedCoin

log = logging.getLogger(__name__)


class PumpFunClient:
    """Read-only HTTP client for Pump.fun front-end style JSON APIs."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _headers(self) -> dict[str, str]:
        h = {
            "Accept": "application/json",
            "Origin": self.settings.pump_origin,
            "Referer": self.settings.pump_referer,
            "User-Agent": "PumpIntelAgent/0.1 (+analytics)",
        }
        if self.settings.pump_api_bearer:
            h["Authorization"] = f"Bearer {self.settings.pump_api_bearer}"
        return h

    async def fetch_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.settings.pump_api_base.rstrip('/')}/{path.lstrip('/')}"
        timeout = httpx.Timeout(self.settings.pump_http_timeout_s)
        async with httpx.AsyncClient(timeout=timeout, headers=self._headers()) as client:
            r = await client.get(url, params=params or {})
            r.raise_for_status()
            if not r.content:
                log.warning("Empty body from %s", url)
                return []
            return r.json()

    def fetch_json_sync(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.settings.pump_api_base.rstrip('/')}/{path.lstrip('/')}"
        timeout = httpx.Timeout(self.settings.pump_http_timeout_s)
        with httpx.Client(timeout=timeout, headers=self._headers()) as client:
            r = client.get(url, params=params or {})
            r.raise_for_status()
            if not r.content:
                log.warning("Empty body from %s", url)
                return []
            return r.json()


def _as_coin_list(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("coins", "data", "items", "results"):
            v = payload.get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        return [payload]
    return []


async def load_coins_for_scan(settings: Settings | None = None) -> list[NormalizedCoin]:
    s = settings or get_settings()
    if s.ingest_source == "fixture":
        path = Path(s.ingest_fixture_path)
        if not path.is_file():
            raise FileNotFoundError(f"Fixture not found: {path}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = _as_coin_list(raw)
        return [NormalizedCoin.from_api_dict(x) for x in items if x.get("mint") or x.get("address")]

    client = PumpFunClient(s)
    merged: list[dict[str, Any]] = []

    async def grab(path: str, **params: Any) -> None:
        try:
            data = await client.fetch_json(path, params)
            merged.extend(_as_coin_list(data))
        except Exception as e:  # noqa: BLE001
            log.warning("Ingest path failed %s: %s", path, e)

    await grab("/coins/latest", limit=s.scan_coin_limit)
    await grab("/coins/graduated", limit=min(s.scan_coin_limit, 200))
    await grab("/coins/currently/live", limit=min(s.scan_coin_limit, 200))

    # Deduplicate by mint
    by_mint: dict[str, dict[str, Any]] = {}
    for row in merged:
        m = str(row.get("mint") or row.get("address") or row.get("id") or "")
        if not m:
            continue
        by_mint[m] = {**by_mint.get(m, {}), **row}

    coins = [NormalizedCoin.from_api_dict(v) for v in by_mint.values()]
    coins.sort(key=lambda c: c.launch_at or datetime.min.replace(tzinfo=UTC), reverse=True)
    return coins[: s.scan_coin_limit]


def load_coins_for_scan_sync(settings: Settings | None = None) -> list[NormalizedCoin]:
    """Synchronous wrapper for jobs / APScheduler."""
    import asyncio

    return asyncio.run(load_coins_for_scan(settings))
