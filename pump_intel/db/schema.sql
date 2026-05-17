-- Pump.fun Market Intelligence — core schema (analytics only)

CREATE TABLE IF NOT EXISTS creator_wallets (
    id              BIGSERIAL PRIMARY KEY,
    address         TEXT NOT NULL UNIQUE,
    total_tokens    INTEGER NOT NULL DEFAULT 0,
    rug_count       INTEGER NOT NULL DEFAULT 0,
    graduate_count  INTEGER NOT NULL DEFAULT 0,
    reputation_score NUMERIC(8, 4) NOT NULL DEFAULT 0,
    risk_flags       JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tokens (
    id                      BIGSERIAL PRIMARY KEY,
    mint_address            TEXT NOT NULL UNIQUE,
    name                    TEXT NOT NULL,
    ticker                  TEXT NOT NULL,
    creator_wallet_id       BIGINT NOT NULL REFERENCES creator_wallets (id),
    launch_timestamp        TIMESTAMPTZ NOT NULL,
    market_cap_usd          NUMERIC(24, 6),
    ath_market_cap_usd      NUMERIC(24, 6),
    ath_reached_at          TIMESTAMPTZ,
    time_to_ath_seconds     INTEGER,
    bonding_curve_progress  NUMERIC(10, 6),
    migration_status        TEXT NOT NULL DEFAULT 'unknown',
    volume_24h_usd          NUMERIC(24, 6),
    holder_count            INTEGER,
    top_holder_concentration NUMERIC(10, 6),
    buy_sell_ratio          NUMERIC(16, 6),
    social_verified_x       BOOLEAN,
    has_website             BOOLEAN,
    has_telegram            BOOLEAN,
    classification          TEXT NOT NULL DEFAULT 'unclassified',
    score_total             NUMERIC(10, 4),
    last_ingested_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tokens_classification ON tokens (classification);
CREATE INDEX IF NOT EXISTS idx_tokens_launch ON tokens (launch_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_tokens_creator ON tokens (creator_wallet_id);

CREATE TABLE IF NOT EXISTS token_snapshots (
    id                      BIGSERIAL PRIMARY KEY,
    token_id                BIGINT NOT NULL REFERENCES tokens (id) ON DELETE CASCADE,
    captured_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    market_cap_usd          NUMERIC(24, 6),
    ath_market_cap_usd      NUMERIC(24, 6),
    bonding_curve_progress  NUMERIC(10, 6),
    migration_status        TEXT,
    volume_24h_usd          NUMERIC(24, 6),
    holder_count            INTEGER,
    top_holder_concentration NUMERIC(10, 6),
    buy_sell_ratio          NUMERIC(16, 6),
    dev_sell_fraction       NUMERIC(10, 6),
    drawdown_from_ath       NUMERIC(10, 6),
    drawdown_24h            NUMERIC(10, 6)
);

CREATE INDEX IF NOT EXISTS idx_token_snapshots_token_time ON token_snapshots (token_id, captured_at DESC);

CREATE TABLE IF NOT EXISTS token_socials (
    id              BIGSERIAL PRIMARY KEY,
    token_id        BIGINT NOT NULL REFERENCES tokens (id) ON DELETE CASCADE,
    platform        TEXT NOT NULL,
    url             TEXT,
    is_present      BOOLEAN NOT NULL DEFAULT FALSE,
    verified_x      BOOLEAN,
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (token_id, platform)
);

CREATE TABLE IF NOT EXISTS holder_snapshots (
    id                      BIGSERIAL PRIMARY KEY,
    token_id                BIGINT NOT NULL REFERENCES tokens (id) ON DELETE CASCADE,
    captured_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    holder_count            INTEGER,
    top_holder_concentration NUMERIC(10, 6),
    top10_concentration     NUMERIC(10, 6),
    extra                   JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_holder_snapshots_token_time ON holder_snapshots (token_id, captured_at DESC);

CREATE TABLE IF NOT EXISTS trade_summaries (
    id                  BIGSERIAL PRIMARY KEY,
    token_id            BIGINT NOT NULL REFERENCES tokens (id) ON DELETE CASCADE,
    window_start        TIMESTAMPTZ NOT NULL,
    window_end          TIMESTAMPTZ NOT NULL,
    volume_usd          NUMERIC(24, 6),
    buy_volume_usd    NUMERIC(24, 6),
    sell_volume_usd   NUMERIC(24, 6),
    buy_sell_ratio      NUMERIC(16, 6),
    creator_sold_usd    NUMERIC(24, 6),
    creator_sell_fraction NUMERIC(10, 6),
    large_dump_detected BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (token_id, window_start, window_end)
);

CREATE TABLE IF NOT EXISTS rug_events (
    id              BIGSERIAL PRIMARY KEY,
    token_id        BIGINT NOT NULL REFERENCES tokens (id) ON DELETE CASCADE,
    event_type      TEXT NOT NULL,
    severity        TEXT NOT NULL,
    details         JSONB NOT NULL DEFAULT '{}'::jsonb,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    bucket_date     DATE GENERATED ALWAYS AS ((detected_at AT TIME ZONE 'UTC')::date) STORED
);

CREATE UNIQUE INDEX IF NOT EXISTS rug_events_token_type_day
    ON rug_events (token_id, event_type, bucket_date);

CREATE TABLE IF NOT EXISTS daily_market_reports (
    id                  BIGSERIAL PRIMARY KEY,
    report_date         DATE NOT NULL UNIQUE,
    coins_scanned       INTEGER NOT NULL,
    structured_stats    JSONB NOT NULL,
    ai_markdown         TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS winner_patterns (
    id                      BIGSERIAL PRIMARY KEY,
    daily_market_report_id  BIGINT NOT NULL REFERENCES daily_market_reports (id) ON DELETE CASCADE,
    pattern_type            TEXT NOT NULL,
    pattern_value           TEXT NOT NULL,
    frequency               INTEGER NOT NULL,
    strength                NUMERIC(12, 6),
    evidence                JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (daily_market_report_id, pattern_type, pattern_value)
);
