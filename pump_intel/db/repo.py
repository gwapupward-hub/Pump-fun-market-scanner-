from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence

import psycopg

from pump_intel.models.domain import NormalizedToken


def ensure_creator(conn: psycopg.Connection, address: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO creator_wallets (address)
            VALUES (%s)
            ON CONFLICT (address) DO UPDATE SET last_seen_at = excluded.last_seen_at
            RETURNING id
            """,
            (address,),
        )
        row = cur.fetchone()
        assert row is not None
        return int(row["id"])


def get_token_by_mint(conn: psycopg.Connection, mint: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM tokens WHERE mint_address = %s", (mint,))
        return cur.fetchone()


def upsert_token(
    conn: psycopg.Connection,
    token: NormalizedToken,
    creator_wallet_id: int,
    *,
    ath_market_cap_usd: float | None,
    ath_reached_at: datetime | None,
    time_to_ath_seconds: int | None,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tokens (
                mint_address, name, ticker, creator_wallet_id, launch_timestamp,
                market_cap_usd, ath_market_cap_usd, ath_reached_at, time_to_ath_seconds,
                bonding_curve_progress, migration_status, volume_24h_usd,
                holder_count, top_holder_concentration, buy_sell_ratio,
                social_verified_x, has_website, has_telegram,
                last_ingested_at, updated_at
            ) VALUES (
                %s,%s,%s,%s,%s,
                %s,%s,%s,%s,
                %s,%s,%s,
                %s,%s,%s,
                %s,%s,%s,
                now(), now()
            )
            ON CONFLICT (mint_address) DO UPDATE SET
                name = EXCLUDED.name,
                ticker = EXCLUDED.ticker,
                creator_wallet_id = EXCLUDED.creator_wallet_id,
                market_cap_usd = EXCLUDED.market_cap_usd,
                ath_market_cap_usd = EXCLUDED.ath_market_cap_usd,
                ath_reached_at = COALESCE(EXCLUDED.ath_reached_at, tokens.ath_reached_at),
                time_to_ath_seconds = COALESCE(EXCLUDED.time_to_ath_seconds, tokens.time_to_ath_seconds),
                bonding_curve_progress = EXCLUDED.bonding_curve_progress,
                migration_status = EXCLUDED.migration_status,
                volume_24h_usd = EXCLUDED.volume_24h_usd,
                holder_count = EXCLUDED.holder_count,
                top_holder_concentration = EXCLUDED.top_holder_concentration,
                buy_sell_ratio = EXCLUDED.buy_sell_ratio,
                social_verified_x = EXCLUDED.social_verified_x,
                has_website = EXCLUDED.has_website,
                has_telegram = EXCLUDED.has_telegram,
                last_ingested_at = now(),
                updated_at = now()
            RETURNING id
            """,
            (
                token.mint_address,
                token.name,
                token.ticker,
                creator_wallet_id,
                token.launch_timestamp.replace(tzinfo=timezone.utc)
                if token.launch_timestamp.tzinfo is None
                else token.launch_timestamp,
                token.market_cap_usd,
                ath_market_cap_usd,
                ath_reached_at,
                time_to_ath_seconds,
                token.bonding_curve_progress,
                token.migration_status,
                token.volume_24h_usd,
                token.holder_count,
                token.top_holder_concentration,
                token.buy_sell_ratio,
                token.social_verified_x,
                token.has_website,
                token.has_telegram,
            ),
        )
        row = cur.fetchone()
        assert row is not None
        return int(row["id"])


def replace_token_socials(conn: psycopg.Connection, token_id: int, token: NormalizedToken) -> None:
    platforms = (
        ("twitter", token.socials.get("twitter"), token.social_verified_x),
        ("telegram", token.socials.get("telegram"), None),
        ("website", token.socials.get("website"), None),
    )
    with conn.cursor() as cur:
        cur.execute("DELETE FROM token_socials WHERE token_id = %s", (token_id,))
        for platform, url, verified in platforms:
            cur.execute(
                """
                INSERT INTO token_socials (token_id, platform, url, is_present, verified_x, last_seen_at)
                VALUES (%s,%s,%s,%s,%s, now())
                """,
                (
                    token_id,
                    platform,
                    url,
                    bool(url),
                    verified if platform == "twitter" else None,
                ),
            )


def insert_token_snapshot(
    conn: psycopg.Connection,
    token_id: int,
    *,
    market_cap_usd: float | None,
    ath_market_cap_usd: float | None,
    bonding_curve_progress: float | None,
    migration_status: str | None,
    volume_24h_usd: float | None,
    holder_count: int | None,
    top_holder_concentration: float | None,
    buy_sell_ratio: float | None,
    dev_sell_fraction: float | None,
    drawdown_from_ath: float | None,
    drawdown_24h: float | None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO token_snapshots (
                token_id, market_cap_usd, ath_market_cap_usd, bonding_curve_progress,
                migration_status, volume_24h_usd, holder_count, top_holder_concentration,
                buy_sell_ratio, dev_sell_fraction, drawdown_from_ath, drawdown_24h
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                token_id,
                market_cap_usd,
                ath_market_cap_usd,
                bonding_curve_progress,
                migration_status,
                volume_24h_usd,
                holder_count,
                top_holder_concentration,
                buy_sell_ratio,
                dev_sell_fraction,
                drawdown_from_ath,
                drawdown_24h,
            ),
        )


def insert_holder_snapshot(
    conn: psycopg.Connection,
    token_id: int,
    *,
    holder_count: int | None,
    top_holder_concentration: float | None,
    top10_concentration: float | None,
    extra: Mapping[str, Any] | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO holder_snapshots (token_id, holder_count, top_holder_concentration, top10_concentration, extra)
            VALUES (%s,%s,%s,%s,%s::jsonb)
            """,
            (
                token_id,
                holder_count,
                top_holder_concentration,
                top10_concentration,
                json.dumps(extra or {}),
            ),
        )


def insert_trade_summary(
    conn: psycopg.Connection,
    token_id: int,
    window_start: datetime,
    window_end: datetime,
    *,
    volume_usd: float | None,
    buy_volume_usd: float | None,
    sell_volume_usd: float | None,
    buy_sell_ratio: float | None,
    creator_sold_usd: float | None,
    creator_sell_fraction: float | None,
    large_dump_detected: bool,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trade_summaries (
                token_id, window_start, window_end, volume_usd, buy_volume_usd, sell_volume_usd,
                buy_sell_ratio, creator_sold_usd, creator_sell_fraction, large_dump_detected
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (token_id, window_start, window_end) DO UPDATE SET
                volume_usd = EXCLUDED.volume_usd,
                buy_volume_usd = EXCLUDED.buy_volume_usd,
                sell_volume_usd = EXCLUDED.sell_volume_usd,
                buy_sell_ratio = EXCLUDED.buy_sell_ratio,
                creator_sold_usd = EXCLUDED.creator_sold_usd,
                creator_sell_fraction = EXCLUDED.creator_sell_fraction,
                large_dump_detected = EXCLUDED.large_dump_detected
            """,
            (
                token_id,
                window_start,
                window_end,
                volume_usd,
                buy_volume_usd,
                sell_volume_usd,
                buy_sell_ratio,
                creator_sold_usd,
                creator_sell_fraction,
                large_dump_detected,
            ),
        )


def insert_rug_event(
    conn: psycopg.Connection,
    token_id: int,
    event_type: str,
    severity: str,
    details: Mapping[str, Any],
) -> bool:
    """Return True if inserted, False if deduped."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO rug_events (token_id, event_type, severity, details, detected_at)
            VALUES (%s,%s,%s,%s::jsonb, now())
            ON CONFLICT (token_id, event_type, bucket_date)
            DO NOTHING
            RETURNING id
            """,
            (token_id, event_type, severity, json.dumps(details)),
        )
        return cur.fetchone() is not None


def list_snapshots_last_n(
    conn: psycopg.Connection, token_id: int, limit: int = 5
) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM token_snapshots
            WHERE token_id = %s
            ORDER BY captured_at DESC
            LIMIT %s
            """,
            (token_id, limit),
        )
        return list(cur.fetchall())


def creator_rug_count_excluding_token(
    conn: psycopg.Connection, creator_wallet_id: int, exclude_token_id: int
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)::int AS c
            FROM rug_events r
            JOIN tokens t ON t.id = r.token_id
            WHERE t.creator_wallet_id = %s AND t.id <> %s
            """,
            (creator_wallet_id, exclude_token_id),
        )
        row = cur.fetchone()
        return int(row["c"]) if row else 0


def creator_token_stats(conn: psycopg.Connection, creator_wallet_id: int) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                COUNT(*)::int AS total,
                COUNT(*) FILTER (WHERE classification IN ('soft_rug','hard_rug'))::int AS rugs,
                COUNT(*) FILTER (WHERE migration_status = 'graduated')::int AS grads
            FROM tokens
            WHERE creator_wallet_id = %s
            """,
            (creator_wallet_id,),
        )
        row = cur.fetchone() or {}
        return {
            "total": int(row.get("total") or 0),
            "rugs": int(row.get("rugs") or 0),
            "grads": int(row.get("grads") or 0),
        }


def update_creator_wallet_stats(
    conn: psycopg.Connection,
    creator_wallet_id: int,
    *,
    total_tokens: int,
    rug_count: int,
    graduate_count: int,
    reputation_score: float,
    risk_flags: Mapping[str, Any],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE creator_wallets
            SET total_tokens = %s,
                rug_count = %s,
                graduate_count = %s,
                reputation_score = %s,
                risk_flags = %s::jsonb,
                last_seen_at = now()
            WHERE id = %s
            """,
            (total_tokens, rug_count, graduate_count, reputation_score, json.dumps(risk_flags), creator_wallet_id),
        )


def update_token_classification(
    conn: psycopg.Connection, token_id: int, classification: str, score_total: float | None
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tokens
            SET classification = %s,
                score_total = %s,
                updated_at = now()
            WHERE id = %s
            """,
            (classification, score_total, token_id),
        )


def tokens_touched_since(conn: psycopg.Connection, since: datetime) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM tokens
            WHERE last_ingested_at >= %s
            ORDER BY last_ingested_at DESC
            """,
            (since,),
        )
        return list(cur.fetchall())


def all_tokens_latest(conn: psycopg.Connection, limit: int = 50_000) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM tokens
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return list(cur.fetchall())


def insert_daily_report(
    conn: psycopg.Connection,
    report_date: date,
    coins_scanned: int,
    structured_stats: Mapping[str, Any],
    ai_markdown: str | None,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO daily_market_reports (report_date, coins_scanned, structured_stats, ai_markdown)
            VALUES (%s,%s,%s::jsonb,%s)
            ON CONFLICT (report_date) DO UPDATE SET
                coins_scanned = EXCLUDED.coins_scanned,
                structured_stats = EXCLUDED.structured_stats,
                ai_markdown = EXCLUDED.ai_markdown
            RETURNING id
            """,
            (report_date, coins_scanned, json.dumps(structured_stats), ai_markdown),
        )
        row = cur.fetchone()
        assert row is not None
        return int(row["id"])


def replace_winner_patterns(
    conn: psycopg.Connection, report_id: int, rows: Sequence[Mapping[str, Any]]
) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM winner_patterns WHERE daily_market_report_id = %s", (report_id,))
        for r in rows:
            cur.execute(
                """
                INSERT INTO winner_patterns (
                    daily_market_report_id, pattern_type, pattern_value, frequency, strength, evidence
                ) VALUES (%s,%s,%s,%s,%s,%s::jsonb)
                """,
                (
                    report_id,
                    r["pattern_type"],
                    r["pattern_value"],
                    int(r["frequency"]),
                    float(r.get("strength") or 0.0),
                    json.dumps(r.get("evidence") or {}),
                ),
            )


def fetch_social_rows(conn: psycopg.Connection, token_id: int) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM token_socials WHERE token_id = %s", (token_id,))
        return list(cur.fetchall())
