from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(
        default="postgresql://pumpintel:pumpintel@localhost:5432/pumpintel",
        alias="DATABASE_URL",
    )

    pumpfun_api_base: str = Field(default="https://frontend-api-v3.pump.fun", alias="PUMPFUN_API_BASE")
    pumpfun_jwt: str | None = Field(default=None, alias="PUMPFUN_JWT")
    pumpfun_timeout_s: float = Field(default=30.0, alias="PUMPFUN_TIMEOUT_S")

    ingest_mode: Literal["live", "fixture"] = Field(default="live", alias="PUMPFUN_INGEST_MODE")
    pumpfun_fixture_path: Path | None = Field(default=None, alias="PUMPFUN_FIXTURE_PATH")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    ai_model: str = Field(default="gpt-4o-mini", alias="AI_MODEL")

    http_user_agent: str = Field(
        default="PumpIntelAnalytics/0.1 (+https://example.invalid; analytics-only)",
        alias="HTTP_USER_AGENT",
    )

    report_timezone: str = Field(default="UTC", alias="REPORT_TIMEZONE")


def get_settings() -> Settings:
    return Settings()
