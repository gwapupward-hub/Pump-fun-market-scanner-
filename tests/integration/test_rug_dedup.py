from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_persist_rug_events_dedups_within_2h(db_conn):
    from pump_intel.services.rug_detection import RugSignal, persist_rug_events

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tokens (mint, name, ticker, creator_wallet, launch_timestamp) "
            "VALUES ('m1', 'n', 't', 'c', NOW())"
        )

    sig = RugSignal(rug_kind="ath_drawdown_90pct", severity="hard", evidence={"x": 1})
    assert persist_rug_events(db_conn, "m1", [sig]) == 1
    # Second call must be deduped.
    assert persist_rug_events(db_conn, "m1", [sig]) == 0

    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM rug_events WHERE mint = 'm1'")
        assert cur.fetchone()[0] == 1


def test_trade_summary_unique_constraint(db_conn):

    from pump_intel.services.trade_summary_writer import write_trade_summaries_for_recent

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tokens (mint, name, ticker, creator_wallet, launch_timestamp) "
            "VALUES ('m2', 'n', 't', 'c', NOW())"
        )
        cur.execute(
            "INSERT INTO token_snapshots (mint, snapshot_at, migration_status, volume_24h_usd) "
            "VALUES ('m2', NOW(), 'bonding', 1234.5)"
        )

    # Two runs must not create duplicate rows for the same window.
    n1 = write_trade_summaries_for_recent(db_conn, hours=24)
    n2 = write_trade_summaries_for_recent(db_conn, hours=24)
    assert n1 == 1 and n2 == 1

    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM trade_summaries WHERE mint = 'm2'")
        assert cur.fetchone()[0] == 1
