"""Snapshot/holder/report retention pruning."""
from __future__ import annotations

import logging

import psycopg

from pump_intel.config import get_settings

log = logging.getLogger(__name__)


def prune_old_data(
    conn: psycopg.Connection,
    *,
    snapshot_days: int | None = None,
    holder_days: int | None = None,
    report_days: int | None = None,
    trade_summary_days: int | None = None,
) -> dict[str, int]:
    """Delete rows older than the configured retention windows. Returns row counts."""
    s = get_settings()
    snap_d = snapshot_days if snapshot_days is not None else s.snapshot_retention_days
    hold_d = holder_days if holder_days is not None else s.holder_retention_days
    rep_d = report_days if report_days is not None else s.report_retention_days
    trade_d = trade_summary_days if trade_summary_days is not None else s.snapshot_retention_days

    stats: dict[str, int] = {}
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM token_snapshots WHERE snapshot_at < NOW() - make_interval(days => %s)",
            (snap_d,),
        )
        stats["token_snapshots"] = cur.rowcount
        cur.execute(
            "DELETE FROM holder_snapshots WHERE snapshot_at < NOW() - make_interval(days => %s)",
            (hold_d,),
        )
        stats["holder_snapshots"] = cur.rowcount
        cur.execute(
            "DELETE FROM trade_summaries WHERE period_end < NOW() - make_interval(days => %s)",
            (trade_d,),
        )
        stats["trade_summaries"] = cur.rowcount
        cur.execute(
            "DELETE FROM rug_events WHERE detected_at < NOW() - make_interval(days => %s)",
            (snap_d,),
        )
        stats["rug_events"] = cur.rowcount
        cur.execute(
            "DELETE FROM daily_market_reports WHERE report_date < (CURRENT_DATE - make_interval(days => %s))",
            (rep_d,),
        )
        stats["daily_market_reports"] = cur.rowcount
        cur.execute(
            "DELETE FROM winner_patterns WHERE report_date < (CURRENT_DATE - make_interval(days => %s))",
            (rep_d,),
        )
        stats["winner_patterns"] = cur.rowcount
    log.info("retention pruning complete", extra=stats)
    return stats
