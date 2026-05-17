"""CLI entrypoint for pump-intel."""

from __future__ import annotations

import argparse
import logging

from pump_intel.logging_setup import configure_logging


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="Pump.fun market intelligence (analytics only)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run-once", help="Run a single ingest + report cycle")
    p_run.set_defaults(func=_cmd_run_once)

    p_sch = sub.add_parser("serve-scheduler", help="Run APScheduler daily job")
    p_sch.set_defaults(func=_cmd_serve_scheduler)

    args = parser.parse_args()
    args.func()


def _cmd_run_once() -> None:
    from pump_intel.pipeline import run_daily_pipeline

    n = run_daily_pipeline()
    logging.getLogger(__name__).info("Processed %s tokens", n)


def _cmd_serve_scheduler() -> None:
    from pump_intel.scheduler import run_forever

    run_forever()


if __name__ == "__main__":
    main()
