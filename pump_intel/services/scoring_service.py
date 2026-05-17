from __future__ import annotations

import logging
import math

from sqlalchemy.orm import Session

from pump_intel.db.models import Token, TokenClassification

log = logging.getLogger(__name__)


def score_token(session: Session, token: Token) -> float:
    """Composite 0–100 intel score for ranking in daily reports (not financial advice)."""
    from pump_intel.services.winner_classification_service import _latest_snapshot

    snap = _latest_snapshot(session, token.id)
    if not snap:
        return 0.0

    mcap = float(snap.market_cap or 0)
    ath = float(snap.ath_market_cap or mcap or 0)
    dd = float(snap.drawdown_from_ath or 0)
    vol = math.log10(float(snap.volume_24h or 0) + 1.0)
    holders = math.log10(float(snap.holder_count or 0) + 1.0)
    bonding = float(snap.bonding_curve_progress or 0)
    bsr = float(snap.buy_sell_ratio or 1.0)

    base = min(40.0, mcap / 25_000.0 * 40.0)
    momentum = min(25.0, (1.0 - dd) * 25.0)
    activity = min(20.0, vol * 4.0)
    community = min(10.0, holders * 3.0)
    curve = min(10.0, bonding * 10.0)
    flow = min(10.0, max(0.0, (bsr - 0.8) * 20.0))

    score = base + momentum + activity + community + curve + flow

    label = token.classification
    if label in (TokenClassification.hard_rug,):
        score *= 0.05
    elif label in (TokenClassification.soft_rug, TokenClassification.abandoned):
        score *= 0.25
    elif label in (TokenClassification.loser,):
        score *= 0.55
    elif label in (TokenClassification.micro_winner,):
        score *= 1.05
    elif label in (TokenClassification.bonding_winner, TokenClassification.graduated_winner):
        score *= 1.15
    elif label in (TokenClassification.viral_winner,):
        score *= 1.25

    score = float(max(0.0, min(100.0, score)))
    token.intel_score = score
    return score
