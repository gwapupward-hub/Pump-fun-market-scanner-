from __future__ import annotations

import logging
import signal
import sys

from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from pump_intel.logging_setup import configure_logging
from pump_intel.pipeline import run_daily_pipeline

log = logging.getLogger(__name__)


def run_forever() -> None:
    configure_logging()
    sched = BlockingScheduler()

    sched.add_job(
        _safe_run,
        IntervalTrigger(hours=24),
        id="pump_intel_daily",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
        next_run_time=datetime.now(tz=UTC) + timedelta(seconds=10),
    )

    def _shutdown(*_a: object) -> None:
        log.info("Shutting down scheduler")
        sched.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    log.info("Scheduler started — interval 24h (first run ~10s after startup)")
    sched.start()


def _safe_run() -> None:
    try:
        run_daily_pipeline()
    except Exception:
        log.exception("Daily pipeline failed")
