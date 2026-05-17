from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from pump_intel.config import get_settings
from pump_intel.db.models import DailyMarketReport

log = logging.getLogger(__name__)


def _fallback_markdown(stats: dict[str, Any]) -> str:
    lines = [
        "# Pump.fun market intelligence",
        "",
        f"**Report date:** {stats.get('report_date')}",
        f"**Coins scanned:** {stats.get('total_coins_scanned')}",
        "",
        "## Highlights",
        f"- Fastest time to ATH (seconds): {stats.get('fastest_ath_seconds')}",
        f"- Highest ATH market cap observed: {stats.get('highest_ath_market_cap')}",
        f"- Average time to ATH (seconds): {stats.get('average_time_to_ath_seconds')}",
        f"- Average drawdown from ATH: {stats.get('average_drawdown_after_ath')}",
        "",
        "## Classification mix",
        json.dumps(stats.get("classification_mix") or {}, indent=2),
        "",
        "## Top winners",
        json.dumps(stats.get("top_winners") or [], indent=2),
        "",
        "## Top rugs",
        json.dumps(stats.get("top_rugs") or [], indent=2),
        "",
        "## Themes (winning names)",
        json.dumps(stats.get("winner_theme_top") or [], indent=2),
        "",
        "## Ticker patterns",
        json.dumps(stats.get("ticker_pattern_analysis") or {}, indent=2),
        "",
        "## Creator reputation (this scan)",
        json.dumps(stats.get("creator_reputation_insights") or [], indent=2),
        "",
        "## Social verification impact",
        json.dumps(stats.get("social_verification_impact") or {}, indent=2),
        "",
        "## Assessment",
        str(stats.get("final_market_assessment") or ""),
        "",
        "_Analytics only — not trading advice._",
    ]
    return "\n".join(lines)


def enrich_report_with_ai(session: Session, report: DailyMarketReport) -> str:
    settings = get_settings()
    stats = dict(report.structured_stats or {})

    if not settings.ai_summary_enabled:
        md = _fallback_markdown(stats)
        report.ai_markdown = md
        return md

    if not settings.openai_api_key:
        md = _fallback_markdown(stats)
        report.ai_markdown = md
        return md

    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        prompt = (
            "You are a crypto *market intelligence* analyst (not a trader). "
            "Given structured JSON stats from a Pump.fun analytics scan, write a concise markdown brief. "
            "Sections: Executive summary, Liquidity & momentum, Rugs & structural risks, "
            "Socials & verification, Creator behavior, Pattern notes (names/tickers), Closing outlook. "
            "Be factual, avoid telling anyone to buy or sell. Data:\n"
            + json.dumps(stats, indent=2)[:120_000]
        )
        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": "Write clear markdown. No trading instructions."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.35,
        )
        md = (resp.choices[0].message.content or "").strip() or _fallback_markdown(stats)
        report.ai_markdown = md
        return md
    except Exception as e:  # noqa: BLE001
        log.warning("AI summary failed, using fallback: %s", e)
        md = _fallback_markdown(stats)
        report.ai_markdown = md
        return md
