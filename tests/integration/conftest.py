"""Integration tests that need a live Postgres.

Prefers `PUMP_INTEL_TEST_DATABASE_URL` (a DSN to a Postgres the suite may
freely truncate). Falls back to `testcontainers`+Docker. Skips when neither is
available.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _apply_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    command.upgrade(cfg, "head")


def _reset_settings_cache() -> None:
    from pump_intel.config import get_settings

    get_settings.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def _migrate():
    explicit = os.environ.get("PUMP_INTEL_TEST_DATABASE_URL")
    if explicit:
        os.environ["DATABASE_URL"] = explicit
        _reset_settings_cache()
        _apply_migrations()
        yield
        return

    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:  # pragma: no cover
        pytest.skip("testcontainers not installed and no PUMP_INTEL_TEST_DATABASE_URL set")

    container = PostgresContainer("postgres:16-alpine")
    try:
        container.start()
    except Exception as exc:  # pragma: no cover — environment-dependent
        pytest.skip(f"could not start postgres container: {exc!r}")

    try:
        url = container.get_connection_url()
        plain = url.replace("postgresql+psycopg2://", "postgresql://").replace(
            "postgresql+psycopg://", "postgresql://"
        )
        os.environ["DATABASE_URL"] = plain
        _reset_settings_cache()
        _apply_migrations()
        yield
    finally:
        container.stop()


@pytest.fixture(autouse=True)
def _clean_tables(_migrate):
    """Truncate volatile tables between integration tests."""
    from pump_intel.db import transaction

    with transaction() as conn, conn.cursor() as cur:
        cur.execute(
            "TRUNCATE winner_patterns, daily_market_reports, rug_events, "
            "trade_summaries, holder_snapshots, token_socials, token_snapshots, "
            "tokens, creator_wallets RESTART IDENTITY CASCADE"
        )
    yield


@pytest.fixture()
def db_conn():
    from pump_intel.db import transaction

    with transaction() as conn:
        yield conn
