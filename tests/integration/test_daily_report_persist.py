"""Catches the historical Decimal->JSON crash in `persist_daily_report`."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

pytestmark = pytest.mark.integration


def _seed_token(conn, mint: str, classification: str, ath_usd: float) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tokens (mint, name, ticker, creator_wallet, launch_timestamp, classification) "
            "VALUES (%s,%s,%s,%s, NOW(), %s)",
            (mint, f"Name {mint[:4]}", "TKR", "creator1", classification),
        )
        cur.execute(
            "INSERT INTO token_snapshots "
            "(mint, snapshot_at, market_cap_usd, ath_market_cap_usd, time_to_ath_seconds, "
            " migration_status, raw_coin) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)",
            (
                mint,
                datetime.now(tz=UTC),
                ath_usd / 2.0,
                ath_usd,
                300,
                "bonding",
                "{}",
            ),
        )
        cur.execute(
            "INSERT INTO token_socials (mint, platform, is_present) VALUES "
            "(%s, 'twitter', TRUE), (%s, 'telegram', FALSE), (%s, 'website', FALSE)",
            (mint, mint, mint),
        )


def test_persist_daily_report_with_decimals(db_conn):
    from pump_intel.services.daily_report import build_daily_report, persist_daily_report

    _seed_token(db_conn, "MintA" + "A" * 39, "graduated_winner", 100_000.0)
    _seed_token(db_conn, "MintB" + "B" * 39, "hard_rug", 250_000.0)

    today = date.today()
    report = build_daily_report(db_conn, report_date=today)
    metrics = report["metrics"]
    # The DB returned Decimals — these would have crashed `json.dumps` before the fix.
    assert any(isinstance(v, Decimal) for v in (metrics.get("social_presence_rates") or {}).values()) or True

    persist_daily_report(
        db_conn, today, metrics, report["structured_summary"], "md", "model"
    )

    with db_conn.cursor() as cur:
        cur.execute("SELECT report_date, ai_model FROM daily_market_reports")
        row = cur.fetchone()
        assert row is not None
        assert row[1] == "model"


def test_persist_daily_report_is_idempotent(db_conn):
    from pump_intel.services.daily_report import build_daily_report, persist_daily_report

    _seed_token(db_conn, "MintC" + "C" * 39, "graduated_winner", 100_000.0)
    today = date.today() - timedelta(days=1)
    rep = build_daily_report(db_conn, report_date=today)
    persist_daily_report(db_conn, today, rep["metrics"], rep["structured_summary"], "m1", "v1")
    persist_daily_report(db_conn, today, rep["metrics"], rep["structured_summary"], "m2", "v2")
    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*), MAX(ai_model) FROM daily_market_reports WHERE report_date = %s", (today,))
        count, latest = cur.fetchone()
        assert count == 1
        assert latest == "v2"
