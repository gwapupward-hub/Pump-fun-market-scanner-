# Pump.fun Market Intelligence Agent

Automated **analytics-only** pipeline that periodically pulls Pump.fun coin data from the public frontend API, stores structured snapshots in **Postgres**, flags likely rug patterns, classifies winners vs losers, and emits a **daily markdown report** (optionally LLM-augmented).

This repository does **not** submit transactions, does **not** build swaps, and does **not** buy or sell tokens.

## What it does

- **Ingestion service**: paginates `GET /coins` on `frontend-api-v3.pump.fun` (configurable), normalizes fields, and writes `tokens`, `token_snapshots`, `token_socials`, and optional `holder_snapshots` (via Solana JSON-RPC when configured).
- **Rug detection service**: emits `rug_events` using ATH drawdown heuristics, holder-concentration deltas (when RPC data exists), and coarse creator-history signals.
- **Winner classification service**: writes `tokens.classification` into the requested taxonomy.
- **Scoring service**: writes a compact `tokens.score` used for ranking and reporting.
- **Daily report service**: aggregates the UTC-day batch into `daily_market_reports` and `winner_patterns`.
- **AI summary layer**: optional OpenAI-compatible narrative over the structured metrics.
- **Scheduler**: APScheduler daily trigger (Docker `CMD`) plus a host-level `crontab` example.

## Quick start (Docker)

```bash
docker compose up --build
```

Postgres is available on `localhost:5432` with credentials from `docker-compose.yml`.

## Quick start (local Python)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# set DATABASE_URL, then:
pump-intel init-db
pump-intel run-job
```

Optional LLM support:

```bash
pip install -e ".[ai]"
```

## Configuration

See `.env.example` for supported environment variables. The only hard requirement is `DATABASE_URL`.

## Cron (24h)

- **In-container scheduler**: `pump-intel scheduler` runs daily at **00:07 UTC**.
- **Host cron example**: `deploy/crontab.example`.

## Architecture map

```text
Pump API (read-only) ──► ingestion ──► Postgres
                              │
                              ├──► rug_detection ──► rug_events
                              ├──► winner_classification / scoring ──► tokens
                              ├──► creator_reputation ──► creator_wallets
                              └──► daily_report + ai_summary ──► daily_market_reports
```

## Notes on data completeness

Pump.fun’s public API responses power most fields. Public trade endpoints are often unavailable without authenticated access; where trades are missing, `volume_24h_usd` and `buy_sell_ratio` are **snapshot-derived proxies** based on consecutive USD market cap deltas, and should be interpreted cautiously.

Holder concentration requires `SOLANA_RPC_URL` with sufficient rate limits (public RPCs frequently throttle).
