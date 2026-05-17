"""trade_summaries uniqueness + retention helper indexes

Revision ID: 0003_trade_summaries_dedup
Revises: 0002_add_indexes
Create Date: 2024-01-03 00:00:00.000000
"""
from __future__ import annotations

from alembic import op

revision = "0003_trade_summaries_dedup"
down_revision = "0002_add_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Collapse pre-existing duplicates that the old append-only path may have left behind.
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY mint, period_start, period_end, source
                       ORDER BY id DESC
                   ) AS rn
            FROM trade_summaries
        )
        DELETE FROM trade_summaries
        WHERE id IN (SELECT id FROM ranked WHERE rn > 1);
        """
    )
    op.execute(
        "ALTER TABLE trade_summaries "
        "ADD CONSTRAINT trade_summaries_mint_period_source_uniq "
        "UNIQUE (mint, period_start, period_end, source);"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE trade_summaries "
        "DROP CONSTRAINT IF EXISTS trade_summaries_mint_period_source_uniq;"
    )
