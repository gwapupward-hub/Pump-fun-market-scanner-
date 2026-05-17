from __future__ import annotations

from datetime import timedelta
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(
        ...,
        description="Postgres DSN, e.g. postgresql://user:pass@localhost:5432/pump_intel",
    )
    pump_api_base: str = Field(
        default="https://frontend-api-v3.pump.fun",
        description="Pump.fun frontend API base URL",
    )
    pump_origin: str = Field(default="https://pump.fun", description="Origin header for Pump API")
    pump_user_agent: str = Field(default="PumpIntelAgent/1.0 (+analytics)")

    ingest_page_size: int = Field(default=100, ge=1, le=500)
    ingest_max_pages: int = Field(default=30, ge=1, le=500)
    ingest_sort: str = Field(default="last_trade_timestamp")
    ingest_order: str = Field(default="DESC")
    include_nsfw: bool = Field(default=False)

    solana_rpc_url: str | None = Field(
        default=None,
        description="Optional Solana HTTP JSON-RPC for holder enrichment",
    )
    solana_holder_top_n: int = Field(default=20, ge=1, le=100)

    openai_api_key: str | None = None
    openai_base_url: str | None = Field(default=None, description="OpenAI-compatible API base")
    openai_model: str = Field(default="gpt-4o-mini")

    # Heuristic: approximate USD market cap at which bonding completes (varies; used only when complete=false).
    bonding_target_usd_mcap: float = Field(default=65_000.0, gt=0)

    snapshot_stale_seconds: int = Field(default=86_400, ge=60)

    @property
    def snapshot_interval(self) -> timedelta:
        return timedelta(seconds=self.snapshot_stale_seconds)


@lru_cache
def get_settings() -> Settings:
    return Settings()
