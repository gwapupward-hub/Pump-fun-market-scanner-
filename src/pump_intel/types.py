from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class MigrationStatus(StrEnum):
    BONDING = "bonding"
    GRADUATED = "graduated"


class TokenClass(StrEnum):
    LOSER = "loser"
    MICRO_WINNER = "micro_winner"
    BONDING_WINNER = "bonding_winner"
    GRADUATED_WINNER = "graduated_winner"
    VIRAL_WINNER = "viral_winner"
    SOFT_RUG = "soft_rug"
    HARD_RUG = "hard_rug"
    ABANDONED = "abandoned"


class RugEventType(StrEnum):
    MAJOR_DEV_SELL = "major_dev_sell"
    DRAWDOWN_70_24H = "drawdown_70pct_24h"
    DRAWDOWN_90 = "drawdown_90pct"
    TOP_HOLDER_DUMP = "top_holder_dump"
    CREATOR_REPUTATION = "creator_reputation"
    SOCIAL_REMOVED = "social_removed"


@dataclass
class NormalizedCoin:
    mint: str
    name: str
    symbol: str
    creator: str
    launch_ts: datetime
    market_cap_sol: float | None
    usd_market_cap: float | None
    ath_usd_mcap: float | None
    ath_ts: datetime | None
    time_to_ath_seconds: int | None
    bonding_curve_progress: float
    migration_status: MigrationStatus
    complete: bool
    volume_24h_usd: float | None
    holder_count: int | None
    top_holder_concentration: float | None
    buy_sell_ratio: float | None
    socials: dict[str, str | None]
    x_username: str | None
    x_verified_signal: bool | None
    reply_count: int
    last_trade_ts: datetime | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TradeAggregate:
    buy_volume_usd: float | None
    sell_volume_usd: float | None
    trade_count: int | None
    largest_sell_notional_usd: float | None
    dev_sell_detected: bool
