from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import httpx

from pump_intel.config import Settings
from pump_intel.models.domain import NormalizedToken


class PumpFunClient:
    """Read-only Pump.fun HTTP client (no transactions)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": self._settings.http_user_agent,
            "Origin": "https://pump.fun",
            "Referer": "https://pump.fun/",
        }
        if self._settings.pumpfun_jwt:
            h["Authorization"] = f"Bearer {self._settings.pumpfun_jwt}"
        return h

    def fetch_fixture_coins(self) -> list[dict[str, Any]]:
        path = self._settings.pumpfun_fixture_path
        if path is None:
            raise RuntimeError("PUMPFUN_FIXTURE_PATH is required when PUMPFUN_INGEST_MODE=fixture")
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("Fixture must be a JSON array of coin objects")
        return [x for x in data if isinstance(x, dict)]

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self._settings.pumpfun_api_base.rstrip('/')}/{path.lstrip('/')}"
        with httpx.Client(timeout=self._settings.pumpfun_timeout_s) as client:
            resp = client.get(url, headers=self._headers(), params=params)
            resp.raise_for_status()
            if not resp.content:
                raise RuntimeError(
                    "Pump.fun API returned an empty body. "
                    "Most Frontend API routes require PUMPFUN_JWT (Bearer token). "
                    "Alternatively set PUMPFUN_INGEST_MODE=fixture for offline fixtures."
                )
            return resp.json()

    def fetch_latest_coins(self, *, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
        data = self._get_json("/coins/latest", {"limit": limit, "offset": offset})
        return self._as_list(data)

    def fetch_graduated_coins(self, *, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
        data = self._get_json("/coins/graduated", {"limit": limit, "offset": offset})
        return self._as_list(data)

    def fetch_live_coins(self, *, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
        data = self._get_json("/coins/currently/live", {"limit": limit, "offset": offset})
        return self._as_list(data)

    @staticmethod
    def _as_list(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            for key in ("coins", "items", "data", "results"):
                v = data.get(key)
                if isinstance(v, list):
                    return [x for x in v if isinstance(x, dict)]
        raise ValueError(f"Unexpected Pump.fun list payload: {type(data)}")

    def collect_scan_batch(self, *, pages: int = 3, page_size: int = 150) -> list[NormalizedToken]:
        if self._settings.ingest_mode == "fixture":
            raw = self.fetch_fixture_coins()
            return [NormalizedToken.from_payload(x) for x in raw]

        merged: dict[str, dict[str, Any]] = {}
        for page in range(pages):
            offset = page * page_size
            for fetcher in (self.fetch_latest_coins, self.fetch_graduated_coins, self.fetch_live_coins):
                rows = fetcher(limit=page_size, offset=offset)
                for row in rows:
                    mint = str(row.get("mint") or row.get("mintAddress") or row.get("id") or "").strip()
                    if mint:
                        merged[mint] = row

        out: list[NormalizedToken] = []
        for row in merged.values():
            try:
                out.append(NormalizedToken.from_payload(row))
            except ValueError:
                continue
        return out


def normalize_many(rows: Iterable[dict[str, Any]]) -> list[NormalizedToken]:
    out: list[NormalizedToken] = []
    for row in rows:
        try:
            out.append(NormalizedToken.from_payload(row))
        except ValueError:
            continue
    return out
