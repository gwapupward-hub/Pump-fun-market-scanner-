from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pump_intel.services.rug_detection import _signals_for


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def test_ath_drawdown_90pct_hard():
    latest = {
        "ath_market_cap_usd": 1000.0,
        "market_cap_usd": 50.0,
        "ath_at": datetime.now(tz=UTC) - timedelta(hours=6),
        "top_holder_concentration_pct": None,
        "raw_coin": {},
    }
    sigs = _signals_for(latest, None, None)
    assert any(s.rug_kind == "ath_drawdown_90pct" and s.severity == "hard" for s in sigs)


def test_fast_drawdown_70pct_within_24h_hard():
    latest = {
        "ath_market_cap_usd": 1000.0,
        "market_cap_usd": 250.0,  # 75% drawdown
        "ath_at": datetime.now(tz=UTC) - timedelta(hours=3),
        "top_holder_concentration_pct": None,
        "raw_coin": {},
    }
    sigs = _signals_for(latest, None, None)
    assert any(s.rug_kind == "ath_drawdown_70pct_within_24h_of_ath" for s in sigs)


def test_top_holder_dump_soft():
    latest = {
        "ath_market_cap_usd": 100.0,
        "market_cap_usd": 90.0,
        "ath_at": datetime.now(tz=UTC),
        "top_holder_concentration_pct": 10.0,
        "raw_coin": {},
    }
    prev = {"top_holder_concentration_pct": 35.0}
    sigs = _signals_for(latest, prev, None)
    assert any(s.rug_kind == "top_holder_dump" for s in sigs)


def test_suspicious_creator():
    latest = {
        "ath_market_cap_usd": 100.0,
        "market_cap_usd": 90.0,
        "ath_at": datetime.now(tz=UTC),
        "top_holder_concentration_pct": None,
        "raw_coin": {"creator": "abc"},
    }
    creator_row = {"hard_rug_count": 2, "soft_rug_count": 2}
    sigs = _signals_for(latest, None, creator_row)
    assert any(s.rug_kind == "suspicious_creator_wallet_history" for s in sigs)


def test_dev_sell_proxy_young_token():
    now = datetime.now(tz=UTC)
    latest = {
        "ath_market_cap_usd": 1000.0,
        "market_cap_usd": 10.0,
        "ath_at": now - timedelta(hours=2),
        "top_holder_concentration_pct": None,
        "raw_coin": {"created_timestamp": _ms(now - timedelta(hours=12))},
    }
    sigs = _signals_for(latest, None, None)
    assert any(s.rug_kind == "major_dev_sell_proxy" for s in sigs)


def test_no_signals_on_healthy():
    now = datetime.now(tz=UTC)
    latest = {
        "ath_market_cap_usd": 100.0,
        "market_cap_usd": 95.0,
        "ath_at": now - timedelta(hours=2),
        "top_holder_concentration_pct": 8.0,
        "raw_coin": {"created_timestamp": _ms(now - timedelta(hours=24))},
    }
    sigs = _signals_for(latest, {"top_holder_concentration_pct": 9.0}, None)
    assert sigs == []
