"""Set-based scorer — single UPDATE replaces N+1 per-mint scoring queries."""
from __future__ import annotations

import logging

import psycopg

log = logging.getLogger(__name__)


def rescore_recent_mints(conn: psycopg.Connection, *, lookback_hours: int = 72) -> int:
    """Recompute `tokens.score` for every mint snapshotted in the lookback window.

    The arithmetic mirrors `pump_intel.services.scoring.score_token` but folds
    all the per-mint queries into a single CTE that scans:
      - the most recent snapshot per active mint,
      - aggregated rug event counts per severity,
      - parsed last-trade timestamps from raw_coin JSON.

    Returns the number of rows updated.
    """
    sql = """
        WITH active AS (
            SELECT DISTINCT mint
            FROM token_snapshots
            WHERE snapshot_at >= NOW() - make_interval(hours => %s)
        ),
        latest AS (
            SELECT DISTINCT ON (ts.mint)
                ts.mint,
                ts.market_cap_usd,
                ts.ath_market_cap_usd,
                ts.migration_status,
                ts.bonding_curve_progress_pct,
                ts.volume_24h_usd,
                ts.buy_sell_ratio,
                ts.top_holder_concentration_pct,
                ts.raw_coin
            FROM token_snapshots ts
            JOIN active a ON a.mint = ts.mint
            ORDER BY ts.mint, ts.snapshot_at DESC
        ),
        rug_agg AS (
            SELECT mint,
                   COUNT(*) FILTER (WHERE severity = 'hard') AS hard_n,
                   COUNT(*) FILTER (WHERE severity = 'soft') AS soft_n
            FROM rug_events
            WHERE mint IN (SELECT mint FROM active)
            GROUP BY mint
        ),
        scored AS (
            SELECT
                l.mint,
                GREATEST(0, LEAST(100,
                    20.0
                    + LEAST(30.0, COALESCE(l.ath_market_cap_usd, 0) / 250000.0 * 30.0)
                    + CASE WHEN COALESCE(l.migration_status,'') LIKE 'graduated%%' THEN 20.0 ELSE 0 END
                    + LEAST(10.0, COALESCE(l.bonding_curve_progress_pct, 0) / 10.0)
                    + LEAST(10.0, COALESCE(l.volume_24h_usd, 0) / 500000.0 * 10.0)
                    + CASE WHEN COALESCE(l.buy_sell_ratio, 0) > 1.0
                           THEN LEAST(5.0, (COALESCE(l.buy_sell_ratio, 0) - 1.0)) ELSE 0 END
                    - CASE
                        WHEN COALESCE(l.top_holder_concentration_pct, 0) > 40 THEN 15.0
                        WHEN COALESCE(l.top_holder_concentration_pct, 0) > 25 THEN 8.0
                        ELSE 0
                      END
                    - 25.0 * COALESCE(r.hard_n, 0)
                    - 8.0  * COALESCE(r.soft_n, 0)
                    + LEAST(10.0, COALESCE((l.raw_coin->>'reply_count')::numeric, 0) / 500.0 * 10.0)
                    - CASE
                        WHEN (l.raw_coin->>'last_trade_timestamp') ~ '^[0-9]+$'
                             AND to_timestamp((l.raw_coin->>'last_trade_timestamp')::bigint / 1000.0)
                                 < NOW() - interval '7 days'
                        THEN 15.0 ELSE 0
                      END
                ))::numeric(12,4) AS score
            FROM latest l
            LEFT JOIN rug_agg r ON r.mint = l.mint
        )
        UPDATE tokens t
        SET score = s.score
        FROM scored s
        WHERE t.mint = s.mint
          AND (t.score IS DISTINCT FROM s.score)
    """
    with conn.cursor() as cur:
        cur.execute(sql, (lookback_hours,))
        updated = cur.rowcount
    log.info("bulk rescore", extra={"changed_rows": updated})
    return updated
