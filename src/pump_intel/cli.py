from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys

from pump_intel.db import init_db, transaction
from pump_intel.jobs.daily_scan import run_daily_job
from pump_intel.logging import configure_logging, new_correlation_id
from pump_intel.services.healthcheck import run_healthcheck
from pump_intel.services.retention import prune_old_data

log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Pump.fun market intelligence (analytics only).")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Run alembic migrations up to head.").set_defaults(func=_cmd_init_db)
    sub.add_parser("run-job", help="Run ingestion + analytics pipeline once.").set_defaults(func=_cmd_run_job)
    sub.add_parser("scheduler", help="Run APScheduler cron (daily, see config).").set_defaults(func=_cmd_scheduler)
    sub.add_parser("healthcheck", help="Probe DB + last report age; exit non-zero on failure.").set_defaults(func=_cmd_healthcheck)
    sub.add_parser("arena-poker", help="Run the arena.dev.fun poker bot loop.").set_defaults(func=_cmd_arena_poker)

    p_prune = sub.add_parser("prune", help="Apply retention policy to historical tables.")
    p_prune.add_argument("--snapshot-days", type=int, default=None)
    p_prune.add_argument("--holder-days", type=int, default=None)
    p_prune.add_argument("--report-days", type=int, default=None)
    p_prune.set_defaults(func=_cmd_prune)

    args = parser.parse_args()
    # Logging is configured straight from env vars so commands that don't touch
    # the DB (arena-poker) don't require DATABASE_URL to be set.
    configure_logging(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        fmt=os.environ.get("LOG_FORMAT", "json"),
    )
    new_correlation_id()
    return int(args.func(args) or 0)


def _cmd_init_db(_args: argparse.Namespace) -> int:
    init_db()
    log.info("init-db complete")
    return 0


def _cmd_run_job(_args: argparse.Namespace) -> int:
    summary = asyncio.run(run_daily_job())
    print(json.dumps(summary, default=str, indent=2))
    return 0


def _cmd_scheduler(_args: argparse.Namespace) -> int:
    from pump_intel.scheduler import run_forever

    run_forever()
    return 0


def _cmd_healthcheck(_args: argparse.Namespace) -> int:
    result = run_healthcheck()
    print(json.dumps(result.summary(), default=str))
    return 0 if result.ok else 1


def _cmd_arena_poker(_args: argparse.Namespace) -> int:
    from pump_intel.arena.bot import run_bot

    return asyncio.run(run_bot())


def _cmd_prune(args: argparse.Namespace) -> int:
    with transaction() as conn:
        stats = prune_old_data(
            conn,
            snapshot_days=args.snapshot_days,
            holder_days=args.holder_days,
            report_days=args.report_days,
        )
    print(json.dumps(stats, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
