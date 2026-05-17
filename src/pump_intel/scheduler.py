from __future__ import annotations

import asyncio
import logging
import signal
import time
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from pump_intel.config import get_settings
from pump_intel.db import fetch_one_dict, transaction
from pump_intel.jobs.daily_scan import run_daily_job
from pump_intel.logging import configure_logging

log = logging.getLogger(__name__)


_JOB_RETRY_DELAYS_S = (60, 300, 900)  # 1m, 5m, 15m


def _run_job() -> None:
    """Run the daily job with a small in-process retry budget.

    A single transient HTTP/DB blip should not cost an entire day's report.
    On exhaustion we log and return; the scheduler will pick up at the next
    cron tick (and the healthcheck will eventually go red if the gap exceeds
    `HEALTHCHECK_MAX_AGE_HOURS`).
    """
    attempts = len(_JOB_RETRY_DELAYS_S) + 1
    for attempt in range(1, attempts + 1):
        try:
            asyncio.run(run_daily_job())
            return
        except Exception:
            if attempt >= attempts:
                log.exception(
                    "daily job exhausted %d attempts; will wait for next tick", attempts
                )
                return
            delay = _JOB_RETRY_DELAYS_S[attempt - 1]
            log.exception(
                "daily job attempt %d/%d failed; retrying in %ds", attempt, attempts, delay
            )
            time.sleep(delay)


def _last_report_age() -> timedelta | None:
    """Return age of the most recent daily report, or None if none exists / DB unreachable."""
    try:
        with transaction() as conn:
            row = fetch_one_dict(
                conn,
                "SELECT generated_at FROM daily_market_reports "
                "ORDER BY generated_at DESC LIMIT 1",
            )
    except Exception:
        log.warning("could not query last report age at startup; skipping catchup", exc_info=True)
        return None
    if row is None:
        return None
    generated_at = row["generated_at"]
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    return datetime.now(tz=UTC) - generated_at


def _should_run_at_startup() -> bool:
    """True when the last report is missing or older than a day."""
    age = _last_report_age()
    if age is None:
        return True
    return age > timedelta(hours=24)


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

    if _should_run_at_startup():
        # Fire ~30s after startup so the pool/DB are warm and we don't race
        # the container's own healthcheck `start_period`.
        scheduler.add_job(
            _run_job,
            DateTrigger(run_date=datetime.now(tz=UTC) + timedelta(seconds=30)),
            id="pump_intel_startup_catchup",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60 * 10,
        )
        log.info("scheduled startup catchup run (last report is stale or missing)")

    def _graceful_stop(*_: object) -> None:
        log.info("received termination signal; shutting scheduler down")
        # wait=True lets the active job finish writing. Pair with a generous
        # container `stop_grace_period` in docker-compose / orchestrator.
        scheduler.shutdown(wait=True)

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
