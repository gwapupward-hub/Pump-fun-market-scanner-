from __future__ import annotations

from typing import Any

import httpx

from pump_intel.config import Settings


class PumpFunClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        headers = {
            "Accept": "application/json",
            "Origin": settings.pump_fun_origin,
            "User-Agent": "pump-intel-analytics/0.1 (+https://github.com)",
        }
        if settings.pump_fun_bearer_token:
            headers["Authorization"] = f"Bearer {settings.pump_fun_bearer_token}"
        self._client = httpx.Client(timeout=30.0, headers=headers)

    def close(self) -> None:
        self._client.close()

    def _get(self, base: str, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{base.rstrip('/')}/{path.lstrip('/')}"
        r = self._client.get(url, params=params)
        r.raise_for_status()
        if not r.content:
            return None
        return r.json()

    def fetch_coins_page(self, offset: int, limit: int) -> list[dict[str, Any]]:
        data = self._get(
            self._settings.pump_fun_frontend_base,
            "/coins",
            {"offset": offset, "limit": limit},
        )
        if data is None:
            return []
        if isinstance(data, list):
            return data
        return []

    def fetch_currently_live(self) -> list[dict[str, Any]]:
        data = self._get(self._settings.pump_fun_frontend_base, "/coins/currently-live")
        if data is None:
            return []
        return data if isinstance(data, list) else []

    def fetch_sol_price_usd(self) -> float | None:
        try:
            data = self._get(self._settings.pump_fun_frontend_base, "/sol/price")
        except httpx.HTTPStatusError:
            return None
        if isinstance(data, (int, float)):
            return float(data)
        if not isinstance(data, dict):
            return None
        for key in ("usd", "price", "solPrice", "sol_price"):
            v = data.get(key)
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str):
                try:
                    return float(v)
                except ValueError:
                    continue
        return None

    def fetch_trades_sample(self, mint: str, limit: int = 200) -> list[dict[str, Any]]:
        data = self._get(
            self._settings.pump_fun_frontend_base,
            f"/trades/all/{mint}",
            {"limit": limit, "offset": 0, "minimumSize": 0},
        )
        if not data:
            return []
        return data if isinstance(data, list) else []

    def fetch_top_holders(self, mint: str) -> list[dict[str, Any]] | None:
        path = f"/coins/top-holders-and-sol-balance/{mint}"
        try:
            data = self._get(self._settings.pump_fun_advanced_base, path)
        except httpx.HTTPStatusError:
            return None
        if data is None:
            return None
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "holders" in data:
            inner = data["holders"]
            return inner if isinstance(inner, list) else None
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return data["data"]
        return None
