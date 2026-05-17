# Pump.fun Market Intelligence Agent

Automated **analytics-only** pipeline that periodically ingests Pump.fun-style token payloads, persists structured history in **PostgreSQL**, classifies outcomes (winners vs rugs vs abandoned), detects rug-like structural signals, and writes a **daily market report** with an optional **LLM-generated markdown** narrative.

This project **does not** submit transactions, sign messages, or trade. It is market intelligence only.

## Architecture

| Module | Role |
|--------|------|
| `pump_intel/clients/pump_client.py` | HTTP (or fixture) ingestion from Pump.fun-compatible JSON APIs |
| `pump_intel/services/ingestion_service.py` | Normalizes rows into `tokens`, `token_snapshots`, `token_socials`, `holder_snapshots`, `trade_summaries` |
| `pump_intel/services/rug_detection_service.py` | Emits `rug_events` (dev sell estimate, ATH drawdowns, holder dumps, creator history, missing socials) |
| `pump_intel/services/winner_classification_service.py` | Labels each token (`loser`, `micro_winner`, `bonding_winner`, `graduated_winner`, `viral_winner`, `soft_rug`, `hard_rug`, `abandoned`) |
| `pump_intel/services/scoring_service.py` | `intel_score` (0–100) for ranking in reports |
| `pump_intel/services/creator_intel.py` | Rolls up `creator_wallets` reputation fields after each run |
| `pump_intel/services/daily_report_service.py` | Builds `daily_market_reports` + `winner_patterns` aggregates |
| `pump_intel/services/ai_summary_service.py` | OpenAI markdown brief when `OPENAI_API_KEY` is set; deterministic fallback otherwise |
| `pump_intel/pipeline.py` | Orchestrates one full scan cycle |
| `pump_intel/scheduler.py` | APScheduler **24-hour interval** job |
| `pump_intel/db/models.py` | SQLAlchemy models / table definitions |

## Database tables

- `tokens` — identity, creator FK, latest classification & score  
- `token_snapshots` — time series of market cap, ATH, bonding progress, migration, volume, holders, concentration, buy/sell ratio, drawdown  
- `creator_wallets` — aggregate creator stats & reputation score  
- `token_socials` — Twitter / Telegram / website URLs, X verification flags, presence flags  
- `holder_snapshots` — holder concentration snapshots  
- `trade_summaries` — rolling window placeholders (enrich from trades API in your deployment)  
- `rug_events` — structured rug signals with JSON evidence  
- `daily_market_reports` — JSON stats + `ai_markdown` narrative  
- `winner_patterns` — name themes & ticker suffix patterns linked to each report  

On startup the agent calls `create_all` (no separate migration runner) — add Alembic if you need versioned migrations in production.

## Configuration

Environment variables (see `.env.example`):

- `DATABASE_URL` — SQLAlchemy URL (Postgres recommended: `postgresql+psycopg://…`)  
- `PUMP_INGEST_SOURCE` — `http` (live API) or `fixture` (local JSON for tests / air-gapped demos)  
- `PUMP_INGEST_FIXTURE_PATH` — path to JSON array when using `fixture`  
- `PUMP_API_BASE` — override API host if Pump.fun changes edge URLs  
- `PUMP_API_BEARER` — optional JWT when your environment requires authenticated reads  
- `PUMP_SCAN_COIN_LIMIT` — max distinct mints per run  
- `AI_SUMMARY_ENABLED` / `OPENAI_API_KEY` / `OPENAI_MODEL` — AI markdown layer  

**Note:** Pump.fun endpoints are often Cloudflare-protected. If `http` mode returns empty data, use `fixture` mode, inject a valid `PUMP_API_BEARER`, or terminate TLS from a trusted browser session per your security policy.

## Commands

```bash
pip install -e ".[dev]"
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/pump_intel
python3 -m pump_intel.cli run-once          # single cycle
python3 -m pump_intel.cli serve-scheduler   # 24h interval loop
```

## Docker Compose

```bash
docker compose up --build
```

Postgres listens on `localhost:5432`; the `intel` service runs the scheduler against the `db` hostname.

## Cron (host)

See `crontab.example` for a daily `run-once` entry you can install with `crontab -e`.

## Tests

```bash
python3 -m pytest
```

Tests use in-memory SQLite plus `fixtures/sample_coins.json` (no network).

## Legal / risk

Meme-coin markets are extremely volatile. Heuristic labels (`hard_rug`, `winner`, etc.) are **statistical opinions** derived from incomplete public data, not ground truth. This software is for research and internal analytics only.
