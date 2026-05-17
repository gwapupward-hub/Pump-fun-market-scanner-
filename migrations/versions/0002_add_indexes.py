"""extra performance indexes

Revision ID: 0002_add_indexes
Revises: 0001_initial
Create Date: 2024-01-02 00:00:00.000000
"""
from __future__ import annotations

from alembic import op

revision = "0002_add_indexes"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_rug_events_mint_severity "
        "ON rug_events (mint, severity);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_creator_wallets_reputation "
        "ON creator_wallets (reputation_score);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_token_snapshots_snapshot_at "
        "ON token_snapshots (snapshot_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tokens_classification "
        "ON tokens (classification) WHERE classification IS NOT NULL;"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_holder_snapshots_snapshot_at "
        "ON holder_snapshots (snapshot_at DESC);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_holder_snapshots_snapshot_at;")
    op.execute("DROP INDEX IF EXISTS idx_tokens_classification;")
    op.execute("DROP INDEX IF EXISTS idx_token_snapshots_snapshot_at;")
    op.execute("DROP INDEX IF EXISTS idx_creator_wallets_reputation;")
    op.execute("DROP INDEX IF EXISTS idx_rug_events_mint_severity;")
