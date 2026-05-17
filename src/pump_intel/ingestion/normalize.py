from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pump_intel.clients.pump_api import ms_to_utc
from pump_intel.config import get_settings
from pump_intel.db.json import dumps_json

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class NormalizedCoin:
    mint: str
    name: str
    ticker: str
    creator_wallet: str
    launch_at: datetime
    market_cap_usd: float | None
    market_cap_sol: float | None
    ath_market_cap_usd: float | None
    ath_market_cap_sol: float | None
    ath_at: datetime | None
    time_to_ath_seconds: int | None
    bonding_curve_progress_pct: float | None
    migration_status: str
    volume_24h_usd: float | None
    holder_count: int | None
    top_holder_concentration_pct: float | None
    buy_sell_ratio: float | None
    last_trade_at: datetime | None
    socials: dict[str, dict[str, Any]]
    raw: dict[str, Any]


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _i(x: Any) -> int | None:
    if x is None:
        return None
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _migration_status(c: dict[str, Any]) -> str:
    if c.get("raydium_pool"):
        return "graduated_raydium"
    if c.get("pump_swap_pool"):
        return "graduated_pump_swap"
    if c.get("complete"):
        return "complete_other"
    return "bonding"


def _bonding_progress(c: dict[str, Any], sol_price: float) -> float | None:
    s = get_settings()
    if bool(c.get("complete")):
        return 100.0
    usd_mcap = _f(c.get("usd_market_cap"))
    if usd_mcap is not None:
        return max(0.0, min(99.9, 100.0 * usd_mcap / s.bonding_target_usd_mcap))
    mcap_sol = _f(c.get("market_cap"))
    if mcap_sol is None or sol_price <= 0:
        return None
    approx_usd = mcap_sol * sol_price
    return max(0.0, min(99.9, 100.0 * approx_usd / s.bonding_target_usd_mcap))


def _socials(c: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for key in ("twitter", "telegram", "website"):
        value = c.get(key)
        if value:
            out[key] = {"url": str(value), "present": True, "x_verified": None}
        else:
            out[key] = {"url": None, "present": False, "x_verified": None}
    return out


def normalize_coin(raw: dict[str, Any], *, sol_price: float) -> NormalizedCoin | None:
    """Convert one raw Pump.fun coin payload into a `NormalizedCoin`.

    Returns `None` (drop) when the payload lacks identifying fields. We
    deliberately **do not** fall back to `now()` for missing launch timestamps
    — those rows would poison `launch_timestamp` analytics.
    """
    mint = raw.get("mint")
    if not mint:
        return None
    creator = str(raw.get("creator") or "").strip()
    if not creator:
        return None

    launch = ms_to_utc(raw.get("created_timestamp"))
    if launch is None:
        log.info("normalize: dropping mint=%s (missing/invalid created_timestamp)", mint)
        return None

    name = str(raw.get("name") or "").strip() or "unknown"
    ticker = str(raw.get("symbol") or "").strip() or "UNKNOWN"

    mcap_sol = _f(raw.get("market_cap"))
    usd_mcap = _f(raw.get("usd_market_cap"))
    if usd_mcap is None and mcap_sol is not None and sol_price > 0:
        usd_mcap = mcap_sol * sol_price

    ath_sol = _f(raw.get("ath_market_cap"))
    ath_usd = _f(raw.get("ath_usd_market_cap") or raw.get("athMarketCapUsd"))
    if ath_usd is None and usd_mcap is not None and mcap_sol and mcap_sol > 0 and ath_sol:
        ath_usd = usd_mcap * (ath_sol / mcap_sol)
    elif ath_usd is None and ath_sol is not None and sol_price > 0:
        ath_usd = ath_sol * sol_price

    ath_at = ms_to_utc(raw.get("ath_market_cap_timestamp"))
    tta: int | None = None
    if ath_at is not None:
        tta = max(0, int((ath_at - launch).total_seconds()))

    return NormalizedCoin(
        mint=str(mint),
        name=name,
        ticker=ticker,
        creator_wallet=creator,
        launch_at=launch,
        market_cap_usd=usd_mcap,
        market_cap_sol=mcap_sol,
        ath_market_cap_usd=ath_usd,
        ath_market_cap_sol=ath_sol,
        ath_at=ath_at,
        time_to_ath_seconds=tta,
        bonding_curve_progress_pct=_bonding_progress(raw, sol_price=sol_price),
        migration_status=_migration_status(raw),
        volume_24h_usd=None,
        holder_count=_i(raw.get("num_participants")),
        top_holder_concentration_pct=None,
        buy_sell_ratio=None,
        last_trade_at=ms_to_utc(raw.get("last_trade_timestamp")),
        socials=_socials(raw),
        raw=dict(raw),
    )


def dumps_jsonb(obj: dict[str, Any]) -> str:
    """Back-compat alias — prefer `pump_intel.db.json.dumps_json`."""
    return dumps_json(obj)
