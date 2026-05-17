from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

import psycopg

from pump_intel.db import repo


@dataclass(slots=True)
class RugSignal:
    event_type: str
    severity: str
    details: dict[str, Any]


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return None


def detect_rug_signals(
    *,
    token_row: Mapping[str, Any],
    snapshots_desc: Sequence[Mapping[str, Any]],
    social_rows: Sequence[Mapping[str, Any]],
    creator_rug_events_on_other_tokens: int,
    dev_sell_fraction: float | None,
) -> list[RugSignal]:
    signals: list[RugSignal] = []

    ath = _f(token_row.get("ath_market_cap_usd")) or 0.0
    mc = _f(token_row.get("market_cap_usd")) or 0.0
    ath_reached_at = _parse_ts(token_row.get("ath_reached_at"))

    if ath > 0 and mc >= 0:
        dd_now = (ath - mc) / ath
        if dd_now >= 0.9:
            signals.append(RugSignal("drawdown_90", "high", {"drawdown": dd_now, "ath": ath, "mc": mc}))

        now = datetime.now(timezone.utc)
        ath_recent = ath_reached_at is not None and ath_reached_at >= (now - timedelta(hours=24))
        if dd_now >= 0.7 and ath_recent:
            signals.append(
                RugSignal(
                    "drawdown_70_24h",
                    "high" if dd_now >= 0.85 else "medium",
                    {"drawdown_from_ath": dd_now, "ath": ath, "mc": mc},
                )
            )

    if snapshots_desc:
        latest = snapshots_desc[0]
        prev = snapshots_desc[1] if len(snapshots_desc) > 1 else None
        c0 = _f(latest.get("top_holder_concentration"))
        c1 = _f(prev.get("top_holder_concentration")) if prev else None
        if c0 is not None and c1 is not None and (c1 - c0) >= 0.15:
            signals.append(
                RugSignal(
                    "top_holder_dump",
                    "medium",
                    {"prev_top_holder": c1, "now_top_holder": c0},
                )
            )

    if creator_rug_events_on_other_tokens >= 2:
        signals.append(
            RugSignal(
                "suspicious_creator",
                "medium",
                {"creator_rug_events": creator_rug_events_on_other_tokens},
            )
        )

    present = [r for r in social_rows if r.get("is_present")]
    if not present:
        signals.append(RugSignal("missing_socials", "low", {"reason": "no_social_links_recorded"}))

    if dev_sell_fraction is not None:
        if dev_sell_fraction >= 0.25:
            signals.append(RugSignal("major_dev_sell", "high", {"dev_sell_fraction": dev_sell_fraction}))
        elif dev_sell_fraction >= 0.12:
            signals.append(RugSignal("major_dev_sell", "medium", {"dev_sell_fraction": dev_sell_fraction}))

    return signals


def persist_signals(conn: psycopg.Connection, token_id: int, signals: Sequence[RugSignal]) -> int:
    inserted = 0
    for s in signals:
        if repo.insert_rug_event(conn, token_id, s.event_type, s.severity, s.details):
            inserted += 1
    return inserted
