from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from pump_intel.db.models import CreatorWallet, Token, TokenClassification

def refresh_creator_rollups(session: Session) -> None:
    """Recompute aggregate creator stats from persisted tokens (analytics only)."""
    wallets = list(session.scalars(select(CreatorWallet)).all())
    for cw in wallets:
        q_tokens = select(Token).where(Token.creator_wallet_id == cw.id)
        tokens = list(session.scalars(q_tokens).all())
        cw.tokens_created = len(tokens)
        cw.graduates_linked = sum(
            1 for t in tokens if t.classification == TokenClassification.graduated_winner
        )
        cw.rugs_linked = sum(
            1
            for t in tokens
            if t.classification in (TokenClassification.hard_rug, TokenClassification.soft_rug)
        )
        scores = [float(t.intel_score or 0) for t in tokens if t.intel_score is not None]
        avg = sum(scores) / len(scores) if scores else 0.0
        cw.reputation_score = float(
            max(0.0, min(100.0, 52.0 + 0.35 * avg + 6.0 * cw.graduates_linked - 9.0 * cw.rugs_linked))
        )
