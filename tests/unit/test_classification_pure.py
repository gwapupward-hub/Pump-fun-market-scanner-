"""Tests for the per-mint `classify_token` against a stub connection.

Covers branches without requiring a real Postgres — the function only uses
`fetch_one_dict`, which we intercept by patching the module-level reference.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pump_intel.services import winner_classification as wc


class _StubConn:
    """fetch_one_dict reads from this script in order."""

    def __init__(self, responses: list[dict | None]):
        self._responses = list(responses)

    def pop(self) -> dict | None:
        return self._responses.pop(0) if self._responses else None


@pytest.fixture()
def patched(monkeypatch):
    state: dict[str, _StubConn] = {}

    def fake_fetch_one_dict(conn, _sql, _params=None):
        return conn.pop()

    monkeypatch.setattr(wc, "fetch_one_dict", fake_fetch_one_dict)
    return state


def test_returns_none_when_no_snapshot(patched):
    conn = _StubConn([None])
    assert wc.classify_token(conn, "mint1") is None


def test_hard_rug_wins(patched):
    conn = _StubConn(
        [
            {"market_cap_usd": 1, "ath_market_cap_usd": 2, "migration_status": "bonding",
             "bonding_curve_progress_pct": 1, "raw_coin": {}},
            {"ok": 1},  # hard rug present
        ]
    )
    assert wc.classify_token(conn, "m") == "hard_rug"


def test_soft_rug(patched):
    conn = _StubConn(
        [
            {"market_cap_usd": 1, "ath_market_cap_usd": 2, "migration_status": "bonding",
             "bonding_curve_progress_pct": 1, "raw_coin": {}},
            None,        # no hard
            {"ok": 1},   # soft present
        ]
    )
    assert wc.classify_token(conn, "m") == "soft_rug"


def test_abandoned(patched):
    last_trade = datetime.now(tz=UTC) - timedelta(days=15)
    conn = _StubConn(
        [
            {
                "market_cap_usd": 1, "ath_market_cap_usd": 2,
                "migration_status": "bonding", "bonding_curve_progress_pct": 1,
                "raw_coin": {"last_trade_timestamp": int(last_trade.timestamp() * 1000)},
            },
            None, None,
        ]
    )
    assert wc.classify_token(conn, "m") == "abandoned"


def test_graduated(patched):
    conn = _StubConn(
        [
            {"market_cap_usd": 100, "ath_market_cap_usd": 600_000,
             "migration_status": "graduated_raydium",
             "bonding_curve_progress_pct": 100, "raw_coin": {}},
            None, None,
        ]
    )
    assert wc.classify_token(conn, "m") == "graduated_winner"


def test_viral(patched):
    conn = _StubConn(
        [
            {"market_cap_usd": 100, "ath_market_cap_usd": 300_000,
             "migration_status": "bonding", "bonding_curve_progress_pct": 10,
             "raw_coin": {"reply_count": 5000}},
            None, None,
        ]
    )
    assert wc.classify_token(conn, "m") == "viral_winner"


def test_bonding_winner(patched):
    conn = _StubConn(
        [
            {"market_cap_usd": 100, "ath_market_cap_usd": 50_000,
             "migration_status": "bonding", "bonding_curve_progress_pct": 90,
             "raw_coin": {}},
            None, None,
        ]
    )
    assert wc.classify_token(conn, "m") == "bonding_winner"


def test_micro_winner(patched):
    conn = _StubConn(
        [
            {"market_cap_usd": 100, "ath_market_cap_usd": 30_000,
             "migration_status": "bonding", "bonding_curve_progress_pct": 10,
             "raw_coin": {}},
            None, None,
        ]
    )
    assert wc.classify_token(conn, "m") == "micro_winner"


def test_loser(patched):
    conn = _StubConn(
        [
            {"market_cap_usd": 1, "ath_market_cap_usd": 100,
             "migration_status": "bonding", "bonding_curve_progress_pct": 1,
             "raw_coin": {}},
            None, None,
        ]
    )
    assert wc.classify_token(conn, "m") == "loser"
