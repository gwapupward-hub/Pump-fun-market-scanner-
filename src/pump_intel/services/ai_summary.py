from __future__ import annotations

import logging
from typing import Any

from pump_intel.config import get_settings
from pump_intel.db.json import dumps_json

log = logging.getLogger(__name__)


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
        dumps_json(metrics.get("social_presence_rates") or {}),
        "```",
        "",
        "## Top winner tickers (sample)",
        "```json",
        dumps_json((metrics.get("top_winners") or [])[:8]),
        "```",
        "",
        "## Top rug labels (sample)",
        "```json",
        dumps_json((metrics.get("top_rugs") or [])[:8]),
        "```",
        "",
        "_This fallback report is generated without an LLM. Configure `OPENAI_API_KEY` for richer synthesis._",
    ]
    return "\n".join(lines)


def generate_ai_markdown(metrics: dict[str, Any], structured: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    if not settings.openai_api_key:
        return {"markdown": _fallback_markdown(metrics, structured), "model": "template-fallback"}

    try:
        from openai import OpenAI
    except ImportError:
        log.warning("openai dependency not installed; falling back to template summary")
        return {
            "markdown": _fallback_markdown(metrics, structured),
            "model": "openai-missing-dependency",
        }

    client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
    payload = dumps_json({"metrics": metrics, "structured": structured})[:120_000]
    prompt = (
        "You are a crypto market intelligence analyst. Write a concise markdown brief for "
        "risk-minded readers. Do not recommend trades, do not instruct buying or selling, and "
        "avoid financial advice. Focus on patterns, rugs, graduation activity, social presence, "
        "and creator reputation signals.\n\n"
        f"Structured JSON metrics:\n{payload}"
    )
    try:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": "Analytics only. No trade execution. No buy/sell instructions."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.35,
        )
    except Exception as exc:  # openai surfaces many exception types; treat all as recoverable.
        log.warning("openai call failed; using fallback markdown", extra={"err": repr(exc)})
        return {
            "markdown": _fallback_markdown(metrics, structured),
            "model": "openai-error-fallback",
        }
    md = (resp.choices[0].message.content or "").strip() or _fallback_markdown(metrics, structured)
    return {"markdown": md, "model": settings.openai_model}
