from __future__ import annotations

import json
from datetime import date
from typing import Any

from pump_intel.config import get_settings


def _fallback_markdown(metrics: dict[str, Any], structured: dict[str, Any]) -> str:
    lines = [
        f"# Pump.fun market intelligence — {metrics.get('report_date')}",
        "",
        "## Summary",
        structured.get("headline") or metrics.get("final_market_assessment") or "",
        "",
        "## Totals",
        f"- Distinct tokens scanned (UTC day): **{metrics.get('total_coins_scanned')}**",
        "",
        "## ATH telemetry (heuristic)",
        f"- Fastest time-to-ATH (seconds): `{metrics.get('fastest_ath_seconds')}`",
        f"- Highest ATH (USD): `{metrics.get('highest_ath_usd')}`",
        f"- Average time-to-ATH (seconds): `{metrics.get('avg_time_to_ath_seconds')}`",
        f"- Average drawdown after ATH (0-1): `{metrics.get('avg_drawdown_after_ath')}`",
        "",
        "## Social presence (link rows)",
        "```json",
        json.dumps(metrics.get("social_presence_rates") or {}, indent=2, default=str),
        "```",
        "",
        "## Top winner tickers (sample)",
        "```json",
        json.dumps((metrics.get("top_winners") or [])[:8], indent=2, default=str),
        "```",
        "",
        "## Top rug labels (sample)",
        "```json",
        json.dumps((metrics.get("top_rugs") or [])[:8], indent=2, default=str),
        "```",
        "",
        "_This fallback report is generated without an LLM. Configure `OPENAI_API_KEY` for richer synthesis._",
    ]
    return "\n".join(lines)


def generate_ai_markdown(metrics: dict[str, Any], structured: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    if not settings.openai_api_key:
        return {
            "markdown": _fallback_markdown(metrics, structured),
            "model": "template-fallback",
        }

    try:
        from openai import OpenAI
    except ImportError:
        return {
            "markdown": _fallback_markdown(metrics, structured),
            "model": "openai-missing-dependency",
        }

    client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
    prompt = (
        "You are a crypto market intelligence analyst. Write a concise markdown brief for risk-minded readers. "
        "Do not recommend trades, do not instruct buying or selling, and avoid financial advice. "
        "Focus on patterns, rugs, graduation activity, social presence, and creator reputation signals.\n\n"
        f"Structured JSON metrics:\n{json.dumps({'metrics': metrics, 'structured': structured}, default=str)[:120_000]}"
    )
    resp = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": "Analytics only. No trade execution. No buy/sell instructions."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.35,
    )
    md = resp.choices[0].message.content or ""
    return {"markdown": md, "model": settings.openai_model}
