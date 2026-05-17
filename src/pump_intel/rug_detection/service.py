from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from psycopg import Connection

from pump_intel.db import repository as repo
from pump_intel.types import NormalizedCoin, RugEventType


@dataclass
class RugSignals:
    drawdown: float
    drawdown_24h: float | None
    social_removed: bool
    dev_sell: bool
    top_holder_dump: bool
    events: list[tuple[RugEventType, str, dict[str, Any]]]


def _drawdown(current: float | None, ath: float | None) -> float:
    if current is None or ath is None or ath <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - (float(current) / float(ath))))


class RugDetectionService:
    def evaluate(
        self,
        conn: Connection,
        token_id: int,
        coin: NormalizedCoin,
        prior_socials: dict[str, bool],
        trade_dev_sell: bool,
    ) -> RugSignals:
        events: list[tuple[RugEventType, str, dict[str, Any]]] = []
        cur_usd = float(coin.usd_market_cap or 0.0)
        ath_usd = float(coin.ath_usd_mcap or cur_usd or 0.0)
        ath_for_dd = ath_usd if ath_usd > 0 else None
        dd = _drawdown(cur_usd, ath_for_dd)

        dd_24h: float | None = None
        if coin.ath_ts:
            hours_since_ath = (datetime.now(tz=UTC) - coin.ath_ts).total_seconds() / 3600.0
            if hours_since_ath <= 24:
                dd_24h = dd

        if dd >= 0.9:
            events.append(
                (
                    RugEventType.DRAWDOWN_90,
                    "high",
                    {"drawdown": dd, "usd": cur_usd, "ath": ath_usd},
                )
            )
        elif dd_24h is not None and dd_24h >= 0.7:
            events.append(
                (
                    RugEventType.DRAWDOWN_70_24H,
                    "high",
                    {"drawdown": dd, "window_hours": 24},
                )
            )
        elif dd >= 0.7:
            events.append(
                (
                    RugEventType.DRAWDOWN_70_24H,
                    "medium",
                    {"drawdown": dd},
                )
            )

        social_removed = False
        for platform, was_present in prior_socials.items():
            if not was_present:
                continue
            url_now = coin.socials.get(platform)
            if not url_now:
                social_removed = True
                events.append(
                    (
                        RugEventType.SOCIAL_REMOVED,
                        "medium",
                        {"platform": platform},
                    )
                )

        dev_sell = trade_dev_sell
        if dev_sell:
            events.append((RugEventType.MAJOR_DEV_SELL, "high", {"creator": coin.creator}))

        top_dump = False
        prior = repo.fetch_prior_snapshot(conn, token_id)
        if prior:
            p_usd = float(prior.get("usd_market_cap") or 0.0)
            if p_usd > 0 and cur_usd / p_usd <= 0.35:
                top_dump = True
                events.append(
                    (
                        RugEventType.TOP_HOLDER_DUMP,
                        "medium",
                        {"mcap_ratio": cur_usd / p_usd},
                    )
                )

        rug_rate = repo.creator_rug_rate(conn, coin.creator)
        if rug_rate >= 0.5:
            events.append(
                (
                    RugEventType.CREATOR_REPUTATION,
                    "medium",
                    {"rug_rate": rug_rate},
                )
            )

        return RugSignals(
            drawdown=dd,
            drawdown_24h=dd_24h,
            social_removed=social_removed,
            dev_sell=dev_sell,
            top_holder_dump=top_dump,
            events=events,
        )


def persist_events(conn: Connection, token_id: int, signals: RugSignals) -> None:
    for ev, severity, details in signals.events:
        repo.insert_rug_event(conn, token_id, ev, severity, details)
