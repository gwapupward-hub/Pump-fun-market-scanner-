from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ScoreBreakdown:
    momentum: float
    liquidity: float
    distribution: float
    social: float
    creator: float
    total: float


def score_token(
    *,
    market_cap_usd: float | None,
    volume_24h_usd: float | None,
    holder_count: int | None,
    top_holder_concentration: float | None,
    buy_sell_ratio: float | None,
    bonding_curve_progress: float | None,
    social_verified_x: bool | None,
    has_website: bool,
    has_telegram: bool,
    creator_reputation: float | None,
) -> ScoreBreakdown:
    """Heuristic 0–100 style subscores (not dollar-normalized to avoid scale brittleness)."""

    mc = float(market_cap_usd or 0.0)
    vol = float(volume_24h_usd or 0.0)
    holders = float(holder_count or 0.0)

    momentum = min(35.0, (vol / 250_000.0) * 35.0) + min(15.0, (holders / 800.0) * 15.0)
    if buy_sell_ratio is not None and buy_sell_ratio > 0:
        # Higher buys vs sells is better, but cap influence
        br = min(buy_sell_ratio, 3.0)
        momentum += min(10.0, (br / 3.0) * 10.0)

    liquidity = min(25.0, (mc / 2_000_000.0) * 25.0)
    if bonding_curve_progress is not None:
        liquidity += min(10.0, max(bonding_curve_progress, 0.0) * 10.0)

    distribution = 20.0
    if top_holder_concentration is not None:
        # concentration 0..1 where higher is worse
        distribution = max(0.0, 20.0 * (1.0 - min(top_holder_concentration, 0.95) / 0.95))

    social = 0.0
    if has_website:
        social += 4.0
    if has_telegram:
        social += 4.0
    if social_verified_x:
        social += 12.0
    elif social_verified_x is False:
        social += 2.0

    creator = 10.0
    if creator_reputation is not None:
        creator = max(0.0, min(20.0, 10.0 + creator_reputation))

    total = momentum + liquidity + distribution + social + creator
    total = max(0.0, min(100.0, total))

    return ScoreBreakdown(
        momentum=round(momentum, 4),
        liquidity=round(liquidity, 4),
        distribution=round(distribution, 4),
        social=round(social, 4),
        creator=round(creator, 4),
        total=round(total, 4),
    )
