from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg

from pump_intel.db import repo
from pump_intel.models.domain import NormalizedToken


def _f(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def compute_ath_state(
    old: dict[str, Any] | None,
    token: NormalizedToken,
    *,
    now: datetime,
) -> tuple[float | None, datetime | None, int | None]:
    prev_ath = _f(old["ath_market_cap_usd"]) if old and old.get("ath_market_cap_usd") is not None else None
    prev_time = old.get("ath_reached_at") if old else None
    if isinstance(prev_time, datetime) and prev_time.tzinfo is None:
        prev_time = prev_time.replace(tzinfo=timezone.utc)

    candidates = [x for x in (prev_ath, token.ath_market_cap_usd, token.market_cap_usd) if x is not None]
    new_ath = max(candidates) if candidates else None

    ath_reached_at: datetime | None = prev_time if isinstance(prev_time, datetime) else None
    if new_ath is not None and (prev_ath is None or new_ath > float(prev_ath) * 1.000_001):
        ath_reached_at = now

    launch = token.launch_timestamp
    if launch.tzinfo is None:
        launch = launch.replace(tzinfo=timezone.utc)

    tta: int | None = None
    if ath_reached_at is not None:
        tta = max(0, int((ath_reached_at - launch).total_seconds()))

    return new_ath, ath_reached_at, tta


def compute_drawdowns(
    *,
    ath: float | None,
    mc: float | None,
    snapshots_desc: list[dict[str, Any]],
) -> tuple[float | None, float | None]:
    drawdown_from_ath: float | None = None
    if ath and ath > 0 and mc is not None:
        drawdown_from_ath = max(0.0, min(1.0, (ath - float(mc)) / float(ath)))

    drawdown_24h: float | None = None
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    old_mc: float | None = None
    for s in snapshots_desc:
        ts = s.get("captured_at")
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts <= cutoff:
                old_mc = _f(s.get("market_cap_usd")) if s.get("market_cap_usd") is not None else None
                break
    if old_mc is not None and old_mc > 0 and mc is not None:
        drawdown_24h = max(0.0, min(1.0, (old_mc - float(mc)) / old_mc))

    return drawdown_from_ath, drawdown_24h


def ingest_tokens(conn: psycopg.Connection, tokens: list[NormalizedToken]) -> int:
    now = datetime.now(timezone.utc)
    count = 0
    for token in tokens:
        creator_id = repo.ensure_creator(conn, token.creator_wallet)
        old = repo.get_token_by_mint(conn, token.mint_address)
        new_ath, ath_reached_at, tta = compute_ath_state(old, token, now=now)

        token_id = repo.upsert_token(
            conn,
            token,
            creator_id,
            ath_market_cap_usd=new_ath,
            ath_reached_at=ath_reached_at,
            time_to_ath_seconds=tta,
        )
        repo.replace_token_socials(conn, token_id, token)

        snaps = repo.list_snapshots_last_n(conn, token_id, limit=10)
        dd_ath, dd_24h = compute_drawdowns(ath=new_ath, mc=token.market_cap_usd, snapshots_desc=snaps)

        repo.insert_token_snapshot(
            conn,
            token_id,
            market_cap_usd=token.market_cap_usd,
            ath_market_cap_usd=new_ath,
            bonding_curve_progress=token.bonding_curve_progress,
            migration_status=token.migration_status,
            volume_24h_usd=token.volume_24h_usd,
            holder_count=token.holder_count,
            top_holder_concentration=token.top_holder_concentration,
            buy_sell_ratio=token.buy_sell_ratio,
            dev_sell_fraction=token.dev_sell_fraction,
            drawdown_from_ath=dd_ath,
            drawdown_24h=dd_24h,
        )

        repo.insert_holder_snapshot(
            conn,
            token_id,
            holder_count=token.holder_count,
            top_holder_concentration=token.top_holder_concentration,
            top10_concentration=None,
            extra={},
        )

        window_end = now
        window_start = window_end - timedelta(hours=24)
        large_dump = bool(dd_24h is not None and dd_24h >= 0.35)

        repo.insert_trade_summary(
            conn,
            token_id,
            window_start,
            window_end,
            volume_usd=token.volume_24h_usd,
            buy_volume_usd=None,
            sell_volume_usd=None,
            buy_sell_ratio=token.buy_sell_ratio,
            creator_sold_usd=token.creator_sell_usd,
            creator_sell_fraction=token.dev_sell_fraction,
            large_dump_detected=large_dump,
        )

        count += 1

    return count
