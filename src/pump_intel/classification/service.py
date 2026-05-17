from __future__ import annotations

from datetime import UTC, datetime

from pump_intel.scoring.service import compute_intel_score
from pump_intel.types import NormalizedCoin, TokenClass


def classify_token(
    coin: NormalizedCoin,
    *,
    ath_ratio: float,
    creator_rug_rate: float,
    drawdown: float,
    drawdown_24h: float | None,
    social_removed: bool,
    dev_sell: bool,
    top_holder_dump: bool,
) -> tuple[TokenClass, float]:
    intel = compute_intel_score(coin, ath_ratio=ath_ratio, creator_rug_rate=creator_rug_rate)

    usd = float(coin.usd_market_cap or 0.0)
    ath = float(coin.ath_usd_mcap or max(usd, 1e-9))
    ath = max(ath, 1e-9)

    replies = int(coin.reply_count or 0)
    has_x = bool(coin.socials.get("twitter"))
    has_web = bool(coin.socials.get("website"))
    has_tg = bool(coin.socials.get("telegram"))

    abandoned = False
    if coin.last_trade_ts:
        now = datetime.now(tz=UTC)
        idle_h = (now - coin.last_trade_ts).total_seconds() / 3600.0
        abandoned = idle_h > 72 and usd < 3000 and not coin.complete

    score = float(intel)

    if abandoned:
        return TokenClass.ABANDONED, min(score, 25.0)
    if drawdown >= 0.9 or dev_sell:
        return TokenClass.HARD_RUG, min(score, 15.0)
    if drawdown_24h is not None and drawdown_24h >= 0.7:
        return TokenClass.SOFT_RUG, min(score, 35.0)
    if social_removed or top_holder_dump or drawdown >= 0.7:
        return TokenClass.SOFT_RUG, min(score, 40.0)
    if creator_rug_rate >= 0.65 and drawdown >= 0.5:
        return TokenClass.HARD_RUG, min(score, 20.0)

    if coin.complete and ath >= 80_000:
        return TokenClass.GRADUATED_WINNER, max(score, 70.0)
    if coin.complete:
        return TokenClass.GRADUATED_WINNER, max(score, 55.0)
    if replies >= 25 and has_x and (has_web or has_tg) and ath >= 40_000:
        return TokenClass.VIRAL_WINNER, max(score, 60.0)
    if not coin.complete and coin.bonding_curve_progress >= 0.85 and usd >= 40_000:
        return TokenClass.BONDING_WINNER, max(score, 58.0)
    if ath >= 25_000:
        return TokenClass.MICRO_WINNER, max(score, max(45.0, score))
    if usd >= 8000 or replies >= 10:
        return TokenClass.MICRO_WINNER, score
    if ath_ratio < 0.08 and usd < 2000:
        return TokenClass.LOSER, min(score, 30.0)
    return TokenClass.LOSER, score
