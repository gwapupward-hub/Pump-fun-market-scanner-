"""Entry point for the 24h scan (invoked by cron or `python -m pump_intel.run_daily`)."""

from __future__ import annotations

from datetime import timezone

from dotenv import load_dotenv

from pump_intel.config import Settings
from pump_intel.db.connection import connect, migrate
from pump_intel.pipeline import run_pipeline
from pump_intel.reports.service import DailyReportService


def main() -> None:
    load_dotenv()
    settings = Settings()
    result = run_pipeline(settings)
    conn = connect(settings.database_url)
    try:
        migrate(conn)
        day = result.report_date.astimezone(timezone.utc).date()
        report = DailyReportService(settings).build(conn, day, result.coins_scanned)
        conn.commit()
        print(
            f"pump-intel: scanned={result.coins_scanned} "
            f"report_id={report.report_id} path={report.markdown_path}"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
