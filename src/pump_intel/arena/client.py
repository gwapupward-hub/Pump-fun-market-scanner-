from __future__ import annotations

import logging
from types import TracebackType
from typing import Any

import httpx

from pump_intel.arena.credentials import ArenaCredentials
from pump_intel.http import with_retry

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://arena.dev.fun/api/arena"


class ArenaAPIError(RuntimeError):
    """Non-2xx response from the arena API. Carries status code + decoded body."""

    def __init__(self, status_code: int, path: str, body: Any) -> None:
        self.status_code = status_code
        self.path = path
        self.body = body
        super().__init__(f"{path} returned {status_code}: {body!r}")


class ArenaClient:
    """Async client for arena.dev.fun. Use as an async context manager."""

    def __init__(
        self,
        credentials: ArenaCredentials,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = 20.0,
        retry_attempts: int = 3,
        retry_base_delay_s: float = 0.5,
    ) -> None:
        self._creds = credentials
        self._base = base_url.rstrip("/")
        self._headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-arena-api-key": credentials.api_key,
            "User-Agent": "pump-intel-arena/0.1",
        }
        self._timeout = httpx.Timeout(timeout_s, connect=10.0)
        self._retry_attempts = retry_attempts
        self._retry_base = retry_base_delay_s
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> ArenaClient:
        self._client = httpx.AsyncClient(headers=self._headers, timeout=self._timeout)
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

    def _ensure(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("ArenaClient must be used as an async context manager")
        return self._client

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        client = self._ensure()

        @with_retry(
            attempts=self._retry_attempts, base_delay=self._retry_base, op_name=f"GET {path}"
        )
        async def _do() -> httpx.Response:
            return await client.get(self._url(path), params=params)

        return await _do()

    async def _post(self, path: str, body: dict[str, Any]) -> httpx.Response:
        client = self._ensure()

        @with_retry(
            attempts=self._retry_attempts, base_delay=self._retry_base, op_name=f"POST {path}"
        )
        async def _do() -> httpx.Response:
            return await client.post(self._url(path), json=body)

        return await _do()

    # ------------------------------------------------------------------ public

    async def me(self) -> dict[str, Any]:
        return _decode(await self._get("/agent/me"), "/agent/me")

    async def list_active_competitions(self) -> Any:
        return _decode(await self._get("/competition/list-active"), "/competition/list-active")

    async def leaderboard(self, competition_id: str) -> dict[str, Any]:
        r = await self._get(
            "/competition/leaderboard", params={"competitionId": competition_id}
        )
        return _decode(r, "/competition/leaderboard")

    async def lobby(self, competition_id: str) -> dict[str, Any]:
        r = await self._get("/texas/lobby", params={"competitionId": competition_id})
        return _decode(r, "/texas/lobby")

    async def join_lobby(self, competition_id: str) -> dict[str, Any]:
        """Queue this agent into the matchmaking lobby.

        Returns the server response on success. 409 ("already in lobby") is
        translated to a normal return with `{"status":"already-queued"}` so
        callers don't need to special-case re-joins.
        """
        r = await self._post("/texas/join", {"competitionId": competition_id})
        if r.status_code == 409:
            return {"status": "already-queued", "raw": _safe_json(r)}
        return _decode(r, "/texas/join")

    async def pending_actions(self, competition_id: str) -> dict[str, Any]:
        r = await self._get(
            "/texas/pending-actions", params={"competitionId": competition_id}
        )
        return _decode(r, "/texas/pending-actions")

    async def recent_tables(
        self, competition_id: str, *, limit: int | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"competitionId": competition_id}
        if limit is not None:
            params["limit"] = limit
        return _decode(await self._get("/texas/recent-tables", params=params), "/texas/recent-tables")

    async def submit_action(self, body: dict[str, Any]) -> dict[str, Any]:
        """POST /texas/action. Body shape is provisional; see arena/bot.py."""
        return _decode(await self._post("/texas/action", body), "/texas/action")


def _safe_json(r: httpx.Response) -> Any:
    try:
        return r.json()
    except ValueError:
        return {"text": r.text[:500]}


def _decode(r: httpx.Response, path: str) -> Any:
    body = _safe_json(r)
    if r.status_code >= 400:
        raise ArenaAPIError(r.status_code, path, body)
    return body
