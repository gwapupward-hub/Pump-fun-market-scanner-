-- Pump.fun Market Intelligence — core schema (analytics only; no trading)

CREATE TABLE IF NOT EXISTS tokens (
    id BIGSERIAL PRIMARY KEY,
    mint_address VARCHAR(128) NOT NULL UNIQUE,
    name TEXT NOT NULL,
    symbol VARCHAR(64) NOT NULL,
    creator_wallet VARCHAR(128) NOT NULL,
    launch_ts TIMESTAMPTZ NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS creator_wallets (
    id BIGSERIAL PRIMARY KEY,
    address VARCHAR(128) NOT NULL UNIQUE,
    tokens_created INT NOT NULL DEFAULT 0,
    rug_count INT NOT NULL DEFAULT 0,
    winner_count INT NOT NULL DEFAULT 0,
    reputation_score NUMERIC(12, 4) NOT NULL DEFAULT 0,
    flags JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS token_snapshots (
    id BIGSERIAL PRIMARY KEY,
    token_id BIGINT NOT NULL REFERENCES tokens (id) ON DELETE CASCADE,
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    market_cap_sol NUMERIC(24, 8),
    usd_market_cap NUMERIC(24, 8),
    ath_usd_mcap NUMERIC(24, 8),
    ath_ts TIMESTAMPTZ,
    time_to_ath_seconds INT,
    bonding_curve_progress NUMERIC(10, 6),
    migration_status VARCHAR(32) NOT NULL,
    volume_24h_usd NUMERIC(24, 8),
    holder_count INT,
    top_holder_concentration NUMERIC(10, 6),
    buy_sell_ratio NUMERIC(12, 6),
    classification VARCHAR(32) NOT NULL,
    intel_score NUMERIC(10, 4),
    raw_coin JSONB
);

CREATE INDEX IF NOT EXISTS idx_token_snapshots_token_time
    ON token_snapshots (token_id, snapshot_at DESC);

CREATE TABLE IF NOT EXISTS token_socials (
    id BIGSERIAL PRIMARY KEY,
    token_id BIGINT NOT NULL REFERENCES tokens (id) ON DELETE CASCADE,
    platform VARCHAR(32) NOT NULL,
    url TEXT,
    x_linked_username VARCHAR(256),
    x_verified_signal BOOLEAN,
    present BOOLEAN NOT NULL DEFAULT TRUE,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (token_id, platform)
);

CREATE TABLE IF NOT EXISTS holder_snapshots (
    id BIGSERIAL PRIMARY KEY,
    token_snapshot_id BIGINT NOT NULL REFERENCES token_snapshots (id) ON DELETE CASCADE,
    holder_rank INT NOT NULL,
    wallet_address VARCHAR(128),
    pct_supply NUMERIC(14, 8)
);

CREATE INDEX IF NOT EXISTS idx_holder_snapshots_snapshot
    ON holder_snapshots (token_snapshot_id);

CREATE TABLE IF NOT EXISTS trade_summaries (
    id BIGSERIAL PRIMARY KEY,
    token_snapshot_id BIGINT NOT NULL UNIQUE REFERENCES token_snapshots (id) ON DELETE CASCADE,
    buy_volume_usd NUMERIC(24, 8),
    sell_volume_usd NUMERIC(24, 8),
    trade_count INT,
    largest_sell_notional_usd NUMERIC(24, 8),
    dev_sell_detected BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS rug_events (
    id BIGSERIAL PRIMARY KEY,
    token_id BIGINT NOT NULL REFERENCES tokens (id) ON DELETE CASCADE,
    event_type VARCHAR(64) NOT NULL,
    severity VARCHAR(16) NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rug_events_token_time ON rug_events (token_id, detected_at DESC);

CREATE TABLE IF NOT EXISTS daily_market_reports (
    id BIGSERIAL PRIMARY KEY,
    report_date DATE NOT NULL UNIQUE,
    stats JSONB NOT NULL DEFAULT '{}'::jsonb,
    structured_markdown TEXT,
    ai_markdown TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS winner_patterns (
    id BIGSERIAL PRIMARY KEY,
    report_id BIGINT NOT NULL REFERENCES daily_market_reports (id) ON DELETE CASCADE,
    pattern_type VARCHAR(64) NOT NULL,
    pattern_value TEXT NOT NULL,
    occurrence_count INT NOT NULL DEFAULT 1,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_winner_patterns_report ON winner_patterns (report_id);
