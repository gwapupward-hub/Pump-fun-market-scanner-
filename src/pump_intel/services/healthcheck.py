from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pump_intel.config import get_settings
from pump_intel.db import fetch_one_dict, transaction

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class HealthResult:
    ok: bool
    db_ok: bool
    last_report_age_hours: float | None
    detail: str

    def summary(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "db_ok": self.db_ok,
            "last_report_age_hours": self.last_report_age_hours,
            "detail": self.detail,
        }


def run_healthcheck() -> HealthResult:
    """Probe DB connectivity and the freshness of the last daily report."""
    settings = get_settings()
    try:
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            row = fetch_one_dict(
                conn,
                "SELECT generated_at FROM daily_market_reports ORDER BY generated_at DESC LIMIT 1",
            )
    except Exception as exc:
        return HealthResult(
            ok=False, db_ok=False, last_report_age_hours=None, detail=f"db error: {exc!r}"
        )

    if row is None:
        # First run / fresh DB — DB up but nothing scheduled yet. Treat as OK.
        return HealthResult(ok=True, db_ok=True, last_report_age_hours=None, detail="no reports yet")

    generated_at = row["generated_at"]
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    age = datetime.now(tz=UTC) - generated_at
    age_hours = age.total_seconds() / 3600.0
    if age > timedelta(hours=settings.healthcheck_max_age_hours):
        return HealthResult(
            ok=False,
            db_ok=True,
            last_report_age_hours=age_hours,
            detail=(
                f"last report is {age_hours:.1f}h old "
                f"(threshold {settings.healthcheck_max_age_hours}h)"
            ),
        )
    return HealthResult(ok=True, db_ok=True, last_report_age_hours=age_hours, detail="ok")
