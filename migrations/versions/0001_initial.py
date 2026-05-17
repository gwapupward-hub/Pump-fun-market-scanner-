"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from __future__ import annotations

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tokens (
            mint TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            ticker TEXT NOT NULL,
            creator_wallet TEXT NOT NULL,
            launch_timestamp TIMESTAMPTZ NOT NULL,
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            classification TEXT,
            score NUMERIC(12, 4),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_tokens_creator ON tokens (creator_wallet);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tokens_launch ON tokens (launch_timestamp DESC);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_snapshots (
            id BIGSERIAL PRIMARY KEY,
            mint TEXT NOT NULL REFERENCES tokens (mint) ON DELETE CASCADE,
            snapshot_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            market_cap_usd NUMERIC(24, 6),
            market_cap_sol NUMERIC(24, 8),
            ath_market_cap_usd NUMERIC(24, 6),
            ath_market_cap_sol NUMERIC(24, 8),
            ath_at TIMESTAMPTZ,
            time_to_ath_seconds INTEGER,
            bonding_curve_progress_pct NUMERIC(8, 4),
            migration_status TEXT NOT NULL,
            volume_24h_usd NUMERIC(24, 6),
            holder_count INTEGER,
            top_holder_concentration_pct NUMERIC(8, 4),
            buy_sell_ratio NUMERIC(16, 8),
            sol_price_usd NUMERIC(16, 8),
            raw_coin JSONB NOT NULL DEFAULT '{}'::jsonb
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_snapshots_mint_time "
        "ON token_snapshots (mint, snapshot_at DESC);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS creator_wallets (
            address TEXT PRIMARY KEY,
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            tokens_created INTEGER NOT NULL DEFAULT 0,
            soft_rug_count INTEGER NOT NULL DEFAULT 0,
            hard_rug_count INTEGER NOT NULL DEFAULT 0,
            abandoned_count INTEGER NOT NULL DEFAULT 0,
            winner_count INTEGER NOT NULL DEFAULT 0,
            reputation_score NUMERIC(12, 4) NOT NULL DEFAULT 0,
            notes JSONB NOT NULL DEFAULT '{}'::jsonb
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_socials (
            id BIGSERIAL PRIMARY KEY,
            mint TEXT NOT NULL REFERENCES tokens (mint) ON DELETE CASCADE,
            platform TEXT NOT NULL,
            url TEXT,
            is_present BOOLEAN NOT NULL DEFAULT FALSE,
            x_verified BOOLEAN,
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (mint, platform)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS holder_snapshots (
            id BIGSERIAL PRIMARY KEY,
            mint TEXT NOT NULL REFERENCES tokens (mint) ON DELETE CASCADE,
            snapshot_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            holder_count INTEGER,
            top1_holder_pct NUMERIC(8, 4),
            top5_holders_pct NUMERIC(8, 4),
            rpc_error TEXT
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_holder_snapshots_mint "
        "ON holder_snapshots (mint, snapshot_at DESC);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_summaries (
            id BIGSERIAL PRIMARY KEY,
            mint TEXT NOT NULL REFERENCES tokens (mint) ON DELETE CASCADE,
            period_start TIMESTAMPTZ NOT NULL,
            period_end TIMESTAMPTZ NOT NULL,
            buys_count INTEGER,
            sells_count INTEGER,
            buy_volume_usd NUMERIC(24, 6),
            sell_volume_usd NUMERIC(24, 6),
            source TEXT NOT NULL DEFAULT 'unknown',
            notes JSONB NOT NULL DEFAULT '{}'::jsonb
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_trade_summaries_mint "
        "ON trade_summaries (mint, period_end DESC);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS rug_events (
            id BIGSERIAL PRIMARY KEY,
            mint TEXT NOT NULL REFERENCES tokens (mint) ON DELETE CASCADE,
            detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            rug_kind TEXT NOT NULL,
            severity TEXT NOT NULL,
            evidence JSONB NOT NULL DEFAULT '{}'::jsonb
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_rug_events_mint "
        "ON rug_events (mint, detected_at DESC);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_market_reports (
            id BIGSERIAL PRIMARY KEY,
            report_date DATE NOT NULL UNIQUE,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            metrics JSONB NOT NULL,
            structured_summary JSONB NOT NULL,
            ai_markdown TEXT,
            ai_model TEXT
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS winner_patterns (
            id BIGSERIAL PRIMARY KEY,
            report_date DATE NOT NULL,
            pattern_type TEXT NOT NULL,
            pattern_value TEXT NOT NULL,
            frequency INTEGER NOT NULL,
            score NUMERIC(12, 4),
            UNIQUE (report_date, pattern_type, pattern_value)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_winner_patterns_date "
        "ON winner_patterns (report_date DESC);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS winner_patterns CASCADE;")
    op.execute("DROP TABLE IF EXISTS daily_market_reports CASCADE;")
    op.execute("DROP TABLE IF EXISTS rug_events CASCADE;")
    op.execute("DROP TABLE IF EXISTS trade_summaries CASCADE;")
    op.execute("DROP TABLE IF EXISTS holder_snapshots CASCADE;")
    op.execute("DROP TABLE IF EXISTS token_socials CASCADE;")
    op.execute("DROP TABLE IF EXISTS creator_wallets CASCADE;")
    op.execute("DROP TABLE IF EXISTS token_snapshots CASCADE;")
    op.execute("DROP TABLE IF EXISTS tokens CASCADE;")
