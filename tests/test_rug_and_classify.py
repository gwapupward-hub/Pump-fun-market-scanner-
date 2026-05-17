from __future__ import annotations

from pump_intel.services.rug_detection import detect_rug_signals
from pump_intel.services.scoring import score_token
from pump_intel.services.winner_classification import classify_token


def test_hard_rug_drawdown_90() -> None:
    token_row = {"ath_market_cap_usd": 100_000, "market_cap_usd": 5_000, "ath_reached_at": None}
    signals = detect_rug_signals(
        token_row=token_row,
        snapshots_desc=[],
        social_rows=[{"is_present": True}],
        creator_rug_events_on_other_tokens=0,
        dev_sell_fraction=None,
    )
    types = {s.event_type for s in signals}
    assert "drawdown_90" in types


def test_major_dev_sell_signal() -> None:
    token_row = {"ath_market_cap_usd": 50_000, "market_cap_usd": 40_000, "ath_reached_at": None}
    signals = detect_rug_signals(
        token_row=token_row,
        snapshots_desc=[],
        social_rows=[{"is_present": True}],
        creator_rug_events_on_other_tokens=0,
        dev_sell_fraction=0.3,
    )
    assert any(s.event_type == "major_dev_sell" for s in signals)


def test_classify_graduated_winner() -> None:
    score = score_token(
        market_cap_usd=900_000,
        volume_24h_usd=800_000,
        holder_count=1500,
        top_holder_concentration=0.15,
        buy_sell_ratio=1.6,
        bonding_curve_progress=1.0,
        social_verified_x=True,
        has_website=True,
        has_telegram=True,
        creator_reputation=2.0,
    )
    cls = classify_token(
        migration_status="graduated",
        score=score,
        signals=[],
        volume_24h_usd=800_000,
        holder_count=1500,
        bonding_curve_progress=1.0,
        market_cap_usd=900_000,
        social_verified_x=True,
    )
    assert cls in {"viral_winner", "graduated_winner"}
