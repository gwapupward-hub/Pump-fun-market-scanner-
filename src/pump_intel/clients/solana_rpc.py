from __future__ import annotations

import asyncio
import logging
from types import TracebackType
from typing import Any

import httpx

from pump_intel.config import get_settings
from pump_intel.http import with_retry

log = logging.getLogger(__name__)


class SolanaRPCClient:
    """Thin pooled JSON-RPC client used for holder enrichment.

    Use as an async context manager. `enrich_largest_accounts(mints)` runs
    requests concurrently under a Semaphore bounded by
    `Settings.solana_rpc_concurrency`.
    """

    def __init__(self) -> None:
        s = get_settings()
        self._url = s.solana_rpc_url
        self._concurrency = s.solana_rpc_concurrency
        self._retry_attempts = s.http_retry_attempts
        self._retry_base = s.http_retry_base_delay_s
        self._timeout = httpx.Timeout(25.0, connect=10.0)
        self._client: httpx.AsyncClient | None = None
        self._sem: asyncio.Semaphore | None = None

    @property
    def enabled(self) -> bool:
        return self._url is not None

    async def __aenter__(self) -> SolanaRPCClient:
        if self.enabled:
            self._client = httpx.AsyncClient(timeout=self._timeout)
            self._sem = asyncio.Semaphore(self._concurrency)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_token_largest_accounts(self, mint: str) -> dict[str, Any] | None:
        if not self.enabled or self._client is None or self._sem is None:
            return None
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenLargestAccounts",
            "params": [mint, {"commitment": "processed"}],
        }
        client = self._client

        @with_retry(
            attempts=self._retry_attempts,
            base_delay=self._retry_base,
            op_name=f"solana getTokenLargestAccounts {mint[:8]}",
        )
        async def _do() -> httpx.Response:
            return await client.post(self._url, json=payload)  # type: ignore[arg-type]

        try:
            async with self._sem:
                r = await _do()
        except httpx.HTTPError as exc:
            log.info("solana rpc error mint=%s err=%s", mint, exc)
            return {"error": str(exc)}
        if r.status_code == 429:
            log.warning("solana rpc rate limited for mint=%s", mint)
            return {"error": "rate_limited", "status": 429}
        if r.status_code >= 400:
            return {"error": f"http {r.status_code}: {r.text[:200]}"}
        try:
            return r.json()
        except ValueError as exc:
            return {"error": f"invalid json: {exc}"}


def parse_largest_accounts_response(
    resp: dict[str, Any] | None,
) -> tuple[int | None, float | None, float | None, str | None]:
    """Return (holder_count, top1_pct, top5_pct, error_message)."""
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
    total_ui = sum(amounts)
    if total_ui <= 0:
        return len(values), None, None, None
    sorted_amts = sorted(amounts, reverse=True)
    top1 = (sorted_amts[0] / total_ui) * 100.0
    top5 = (sum(sorted_amts[:5]) / total_ui) * 100.0
    return len(values), top1, top5, None


__all__ = ["SolanaRPCClient", "parse_largest_accounts_response"]
