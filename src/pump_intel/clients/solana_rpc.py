from __future__ import annotations

import logging
from typing import Any

import httpx

from pump_intel.config import get_settings

log = logging.getLogger(__name__)


async def fetch_token_largest_accounts(mint: str) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.solana_rpc_url:
        return None
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenLargestAccounts",
        "params": [mint, {"commitment": "processed"}],
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(25.0)) as client:
            r = await client.post(settings.solana_rpc_url, json=payload)
            if r.status_code == 429:
                log.warning("Solana RPC rate limited for mint=%s", mint)
                return {"error": "rate_limited", "status": 429}
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as exc:
        log.info("Solana RPC error mint=%s err=%s", mint, exc)
        return {"error": str(exc)}


def parse_largest_accounts_response(resp: dict[str, Any] | None) -> tuple[int | None, float | None, float | None, str | None]:
    if not resp:
        return None, None, None, None
    if resp.get("error"):
        err = resp.get("error")
        if isinstance(err, dict):
            return None, None, None, err.get("message") or str(err)
        return None, None, None, str(err)
    result = resp.get("result") or {}
    values = result.get("value") or []
    if not isinstance(values, list) or not values:
        return 0, None, None, None
    total_ui = 0.0
    amounts: list[float] = []
    for row in values:
        ui = row.get("uiAmount")
        if ui is None and row.get("uiAmountString") is not None:
            ui = row.get("uiAmountString")
        if ui is None:
            continue
        try:
            amt = float(ui)
        except (TypeError, ValueError):
            continue
        amounts.append(amt)
        total_ui += amt
    if total_ui <= 0:
        return len(values), None, None, None
    sorted_amts = sorted(amounts, reverse=True)
    top1 = (sorted_amts[0] / total_ui) * 100.0 if sorted_amts else None
    top5_sum = sum(sorted_amts[:5])
    top5 = (top5_sum / total_ui) * 100.0 if sorted_amts else None
    return len(values), top1, top5, None
