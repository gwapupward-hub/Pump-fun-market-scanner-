from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from psycopg import Connection

from pump_intel.db.connection import json_dumps_safe
from pump_intel.types import NormalizedCoin, RugEventType, TokenClass, TradeAggregate


def upsert_token(conn: Connection, coin: NormalizedCoin) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tokens (mint_address, name, symbol, creator_wallet, launch_ts)
            VALUES (%(mint)s, %(name)s, %(symbol)s, %(creator)s, %(launch)s)
            ON CONFLICT (mint_address) DO UPDATE SET
                name = EXCLUDED.name,
                symbol = EXCLUDED.symbol,
                creator_wallet = EXCLUDED.creator_wallet,
                updated_at = NOW()
            RETURNING id
            """,
            {
                "mint": coin.mint,
                "name": coin.name,
                "symbol": coin.symbol,
                "creator": coin.creator,
                "launch": coin.launch_ts,
            },
        )
        row = cur.fetchone()
        assert row
        return int(row["id"])


def ensure_creator_wallet(conn: Connection, address: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO creator_wallets (address)
            VALUES (%(a)s)
            ON CONFLICT (address) DO NOTHING
            """,
            {"a": address},
        )


def replace_token_socials(conn: Connection, token_id: int, coin: NormalizedCoin) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM token_socials WHERE token_id = %s", (token_id,))
        entries: list[tuple[Any, ...]] = []
        for platform, url in coin.socials.items():
            entries.append(
                (
                    token_id,
                    platform,
                    url,
                    coin.x_username if platform == "twitter" else None,
                    coin.x_verified_signal if platform == "twitter" else None,
                    bool(url),
                )
            )
        if coin.x_username:
            has_twitter_row = any(p == "twitter" for p in coin.socials)
            if not has_twitter_row:
                entries.append(
                    (
                        token_id,
                        "twitter",
                        coin.socials.get("twitter"),
                        coin.x_username,
                        coin.x_verified_signal,
                        bool(coin.socials.get("twitter")),
                    )
                )
        for r in entries:
            cur.execute(
                """
                INSERT INTO token_socials
                  (token_id, platform, url, x_linked_username, x_verified_signal, present)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                r,
            )


def insert_token_snapshot(
    conn: Connection,
    token_id: int,
    coin: NormalizedCoin,
    classification: TokenClass,
    intel_score: float,
    trade: TradeAggregate | None,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO token_snapshots (
              token_id, market_cap_sol, usd_market_cap, ath_usd_mcap, ath_ts,
              time_to_ath_seconds, bonding_curve_progress, migration_status,
              volume_24h_usd, holder_count, top_holder_concentration, buy_sell_ratio,
              classification, intel_score, raw_coin
            ) VALUES (
              %(tid)s, %(mcs)s, %(usd)s, %(ath)s, %(ath_ts)s,
              %(tta)s, %(bond)s, %(mig)s,
              %(vol)s, %(hc)s, %(thc)s, %(bsr)s,
              %(cls)s, %(score)s, %(raw)s::jsonb
            )
            RETURNING id
            """,
            {
                "tid": token_id,
                "mcs": coin.market_cap_sol,
                "usd": coin.usd_market_cap,
                "ath": coin.ath_usd_mcap,
                "ath_ts": coin.ath_ts,
                "tta": coin.time_to_ath_seconds,
                "bond": coin.bonding_curve_progress,
                "mig": coin.migration_status.value,
                "vol": coin.volume_24h_usd,
                "hc": coin.holder_count,
                "thc": coin.top_holder_concentration,
                "bsr": coin.buy_sell_ratio,
                "cls": classification.value,
                "score": intel_score,
                "raw": json_dumps_safe(coin.raw),
            },
        )
        row = cur.fetchone()
        assert row
        snap_id = int(row["id"])

    if trade:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO trade_summaries (
                  token_snapshot_id, buy_volume_usd, sell_volume_usd, trade_count,
                  largest_sell_notional_usd, dev_sell_detected
                ) VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (token_snapshot_id) DO UPDATE SET
                  buy_volume_usd = EXCLUDED.buy_volume_usd,
                  sell_volume_usd = EXCLUDED.sell_volume_usd,
                  trade_count = EXCLUDED.trade_count,
                  largest_sell_notional_usd = EXCLUDED.largest_sell_notional_usd,
                  dev_sell_detected = EXCLUDED.dev_sell_detected
                """,
                (
                    snap_id,
                    trade.buy_volume_usd,
                    trade.sell_volume_usd,
                    trade.trade_count,
                    trade.largest_sell_notional_usd,
                    trade.dev_sell_detected,
                ),
            )
    return snap_id


def insert_rug_event(
    conn: Connection,
    token_id: int,
    event_type: RugEventType,
    severity: str,
    details: dict[str, Any],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO rug_events (token_id, event_type, severity, details)
            VALUES (%s, %s, %s, %s::jsonb)
            """,
            (token_id, event_type.value, severity, json_dumps_safe(details)),
        )


def fetch_prior_snapshot(conn: Connection, token_id: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT usd_market_cap, ath_usd_mcap, snapshot_at, classification
            FROM token_snapshots
            WHERE token_id = %s
            ORDER BY snapshot_at DESC
            LIMIT 1
            """,
            (token_id,),
        )
        return cur.fetchone()


def fetch_prior_socials(conn: Connection, token_id: int) -> dict[str, bool]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT platform, present FROM token_socials WHERE token_id = %s",
            (token_id,),
        )
        rows = cur.fetchall()
    return {r["platform"]: bool(r["present"]) for r in rows}


def insert_daily_report(
    conn: Connection,
    report_date: date | datetime,
    stats: dict[str, Any],
    structured_md: str,
    ai_md: str | None,
) -> int:
    if isinstance(report_date, datetime):
        d = report_date.astimezone(UTC).date()
    else:
        d = report_date
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO daily_market_reports (report_date, stats, structured_markdown, ai_markdown)
            VALUES (%s, %s::jsonb, %s, %s)
            ON CONFLICT (report_date) DO UPDATE SET
              stats = EXCLUDED.stats,
              structured_markdown = EXCLUDED.structured_markdown,
              ai_markdown = EXCLUDED.ai_markdown,
              created_at = NOW()
            RETURNING id
            """,
            (d, json_dumps_safe(stats), structured_md, ai_md),
        )
        row = cur.fetchone()
        assert row
        return int(row["id"])


def replace_winner_patterns(conn: Connection, report_id: int, patterns: list[dict[str, Any]]) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM winner_patterns WHERE report_id = %s", (report_id,))
        for p in patterns:
            cur.execute(
                """
                INSERT INTO winner_patterns
                  (report_id, pattern_type, pattern_value, occurrence_count, metadata)
                VALUES (%s,%s,%s,%s,%s::jsonb)
                """,
                (
                    report_id,
                    p["pattern_type"],
                    p["pattern_value"],
                    p["occurrence_count"],
                    json_dumps_safe(p.get("metadata") or {}),
                ),
            )


def creator_rug_rate(conn: Connection, creator: str) -> float:
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH latest AS (
              SELECT DISTINCT ON (token_id)
                token_id, classification
              FROM token_snapshots
              ORDER BY token_id, snapshot_at DESC
            )
            SELECT
              COUNT(*) FILTER (
                WHERE l.classification IN ('soft_rug', 'hard_rug')
              )::float / NULLIF(COUNT(*), 0) AS rate
            FROM tokens t
            JOIN latest l ON l.token_id = t.id
            WHERE t.creator_wallet = %s
            """,
            (creator,),
        )
        row = cur.fetchone()
        if not row or row["rate"] is None:
            return 0.0
        return float(row["rate"])


def insert_holder_snapshots(
    conn: Connection, token_snapshot_id: int, rows: list[tuple[int, str, float]]
) -> None:
    if not rows:
        return
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM holder_snapshots WHERE token_snapshot_id = %s",
            (token_snapshot_id,),
        )
        for rank, wallet, pct in rows:
            cur.execute(
                """
                INSERT INTO holder_snapshots (token_snapshot_id, holder_rank, wallet_address, pct_supply)
                VALUES (%s,%s,%s,%s)
                """,
                (token_snapshot_id, rank, wallet, pct),
            )


def refresh_creator_aggregates(conn: Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO creator_wallets (address)
            SELECT DISTINCT creator_wallet FROM tokens
            ON CONFLICT (address) DO NOTHING
            """
        )
        cur.execute(
            """
            WITH latest AS (
              SELECT DISTINCT ON (token_id)
                token_id, classification, usd_market_cap, ath_usd_mcap
              FROM token_snapshots
              ORDER BY token_id, snapshot_at DESC
            )
            UPDATE creator_wallets cw SET
              tokens_created = agg.tc,
              rug_count = agg.rugs,
              winner_count = agg.wins,
              reputation_score = LEAST(100::numeric, GREATEST(-100::numeric,
                agg.wins * 2 - agg.rugs * 5
              )),
              flags = jsonb_build_object(
                'rug_rate', CASE WHEN agg.tc > 0 THEN ROUND((agg.rugs::numeric / agg.tc), 4) ELSE 0 END
              ),
              updated_at = NOW()
            FROM (
              SELECT
                t.creator_wallet AS address,
                COUNT(*)::int AS tc,
                COUNT(*) FILTER (
                  WHERE l.classification IN ('soft_rug', 'hard_rug')
                )::int AS rugs,
                COUNT(*) FILTER (
                  WHERE l.classification IN (
                    'micro_winner', 'bonding_winner', 'graduated_winner', 'viral_winner'
                  )
                )::int AS wins
              FROM tokens t
              JOIN latest l ON l.token_id = t.id
              GROUP BY t.creator_wallet
            ) agg
            WHERE cw.address = agg.address
            """
        )
