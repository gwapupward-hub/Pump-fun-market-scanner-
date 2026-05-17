from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from pump_intel.db.models import RugEvent, RugSignal, Token, TokenSnapshot, TradeSummary

log = logging.getLogger(__name__)


def _last_snapshots(session: Session, token_id: int, n: int = 3) -> list[TokenSnapshot]:
    q = (
        select(TokenSnapshot)
        .where(TokenSnapshot.token_id == token_id)
        .order_by(desc(TokenSnapshot.captured_at))
        .limit(n)
    )
    return list(session.execute(q).scalars().all())


def _last_trade_summary(session: Session, token_id: int) -> TradeSummary | None:
    q = (
        select(TradeSummary)
        .where(TradeSummary.token_id == token_id)
        .order_by(desc(TradeSummary.window_end))
        .limit(1)
    )
    return session.execute(q).scalar_one_or_none()


def _has_recent_event(session: Session, token_id: int, signal: RugSignal, hours: int = 48) -> bool:
    from datetime import UTC, datetime, timedelta

    since = datetime.now(tz=UTC) - timedelta(hours=hours)
    q = select(RugEvent.id).where(
        RugEvent.token_id == token_id,
        RugEvent.signal == signal,
        RugEvent.detected_at >= since,
    )
    return session.execute(q).first() is not None


def _add_event(session: Session, token_id: int, signal: RugSignal, severity: str, details: dict[str, Any]) -> None:
    if _has_recent_event(session, token_id, signal, hours=6):
        return
    session.add(RugEvent(token_id=token_id, signal=signal, severity=severity, details=details))


def evaluate_token(session: Session, token: Token) -> list[RugSignal]:
    """Heuristic rug detection from snapshots, trades, and social rows (via token relationship)."""
    snaps = _last_snapshots(session, token.id, n=5)
    if not snaps:
        return []
    latest = snaps[0]
    emitted: list[RugSignal] = []

    # Drawdown thresholds
    dd = float(latest.drawdown_from_ath) if latest.drawdown_from_ath is not None else None
    if dd is not None and dd >= 0.9:
        _add_event(
            session,
            token.id,
            RugSignal.drawdown_90pct,
            "high",
            {"drawdown_from_ath": dd, "snapshot_id": latest.id},
        )
        emitted.append(RugSignal.drawdown_90pct)

    if len(snaps) >= 2:
        prior = snaps[1]
        age_hours = (latest.captured_at - prior.captured_at).total_seconds() / 3600.0
        pdd = float(prior.drawdown_from_ath) if prior.drawdown_from_ath is not None else None
        if age_hours <= 24 and pdd is not None and pdd < 0.25 and dd is not None and dd >= 0.70:
            _add_event(
                session,
                token.id,
                RugSignal.drawdown_70pct_24h,
                "high",
                {
                    "prior_drawdown": pdd,
                    "latest_drawdown": dd,
                    "hours_between": age_hours,
                },
            )
            emitted.append(RugSignal.drawdown_70pct_24h)

    # Top holder dump: concentration spike down implies distribution
    if len(snaps) >= 2:
        prev, cur = snaps[1], snaps[0]
        if prev.top_holder_concentration and cur.top_holder_concentration:
            drop = float(prev.top_holder_concentration) - float(cur.top_holder_concentration)
            if drop >= 0.15:
                _add_event(
                    session,
                    token.id,
                    RugSignal.top_holder_dump,
                    "medium",
                    {"concentration_delta": drop},
                )
                emitted.append(RugSignal.top_holder_dump)

    trade = _last_trade_summary(session, token.id)
    if trade and trade.creator_sell_volume_estimate and trade.buy_volume:
        ratio = float(trade.creator_sell_volume_estimate) / max(float(trade.buy_volume), 1e-9)
        if ratio >= 0.45:
            _add_event(
                session,
                token.id,
                RugSignal.major_dev_sell,
                "high",
                {"creator_sell_to_buy_ratio": ratio},
            )
            emitted.append(RugSignal.major_dev_sell)

    # Missing socials for active markets
    from pump_intel.db.models import TokenSocial

    qsoc = select(TokenSocial).where(TokenSocial.token_id == token.id, TokenSocial.is_active.is_(True))
    socials = list(session.execute(qsoc).scalars().all())
    urls = [s.url for s in socials if s.url]
    if not urls and (latest.volume_24h or 0) > 0:
        _add_event(session, token.id, RugSignal.socials_missing, "low", {"reason": "no_active_urls"})
        emitted.append(RugSignal.socials_missing)

    # Creator history — handled in pipeline after counting rugs for wallet
    return emitted


def evaluate_creator_history(session: Session, token: Token) -> None:
    from pump_intel.db.models import CreatorWallet

    if not token.creator_wallet_id:
        return
    cw = session.get(CreatorWallet, token.creator_wallet_id)
    if not cw:
        return
    if cw.rugs_linked >= 3 and cw.tokens_created >= 4:
        _add_event(
            session,
            token.id,
            RugSignal.suspicious_creator_history,
            "medium",
            {"creator_wallet_id": cw.id, "rugs_linked": cw.rugs_linked},
        )
