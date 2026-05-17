from __future__ import annotations

import json
from typing import Any

import httpx

from pump_intel.config import Settings


def render_fallback_markdown(structured: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Pump.fun market intelligence — {structured.get('report_date')}")
    lines.append("")
    lines.append("## Executive snapshot")
    lines.append(f"- Coins scanned this run: **{structured.get('coins_scanned')}**")
    lines.append(f"- Tracked universe: **{structured.get('universe_size')}** tokens")
    lines.append("")
    lines.append("## Highlights")
    lines.append(f"- Fastest time-to-ATH (seconds): `{structured.get('fastest_time_to_ath_seconds')}`")
    lines.append(f"- Highest ATH (USD): `{structured.get('highest_ath_market_cap_usd')}`")
    lines.append(f"- Average time-to-ATH (seconds): `{structured.get('avg_time_to_ath_seconds')}`")
    lines.append(f"- Average drawdown after ATH (recent snapshots): `{structured.get('avg_drawdown_after_ath')}`")
    lines.append("")
    lines.append("## Classifications")
    lines.append("```json")
    lines.append(json.dumps(structured.get("classification_counts", {}), indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("## Top winners (score-ranked)")
    lines.append("```json")
    lines.append(json.dumps(structured.get("top_winners", []), indent=2)[:8000])
    lines.append("```")
    lines.append("")
    lines.append("## Top rugs (ATH vs current MC gap)")
    lines.append("```json")
    lines.append(json.dumps(structured.get("top_rugs", []), indent=2)[:8000])
    lines.append("```")
    lines.append("")
    lines.append("## Winner themes (name tokens)")
    lines.append("```json")
    lines.append(json.dumps(structured.get("winner_themes", []), indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## Ticker patterns")
    lines.append("```json")
    lines.append(json.dumps(structured.get("ticker_length", {}), indent=2))
    lines.append(json.dumps(structured.get("ticker_suffixes_top", []), indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## Social verification impact")
    lines.append("```json")
    lines.append(json.dumps(structured.get("social_verification", {}), indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## Creator wallet reputation (sample)")
    lines.append("```json")
    lines.append(json.dumps(structured.get("creator_insights", []), indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## Final market assessment (template)")
    lines.append(
        "Liquidity rotation remains highly path-dependent: verified social presence correlates with "
        "higher average attention proxies in this dataset, but rugs cluster around rapid post-ATH "
        "drawdowns and holder concentration shifts. Treat classifications as risk flags, not trade signals."
    )
    lines.append("")
    lines.append("_Analytics only. This system does not execute trades._")
    return "\n".join(lines)


def generate_ai_markdown(structured: dict[str, Any], settings: Settings) -> str:
    if not settings.openai_api_key:
        return render_fallback_markdown(structured)

    prompt = (
        "You are a crypto market intelligence analyst. Write a concise markdown report for traders "
        "summarizing Pump.fun-style meme coin telemetry. Emphasize risk, uncertainty, and data limits. "
        "Do not recommend buying or selling. Use the JSON stats as facts.\n\n"
        f"STATS_JSON:\n{json.dumps(structured, indent=2)[:24000]}"
    )

    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}
    body = {
        "model": settings.ai_model,
        "messages": [
            {"role": "system", "content": "You produce factual, cautious market intelligence in Markdown."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.35,
    }

    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
        return str(data["choices"][0]["message"]["content"])
