from __future__ import annotations

import json
from pathlib import Path

import pytest

from pump_intel.ingestion.normalize import normalize_coin

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "pump_coins.json"


@pytest.fixture(scope="module")
def coins() -> list[dict]:
    return json.loads(FIXTURE.read_text())


def test_normalize_graduated(coins):
    n = normalize_coin(coins[0], sol_price=200.0)
    assert n is not None
    assert n.mint.startswith("MintGraduated")
    assert n.migration_status == "graduated_raydium"
    assert n.bonding_curve_progress_pct == 100.0
    assert n.ath_market_cap_usd == pytest.approx(1_200_000.0)
    assert n.socials["twitter"]["present"] is True
    assert n.socials["telegram"]["present"] is False
    assert n.time_to_ath_seconds == 3_600


def test_normalize_bonding(coins):
    n = normalize_coin(coins[1], sol_price=200.0)
    assert n is not None
    assert n.migration_status == "bonding"
    assert n.bonding_curve_progress_pct is not None
    assert 0 <= n.bonding_curve_progress_pct <= 99.9


def test_normalize_drops_bad_timestamp(coins):
    assert normalize_coin(coins[2], sol_price=200.0) is None


def test_normalize_drops_missing_creator(coins):
    assert normalize_coin(coins[3], sol_price=200.0) is None


def test_normalize_loser_still_emitted(coins):
    n = normalize_coin(coins[4], sol_price=200.0)
    assert n is not None
    assert n.migration_status == "bonding"
    assert all(not s["present"] for s in n.socials.values())


def test_normalize_missing_mint_returns_none():
    assert normalize_coin({"creator": "x", "created_timestamp": 1}, sol_price=1.0) is None
