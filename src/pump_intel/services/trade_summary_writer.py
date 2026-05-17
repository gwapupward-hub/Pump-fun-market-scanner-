from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pump_intel.db import executemany, fetch_all_dict


def write_trade_summaries_for_recent(conn, *, hours: int = 24) -> int:
    from psycopg.types.json import Json

    now = datetime.now(tz=timezone.utc)
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
    out = []
    for r in rows:
        out.append(
            (
                r["mint"],
                start,
                now,
                None,
                None,
                r.get("volume_24h_usd"),
                None,
                "mcap_delta_proxy",
                Json({"buy_sell_ratio": r.get("buy_sell_ratio")}),
            )
        )
    if not out:
        return 0
    executemany(
        conn,
        """
        INSERT INTO trade_summaries (
            mint, period_start, period_end,
            buys_count, sells_count, buy_volume_usd, sell_volume_usd,
            source, notes
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        out,
    )
    return len(out)
