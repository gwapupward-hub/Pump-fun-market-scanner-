from __future__ import annotations

import argparse
import asyncio
import logging

from pump_intel.db import init_db
from pump_intel.jobs.daily_scan import run_daily_job


def main() -> None:
    parser = argparse.ArgumentParser(description="Pump.fun market intelligence (analytics only).")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-db", help="Create tables in Postgres if missing.")
    p_init.set_defaults(func=_cmd_init_db)

    p_run = sub.add_parser("run-job", help="Run ingestion + analytics pipeline once.")
    p_run.set_defaults(func=_cmd_run_job)

    p_sched = sub.add_parser("scheduler", help="Run APScheduler cron (default: daily 00:07 UTC).")
    p_sched.set_defaults(func=_cmd_scheduler)

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args.func(args)


def _cmd_init_db(_args: argparse.Namespace) -> None:
    init_db()


def _cmd_run_job(_args: argparse.Namespace) -> None:
    asyncio.run(run_daily_job())


def _cmd_scheduler(_args: argparse.Namespace) -> None:
    from pump_intel.scheduler import run_forever

    run_forever()


if __name__ == "__main__":
    main()
