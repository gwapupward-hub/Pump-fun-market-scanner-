from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


def _first(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> Any | None:
    for k in keys:
        if k in mapping and mapping[k] is not None:
            return mapping[k]
    return None


def _as_bool(v: Any) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.lower() in {"1", "true", "yes", "y"}
    return None


def _as_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _as_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _parse_ts_ms(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    ms = _as_int(v)
    if ms is None:
        return None
    # Heuristic: seconds vs milliseconds
    if ms < 10_000_000_000:  # ~2001 in seconds
        return datetime.fromtimestamp(float(ms), tz=timezone.utc)
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


@dataclass(slots=True)
class RawCoinPayload:
    """Loosely typed Pump.fun coin JSON."""

    data: dict[str, Any]


@dataclass(slots=True)
class NormalizedToken:
    mint_address: str
    name: str
    ticker: str
    creator_wallet: str
    launch_timestamp: datetime
    market_cap_usd: float | None
    ath_market_cap_usd: float | None
    bonding_curve_progress: float | None
    migration_status: str
    volume_24h_usd: float | None
    holder_count: int | None
    top_holder_concentration: float | None
    buy_sell_ratio: float | None
    social_verified_x: bool | None
    has_website: bool
    has_telegram: bool
    socials: dict[str, str | None] = field(default_factory=dict)
    dev_sell_fraction: float | None = None
    creator_sell_usd: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_payload(payload: Mapping[str, Any]) -> "NormalizedToken":
        mint = str(_first(payload, ("mint", "mintAddress", "id")) or "").strip()
        if not mint:
            raise ValueError("Coin payload missing mint")

        name = str(_first(payload, ("name", "title")) or "").strip() or "unknown"
        ticker = str(_first(payload, ("symbol", "ticker")) or "").strip() or "UNKNOWN"

        creator = _first(payload, ("creator", "creatorAddress", "user", "creator_wallet"))
        creator_wallet = str(creator or "").strip()
        if not creator_wallet:
            raise ValueError(f"Coin {mint} missing creator wallet")

        launch = _parse_ts_ms(_first(payload, ("created_timestamp", "createdTimestamp", "createdAt")))
        if launch is None:
            launch = datetime.now(timezone.utc)

        market_cap = _as_float(_first(payload, ("usd_market_cap", "marketCapUsd", "market_cap_usd", "marketCap")))
        ath = _as_float(_first(payload, ("ath_market_cap", "athMarketCapUsd", "ath_usd", "athUsd")))
        if ath is None:
            ath = market_cap

        complete = _as_bool(_first(payload, ("complete", "isComplete", "migrated")))
        raydium = _first(payload, ("raydium_pool", "raydiumPool", "pool"))
        migration_status = "unknown"
        if complete or (isinstance(raydium, str) and len(raydium) > 10):
            migration_status = "graduated"
        elif _as_bool(_first(payload, ("bonding_curve_complete",))):
            migration_status = "bonding_complete"
        else:
            migration_status = "bonding"

        bonding = _as_float(_first(payload, ("bonding_curve_progress", "bondingProgress", "curveProgress")))
        if bonding is None and complete is True:
            bonding = 1.0

        volume = _as_float(_first(payload, ("volume_24h", "volume24h", "volumeUsd", "volume_usd")))
        holders = _as_int(_first(payload, ("holder_count", "holders", "numHolders")))
        top_holder = _as_float(_first(payload, ("top_holder_concentration", "topHolderPct", "topHolderShare")))
        buy_sell = _as_float(_first(payload, ("buy_sell_ratio", "buySellRatio")))

        twitter = _first(payload, ("twitter", "twitterUrl", "x"))
        telegram = _first(payload, ("telegram", "telegramUrl"))
        website = _first(payload, ("website", "websiteUrl"))

        socials: dict[str, str | None] = {}
        for key, val in (("twitter", twitter), ("telegram", telegram), ("website", website)):
            if isinstance(val, str) and val.strip():
                socials[key] = val.strip()
            else:
                socials[key] = None

        verified_x = _as_bool(_first(payload, ("twitter_verified", "x_verified", "isTwitterVerified")))

        dev_sell_fraction = _as_float(_first(payload, ("dev_sell_fraction", "creatorSellFraction")))
        creator_sell_usd = _as_float(_first(payload, ("creator_sell_usd", "creatorSellUsd")))

        return NormalizedToken(
            mint_address=mint,
            name=name,
            ticker=ticker,
            creator_wallet=creator_wallet,
            launch_timestamp=launch,
            market_cap_usd=market_cap,
            ath_market_cap_usd=ath,
            bonding_curve_progress=bonding,
            migration_status=migration_status,
            volume_24h_usd=volume,
            holder_count=holders,
            top_holder_concentration=top_holder,
            buy_sell_ratio=buy_sell,
            social_verified_x=verified_x,
            has_website=bool(socials.get("website")),
            has_telegram=bool(socials.get("telegram")),
            socials=socials,
            dev_sell_fraction=dev_sell_fraction,
            creator_sell_usd=creator_sell_usd,
            raw=dict(payload),
        )
