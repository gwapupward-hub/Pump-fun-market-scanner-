from __future__ import annotations

from typing import Literal

from pump_intel.services.rug_detection import RugSignal
from pump_intel.services.scoring import ScoreBreakdown

Classification = Literal[
    "loser",
    "micro_winner",
    "bonding_winner",
    "graduated_winner",
    "viral_winner",
    "soft_rug",
    "hard_rug",
    "abandoned",
    "unclassified",
]


def classify_token(
    *,
    migration_status: str,
    score: ScoreBreakdown,
    signals: list[RugSignal],
    volume_24h_usd: float | None,
    holder_count: int | None,
    bonding_curve_progress: float | None,
    market_cap_usd: float | None,
    social_verified_x: bool | None,
) -> Classification:
    types = {s.event_type for s in signals}

    major_dev_high = any(s.event_type == "major_dev_sell" and s.severity == "high" for s in signals)
    major_dev_med = any(s.event_type == "major_dev_sell" and s.severity == "medium" for s in signals)

    if "drawdown_90" in types or major_dev_high:
        return "hard_rug"

    if "drawdown_70_24h" in types or "top_holder_dump" in types or major_dev_med:
        # Escalate if multiple independent rug signals fire together
        if ("drawdown_70_24h" in types and "top_holder_dump" in types) or (
            "suspicious_creator" in types and "top_holder_dump" in types
        ):
            return "hard_rug"
        return "soft_rug"

    vol = float(volume_24h_usd or 0.0)
    holders = int(holder_count or 0)
    mc = float(market_cap_usd or 0.0)
    bonding = float(bonding_curve_progress or 0.0)

    if migration_status == "graduated":
        if vol > 750_000 and holders > 1_200 and score.total >= 55:
            return "viral_winner"
        return "graduated_winner"

    if vol < 2_000 and holders < 20 and mc < 25_000:
        return "abandoned"

    if "suspicious_creator" in types and score.total < 35:
        return "soft_rug"

    if bonding >= 0.85 and migration_status != "graduated":
        return "bonding_winner"

    if mc >= 150_000 or (vol > 200_000 and holders > 250):
        return "micro_winner" if mc < 800_000 else "viral_winner"

    if social_verified_x and vol > 120_000:
        return "viral_winner"

    if score.total < 22:
        return "loser"

    return "micro_winner"
