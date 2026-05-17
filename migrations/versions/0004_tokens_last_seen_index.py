"""tokens.last_seen_at index for daily report range scans

Revision ID: 0004_tokens_last_seen_index
Revises: 0003_trade_summaries_dedup
Create Date: 2024-01-04 00:00:00.000000
"""
from __future__ import annotations

from alembic import op

revision = "0004_tokens_last_seen_index"
down_revision = "0003_trade_summaries_dedup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # `build_daily_report` runs four range-scan queries against
    # tokens.last_seen_at. Without this index every report build is a full
    # sequential scan of the tokens table.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tokens_last_seen_at "
        "ON tokens (last_seen_at DESC);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tokens_last_seen_at;")
