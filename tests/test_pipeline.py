from sqlalchemy import select

from pump_intel.db.models import DailyMarketReport, Token, TokenClassification
from pump_intel.db.session import session_scope
from pump_intel.pipeline import run_daily_pipeline


def test_pipeline_fixture_run_creates_report() -> None:
    n = run_daily_pipeline()
    assert n == 5
    with session_scope() as s:
        tokens = list(s.scalars(select(Token)).all())
        assert len(tokens) == 5
        rep = s.scalars(select(DailyMarketReport)).one()
        assert rep.coins_scanned == 5
        assert rep.structured_stats.get("total_coins_scanned") == 5
        assert rep.ai_markdown
        labels = {t.classification for t in tokens if t.classification}
        assert {TokenClassification.graduated_winner, TokenClassification.hard_rug}.issubset(labels)
