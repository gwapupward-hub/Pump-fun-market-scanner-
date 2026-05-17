from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/pump_intel",
        validation_alias=AliasChoices("DATABASE_URL", "PUMP_DATABASE_URL"),
        description="SQLAlchemy URL for Postgres",
    )

    pump_api_base: str = Field(
        default="https://frontend-api-v3.pump.fun",
        validation_alias=AliasChoices("PUMP_API_BASE", "PUMP_FUN_API_BASE"),
        description="Pump.fun HTTP API base (no trailing slash)",
    )
    pump_api_bearer: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PUMP_API_BEARER", "PUMP_FUN_API_BEARER"),
        description="Optional Bearer token if your deployment requires JWT",
    )
    pump_http_timeout_s: float = 30.0
    pump_origin: str = "https://pump.fun"
    pump_referer: str = "https://pump.fun/"

    ingest_source: str = Field(
        default="http",
        validation_alias=AliasChoices("PUMP_INGEST_SOURCE", "INGEST_SOURCE"),
        description="http | fixture — fixture reads local JSON for dev/CI",
    )
    ingest_fixture_path: str = Field(
        default="fixtures/sample_coins.json",
        validation_alias=AliasChoices("PUMP_INGEST_FIXTURE_PATH", "INGEST_FIXTURE_PATH"),
    )

    scan_coin_limit: int = Field(
        default=200,
        ge=1,
        le=5000,
        validation_alias=AliasChoices("PUMP_SCAN_COIN_LIMIT", "SCAN_COIN_LIMIT"),
    )
    openai_api_key: str | None = Field(default=None, validation_alias=AliasChoices("OPENAI_API_KEY"))
    openai_model: str = Field(default="gpt-4o-mini", validation_alias=AliasChoices("OPENAI_MODEL"))
    ai_summary_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("AI_SUMMARY_ENABLED", "PUMP_AI_SUMMARY_ENABLED"),
    )

    log_level: str = "INFO"


def get_settings() -> Settings:
    return Settings()
