from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from pump_intel.db import connect, ensure_schema, fetch_all_dict
from pump_intel.ingestion.service import ingest_latest_coins
from pump_intel.services.ai_summary import generate_ai_markdown
from pump_intel.services.creator_reputation import recompute_creator_wallets
from pump_intel.services.daily_report import build_daily_report, persist_daily_report
from pump_intel.services.rug_detection import scan_recent_mints_for_rugs
from pump_intel.services.scoring import score_token, update_token_score
from pump_intel.services.trade_summary_writer import write_trade_summaries_for_recent
from pump_intel.services.winner_classification import classify_token, persist_classification

log = logging.getLogger(__name__)


async def run_daily_job() -> dict:
    ingest_stats = await ingest_latest_coins()
    report_date = datetime.now(tz=timezone.utc).date()

    with connect() as conn:
        ensure_schema(conn)
        rug_stats = scan_recent_mints_for_rugs(conn, lookback_hours=72)

        mint_rows = fetch_all_dict(
            conn,
            """
            SELECT DISTINCT mint
            FROM token_snapshots
            WHERE snapshot_at >= NOW() - interval '72 hours'
            """,
        )
        for row in mint_rows:
            mint = row["mint"]
            label = classify_token(conn, mint)
            persist_classification(conn, mint, label)
            sc = score_token(conn, mint)
            update_token_score(conn, mint, sc)

        recompute_creator_wallets(conn)
        trade_rows = write_trade_summaries_for_recent(conn, hours=24)

        report = build_daily_report(conn, report_date=report_date)
        ai = generate_ai_markdown(report["metrics"], report["structured_summary"])
        persist_daily_report(
            conn,
            report_date,
            report["metrics"],
            report["structured_summary"],
            ai["markdown"],
            ai["model"],
        )

    summary = {
        "report_date": str(report_date),
        "ingest": ingest_stats,
        "rug_scan": rug_stats,
        "classified_mints": len(mint_rows),
        "trade_summary_rows": trade_rows,
    }
    log.info("Daily job complete: %s", summary)
    return summary


def run_daily_job_sync() -> dict:
    return asyncio.run(run_daily_job())
