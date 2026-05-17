from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import date
from statistics import fmean
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from pump_intel.db.models import DailyMarketReport, Token, TokenClassification, TokenSnapshot, WinnerPattern
from pump_intel.services.ingestion_service import token_display_name
from pump_intel.services.winner_classification_service import _latest_snapshot

log = logging.getLogger(__name__)

_STOP = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "in",
    "on",
    "for",
    "coin",
    "token",
    "pump",
    "fun",
    "official",
    "real",
}


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-zA-Z]{3,}", text.lower()) if w not in _STOP]


def _ticker_patterns(tickers: list[str]) -> dict[str, Any]:
    lengths = [len(t) for t in tickers if t]
    suff = Counter()
    for t in tickers:
        u = t.upper()
        for s in ("INU", "AI", "GPT", "404", "6900", "COIN", "MOON"):
            if u.endswith(s):
                suff[s] += 1
    return {
        "avg_ticker_length": round(fmean(lengths), 2) if lengths else None,
        "suffix_counts": dict(suff.most_common(10)),
    }


def build_daily_report(
    session: Session,
    *,
    report_date: date,
    scanned_token_ids: list[int],
) -> DailyMarketReport:
    tokens: list[Token] = []
    for tid in scanned_token_ids:
        t = session.get(Token, tid)
        if t:
            tokens.append(t)

    snaps: list[tuple[Token, TokenSnapshot]] = []
    for t in tokens:
        s = _latest_snapshot(session, t.id)
        if s:
            snaps.append((t, s))

    winners = [t for t in tokens if t.classification and "winner" in t.classification.value]
    rugs = [
        t
        for t in tokens
        if t.classification in (TokenClassification.hard_rug, TokenClassification.soft_rug)
    ]

    def sort_by_score(ts: list[Token]) -> list[Token]:
        return sorted(ts, key=lambda x: float(x.intel_score or 0), reverse=True)

    top_winners = [
        {"mint": t.mint_address, "name": token_display_name(t), "label": t.classification.value if t.classification else None, "score": t.intel_score}
        for t in sort_by_score(winners)[:15]
    ]
    top_rugs = [
        {"mint": t.mint_address, "name": token_display_name(t), "label": t.classification.value if t.classification else None, "score": t.intel_score}
        for t in sort_by_score(rugs)[:15]
    ]

    tta_list = [float(s.time_to_ath_seconds) for _, s in snaps if s.time_to_ath_seconds is not None]
    ath_list = [float(s.ath_market_cap or 0) for _, s in snaps if s.ath_market_cap is not None]
    dd_list = [float(s.drawdown_from_ath) for _, s in snaps if s.drawdown_from_ath is not None]

    fastest_ath = min(tta_list) if tta_list else None
    highest_ath = max(ath_list) if ath_list else None
    avg_tta = fmean(tta_list) if tta_list else None
    avg_dd = fmean(dd_list) if dd_list else None

    wc = Counter((t.classification.value if t.classification else "unknown") for t in tokens)

    # Theme from winner names
    theme_counter: Counter[str] = Counter()
    for t in winners:
        theme_counter.update(_words(token_display_name(t)))

    # Social verification impact
    from pump_intel.db.models import TokenSocial

    verified_scores: list[float] = []
    unverified_scores: list[float] = []
    for t in tokens:
        q = select(TokenSocial).where(TokenSocial.token_id == t.id, TokenSocial.platform == "twitter")
        soc = session.execute(q).scalars().first()
        sc = float(t.intel_score or 0)
        if soc and soc.x_verified:
            verified_scores.append(sc)
        else:
            unverified_scores.append(sc)

    structured: dict[str, Any] = {
        "report_date": report_date.isoformat(),
        "total_coins_scanned": len(scanned_token_ids),
        "classification_mix": dict(wc),
        "top_winners": top_winners,
        "top_rugs": top_rugs,
        "fastest_ath_seconds": fastest_ath,
        "highest_ath_market_cap": highest_ath,
        "average_time_to_ath_seconds": avg_tta,
        "average_drawdown_after_ath": avg_dd,
        "winner_theme_top": theme_counter.most_common(20),
        "ticker_pattern_analysis": _ticker_patterns([t.ticker or "" for t in tokens if t.ticker]),
        "creator_reputation_insights": _creator_insights(session, tokens),
        "social_verification_impact": {
            "avg_score_verified_x": fmean(verified_scores) if verified_scores else None,
            "avg_score_unverified": fmean(unverified_scores) if unverified_scores else None,
            "verified_count": len(verified_scores),
            "unverified_count": len(unverified_scores),
        },
        "final_market_assessment": _market_assessment(wc, avg_dd, len(winners), len(rugs)),
    }

    q = select(DailyMarketReport).where(DailyMarketReport.report_date == report_date)
    existing = session.execute(q).scalar_one_or_none()
    if existing:
        rep = existing
        rep.coins_scanned = len(scanned_token_ids)
        rep.structured_stats = structured
    else:
        rep = DailyMarketReport(report_date=report_date, coins_scanned=len(scanned_token_ids), structured_stats=structured)
        session.add(rep)
    session.flush()

    session.execute(delete(WinnerPattern).where(WinnerPattern.report_id == rep.id))
    ticker_analysis = structured["ticker_pattern_analysis"]
    for word, n in theme_counter.most_common(30):
        session.add(
            WinnerPattern(
                report_id=rep.id,
                pattern_kind="name_theme",
                pattern_key=word,
                weight=float(n),
                supporting_mints=[t.mint_address for t in winners if word in _words(token_display_name(t))][:20],
            )
        )
    for suf, n in Counter(ticker_analysis.get("suffix_counts") or {}).most_common(10):
        session.add(
            WinnerPattern(
                report_id=rep.id,
                pattern_kind="ticker_suffix",
                pattern_key=suf,
                weight=float(n),
                supporting_mints=[t.mint_address for t in tokens if (t.ticker or "").upper().endswith(suf)][:20],
            )
        )

    return rep


def _creator_insights(session: Session, tokens: list[Token]) -> list[dict[str, Any]]:
    from pump_intel.db.models import CreatorWallet

    by_c: dict[int, list[Token]] = {}
    for t in tokens:
        if t.creator_wallet_id:
            by_c.setdefault(t.creator_wallet_id, []).append(t)
    out: list[dict[str, Any]] = []
    for cid, ts in sorted(by_c.items(), key=lambda x: len(x[1]), reverse=True)[:12]:
        cw = session.get(CreatorWallet, cid)
        if not cw:
            continue
        scores = [float(x.intel_score or 0) for x in ts]
        rugs = sum(1 for x in ts if x.classification in (TokenClassification.hard_rug, TokenClassification.soft_rug))
        out.append(
            {
                "creator_wallet": cw.wallet_address,
                "tokens_in_scan": len(ts),
                "avg_intel_score": round(fmean(scores), 2) if scores else None,
                "rug_like_in_scan": rugs,
                "stored_reputation": cw.reputation_score,
            }
        )
    return out


def _market_assessment(mix: Counter[str], avg_dd: float | None, n_win: int, n_rug: int) -> str:
    parts = [
        f"Scan covered {sum(mix.values())} classified tokens.",
        f"Winner-tagged tokens: {n_win}; rug-tagged tokens: {n_rug}.",
    ]
    if avg_dd is not None:
        parts.append(f"Mean drawdown from ATH across observed snapshots: {avg_dd:.2%}.")
    top = mix.most_common(3)
    parts.append("Top labels: " + ", ".join(f"{k} ({v})" for k, v in top) + ".")
    return " ".join(parts)
