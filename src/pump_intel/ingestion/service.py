from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

import psycopg

from pump_intel.clients.pump_api import PumpFunClient
from pump_intel.clients.solana_rpc import SolanaRPCClient, parse_largest_accounts_response
from pump_intel.config import get_settings
from pump_intel.db import execute, executemany, fetch_all_dict, jsonb, transaction
from pump_intel.ingestion.normalize import NormalizedCoin, normalize_coin

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def ingest_latest_coins() -> dict[str, Any]:
    """Pull the latest coins from Pump.fun, persist them, then enrich holders.

    Returns a stats dict for observability.
    """
    settings = get_settings()
    raw_coins: dict[str, dict[str, Any]] = {}

    async with PumpFunClient() as client:
        sol_price = await client.get_sol_price()
        async for page in client.iter_coins_pages():
            for raw in page:
                mint = raw.get("mint")
                if mint:
                    raw_coins[str(mint)] = raw

    normalized: dict[str, NormalizedCoin] = {}
    rejected = 0
    for raw in raw_coins.values():
        n = normalize_coin(raw, sol_price=sol_price)
        if n is None:
            rejected += 1
            continue
        normalized[n.mint] = n

    log.info(
        "ingest fetched coins",
        extra={
            "raw_count": len(raw_coins),
            "normalized": len(normalized),
            "rejected": rejected,
            "sol_price_usd": sol_price,
        },
    )

    snapshot_at = _now()
    snapshots_written = 0
    with transaction() as conn:
        _upsert_tokens(conn, normalized, snapshot_at=snapshot_at)
        _upsert_socials(conn, normalized, snapshot_at=snapshot_at)
        fresh_mints = _select_fresh_mints(
            conn, list(normalized.keys()), settings.snapshot_stale_seconds
        )
        snapshots_written = _insert_snapshots(
            conn,
            {m: normalized[m] for m in fresh_mints},
            sol_price_usd=sol_price,
            snapshot_at=snapshot_at,
        )
        if snapshots_written:
            _backfill_volume_and_ratio(conn, fresh_mints)

    holder_stats = await _enrich_holders(normalized, snapshot_at=snapshot_at)
    if holder_stats["written"]:
        with transaction() as conn:
            _apply_holder_concentration_to_latest_snapshots(conn, list(normalized.keys()))

    stats = {
        "sol_price_usd": sol_price,
        "raw_coins": len(raw_coins),
        "unique_mints": len(normalized),
        "rejected_coins": rejected,
        "snapshots_written": snapshots_written,
        "holder_snapshots": holder_stats,
    }
    log.info("ingest complete", extra=stats)
    return stats


# ----------------------- write helpers ----------------------- #


def _upsert_tokens(
    conn: psycopg.Connection,
    coins: dict[str, NormalizedCoin],
    *,
    snapshot_at: datetime,
) -> None:
    if not coins:
        return
    rows = [
        (
            c.mint,
            c.name,
            c.ticker,
            c.creator_wallet,
            c.launch_at,
            snapshot_at,
            jsonb({"last_source": "pump_frontend"}),
        )
        for c in coins.values()
    ]
    sql = """
        INSERT INTO tokens (mint, name, ticker, creator_wallet, launch_timestamp, last_seen_at, metadata)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (mint) DO UPDATE SET
            name = EXCLUDED.name,
            ticker = EXCLUDED.ticker,
            creator_wallet = EXCLUDED.creator_wallet,
            last_seen_at = EXCLUDED.last_seen_at,
            metadata = tokens.metadata || EXCLUDED.metadata
    """
    executemany(conn, sql, rows)


def _upsert_socials(
    conn: psycopg.Connection,
    coins: dict[str, NormalizedCoin],
    *,
    snapshot_at: datetime,
) -> None:
    rows: list[tuple[Any, ...]] = []
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
    if not rows:
        return
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


def _select_fresh_mints(
    conn: psycopg.Connection,
    mints: list[str],
    stale_seconds: int,
) -> list[str]:
    """Return the subset of *mints* whose latest snapshot is older than *stale_seconds*."""
    if not mints:
        return []
    rows = fetch_all_dict(
        conn,
        """
        SELECT mint, MAX(snapshot_at) AS last_at
        FROM token_snapshots
        WHERE mint = ANY(%s::text[])
        GROUP BY mint
        """,
        (mints,),
    )
    recent: dict[str, datetime] = {r["mint"]: r["last_at"] for r in rows}
    threshold = _now()
    out: list[str] = []
    for m in mints:
        last = recent.get(m)
        if last is None or (threshold - last).total_seconds() >= stale_seconds:
            out.append(m)
    return out


def _insert_snapshots(
    conn: psycopg.Connection,
    coins: dict[str, NormalizedCoin],
    *,
    sol_price_usd: float,
    snapshot_at: datetime,
) -> int:
    if not coins:
        return 0
    rows = [
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
            jsonb(c.raw),
        )
        for c in coins.values()
    ]
    sql = """
        INSERT INTO token_snapshots (
            mint, snapshot_at, market_cap_usd, market_cap_sol,
            ath_market_cap_usd, ath_market_cap_sol, ath_at, time_to_ath_seconds,
            bonding_curve_progress_pct, migration_status, volume_24h_usd,
            holder_count, top_holder_concentration_pct, buy_sell_ratio, sol_price_usd, raw_coin
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    return executemany(conn, sql, rows)


def _backfill_volume_and_ratio(conn: psycopg.Connection, mints: list[str]) -> None:
    """Bound the CTE to the recently-touched mints + last 72h of history."""
    if not mints:
        return
    sql = """
        WITH ranked AS (
            SELECT
                id,
                mint,
                snapshot_at,
                market_cap_usd,
                LAG(market_cap_usd) OVER (PARTITION BY mint ORDER BY snapshot_at) AS prev_mcap,
                LAG(snapshot_at)    OVER (PARTITION BY mint ORDER BY snapshot_at) AS prev_at
            FROM token_snapshots
            WHERE mint = ANY(%s::text[])
              AND snapshot_at >= NOW() - interval '72 hours'
        )
        UPDATE token_snapshots ts
        SET
            volume_24h_usd = CASE
                WHEN r.prev_mcap IS NULL OR r.market_cap_usd IS NULL THEN ts.volume_24h_usd
                ELSE ABS(r.market_cap_usd - r.prev_mcap)
            END,
            buy_sell_ratio = CASE
                WHEN r.prev_mcap IS NULL OR r.prev_mcap <= 0 OR r.market_cap_usd IS NULL
                    THEN ts.buy_sell_ratio
                WHEN r.market_cap_usd >= r.prev_mcap
                    THEN LEAST(50, 1 + (r.market_cap_usd - r.prev_mcap) / r.prev_mcap * 10)
                ELSE GREATEST(0.02, 1 / (1 + (r.prev_mcap - r.market_cap_usd) / NULLIF(r.prev_mcap,0) * 10))
            END
        FROM ranked r
        WHERE ts.id = r.id
          AND r.prev_at IS NOT NULL
          AND r.snapshot_at - r.prev_at <= interval '36 hours'
    """
    execute(conn, sql, (mints,))


def _apply_holder_concentration_to_latest_snapshots(
    conn: psycopg.Connection, mints: list[str]
) -> None:
    if not mints:
        return
    sql = """
        WITH latest_snap AS (
            SELECT DISTINCT ON (mint) id, mint
            FROM token_snapshots
            WHERE mint = ANY(%s::text[])
            ORDER BY mint, snapshot_at DESC
        ),
        latest_h AS (
            SELECT DISTINCT ON (mint) mint, top1_holder_pct
            FROM holder_snapshots
            WHERE mint = ANY(%s::text[])
            ORDER BY mint, snapshot_at DESC
        )
        UPDATE token_snapshots ts
        SET top_holder_concentration_pct = h.top1_holder_pct
        FROM latest_snap ls
        JOIN latest_h h ON h.mint = ls.mint
        WHERE ts.id = ls.id AND h.top1_holder_pct IS NOT NULL
    """
    execute(conn, sql, (mints, mints))


# ----------------------- holder enrichment ----------------------- #


async def _enrich_holders(
    normalized: dict[str, NormalizedCoin],
    *,
    snapshot_at: datetime,
) -> dict[str, int]:
    """Run Solana RPC outside of any DB transaction, then bulk-insert results."""
    settings = get_settings()
    if not settings.solana_rpc_url or not normalized:
        return {"requested": 0, "written": 0, "errors": 0, "skipped": len(normalized)}

    # Cap to top-N most-recently-active mints to keep cost bounded.
    coins_sorted = sorted(
        normalized.values(),
        key=lambda c: (c.last_trade_at or c.launch_at),
        reverse=True,
    )
    target = coins_sorted[: settings.holder_enrichment_top_n]

    async with SolanaRPCClient() as rpc:
        async def _fetch(mint: str) -> tuple[str, dict[str, Any] | None]:
            return mint, await rpc.get_token_largest_accounts(mint)

        results = await asyncio.gather(*(_fetch(c.mint) for c in target), return_exceptions=False)

    rows: list[tuple[Any, ...]] = []
    errors = 0
    for mint, resp in results:
        holders, top1, top5, err = parse_largest_accounts_response(resp)
        if err:
            errors += 1
        rows.append((mint, snapshot_at, holders, top1, top5, err))

    written = 0
    if rows:
        with transaction() as conn:
            written = executemany(
                conn,
                """
                INSERT INTO holder_snapshots
                    (mint, snapshot_at, holder_count, top1_holder_pct, top5_holders_pct, rpc_error)
                VALUES (%s,%s,%s,%s,%s,%s)
                """,
                rows,
            )

    stats = {
        "requested": len(target),
        "written": written,
        "errors": errors,
        "skipped": max(0, len(normalized) - len(target)),
    }
    log.info("holder enrichment complete", extra=stats)
    return stats


# ----------------------- query helpers ----------------------- #


def load_latest_snapshots_map(conn: psycopg.Connection, mints: list[str]) -> dict[str, dict]:
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
