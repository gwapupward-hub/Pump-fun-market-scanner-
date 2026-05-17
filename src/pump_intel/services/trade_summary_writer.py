from __future__ import annotations

from datetime import UTC, datetime, timedelta

import psycopg

from pump_intel.db import executemany, fetch_all_dict, jsonb


def write_trade_summaries_for_recent(conn: psycopg.Connection, *, hours: int = 24) -> int:
    """Roll up the latest snapshot per active mint into a `trade_summaries` row.

    `period_end` is bucketed to the top of the current UTC hour so multiple runs
    inside the same hour collide on the `(mint, period_start, period_end, source)`
    unique constraint (migration 0003) and upsert in place.
    """
    now = datetime.now(tz=UTC).replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(hours=hours)
    rows = fetch_all_dict(
        conn,
        """
        SELECT DISTINCT ON (mint)
            mint,
            snapshot_at,
            volume_24h_usd,
            buy_sell_ratio
        FROM token_snapshots
        WHERE snapshot_at >= %s
        ORDER BY mint, snapshot_at DESC
        """,
        (start,),
    )
    if not rows:
        return 0

    payload = [
        (
            r["mint"],
            start,
            now,
            None,
            None,
            r.get("volume_24h_usd"),
            None,
            "mcap_delta_proxy",
            jsonb({"buy_sell_ratio": r.get("buy_sell_ratio")}),
        )
        for r in rows
    ]
    executemany(
        conn,
        """
        INSERT INTO trade_summaries (
            mint, period_start, period_end,
            buys_count, sells_count, buy_volume_usd, sell_volume_usd,
            source, notes
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (mint, period_start, period_end, source) DO UPDATE SET
            buy_volume_usd = EXCLUDED.buy_volume_usd,
            notes = EXCLUDED.notes
        """,
        payload,
    )
    return len(payload)
