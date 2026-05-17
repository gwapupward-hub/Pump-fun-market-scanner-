from __future__ import annotations

import psycopg

from pump_intel.db import execute


def recompute_creator_wallets(conn: psycopg.Connection) -> None:
    """Aggregate per-creator stats from `tokens` and upsert into `creator_wallets`."""
    sql = """
        INSERT INTO creator_wallets (
            address,
            last_seen_at,
            tokens_created,
            soft_rug_count,
            hard_rug_count,
            abandoned_count,
            winner_count,
            reputation_score,
            notes
        )
        SELECT
            t.creator_wallet AS address,
            MAX(t.last_seen_at) AS last_seen_at,
            COUNT(*)::int AS tokens_created,
            SUM(CASE WHEN t.classification = 'soft_rug' THEN 1 ELSE 0 END)::int,
            SUM(CASE WHEN t.classification = 'hard_rug' THEN 1 ELSE 0 END)::int,
            SUM(CASE WHEN t.classification = 'abandoned' THEN 1 ELSE 0 END)::int,
            SUM(CASE WHEN t.classification IN (
                    'graduated_winner','viral_winner','bonding_winner','micro_winner'
                ) THEN 1 ELSE 0 END)::int,
            GREATEST(0, LEAST(100,
                100
                - 12 * SUM(CASE WHEN t.classification = 'hard_rug' THEN 1 ELSE 0 END)
                - 5  * SUM(CASE WHEN t.classification = 'soft_rug' THEN 1 ELSE 0 END)
                - 2  * SUM(CASE WHEN t.classification = 'abandoned' THEN 1 ELSE 0 END)
                + 3  * SUM(CASE WHEN t.classification IN (
                        'graduated_winner','viral_winner','bonding_winner','micro_winner'
                    ) THEN 1 ELSE 0 END)
            ))::numeric(12,4),
            '{}'::jsonb
        FROM tokens t
        WHERE t.creator_wallet IS NOT NULL AND t.creator_wallet <> ''
        GROUP BY t.creator_wallet
        ON CONFLICT (address) DO UPDATE SET
            last_seen_at = EXCLUDED.last_seen_at,
            tokens_created = EXCLUDED.tokens_created,
            soft_rug_count = EXCLUDED.soft_rug_count,
            hard_rug_count = EXCLUDED.hard_rug_count,
            abandoned_count = EXCLUDED.abandoned_count,
            winner_count = EXCLUDED.winner_count,
            reputation_score = EXCLUDED.reputation_score
    """
    execute(conn, sql)
