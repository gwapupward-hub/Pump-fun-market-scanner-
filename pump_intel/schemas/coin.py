from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _first(d: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


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


def _as_bool(v: Any) -> bool:
    return bool(v)


def _parse_ts(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.astimezone(UTC) if v.tzinfo else v.replace(tzinfo=UTC)
    iv = _as_int(v)
    if iv is not None:
        # Heuristic: ms vs s
        if iv > 10_000_000_000:
            iv = iv // 1000
        try:
            return datetime.fromtimestamp(iv, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(v, str):
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except ValueError:
            return None
    return None


@dataclass
class NormalizedCoin:
    """Canonical view after ingestion — numbers are best-effort from API payloads."""

    mint: str
    name: str | None = None
    ticker: str | None = None
    creator_wallet: str | None = None
    launch_at: datetime | None = None
    market_cap: float | None = None
    ath_market_cap: float | None = None
    time_to_ath_seconds: int | None = None
    bonding_curve_progress: float | None = None
    migration_status: str | None = None
    volume_24h: float | None = None
    holder_count: int | None = None
    top_holder_concentration: float | None = None
    buy_sell_ratio: float | None = None
    twitter_url: str | None = None
    telegram_url: str | None = None
    website_url: str | None = None
    x_verified: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_dict(d: dict[str, Any]) -> "NormalizedCoin":
        mint = str(_first(d, ["mint", "address", "id"], "") or "")
        name = _first(d, ["name", "title"], None)
        ticker = _first(d, ["symbol", "ticker", "ticker_symbol"], None)
        creator = _first(d, ["creator", "creator_address", "creatorAddress", "user"], None)
        if isinstance(creator, dict):
            creator = creator.get("address") or creator.get("wallet")

        launch = _parse_ts(
            _first(
                d,
                [
                    "created_timestamp",
                    "createdTimestamp",
                    "created_at",
                    "createdAt",
                    "timestamp",
                ],
            )
        )

        mcap = _as_float(
            _first(
                d,
                [
                    "usd_market_cap",
                    "market_cap",
                    "marketCap",
                    "mcap",
                    "marketCapUsd",
                ],
            )
        )
        ath = _as_float(
            _first(
                d,
                [
                    "ath_market_cap",
                    "athMarketCap",
                    "ath_usd_market_cap",
                    "athUsdMarketCap",
                    "usd_market_cap_ath",
                ],
            )
        )
        if ath is None and mcap is not None:
            ath = mcap

        tta = _as_int(_first(d, ["time_to_ath_seconds", "timeToAthSeconds", "seconds_to_ath"], None))

        bonding = _as_float(
            _first(
                d,
                [
                    "bonding_curve_progress",
                    "bondingCurveProgress",
                    "bonding_progress",
                    "curve_progress",
                ],
            )
        )
        if bonding is not None and bonding > 1:
            bonding = bonding / 100.0

        migrated = _first(d, ["complete", "is_complete", "migrated", "raydium_pool"], None)
        migration_status = "unknown"
        if migrated is True:
            migration_status = "graduated"
        elif migrated is False:
            migration_status = "bonding"

        vol = _as_float(
            _first(
                d,
                [
                    "volume_24h",
                    "volume24h",
                    "usd_volume_24h",
                    "volume",
                ],
            )
        )
        holders = _as_int(_first(d, ["holder_count", "holders", "numHolders", "holderCount"], None))
        top1 = _as_float(
            _first(
                d,
                [
                    "top_holder_pct",
                    "topHolderPct",
                    "top_holder_concentration",
                    "topHolderConcentration",
                ],
            )
        )
        if top1 is not None and top1 > 1:
            top1 = top1 / 100.0

        buys = _as_float(_first(d, ["buy_volume", "buyVolume", "buys"], None))
        sells = _as_float(_first(d, ["sell_volume", "sellVolume", "sells"], None))
        ratio = _as_float(_first(d, ["buy_sell_ratio", "buySellRatio"], None))
        if ratio is None and buys is not None and sells not in (None, 0):
            ratio = buys / max(sells, 1e-9)

        tw = _first(d, ["twitter", "twitter_url", "twitterUrl", "x_url", "xUrl"], None)
        tg = _first(d, ["telegram", "telegram_url", "telegramUrl"], None)
        web = _first(d, ["website", "website_url", "websiteUrl"], None)

        if isinstance(tw, dict):
            tw = tw.get("url") or tw.get("link")
        if isinstance(tg, dict):
            tg = tg.get("url") or tg.get("link")
        if isinstance(web, dict):
            web = web.get("url") or web.get("link")

        x_verified = _as_bool(_first(d, ["twitter_verified", "twitterVerified", "x_verified", "xVerified"], False))

        return NormalizedCoin(
            mint=mint,
            name=str(name) if name is not None else None,
            ticker=str(ticker) if ticker is not None else None,
            creator_wallet=str(creator) if creator is not None else None,
            launch_at=launch,
            market_cap=mcap,
            ath_market_cap=ath,
            time_to_ath_seconds=tta,
            bonding_curve_progress=bonding,
            migration_status=migration_status,
            volume_24h=vol,
            holder_count=holders,
            top_holder_concentration=top1,
            buy_sell_ratio=ratio,
            twitter_url=str(tw) if tw else None,
            telegram_url=str(tg) if tg else None,
            website_url=str(web) if web else None,
            x_verified=x_verified,
            raw=dict(d),
        )
