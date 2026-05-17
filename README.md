# Pump.fun market intelligence

Analytics-only agent: ingests Pump.fun coin listings, scores tokens, flags rug-like behavior, stores structured history in Postgres, and emits daily markdown reports (optional OpenAI narrative).

## Quick start

1. Copy `.env.example` to `.env` and set `DATABASE_URL` (and optional `OPENAI_API_KEY`, `PUMP_FUN_BEARER_TOKEN` for richer trade/holder endpoints).
2. `pip install -e .`
3. `python3 -m pump_intel.cli migrate-db`
4. `python3 -m pump_intel.run_daily` (or `docker compose up` for Postgres + `scheduler` using `crontab`).

This project does **not** execute trades.
