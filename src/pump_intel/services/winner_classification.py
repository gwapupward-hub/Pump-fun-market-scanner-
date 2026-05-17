from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pump_intel.db import execute, fetch_one_dict


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _ms_to_dt(ms: Any) -> datetime | None:
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc)
    except (OSError, ValueError, OverflowError, TypeError):
        return None


def classify_token(conn, mint: str) -> str:
    snap = fetch_one_dict(
        conn,
        """
        SELECT market_cap_usd, ath_market_cap_usd, migration_status, bonding_curve_progress_pct,
               raw_coin
        FROM token_snapshots
        WHERE mint = %s
        ORDER BY snapshot_at DESC
        LIMIT 1
        """,
        (mint,),
    )
    if not snap:
        return "loser"

    raw = snap.get("raw_coin") or {}

    hard_rug = fetch_one_dict(
        conn,
        "SELECT 1 AS ok FROM rug_events WHERE mint = %s AND severity = 'hard' LIMIT 1",
        (mint,),
    )
    soft_rug = fetch_one_dict(
        conn,
        "SELECT 1 AS ok FROM rug_events WHERE mint = %s AND severity = 'soft' LIMIT 1",
        (mint,),
    )
    if hard_rug:
        return "hard_rug"
    if soft_rug:
        return "soft_rug"

    last_trade = _ms_to_dt(raw.get("last_trade_timestamp"))
    if last_trade and (_now() - last_trade) > timedelta(days=10):
        return "abandoned"

    ath = float(snap["ath_market_cap_usd"] or 0)
    mcap = float(snap["market_cap_usd"] or 0)
    mig = str(snap.get("migration_status") or "")
    bonding = float(snap.get("bonding_curve_progress_pct") or 0)

    replies = int(raw.get("reply_count") or 0)

    if mig.startswith("graduated") and ath >= 500_000:
        return "graduated_winner"
    if mig.startswith("graduated"):
        return "graduated_winner"

    if replies >= 2000 and ath >= 250_000:
        return "viral_winner"

    if (not mig.startswith("graduated")) and bonding >= 85 and ath >= 40_000:
        return "bonding_winner"

    if ath >= 25_000:
        return "micro_winner"

    if mcap <= 5_000 and ath < 15_000:
        return "loser"

    return "loser"


def persist_classification(conn, mint: str, label: str) -> None:
    execute(conn, "UPDATE tokens SET classification = %s WHERE mint = %s", (label, mint))
