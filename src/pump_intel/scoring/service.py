"""Heuristic market-cap / engagement scoring (0–100)."""

from __future__ import annotations

from pump_intel.types import NormalizedCoin


def compute_intel_score(
    coin: NormalizedCoin,
    *,
    ath_ratio: float,
    creator_rug_rate: float,
) -> float:
    usd = float(coin.usd_market_cap or 0.0)
    ath = float(coin.ath_usd_mcap or max(usd, 1e-9))
    ath = max(ath, 1e-9)
    replies = int(coin.reply_count or 0)
    has_x = bool(coin.socials.get("twitter"))
    has_web = bool(coin.socials.get("website"))
    has_tg = bool(coin.socials.get("telegram"))
    social_score = (2 if has_x else 0) + (1 if has_web else 0) + (1 if has_tg else 0)
    if coin.x_verified_signal:
        social_score += 1

    base = 20.0
    base += min(30.0, usd / 2000.0 * 3.0)
    base += min(25.0, ath / 5000.0 * 2.5)
    base += min(15.0, float(coin.bonding_curve_progress) * 15.0)
    base += min(10.0, social_score * 2.0)
    base += min(10.0, replies / 5.0)

    if coin.complete:
        base += 10.0

    ar = max(0.0, min(1.0, float(ath_ratio)))
    score = max(0.0, min(100.0, base * (0.4 + 0.6 * ar)))
    if creator_rug_rate >= 0.55:
        score *= 0.55
    return round(score, 4)
