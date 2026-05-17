"""Single-mint scoring — used by unit tests and ad-hoc lookups.

For the daily job, see `pump_intel.services.scoring_bulk.rescore_recent_mints`,
which folds this logic into one SQL statement.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pump_intel.db import execute, fetch_one_dict


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _ms_to_dt(ms: Any) -> datetime | None:
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(float(ms) / 1000.0, tz=UTC)
    except (OSError, ValueError, OverflowError, TypeError):
        return None


def score_token(conn, mint: str) -> float:
    snap = fetch_one_dict(
        conn,
        """
        SELECT market_cap_usd, ath_market_cap_usd, migration_status, bonding_curve_progress_pct,
               volume_24h_usd, buy_sell_ratio, top_holder_concentration_pct, raw_coin
        FROM token_snapshots
        WHERE mint = %s
        ORDER BY snapshot_at DESC
        LIMIT 1
        """,
        (mint,),
    )
    if not snap:
        return 0.0

    raw = snap.get("raw_coin") or {}
    score = 20.0

    ath = float(snap["ath_market_cap_usd"] or 0)
    if ath > 0:
        score += min(30.0, (ath / 250_000.0) * 30.0)

    mig = str(snap.get("migration_status") or "")
    if mig.startswith("graduated"):
        score += 20.0

    bp = snap.get("bonding_curve_progress_pct")
    if bp is not None:
        score += min(10.0, float(bp) / 10.0)

    vol = snap.get("volume_24h_usd")
    if vol is not None:
        score += min(10.0, float(vol) / 500_000.0 * 10.0)

    bsr = snap.get("buy_sell_ratio")
    if bsr is not None and float(bsr) > 1.0:
        score += min(5.0, (float(bsr) - 1.0))

    top = snap.get("top_holder_concentration_pct")
    if top is not None:
        if float(top) > 40:
            score -= 15.0
        elif float(top) > 25:
            score -= 8.0

    rug_hard = fetch_one_dict(
        conn,
        "SELECT COUNT(*)::int AS c FROM rug_events WHERE mint = %s AND severity = 'hard'",
        (mint,),
    )
    if rug_hard and int(rug_hard["c"]) > 0:
        score -= 25.0 * int(rug_hard["c"])

    rug_soft = fetch_one_dict(
        conn,
        "SELECT COUNT(*)::int AS c FROM rug_events WHERE mint = %s AND severity = 'soft'",
        (mint,),
    )
    if rug_soft and int(rug_soft["c"]) > 0:
        score -= 8.0 * int(rug_soft["c"])

    replies = int(raw.get("reply_count") or 0)
    score += min(10.0, replies / 500.0 * 10.0)

    last_trade = _ms_to_dt(raw.get("last_trade_timestamp"))
    if last_trade and (_now() - last_trade) > timedelta(days=7):
        score -= 15.0

    return max(0.0, min(100.0, score))


def update_token_score(conn, mint: str, score: float) -> None:
    execute(conn, "UPDATE tokens SET score = %s WHERE mint = %s", (score, mint))
