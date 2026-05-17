from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(
        default="postgresql://pumpintel:pumpintel@localhost:5432/pumpintel",
        alias="DATABASE_URL",
    )

    pump_fun_origin: str = Field(default="https://pump.fun", alias="PUMP_FUN_ORIGIN")
    pump_fun_frontend_base: str = Field(
        default="https://frontend-api-v3.pump.fun",
        alias="PUMP_FUN_FRONTEND_BASE",
    )
    pump_fun_advanced_base: str = Field(
        default="https://advanced-api-v2.pump.fun",
        alias="PUMP_FUN_ADVANCED_BASE",
    )
    pump_fun_bearer_token: str | None = Field(default=None, alias="PUMP_FUN_BEARER_TOKEN")

    ingest_page_size: int = Field(default=100, ge=1, le=500, alias="INGEST_PAGE_SIZE")
    ingest_max_pages: int = Field(default=50, ge=1, le=500, alias="INGEST_MAX_PAGES")
    enrich_trades_top_n: int = Field(default=150, ge=0, le=5000, alias="ENRICH_TRADES_TOP_N")
    sol_usd_fallback: float = Field(default=165.0, alias="SOL_USD_FALLBACK")
    bonding_target_sol: float = Field(default=85.0, alias="BONDING_TARGET_SOL")
    bonding_fallback_usd_mcap: float = Field(default=69_000.0, alias="BONDING_FALLBACK_USD_MCAP")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    ai_summary_enabled: bool = Field(default=True, alias="AI_SUMMARY_ENABLED")

    reports_dir: Path = Field(default=Path("./reports"), alias="REPORTS_DIR")


def get_settings() -> Settings:
    return Settings()
