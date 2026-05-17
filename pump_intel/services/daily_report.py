from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

import psycopg

from pump_intel.db import repo
from pump_intel.services.rug_detection import detect_rug_signals, persist_signals
from pump_intel.services.scoring import score_token
from pump_intel.services.winner_classification import Classification, classify_token


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _theme_tokens(name: str) -> list[str]:
    cleaned = re.sub(r"[^a-zA-Z0-9\s]+", " ", name.lower())
    stop = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "coin",
        "token",
        "inu",
        "official",
        "real",
        "new",
    }
    return [w for w in cleaned.split() if len(w) >= 3 and w not in stop]


def analyze_and_update_tokens(conn: psycopg.Connection, *, since: datetime) -> None:
    rows = repo.tokens_touched_since(conn, since)
    for t in rows:
        token_id = int(t["id"])
        creator_id = int(t["creator_wallet_id"])

        snaps = repo.list_snapshots_last_n(conn, token_id, limit=10)
        social_rows = repo.fetch_social_rows(conn, token_id)

        creator_other_rugs = repo.creator_rug_count_excluding_token(conn, creator_id, token_id)
        latest_dev = _f(snaps[0].get("dev_sell_fraction")) if snaps else None

        signals = detect_rug_signals(
            token_row=t,
            snapshots_desc=snaps,
            social_rows=social_rows,
            creator_rug_events_on_other_tokens=creator_other_rugs,
            dev_sell_fraction=latest_dev,
        )

        persist_signals(conn, token_id, signals)

        stats_pre = repo.creator_token_stats(conn, creator_id)
        rugs_pre = int(stats_pre["rugs"])
        grads_pre = int(stats_pre["grads"])
        total_pre = max(int(stats_pre["total"]), 1)
        reputation_pre = max(-10.0, min(10.0, (grads_pre * 3.0) - (rugs_pre * 4.0) + (total_pre * 0.05)))

        breakdown = score_token(
            market_cap_usd=_f(t.get("market_cap_usd")),
            volume_24h_usd=_f(t.get("volume_24h_usd")),
            holder_count=int(t["holder_count"]) if t.get("holder_count") is not None else None,
            top_holder_concentration=_f(t.get("top_holder_concentration")),
            buy_sell_ratio=_f(t.get("buy_sell_ratio")),
            bonding_curve_progress=_f(t.get("bonding_curve_progress")),
            social_verified_x=t.get("social_verified_x"),
            has_website=bool(t.get("has_website")),
            has_telegram=bool(t.get("has_telegram")),
            creator_reputation=reputation_pre,
        )

        cls: Classification = classify_token(
            migration_status=str(t.get("migration_status") or "unknown"),
            score=breakdown,
            signals=signals,
            volume_24h_usd=_f(t.get("volume_24h_usd")),
            holder_count=int(t["holder_count"]) if t.get("holder_count") is not None else None,
            bonding_curve_progress=_f(t.get("bonding_curve_progress")),
            market_cap_usd=_f(t.get("market_cap_usd")),
            social_verified_x=t.get("social_verified_x"),
        )

        repo.update_token_classification(conn, token_id, cls, breakdown.total)

        stats = repo.creator_token_stats(conn, creator_id)
        rugs = int(stats["rugs"])
        grads = int(stats["grads"])
        total = max(int(stats["total"]), 1)
        reputation = max(-10.0, min(10.0, (grads * 3.0) - (rugs * 4.0) + (total * 0.05)))

        risk_flags = {
            "creator_total_tokens": total,
            "creator_rug_tokens": rugs,
            "creator_graduated_tokens": grads,
        }
        repo.update_creator_wallet_stats(
            conn,
            creator_id,
            total_tokens=total,
            rug_count=rugs,
            graduate_count=grads,
            reputation_score=float(reputation),
            risk_flags=risk_flags,
        )


def _top_by(
    tokens: Iterable[dict[str, Any]],
    *,
    key: str,
    reverse: bool = True,
    k: int = 10,
) -> list[dict[str, Any]]:
    rows = [t for t in tokens if t.get(key) is not None]
    rows.sort(key=lambda r: float(r[key]), reverse=reverse)
    return rows[:k]


def build_structured_report(conn: psycopg.Connection, *, report_date: date, coins_scanned: int) -> dict[str, Any]:
    tokens = repo.all_tokens_latest(conn, limit=50_000)

    winners = [t for t in tokens if str(t.get("classification") or "").endswith("winner")]

    ath_times = [int(t["time_to_ath_seconds"]) for t in tokens if t.get("time_to_ath_seconds") is not None]
    aths = [_f(t.get("ath_market_cap_usd")) for t in tokens if _f(t.get("ath_market_cap_usd"))]

    snaps_drawdowns: list[float] = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT drawdown_from_ath
            FROM token_snapshots
            WHERE captured_at >= %s AND drawdown_from_ath IS NOT NULL
            """,
            (datetime.now(timezone.utc) - timedelta(days=2),),
        )
        for row in cur.fetchall():
            v = _f(row.get("drawdown_from_ath"))
            if v is not None and not math.isnan(v):
                snaps_drawdowns.append(float(v))

    verified = [t for t in tokens if t.get("social_verified_x") is True]
    unverified = [t for t in tokens if t.get("social_verified_x") is not True]

    def avg_mc(rows: list[dict[str, Any]]) -> float | None:
        vals = [_f(r.get("market_cap_usd")) for r in rows]
        vals = [v for v in vals if v is not None]
        if not vals:
            return None
        return float(sum(vals) / len(vals))

    theme_counter: Counter[str] = Counter()
    for t in winners[:50]:
        for tok in _theme_tokens(str(t.get("name") or "")):
            theme_counter[tok] += 1

    ticker_lengths = [len(str(t.get("ticker") or "")) for t in tokens]
    suffix_counter: Counter[str] = Counter()
    for t in tokens:
        tick = str(t.get("ticker") or "").upper()
        if len(tick) >= 3:
            suffix_counter[tick[-3:]] += 1

    winner_pool = [t for t in tokens if str(t.get("classification") or "").endswith("winner")]
    winner_pool.sort(key=lambda r: float(r.get("score_total") or 0.0), reverse=True)
    top_winners = [
        {
            "mint": t.get("mint_address"),
            "name": t.get("name"),
            "ticker": t.get("ticker"),
            "classification": t.get("classification"),
            "score": _f(t.get("score_total")),
            "ath": _f(t.get("ath_market_cap_usd")),
            "mc": _f(t.get("market_cap_usd")),
        }
        for t in winner_pool[:15]
    ]

    top_rugs = [
        {
            "mint": t.get("mint_address"),
            "name": t.get("name"),
            "ticker": t.get("ticker"),
            "classification": t.get("classification"),
            "mc": _f(t.get("market_cap_usd")),
            "ath": _f(t.get("ath_market_cap_usd")),
        }
        for t in sorted(
            [x for x in tokens if "rug" in str(x.get("classification") or "")],
            key=lambda r: float(r.get("ath_market_cap_usd") or 0.0) - float(r.get("market_cap_usd") or 0.0),
            reverse=True,
        )[:15]
    ]

    fastest_ath = min(ath_times) if ath_times else None
    highest_ath = max(aths) if aths else None
    avg_tta = float(sum(ath_times) / len(ath_times)) if ath_times else None
    avg_dd = float(sum(snaps_drawdowns) / len(snaps_drawdowns)) if snaps_drawdowns else None

    creator_rows = _top_by(tokens, key="score_total", reverse=True, k=200)
    creator_rep = []
    seen: set[int] = set()
    for t in creator_rows:
        cid = int(t["creator_wallet_id"])
        if cid in seen:
            continue
        seen.add(cid)
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM creator_wallets WHERE id = %s", (cid,))
            cw = cur.fetchone()
        if cw:
            creator_rep.append(
                {
                    "creator_wallet_id": cid,
                    "address": cw.get("address"),
                    "reputation_score": _f(cw.get("reputation_score")),
                    "rug_count": int(cw.get("rug_count") or 0),
                    "graduate_count": int(cw.get("graduate_count") or 0),
                }
            )
        if len(creator_rep) >= 10:
            break

    return {
        "report_date": report_date.isoformat(),
        "coins_scanned": coins_scanned,
        "universe_size": len(tokens),
        "top_winners": top_winners,
        "top_rugs": top_rugs,
        "fastest_time_to_ath_seconds": fastest_ath,
        "highest_ath_market_cap_usd": highest_ath,
        "avg_time_to_ath_seconds": avg_tta,
        "avg_drawdown_after_ath": avg_dd,
        "winner_themes": [{"token": w, "count": int(c)} for w, c in theme_counter.most_common(25)],
        "ticker_length": {
            "avg": float(sum(ticker_lengths) / len(ticker_lengths)) if ticker_lengths else None,
            "max": max(ticker_lengths) if ticker_lengths else None,
            "min": min(ticker_lengths) if ticker_lengths else None,
        },
        "ticker_suffixes_top": [{"suffix": s, "count": int(c)} for s, c in suffix_counter.most_common(15)],
        "social_verification": {
            "verified_count": len(verified),
            "unverified_or_unknown_count": len(unverified),
            "avg_market_cap_verified_usd": avg_mc(verified),
            "avg_market_cap_unverified_usd": avg_mc(unverified),
        },
        "classification_counts": dict(Counter(str(t.get("classification") or "unknown") for t in tokens)),
        "creator_insights": creator_rep,
    }


def build_winner_pattern_rows(structured: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in structured.get("winner_themes", [])[:30]:
        word = str(item.get("token"))
        freq = int(item.get("count") or 0)
        rows.append(
            {
                "pattern_type": "theme",
                "pattern_value": word,
                "frequency": freq,
                "strength": float(freq),
                "evidence": {"source": "winner_names"},
            }
        )
    for item in structured.get("ticker_suffixes_top", [])[:20]:
        suf = str(item.get("suffix"))
        freq = int(item.get("count") or 0)
        rows.append(
            {
                "pattern_type": "ticker_suffix",
                "pattern_value": suf,
                "frequency": freq,
                "strength": float(freq),
                "evidence": {"source": "all_tickers"},
            }
        )
    return rows
