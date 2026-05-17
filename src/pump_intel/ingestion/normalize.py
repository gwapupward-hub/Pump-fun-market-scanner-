from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pump_intel.config import Settings
from pump_intel.types import MigrationStatus, NormalizedCoin


def _ms_to_dt(ms: int | float | None) -> datetime | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(float(ms) / 1000.0, tz=UTC)


def estimate_bonding_progress(raw: dict[str, Any], settings: Settings) -> float:
    if raw.get("complete"):
        return 1.0
    real_sol = float(raw.get("real_sol_reserves") or 0)
    target_lamports = settings.bonding_target_sol * 1e9
    if target_lamports > 0 and real_sol > 0:
        return max(0.0, min(1.0, real_sol / target_lamports))
    usd = float(raw.get("usd_market_cap") or raw.get("market_cap") or 0)
    if settings.bonding_fallback_usd_mcap > 0:
        return max(0.0, min(1.0, usd / settings.bonding_fallback_usd_mcap))
    return 0.0


def normalize_coin(raw: dict[str, Any], settings: Settings) -> NormalizedCoin:
    mint = str(raw["mint"])
    launch = _ms_to_dt(raw.get("created_timestamp")) or datetime.now(tz=UTC)
    ath_usd = raw.get("ath_market_cap")
    ath_ts = _ms_to_dt(raw.get("ath_market_cap_timestamp"))
    ath_usd_f = float(ath_usd) if ath_usd is not None else None

    time_to_ath_s: int | None = None
    if ath_ts and launch:
        delta = ath_ts - launch
        if delta.total_seconds() >= 0:
            time_to_ath_s = int(delta.total_seconds())

    complete = bool(raw.get("complete"))
    migration = MigrationStatus.GRADUATED if complete else MigrationStatus.BONDING

    socials: dict[str, str | None] = {
        "twitter": raw.get("twitter"),
        "website": raw.get("website"),
        "telegram": raw.get("telegram"),
    }

    x_user = raw.get("username")
    if isinstance(x_user, str) and x_user:
        x_verified_signal: bool | None = True
        x_username = x_user
    else:
        x_verified_signal = None
        x_username = None

    last_trade = _ms_to_dt(raw.get("last_trade_timestamp"))

    return NormalizedCoin(
        mint=mint,
        name=str(raw.get("name") or ""),
        symbol=str(raw.get("symbol") or ""),
        creator=str(raw.get("creator") or ""),
        launch_ts=launch,
        market_cap_sol=float(raw["market_cap"]) if raw.get("market_cap") is not None else None,
        usd_market_cap=float(raw["usd_market_cap"])
        if raw.get("usd_market_cap") is not None
        else None,
        ath_usd_mcap=ath_usd_f,
        ath_ts=ath_ts,
        time_to_ath_seconds=time_to_ath_s,
        bonding_curve_progress=estimate_bonding_progress(raw, settings),
        migration_status=migration,
        complete=complete,
        volume_24h_usd=None,
        holder_count=None,
        top_holder_concentration=None,
        buy_sell_ratio=None,
        socials=socials,
        x_username=x_username,
        x_verified_signal=x_verified_signal,
        reply_count=int(raw.get("reply_count") or 0),
        last_trade_ts=last_trade,
        raw=dict(raw),
    )
