from __future__ import annotations

from decimal import Decimal

from pump_intel.services.daily_report import _market_assessment


def test_no_scans_message():
    msg = _market_assessment(0, [], [], None, None)
    assert "No fresh snapshots" in msg


def test_scan_with_decimals_does_not_crash():
    ath = {"avg_drawdown_after_ath": Decimal("0.42")}
    social = {"twitter_rate": Decimal("0.5")}
    msg = _market_assessment(10, [{"x": 1}], [{"y": 1}], ath, social)
    assert "42.0%" in msg or "42.00%" in msg or "Mean post-ATH drawdown" in msg
    assert "Twitter link prevalence" in msg


def test_caps_count_text_to_actual_lengths():
    winners = [{"x": i} for i in range(3)]
    rugs = [{"y": i} for i in range(2)]
    msg = _market_assessment(50, winners, rugs, None, None)
    assert "3 winner picks" in msg
    assert "2 elevated-risk" in msg
