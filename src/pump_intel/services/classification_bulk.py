"""Set-based classifier — collapses thousands of per-mint round-trips into one CTE."""
from __future__ import annotations

import logging

import psycopg

from pump_intel.db import execute, fetch_all_dict

log = logging.getLogger(__name__)


WINNER_LABELS = ("graduated_winner", "viral_winner", "bonding_winner", "micro_winner")


def reclassify_recent_mints(conn: psycopg.Connection, *, lookback_hours: int = 72) -> dict[str, int]:
    """Recompute `tokens.classification` for every mint that was snapshotted recently.

    Implements the same logic as `classify_token` but as a single bulk
    SQL statement. Returns counts per label for observability.
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
                ts.raw_coin
            FROM token_snapshots ts
            JOIN active a ON a.mint = ts.mint
            ORDER BY ts.mint, ts.snapshot_at DESC
        ),
        rug_agg AS (
            SELECT mint,
                   BOOL_OR(severity = 'hard') AS has_hard,
                   BOOL_OR(severity = 'soft') AS has_soft
            FROM rug_events
            WHERE mint IN (SELECT mint FROM active)
            GROUP BY mint
        ),
        classified AS (
            SELECT
                l.mint,
                CASE
                    WHEN COALESCE(r.has_hard, FALSE) THEN 'hard_rug'
                    WHEN COALESCE(r.has_soft, FALSE) THEN 'soft_rug'
                    WHEN (l.raw_coin->>'last_trade_timestamp') ~ '^[0-9]+$'
                         AND to_timestamp((l.raw_coin->>'last_trade_timestamp')::bigint / 1000.0)
                             < NOW() - interval '10 days'
                        THEN 'abandoned'
                    WHEN COALESCE(l.migration_status,'') LIKE 'graduated%%' THEN 'graduated_winner'
                    WHEN COALESCE((l.raw_coin->>'reply_count')::int, 0) >= 2000
                         AND COALESCE(l.ath_market_cap_usd, 0) >= 250000 THEN 'viral_winner'
                    WHEN COALESCE(l.bonding_curve_progress_pct, 0) >= 85
                         AND COALESCE(l.ath_market_cap_usd, 0) >= 40000 THEN 'bonding_winner'
                    WHEN COALESCE(l.ath_market_cap_usd, 0) >= 25000 THEN 'micro_winner'
                    ELSE 'loser'
                END AS label
            FROM latest l
            LEFT JOIN rug_agg r ON r.mint = l.mint
        )
        UPDATE tokens t
        SET classification = c.label
        FROM classified c
        WHERE t.mint = c.mint
          AND (t.classification IS DISTINCT FROM c.label)
        RETURNING t.classification
    """
    rows = fetch_all_dict(conn, sql, (lookback_hours,))
    counts: dict[str, int] = {}
    for r in rows:
        label = str(r["classification"])
        counts[label] = counts.get(label, 0) + 1
    log.info("bulk reclassification", extra={"changed_rows": len(rows), "by_label": counts})
    return counts


def clear_classifications_for_unseen(conn: psycopg.Connection, *, lookback_hours: int = 720) -> int:
    """Optional housekeeping: NULL out classifications on mints not snapshotted in a long time.

    Not called by the daily job — provided for ad-hoc cleanup.
    """
    sql = """
        WITH cold AS (
            SELECT t.mint
            FROM tokens t
            LEFT JOIN LATERAL (
                SELECT 1 FROM token_snapshots ts
                WHERE ts.mint = t.mint
                  AND ts.snapshot_at >= NOW() - make_interval(hours => %s)
                LIMIT 1
            ) s ON TRUE
            WHERE s IS NULL AND t.classification IS NOT NULL
        )
        UPDATE tokens t SET classification = NULL FROM cold WHERE t.mint = cold.mint
    """
    execute(conn, sql, (lookback_hours,))
    return 0
