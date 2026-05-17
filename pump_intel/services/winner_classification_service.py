from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from pump_intel.db.models import (
    MigrationStatus,
    RugEvent,
    RugSignal,
    Token,
    TokenClassification,
    TokenSnapshot,
)


def _latest_snapshot(session: Session, token_id: int) -> TokenSnapshot | None:
    q = (
        select(TokenSnapshot)
        .where(TokenSnapshot.token_id == token_id)
        .order_by(TokenSnapshot.captured_at.desc())
        .limit(1)
    )
    return session.execute(q).scalar_one_or_none()


def _rug_counts(session: Session, token_id: int) -> tuple[int, int, Counter[RugSignal]]:
    q = select(RugEvent.signal, RugEvent.severity).where(RugEvent.token_id == token_id)
    rows = list(session.execute(q).all())
    c = Counter(s for s, _ in rows)
    hard = sum(1 for _, sev in rows if sev == "high")
    soft = len(rows) - hard
    return hard, soft, c


def _social_flags(session: Session, token_id: int) -> tuple[bool, bool, bool]:
    from pump_intel.db.models import TokenSocial

    q = select(TokenSocial).where(TokenSocial.token_id == token_id, TokenSocial.is_active.is_(True))
    socials = list(session.execute(q).scalars().all())
    x_ver = any(s.platform == "twitter" and s.x_verified for s in socials)
    tg = any(s.platform == "telegram" and (s.url or s.telegram_present) for s in socials)
    web = any(s.platform == "website" and (s.url or s.website_present) for s in socials)
    return x_ver, tg, web


def classify_token(session: Session, token: Token) -> TokenClassification:
    snap = _latest_snapshot(session, token.id)
    if not snap:
        return TokenClassification.abandoned

    hard, soft, sigs = _rug_counts(session, token.id)
    x_ver, _tg, _web = _social_flags(session, token.id)

    dd = float(snap.drawdown_from_ath) if snap.drawdown_from_ath is not None else 0.0
    vol = float(snap.volume_24h or 0)
    holders = int(snap.holder_count or 0)
    bonding = float(snap.bonding_curve_progress or 0)
    migrated = snap.migration_status == MigrationStatus.graduated
    bsr = float(snap.buy_sell_ratio) if snap.buy_sell_ratio is not None else 1.0
    mcap = float(snap.market_cap or 0)
    ath = float(snap.ath_market_cap or mcap or 0)

    # Hard rug
    if dd >= 0.9 or sigs.get(RugSignal.drawdown_90pct, 0) >= 1 or hard >= 2:
        return TokenClassification.hard_rug
    if sigs.get(RugSignal.major_dev_sell, 0) >= 1 and dd >= 0.5:
        return TokenClassification.hard_rug

    # Soft rug (requires structured signals — not raw drawdown alone)
    if soft >= 2 or sigs.get(RugSignal.drawdown_70pct_24h, 0) >= 1:
        return TokenClassification.soft_rug
    if sigs.get(RugSignal.top_holder_dump, 0) >= 1 and dd >= 0.35:
        return TokenClassification.soft_rug
    if sigs.get(RugSignal.socials_missing, 0) >= 1 and dd >= 0.55:
        return TokenClassification.soft_rug

    # Abandoned / loser
    if vol < 1e-6 and holders < 5:
        return TokenClassification.abandoned
    if mcap < max(500.0, ath * 0.05) and bsr < 0.85:
        return TokenClassification.loser

    # Winners ladder
    if migrated and mcap > 0 and dd < 0.45:
        return TokenClassification.graduated_winner
    if bonding >= 0.82 and not migrated and vol > 0:
        return TokenClassification.bonding_winner
    if x_ver and (holders >= 80 or bsr >= 1.25) and dd < 0.35:
        return TokenClassification.viral_winner
    if mcap >= max(3000.0, ath * 0.15) and dd < 0.55 and vol > 0:
        return TokenClassification.micro_winner

    return TokenClassification.loser


def apply_classification(session: Session, token: Token) -> TokenClassification:
    label = classify_token(session, token)
    token.classification = label
    return label
