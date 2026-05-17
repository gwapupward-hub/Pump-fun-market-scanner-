from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import psycopg

from pump_intel.db import execute, executemany, fetch_all_dict, fetch_one_dict, jsonb


def _today_utc() -> date:
    return datetime.now(tz=UTC).date()


def _tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-zA-Z]{3,}", text.lower()) if len(t) <= 32]


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_daily_report(conn: psycopg.Connection, report_date: date | None = None) -> dict[str, Any]:
    report_date = report_date or _today_utc()
    day_start = datetime.combine(report_date, datetime.min.time(), tzinfo=UTC)
    day_end = day_start + timedelta(days=1)

    scanned = fetch_one_dict(
        conn,
        """
        SELECT COUNT(DISTINCT mint)::int AS c
        FROM token_snapshots
        WHERE snapshot_at >= %s AND snapshot_at < %s
        """,
        (day_start, day_end),
    )
    total_scanned = int(scanned["c"] or 0) if scanned else 0

    winners = fetch_all_dict(
        conn,
        """
        SELECT t.mint, t.name, t.ticker, t.classification, t.score,
               s.market_cap_usd, s.ath_market_cap_usd, s.time_to_ath_seconds, s.migration_status
        FROM tokens t
        JOIN LATERAL (
            SELECT *
            FROM token_snapshots ts
            WHERE ts.mint = t.mint
            ORDER BY ts.snapshot_at DESC
            LIMIT 1
        ) s ON true
        WHERE t.classification IN ('graduated_winner','viral_winner','bonding_winner','micro_winner')
          AND t.last_seen_at >= %s AND t.last_seen_at < %s
        ORDER BY s.ath_market_cap_usd DESC NULLS LAST
        LIMIT 25
        """,
        (day_start, day_end),
    )

    rugs = fetch_all_dict(
        conn,
        """
        SELECT t.mint, t.name, t.ticker, t.classification, t.score,
               s.market_cap_usd, s.ath_market_cap_usd
        FROM tokens t
        JOIN LATERAL (
            SELECT *
            FROM token_snapshots ts
            WHERE ts.mint = t.mint
            ORDER BY ts.snapshot_at DESC
            LIMIT 1
        ) s ON true
        WHERE t.classification IN ('hard_rug','soft_rug')
          AND t.last_seen_at >= %s AND t.last_seen_at < %s
        ORDER BY s.ath_market_cap_usd DESC NULLS LAST
        LIMIT 25
        """,
        (day_start, day_end),
    )

    ath_stats = fetch_one_dict(
        conn,
        """
        SELECT
            MIN(time_to_ath_seconds) FILTER (
                WHERE time_to_ath_seconds IS NOT NULL AND time_to_ath_seconds > 0
            ) AS fastest_ath_seconds,
            MAX(ath_market_cap_usd) AS highest_ath_usd,
            AVG(time_to_ath_seconds) FILTER (
                WHERE time_to_ath_seconds IS NOT NULL AND time_to_ath_seconds > 0
            ) AS avg_time_to_ath_seconds,
            AVG(
                CASE
                    WHEN ath_market_cap_usd IS NOT NULL AND ath_market_cap_usd > 0
                         AND market_cap_usd IS NOT NULL
                    THEN GREATEST(0, LEAST(1, 1 - (market_cap_usd / ath_market_cap_usd)))
                END
            ) AS avg_drawdown_after_ath
        FROM token_snapshots
        WHERE snapshot_at >= %s AND snapshot_at < %s
        """,
        (day_start, day_end),
    )

    social = fetch_one_dict(
        conn,
        """
        WITH latest AS (
            SELECT DISTINCT ON (ts.mint)
                ts.mint,
                ts.snapshot_at
            FROM token_snapshots ts
            WHERE ts.snapshot_at >= %s AND ts.snapshot_at < %s
            ORDER BY ts.mint, ts.snapshot_at DESC
        ),
        joined AS (
            SELECT
                l.mint,
                BOOL_OR(ts.is_present AND ts.platform = 'twitter')  AS has_twitter,
                BOOL_OR(ts.is_present AND ts.platform = 'telegram') AS has_tg,
                BOOL_OR(ts.is_present AND ts.platform = 'website')  AS has_web
            FROM latest l
            JOIN token_socials ts ON ts.mint = l.mint
            GROUP BY l.mint
        )
        SELECT
            AVG(CASE WHEN has_twitter THEN 1 ELSE 0 END) AS twitter_rate,
            AVG(CASE WHEN has_tg      THEN 1 ELSE 0 END) AS tg_rate,
            AVG(CASE WHEN has_web     THEN 1 ELSE 0 END) AS web_rate
        FROM joined
        """,
        (day_start, day_end),
    )

    name_rows = fetch_all_dict(
        conn,
        """
        SELECT t.name, t.ticker, t.classification
        FROM tokens t
        WHERE EXISTS (
            SELECT 1 FROM token_snapshots ts
            WHERE ts.mint = t.mint
              AND ts.snapshot_at >= %s
              AND ts.snapshot_at < %s
        )
        """,
        (day_start, day_end),
    )

    theme_counter: Counter[str] = Counter()
    ticker_counter: Counter[str] = Counter()
    for row in name_rows:
        for tok in _tokenize(str(row.get("name") or "")):
            theme_counter[tok] += 1
        ticker = str(row.get("ticker") or "").upper()
        if ticker:
            ticker_counter[ticker] += 1

    top_themes = [{"token": k, "count": v} for k, v in theme_counter.most_common(25)]
    top_tickers = [{"ticker": k, "count": v} for k, v in ticker_counter.most_common(25)]

    creator_insights = fetch_all_dict(
        conn,
        """
        SELECT address, tokens_created, reputation_score, hard_rug_count, soft_rug_count, winner_count
        FROM creator_wallets
        ORDER BY reputation_score ASC, tokens_created DESC
        LIMIT 15
        """,
    )

    metrics: dict[str, Any] = {
        "report_date": str(report_date),
        "total_coins_scanned": total_scanned,
        "top_winners": winners,
        "top_rugs": rugs,
        "fastest_ath_seconds": ath_stats.get("fastest_ath_seconds") if ath_stats else None,
        "highest_ath_usd": _to_float(ath_stats.get("highest_ath_usd")) if ath_stats else None,
        "avg_time_to_ath_seconds": _to_float(ath_stats.get("avg_time_to_ath_seconds")) if ath_stats else None,
        "avg_drawdown_after_ath": _to_float(ath_stats.get("avg_drawdown_after_ath")) if ath_stats else None,
        "winner_theme_tokens": top_themes,
        "ticker_patterns": top_tickers,
        "creator_wallet_low_reputation": creator_insights,
        "social_presence_rates": dict(social) if social else {},
        "final_market_assessment": _market_assessment(
            total_scanned, winners, rugs, ath_stats, social
        ),
    }

    structured = {
        "headline": metrics["final_market_assessment"],
        "totals": {"scanned": total_scanned},
        "liquidity_quality_proxy": {
            "avg_drawdown_after_ath": metrics.get("avg_drawdown_after_ath"),
            "avg_time_to_ath_seconds": metrics.get("avg_time_to_ath_seconds"),
        },
    }

    _persist_winner_patterns(conn, report_date, top_themes, top_tickers)
    return {"metrics": metrics, "structured_summary": structured}


def _market_assessment(
    scanned: int,
    winners: list[dict],
    rugs: list[dict],
    ath_stats: dict | None,
    social: dict | None,
) -> str:
    if scanned == 0:
        return (
            "No fresh snapshots were recorded for this UTC day; widen ingestion "
            "limits or confirm scheduler connectivity."
        )
    dd = _to_float(ath_stats.get("avg_drawdown_after_ath")) if ath_stats else None
    parts = [
        f"Scanned {scanned} distinct tokens with intraday snapshots.",
        f"Leaderboard shows up to {len(winners)} winner picks and {len(rugs)} elevated-risk listings (top-25 cap).",
    ]
    if dd is not None:
        parts.append(
            f"Mean post-ATH drawdown across the batch is about {dd * 100:.1f}% "
            "(USD mcap ratio heuristic)."
        )
    if social:
        tw = _to_float(social.get("twitter_rate")) or 0.0
        parts.append(f"Twitter link prevalence in social rows is ~{tw * 100:.1f}%.")
    return " ".join(parts)


def _persist_winner_patterns(
    conn: psycopg.Connection,
    report_date: date,
    themes: list[dict],
    tickers: list[dict],
) -> None:
    execute(conn, "DELETE FROM winner_patterns WHERE report_date = %s", (report_date,))
    rows: list[tuple[Any, ...]] = []
    for row in themes:
        rows.append((report_date, "name_token", row["token"], int(row["count"]), float(row["count"])))
    for row in tickers:
        rows.append((report_date, "ticker", row["ticker"], int(row["count"]), float(row["count"])))
    if not rows:
        return
    executemany(
        conn,
        """
        INSERT INTO winner_patterns (report_date, pattern_type, pattern_value, frequency, score)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (report_date, pattern_type, pattern_value) DO UPDATE SET
            frequency = EXCLUDED.frequency,
            score = EXCLUDED.score
        """,
        rows,
    )


def persist_daily_report(
    conn: psycopg.Connection,
    report_date: date,
    metrics: dict,
    structured: dict,
    ai_md: str | None,
    ai_model: str | None,
) -> None:
    execute(
        conn,
        """
        INSERT INTO daily_market_reports
            (report_date, metrics, structured_summary, ai_markdown, ai_model)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (report_date) DO UPDATE SET
            generated_at = NOW(),
            metrics = EXCLUDED.metrics,
            structured_summary = EXCLUDED.structured_summary,
            ai_markdown = EXCLUDED.ai_markdown,
            ai_model = EXCLUDED.ai_model
        """,
        (report_date, jsonb(metrics), jsonb(structured), ai_md, ai_model),
    )
