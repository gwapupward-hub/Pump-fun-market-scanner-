from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from pump_intel.jobs.daily_scan import run_daily_job

log = logging.getLogger(__name__)


def run_forever() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    def _job() -> None:
        asyncio.run(run_daily_job())

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(_job, CronTrigger(hour=0, minute=7), id="pump_intel_daily", replace_existing=True)
    log.info("Scheduler started: daily at 00:07 UTC")
    scheduler.start()
