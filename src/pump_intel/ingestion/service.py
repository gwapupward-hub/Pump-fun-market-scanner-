from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pump_intel.clients.pump_api import PumpFunClient
from pump_intel.clients.solana_rpc import fetch_token_largest_accounts, parse_largest_accounts_response
from pump_intel.db import connect, ensure_schema, executemany, execute, fetch_all_dict, fetch_one_dict
from pump_intel.ingestion.normalize import NormalizedCoin, dumps_jsonb, normalize_coin

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


async def ingest_latest_coins() -> dict[str, Any]:
    client = PumpFunClient()
    sol_price = await client.get_sol_price()

    coins: dict[str, dict[str, Any]] = {}
    async for page in client.iter_coins_pages():
        for raw in page:
            mint = raw.get("mint")
            if mint:
                coins[str(mint)] = raw

    normalized: dict[str, NormalizedCoin] = {}
    for raw in coins.values():
        n = normalize_coin(raw, sol_price=sol_price)
        if n:
            normalized[n.mint] = n

    with connect() as conn:
        ensure_schema(conn)
        _upsert_tokens(conn, normalized)
        _upsert_socials(conn, normalized, snapshot_at=_now())
        snapshot_ids = _insert_snapshots(conn, normalized, sol_price_usd=sol_price, snapshot_at=_now())
        _backfill_volume_and_ratio(conn)
        await _insert_holder_snapshots(conn, normalized)
        _apply_holder_concentration_to_latest_snapshots(conn)

    return {
        "sol_price_usd": sol_price,
        "unique_mints": len(normalized),
        "snapshots_written": len(snapshot_ids),
    }


def _upsert_tokens(conn, coins: dict[str, NormalizedCoin]) -> None:
    rows = []
    now = _now()
    for c in coins.values():
        rows.append(
            (
                c.mint,
                c.name,
                c.ticker,
                c.creator_wallet,
                c.launch_at,
                now,
                dumps_jsonb({"last_source": "pump_frontend"}),
            )
        )
    sql = """
        INSERT INTO tokens (mint, name, ticker, creator_wallet, launch_timestamp, last_seen_at, metadata)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT (mint) DO UPDATE SET
            name = EXCLUDED.name,
            ticker = EXCLUDED.ticker,
            creator_wallet = EXCLUDED.creator_wallet,
            last_seen_at = EXCLUDED.last_seen_at,
            metadata = tokens.metadata || EXCLUDED.metadata
    """
    executemany(conn, sql, rows)


def _upsert_socials(conn, coins: dict[str, NormalizedCoin], *, snapshot_at: datetime) -> None:
    rows = []
    for c in coins.values():
        for platform, meta in c.socials.items():
            rows.append(
                (
                    c.mint,
                    platform,
                    meta.get("url"),
                    bool(meta.get("present")),
                    meta.get("x_verified"),
                    snapshot_at,
                    snapshot_at,
                )
            )
    sql = """
        INSERT INTO token_socials (mint, platform, url, is_present, x_verified, first_seen_at, last_seen_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (mint, platform) DO UPDATE SET
            url = EXCLUDED.url,
            is_present = EXCLUDED.is_present,
            x_verified = COALESCE(EXCLUDED.x_verified, token_socials.x_verified),
            last_seen_at = EXCLUDED.last_seen_at
    """
    executemany(conn, sql, rows)


def _insert_snapshots(
    conn,
    coins: dict[str, NormalizedCoin],
    *,
    sol_price_usd: float,
    snapshot_at: datetime,
) -> list[int]:
    rows = []
    for c in coins.values():
        rows.append(
            (
                c.mint,
                snapshot_at,
                c.market_cap_usd,
                c.market_cap_sol,
                c.ath_market_cap_usd,
                c.ath_market_cap_sol,
                c.ath_at,
                c.time_to_ath_seconds,
                c.bonding_curve_progress_pct,
                c.migration_status,
                c.volume_24h_usd,
                c.holder_count,
                c.top_holder_concentration_pct,
                c.buy_sell_ratio,
                sol_price_usd,
                dumps_jsonb(c.raw),
            )
        )
    sql = """
        INSERT INTO token_snapshots (
            mint, snapshot_at, market_cap_usd, market_cap_sol,
            ath_market_cap_usd, ath_market_cap_sol, ath_at, time_to_ath_seconds,
            bonding_curve_progress_pct, migration_status, volume_24h_usd,
            holder_count, top_holder_concentration_pct, buy_sell_ratio, sol_price_usd, raw_coin
        ) VALUES (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb
        ) RETURNING id
    """
    ids: list[int] = []
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(sql, row)
            ids.append(int(cur.fetchone()[0]))
    conn.commit()
    return ids


def _backfill_volume_and_ratio(conn) -> None:
    """Estimate 24h volume from mcap change vs prior snapshot; rough buy/sell proxy."""
    sql = """
        WITH ranked AS (
            SELECT
                id,
                mint,
                snapshot_at,
                market_cap_usd,
                LAG(market_cap_usd) OVER (PARTITION BY mint ORDER BY snapshot_at) AS prev_mcap,
                LAG(snapshot_at) OVER (PARTITION BY mint ORDER BY snapshot_at) AS prev_at
            FROM token_snapshots
        )
        UPDATE token_snapshots ts
        SET
            volume_24h_usd = CASE
                WHEN r.prev_mcap IS NULL OR r.market_cap_usd IS NULL THEN ts.volume_24h_usd
                ELSE ABS(r.market_cap_usd - r.prev_mcap)
            END,
            buy_sell_ratio = CASE
                WHEN r.prev_mcap IS NULL OR r.prev_mcap <= 0 OR r.market_cap_usd IS NULL THEN ts.buy_sell_ratio
                WHEN r.market_cap_usd >= r.prev_mcap THEN LEAST(50, 1 + (r.market_cap_usd - r.prev_mcap) / r.prev_mcap * 10)
                ELSE GREATEST(0.02, 1 / (1 + (r.prev_mcap - r.market_cap_usd) / NULLIF(r.prev_mcap,0) * 10))
            END
        FROM ranked r
        WHERE ts.id = r.id
          AND r.prev_at IS NOT NULL
          AND r.snapshot_at - r.prev_at <= interval '36 hours'
    """
    execute(conn, sql)


def _apply_holder_concentration_to_latest_snapshots(conn) -> None:
    sql = """
        WITH latest_snap AS (
            SELECT DISTINCT ON (mint) id, mint
            FROM token_snapshots
            ORDER BY mint, snapshot_at DESC
        ),
        latest_h AS (
            SELECT DISTINCT ON (mint) mint, top1_holder_pct
            FROM holder_snapshots
            ORDER BY mint, snapshot_at DESC
        )
        UPDATE token_snapshots ts
        SET top_holder_concentration_pct = h.top1_holder_pct
        FROM latest_snap ls
        JOIN latest_h h ON h.mint = ls.mint
        WHERE ts.id = ls.id AND h.top1_holder_pct IS NOT NULL
    """
    execute(conn, sql)


async def _insert_holder_snapshots(conn, coins: dict[str, NormalizedCoin]) -> None:
    """Optional RPC enrichment; failures are recorded on holder_snapshots."""
    now = _now()
    rows: list[tuple[Any, ...]] = []
    for c in coins.values():
        resp = await fetch_token_largest_accounts(c.mint)
        holders, top1, top5, err = parse_largest_accounts_response(resp)
        rows.append((c.mint, now, holders, top1, top5, err))
    sql = """
        INSERT INTO holder_snapshots (mint, snapshot_at, holder_count, top1_holder_pct, top5_holders_pct, rpc_error)
        VALUES (%s,%s,%s,%s,%s,%s)
    """
    executemany(conn, sql, rows)


def load_latest_snapshots_map(conn, mints: list[str]) -> dict[str, dict]:
    if not mints:
        return {}
    rows = fetch_all_dict(
        conn,
        """
        SELECT DISTINCT ON (mint)
            mint,
            market_cap_usd,
            ath_market_cap_usd,
            ath_at,
            snapshot_at,
            top_holder_concentration_pct,
            migration_status,
            raw_coin
        FROM token_snapshots
        WHERE mint = ANY(%s::text[])
        ORDER BY mint, snapshot_at DESC
        """,
        (mints,),
    )
    return {r["mint"]: r for r in rows}


def load_prev_snapshot(conn, mint: str) -> dict | None:
    return fetch_one_dict(
        conn,
        """
        SELECT market_cap_usd, ath_market_cap_usd, snapshot_at, top_holder_concentration_pct, raw_coin
        FROM token_snapshots
        WHERE mint = %s
        ORDER BY snapshot_at DESC
        OFFSET 1
        LIMIT 1
        """,
        (mint,),
    )
