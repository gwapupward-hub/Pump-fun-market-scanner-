from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from pump_intel.db import transaction
from pump_intel.ingestion.service import ingest_latest_coins
from pump_intel.logging import new_correlation_id
from pump_intel.services.ai_summary import generate_ai_markdown
from pump_intel.services.classification_bulk import reclassify_recent_mints
from pump_intel.services.creator_reputation import recompute_creator_wallets
from pump_intel.services.daily_report import build_daily_report, persist_daily_report
from pump_intel.services.retention import prune_old_data
from pump_intel.services.rug_detection import scan_recent_mints_for_rugs
from pump_intel.services.scoring_bulk import rescore_recent_mints
from pump_intel.services.trade_summary_writer import write_trade_summaries_for_recent

log = logging.getLogger(__name__)


async def run_daily_job() -> dict:
    """End-to-end daily pipeline: ingest → analytics → report → retention."""
    cid = new_correlation_id()
    log.info("daily job starting", extra={"correlation_id": cid})

    ingest_stats = await ingest_latest_coins()
    report_date = datetime.now(tz=UTC).date()

    with transaction() as conn:
        rug_stats = scan_recent_mints_for_rugs(conn, lookback_hours=72)
        reclass_counts = reclassify_recent_mints(conn, lookback_hours=72)
        rescored = rescore_recent_mints(conn, lookback_hours=72)
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

    with transaction() as conn:
        prune_stats = prune_old_data(conn)

    summary = {
        "report_date": str(report_date),
        "ingest": ingest_stats,
        "rug_scan": rug_stats,
        "reclassified": reclass_counts,
        "rescored": rescored,
        "trade_summary_rows": trade_rows,
        "pruned": prune_stats,
        "ai_model": ai["model"],
    }
    log.info("daily job complete", extra=summary)
    return summary


def run_daily_job_sync() -> dict:
    return asyncio.run(run_daily_job())
