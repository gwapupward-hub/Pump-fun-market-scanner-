from datetime import UTC, datetime

from pump_intel.classification.service import classify_token
from pump_intel.types import MigrationStatus, NormalizedCoin, TokenClass


def _coin(**kwargs) -> NormalizedCoin:
    base = dict(
        mint="m",
        name="Test",
        symbol="TST",
        creator="creator1",
        launch_ts=datetime(2026, 1, 1, tzinfo=UTC),
        market_cap_sol=10.0,
        usd_market_cap=10_000.0,
        ath_usd_mcap=50_000.0,
        ath_ts=datetime(2026, 1, 1, 1, 0, tzinfo=UTC),
        time_to_ath_seconds=3600,
        bonding_curve_progress=0.2,
        migration_status=MigrationStatus.BONDING,
        complete=False,
        volume_24h_usd=None,
        holder_count=None,
        top_holder_concentration=None,
        buy_sell_ratio=None,
        socials={"twitter": "https://x.com/a", "website": None, "telegram": None},
        x_username="a",
        x_verified_signal=True,
        reply_count=30,
        last_trade_ts=datetime.now(tz=UTC),
        raw={},
    )
    base.update(kwargs)
    return NormalizedCoin(**base)


def test_classify_graduated_winner():
    c = _coin(complete=True, ath_usd_mcap=90_000.0, usd_market_cap=80_000.0)
    cls, score = classify_token(
        c,
        ath_ratio=0.9,
        creator_rug_rate=0.0,
        drawdown=0.1,
        drawdown_24h=None,
        social_removed=False,
        dev_sell=False,
        top_holder_dump=False,
    )
    assert cls == TokenClass.GRADUATED_WINNER
    assert score >= 55


def test_classify_hard_rug_drawdown():
    c = _coin(usd_market_cap=1000.0, ath_usd_mcap=100_000.0)
    cls, score = classify_token(
        c,
        ath_ratio=0.01,
        creator_rug_rate=0.0,
        drawdown=0.99,
        drawdown_24h=None,
        social_removed=False,
        dev_sell=False,
        top_holder_dump=False,
    )
    assert cls == TokenClass.HARD_RUG
    assert score <= 20
