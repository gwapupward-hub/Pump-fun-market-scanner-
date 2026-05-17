from __future__ import annotations

import argparse

from dotenv import load_dotenv

from pump_intel.config import Settings
from pump_intel.db.connection import connect, migrate
from pump_intel.run_daily import main as run_daily_main


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Pump.fun market intelligence (analytics only).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run-daily", help="Ingest, score, persist, and generate the daily report.")
    p_run.set_defaults(func=lambda _: run_daily_main())

    p_mig = sub.add_parser("migrate-db", help="Apply SQL schema to Postgres.")
    p_mig.set_defaults(func=lambda args: _migrate())

    args = parser.parse_args()
    args.func(args)


def _migrate() -> None:
    settings = Settings()
    conn = connect(settings.database_url)
    try:
        migrate(conn)
        conn.commit()
        print("migrate-db: ok")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
