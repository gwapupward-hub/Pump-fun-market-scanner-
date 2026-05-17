# Pump.fun Market Intelligence Agent

Automated **analytics-only** pipeline that periodically pulls Pump.fun coin
data, stores structured snapshots in **Postgres**, flags likely rug patterns,
classifies winners vs losers, and emits a **daily markdown report**
(optionally LLM-augmented).

This repository does **not** submit transactions, does **not** build swaps,
and does **not** buy or sell tokens.

---

## Architecture

```text
Pump API (read-only) ──► PumpFunClient ──► ingestion.service ──► Postgres
                                                  │
                                                  ├── rug_detection      ─► rug_events
                                                  ├── classification_bulk─► tokens.classification
                                                  ├── scoring_bulk       ─► tokens.score
                                                  ├── creator_reputation ─► creator_wallets
                                                  ├── trade_summary      ─► trade_summaries
                                                  ├── daily_report+AI    ─► daily_market_reports / winner_patterns
                                                  └── retention prune    ─► (deletes stale rows)

Solana RPC (optional) ──► SolanaRPCClient ──► holder_snapshots
```

Every component is a stateless function over the shared connection pool. The
scheduler boots the daily pipeline at the configured UTC cron time; the same
pipeline is also invocable as `pump-intel run-job`.

### Modules

| Path                                          | Role                                          |
| --------------------------------------------- | --------------------------------------------- |
| `pump_intel.cli`                              | argparse entrypoint, structured logging boot  |
| `pump_intel.config`                           | pydantic settings with strict validators      |
| `pump_intel.db`                               | psycopg pool, `transaction()`, JSON helpers   |
| `pump_intel.http`                             | retry decorator (exp-backoff + jitter)        |
| `pump_intel.logging`                          | JSON formatter, per-run correlation IDs       |
| `pump_intel.clients.pump_api`                 | pooled httpx client for Pump.fun              |
| `pump_intel.clients.solana_rpc`               | bounded-concurrency JSON-RPC client           |
| `pump_intel.ingestion.{normalize,service}`    | API → typed rows → Postgres                   |
| `pump_intel.services.classification_bulk`     | set-based classifier (one CTE)                |
| `pump_intel.services.scoring_bulk`            | set-based scorer (one CTE)                    |
| `pump_intel.services.rug_detection`           | drawdown / holder-dump / dev-sell heuristics  |
| `pump_intel.services.creator_reputation`      | per-creator aggregates                        |
| `pump_intel.services.daily_report`            | markdown + structured metrics                 |
| `pump_intel.services.retention`               | snapshot / report pruning                     |
| `pump_intel.services.healthcheck`             | `pump-intel healthcheck` body                 |
| `pump_intel.jobs.daily_scan`                  | end-to-end orchestration                      |
| `pump_intel.scheduler`                        | APScheduler cron + graceful shutdown          |

---

## Quick start (Docker Compose)

```bash
cp .env.example .env             # then edit POSTGRES_PASSWORD to something real
docker compose --profile migrate run --rm migrate   # one-shot alembic upgrade head
docker compose up -d                                 # boots postgres + scheduler
docker compose exec pump-intel pump-intel healthcheck
docker compose logs -f pump-intel
```

The scheduler runs the full pipeline daily at `SCHEDULER_CRON_HOUR:SCHEDULER_CRON_MINUTE` UTC
(default 00:07). `AUTO_MIGRATE=true` in the container also runs `alembic upgrade head`
before launching the scheduler, so a single `docker compose up --build` from a fresh
clone is enough provided the env file is set.

Run an ad-hoc pipeline pass:

```bash
docker compose exec pump-intel pump-intel run-job
```

### Exposing Postgres for debugging

The compose file keeps Postgres on an internal network by default. To expose it on
`127.0.0.1:5432` for psql access:

```bash
docker compose --profile debug up -d
```

---

## Quick start (local Python)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,ai]"
cp .env.example .env             # set DATABASE_URL to your local Postgres
pump-intel init-db               # runs alembic upgrade head
pump-intel run-job
```

---

## CLI reference

| Command                          | What it does                                                                  |
| -------------------------------- | ----------------------------------------------------------------------------- |
| `pump-intel init-db`             | Run alembic migrations to head.                                               |
| `pump-intel run-job`             | Execute the full ingestion + analytics + report pipeline once.                |
| `pump-intel scheduler`           | Run as a long-lived process; APScheduler triggers daily.                      |
| `pump-intel healthcheck`         | DB ping + report-age probe. Exit 0 on healthy, 1 on degraded.                 |
| `pump-intel prune`               | Apply retention policy to historical tables. Flags override defaults.         |

All commands emit structured JSON logs by default (`LOG_FORMAT=text` switches to plain).

---

## Configuration

Every setting in `pump_intel/config.py` is overridable via env vars. See
`.env.example` for the full list. Hard requirement: `DATABASE_URL`.

Key knobs:

- `SNAPSHOT_STALE_SECONDS` (default 86400) — only insert a fresh snapshot for a
  mint if its previous snapshot is older than this. Caps write amplification.
- `HOLDER_ENRICHMENT_TOP_N` (default 500) — cap on Solana RPC requests per run.
- `SOLANA_RPC_CONCURRENCY` (default 4) — semaphore size for the RPC pool.
- `HTTP_RETRY_ATTEMPTS` / `HTTP_RETRY_BASE_DELAY_S` — applied to Pump + Solana clients.
- `SNAPSHOT_RETENTION_DAYS` / `HOLDER_RETENTION_DAYS` / `REPORT_RETENTION_DAYS` —
  consumed by `pump-intel prune` (also called at the end of every daily run).

### Secrets

The compose file fails fast if `POSTGRES_PASSWORD` is unset. For production,
either source `.env` from a secret store or pass each variable through Docker
secrets / your platform's secret manager.

---

## Migrations

Schema changes go through Alembic. Common operations:

```bash
# Apply all pending migrations
alembic upgrade head

# Generate a new revision (the project does not use SQLAlchemy models, so write SQL manually)
alembic revision -m "describe change"

# Inspect current head
alembic current
```

The runtime applies migrations from `migrations/versions/`. If you're upgrading
from v0.1.0 (which used the bundled `schema.sql`), run
`alembic stamp 0001_initial` once against the existing DB before
`alembic upgrade head`.

---

## Tests

```bash
pip install -e ".[dev]"
pytest -q tests/unit                 # no DB required
pytest -q -m integration tests/integration   # uses testcontainers (needs Docker)
```

CI runs lint (ruff) + type check (mypy) + unit + integration + a docker build.

---

## Operational notes

- **Single-flight**: the scheduler is configured with `max_instances=1` and
  `coalesce=True`. A long-running job will not be doubled up by the next tick;
  missed ticks are collapsed.
- **Health**: the container's `HEALTHCHECK` invokes `pump-intel healthcheck`,
  which probes the DB and asserts the most recent `daily_market_reports` row
  is fresher than `HEALTHCHECK_MAX_AGE_HOURS` (default 36).
- **Data persistence**: Postgres is backed by the named `pgdata` volume.
  `docker compose down` preserves it; use `docker compose down -v` only when
  you really mean to wipe.
- **Cron alternative**: `deploy/crontab.example` shows a host-side wrapper that
  uses `flock` to prevent overlapping runs.

---

## Data caveats

Pump.fun's public API powers most fields. Public trade endpoints are usually
unavailable without authenticated access; where trades are missing,
`volume_24h_usd` and `buy_sell_ratio` are **snapshot-derived proxies** based
on consecutive USD market-cap deltas and should be interpreted cautiously.

Holder concentration requires `SOLANA_RPC_URL` with sufficient rate limits
(public RPCs frequently throttle). Enrichment is capped to the top-N
recently-active mints to keep daily cost bounded.
