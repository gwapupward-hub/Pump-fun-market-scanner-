from __future__ import annotations

from typing import Any

from pump_intel.config import Settings
from pump_intel.ingestion.normalize import normalize_coin
from pump_intel.ingestion.pump_client import PumpFunClient


class IngestionService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.client = PumpFunClient(self.settings)

    def close(self) -> None:
        self.client.close()

    def collect_coins(self) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for coin in self.client.fetch_currently_live():
            merged[str(coin["mint"])] = coin
        offset = 0
        for _ in range(self.settings.ingest_max_pages):
            page = self.client.fetch_coins_page(offset, self.settings.ingest_page_size)
            if not page:
                break
            for coin in page:
                merged[str(coin["mint"])] = coin
            offset += len(page)
            if len(page) < self.settings.ingest_page_size:
                break
        return list(merged.values())

    def normalize_all(self, raw_coins: list[dict[str, Any]]) -> list[Any]:
        return [normalize_coin(c, self.settings) for c in raw_coins]
