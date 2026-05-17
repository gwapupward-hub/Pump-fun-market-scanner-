from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------- DB -------------------------
    database_url: str = Field(
        ...,
        description="Postgres DSN, e.g. postgresql://user:pass@localhost:5432/pump_intel",
    )
    db_pool_min_size: int = Field(default=1, ge=0, le=50)
    db_pool_max_size: int = Field(default=8, ge=1, le=200)
    db_pool_timeout_s: float = Field(default=30.0, gt=0)

    # ----------------------- Pump API ---------------------
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

    # --------------------- Solana RPC ---------------------
    solana_rpc_url: str | None = Field(
        default=None,
        description="Optional Solana HTTP JSON-RPC for holder enrichment",
    )
    solana_holder_top_n: int = Field(default=20, ge=1, le=100)
    solana_rpc_concurrency: int = Field(default=4, ge=1, le=64)
    holder_enrichment_top_n: int = Field(
        default=500, ge=1, le=10_000,
        description="Cap on mints sent to Solana RPC per run (most-recently-active first).",
    )

    # ----------------------- HTTP -------------------------
    http_retry_attempts: int = Field(default=3, ge=1, le=10)
    http_retry_base_delay_s: float = Field(default=0.5, gt=0, le=10.0)

    # ----------------------- OpenAI -----------------------
    openai_api_key: str | None = None
    openai_base_url: str | None = Field(default=None, description="OpenAI-compatible API base")
    openai_model: str = Field(default="gpt-4o-mini")

    # --------------------- Heuristics ---------------------
    bonding_target_usd_mcap: float = Field(default=65_000.0, gt=0)
    snapshot_stale_seconds: int = Field(default=86_400, ge=60)
    snapshot_retention_days: int = Field(default=90, ge=1, le=3650)
    holder_retention_days: int = Field(default=180, ge=1, le=3650)
    report_retention_days: int = Field(default=365, ge=1, le=3650)

    # --------------------- Observability ------------------
    log_level: str = Field(default="INFO")
    log_format: Literal["json", "text"] = Field(default="json")

    # --------------------- Scheduler ----------------------
    scheduler_cron_hour: int = Field(default=0, ge=0, le=23)
    scheduler_cron_minute: int = Field(default=7, ge=0, le=59)

    # --------------------- Healthcheck --------------------
    healthcheck_max_age_hours: int = Field(
        default=36, ge=1, le=720,
        description="Healthcheck fails if no daily_market_reports row newer than this.",
    )

    @property
    def snapshot_interval(self) -> timedelta:
        return timedelta(seconds=self.snapshot_stale_seconds)

    @field_validator("database_url")
    @classmethod
    def _validate_db_url(cls, v: str) -> str:
        if not v.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
            raise ValueError(
                "database_url must be a Postgres DSN starting with postgresql:// or postgres://"
            )
        return v

    @field_validator("pump_api_base")
    @classmethod
    def _validate_pump_base(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("pump_api_base must include an http(s) scheme")
        return v.rstrip("/")

    @field_validator("solana_rpc_url")
    @classmethod
    def _validate_solana_url(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not v.startswith(("http://", "https://")):
            raise ValueError("solana_rpc_url must include an http(s) scheme")
        return v

    @field_validator("openai_api_key", "openai_base_url", mode="before")
    @classmethod
    def _coerce_blank_openai_strings(cls, v: object) -> object:
        # docker-compose interpolates unset vars as empty strings; OpenAI(base_url="")
        # fails at request time. Treat blank as unset.
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


@lru_cache
def get_settings() -> Settings:
    # pydantic-settings reads `database_url` and friends from env / .env.
    return Settings()  # type: ignore[call-arg]
