from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

from pump_intel.clients.pumpfun import PumpFunClient
from pump_intel.config import get_settings
from pump_intel.db import repo
from pump_intel.db.init_db import apply_schema
from pump_intel.db.session import connect
from pump_intel.services.ai_summary import generate_ai_markdown
from pump_intel.services.daily_report import analyze_and_update_tokens, build_structured_report, build_winner_pattern_rows
from pump_intel.services.ingestion import ingest_tokens


def cmd_init_db() -> None:
    settings = get_settings()
    apply_schema(settings.database_url)
    print("Database schema applied.")


def cmd_run_daily() -> int:
    settings = get_settings()
    client = PumpFunClient(settings)

    started = datetime.now(timezone.utc)
    batch = client.collect_scan_batch(pages=3, page_size=150)

    with connect(settings.database_url) as conn:
        scanned = ingest_tokens(conn, batch)
        analyze_and_update_tokens(conn, since=started - timedelta(seconds=30))

        report_date = started.date()
        structured = build_structured_report(conn, report_date=report_date, coins_scanned=scanned)
        md = generate_ai_markdown(structured, settings)
        structured["final_market_assessment"] = (
            "See markdown narrative. Structured aggregates are intended for dashboards and follow-up research."
        )

        report_id = repo.insert_daily_report(conn, report_date, scanned, structured, md)
        repo.replace_winner_patterns(conn, report_id, build_winner_pattern_rows(structured))

    print(f"Daily run complete. scanned={scanned} report_date={report_date}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pump-intel", description="Pump.fun market intelligence (analytics only).")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="Apply Postgres schema from pump_intel/db/schema.sql")
    sub.add_parser("run-daily", help="Ingest a batch, analyze, and write the daily report")

    return p


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "init-db":
        cmd_init_db()
        return 0
    if args.cmd == "run-daily":
        return cmd_run_daily()

    parser.error(f"Unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
