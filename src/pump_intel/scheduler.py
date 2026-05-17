from __future__ import annotations

import asyncio
import logging
import signal

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from pump_intel.config import get_settings
from pump_intel.jobs.daily_scan import run_daily_job
from pump_intel.logging import configure_logging

log = logging.getLogger(__name__)


def _run_job() -> None:
    try:
        asyncio.run(run_daily_job())
    except Exception:
        log.exception("daily job raised; scheduler will continue with next tick")


def run_forever() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format)

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        _run_job,
        CronTrigger(hour=settings.scheduler_cron_hour, minute=settings.scheduler_cron_minute),
        id="pump_intel_daily",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60 * 30,
    )

    def _graceful_stop(*_: object) -> None:
        log.info("received termination signal; shutting scheduler down")
        scheduler.shutdown(wait=False)

    signal.signal(signal.SIGTERM, _graceful_stop)
    signal.signal(signal.SIGINT, _graceful_stop)

    log.info(
        "scheduler started",
        extra={
            "cron_hour": settings.scheduler_cron_hour,
            "cron_minute": settings.scheduler_cron_minute,
        },
    )
    scheduler.start()
