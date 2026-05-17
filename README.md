# Pump.fun Market Intelligence Agent

Automated **analytics-only** pipeline that ingests Pump.fun-style coin telemetry, stores structured time series in **Postgres**, detects rug-like stress patterns, classifies outcomes, and emits a **daily markdown** intelligence report (optionally LLM-augmented).

This repository **does not** submit transactions, sign trades, or interact with wallets for execution.

## Architecture

Modular Python services:

- **Data ingestion** (`pump_intel/services/ingestion.py`, `pump_intel/clients/pumpfun.py`): pulls coin batches (live API with JWT, or local fixtures), normalizes fields, upserts core tables, appends snapshots.
- **Scoring** (`pump_intel/services/scoring.py`): momentum, liquidity, holder distribution, social, and creator reputation subscores.
- **Rug detection** (`pump_intel/services/rug_detection.py`): drawdown-from-ATH, rapid post-ATH collapse window, dev-sell pressure, holder concentration shocks, creator history, missing socials.
- **Winner classification** (`pump_intel/services/winner_classification.py`): maps scores + rug signals + migration state into labels (`micro_winner`, `viral_winner`, `soft_rug`, …).
- **Daily report** (`pump_intel/services/daily_report.py`): aggregates winners/rugs, ATH stats, theme and ticker pattern mining, creator wallet insights, verification impact.
- **AI summary** (`pump_intel/services/ai_summary.py`): optional OpenAI-compatible chat completion over the structured JSON; otherwise a deterministic markdown template.
- **Database layer** (`pump_intel/db/`): SQL schema + repositories (`repo.py`) + `psycopg` session helper.
- **Scheduler** (`deploy/crontab`, `docker-compose.yml` `scheduler` service): `supercronic` runs `python -m pump_intel run-daily` every 24 hours.

## Database tables

Defined in `pump_intel/db/schema.sql`:

`tokens`, `token_snapshots`, `creator_wallets`, `token_socials`, `holder_snapshots`, `trade_summaries`, `rug_events`, `daily_market_reports`, `winner_patterns`.

## Configuration

See `.env.example`.

- **`PUMPFUN_JWT`**: Pump.fun Frontend API routes typically return data only with a valid Bearer JWT. Without it, live ingestion may fail; use fixtures for demos.
- **`PUMPFUN_INGEST_MODE=fixture`** + **`PUMPFUN_FIXTURE_PATH`**: deterministic local JSON (see `fixtures/sample_coins.json`).
- **`OPENAI_API_KEY`**: optional narrative layer for the markdown report.

## CLI

```bash
pip install -r requirements.txt
export DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
python -m pump_intel init-db
python -m pump_intel run-daily
```

Developer tests:

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## Docker

`docker compose up -d postgres` then `docker compose up agent` (or rely on the `scheduler` service for daily runs). The image entrypoint applies schema idempotently before executing the container command.

## Important limitations

- On-chain trade reconstruction and perfect creator-sell attribution require richer data than a single REST snapshot. The schema supports those metrics; enrich `NormalizedToken` mapping as your data sources allow.
- Classifications are **heuristic risk intelligence**, not investment advice.
