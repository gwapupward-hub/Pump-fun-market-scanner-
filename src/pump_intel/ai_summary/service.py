from __future__ import annotations

import json
from typing import Any

from pump_intel.config import Settings


def generate_ai_markdown(settings: Settings, stats: dict[str, Any], structured_md: str) -> str | None:
    if not settings.ai_summary_enabled:
        return None
    if not settings.openai_api_key:
        return None
    try:
        from openai import OpenAI
    except Exception:
        return None

    client = OpenAI(api_key=settings.openai_api_key)
    payload = {
        "stats": stats,
        "structured_report_excerpt": structured_md[:6000],
    }
    prompt = (
        "You are a crypto meme-market analyst. Using ONLY the JSON stats and excerpt, "
        "write a concise markdown brief: key risks, pockets of strength, what changed vs typical tape, "
        "and what to watch next. No trading instructions; no buy/sell language; analytics only."
    )
    resp = client.chat.completions.create(
        model=settings.openai_model,
        temperature=0.35,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload, default=str)},
        ],
    )
    msg = resp.choices[0].message.content
    return msg.strip() if msg else None
