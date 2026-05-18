"""Long-running poker bot for arena.dev.fun Texas Hold'em competitions.

The bot:
  1. Auto-joins the matchmaking lobby (idempotent).
  2. Polls `/texas/pending-actions` on a tunable interval.
  3. For each pending action, picks a move via `strategy.decide` and submits.
  4. Logs every raw pending-action payload and every action-submission body
     + response, so the exact server schema can be discovered in production.

Action submission body shape is not documented and the server returns
`{"error":"Error"}` on bad input without leaking which fields it wanted. The
bot starts with the most likely shape (`tableId`, `action`, `amount`) and
falls back through a small list of alternates on 400, logging each attempt.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from contextlib import suppress
from typing import Any

from pump_intel.arena.client import ArenaAPIError, ArenaClient
from pump_intel.arena.credentials import load_credentials
from pump_intel.arena.strategy import Decision, decide

log = logging.getLogger(__name__)


# ---- env knobs (no DB-coupled Settings dependency) -----------------------

def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ---- payload extraction --------------------------------------------------

_HOLE_KEYS = ("holeCards", "hole_cards", "cards", "hand", "playerCards")
_BOARD_KEYS = ("boardCards", "board", "communityCards", "community_cards")
_ACTIONS_KEYS = ("availableActions", "legalActions", "actions", "validActions")
_POT_KEYS = ("pot", "potChips", "potSize", "pot_size")
_TO_CALL_KEYS = ("toCall", "toCallChips", "amountToCall", "callAmount", "call_amount")
_BB_KEYS = ("bigBlind", "bb", "bigBlindAmount")
_TABLE_ID_KEYS = ("tableId", "id", "table_id")
_HAND_ID_KEYS = ("handId", "hand_id", "roundId", "round_id")
_ACTION_TOKEN_KEYS = ("actionId", "action_id", "actionToken", "token")
_SEAT_KEYS = ("seatNumber", "seat_number", "seat")


def _first(d: dict[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _flatten_action_strings(actions_field: Any) -> list[str]:
    """`actions` may be ['check','call'] or [{'action':'check'}, {'action':'raise', 'min':4}]."""
    if not actions_field:
        return []
    out: list[str] = []
    for a in actions_field:
        if isinstance(a, str):
            out.append(a)
        elif isinstance(a, dict):
            name = a.get("action") or a.get("name") or a.get("type")
            if isinstance(name, str):
                out.append(name)
    return out


def _extract_state(table: dict[str, Any]) -> dict[str, Any]:
    """Pull poker state from a pending-action payload, robust to naming variants."""
    # players sometimes nests our own seat under a `self`/`me`/`you` key
    me = table.get("self") or table.get("me") or table.get("you") or table
    return {
        "hole_cards": list(_first(me, _HOLE_KEYS, []) or _first(table, _HOLE_KEYS, []) or []),
        "board_cards": list(_first(table, _BOARD_KEYS, []) or []),
        "available_actions": _flatten_action_strings(_first(table, _ACTIONS_KEYS, [])),
        "pot_chips": int(_first(table, _POT_KEYS, 0) or 0),
        "to_call_chips": int(_first(table, _TO_CALL_KEYS, 0) or 0),
        "big_blind": int(_first(table, _BB_KEYS, 2) or 2),
        "table_id": _first(table, _TABLE_ID_KEYS),
        "hand_id": _first(table, _HAND_ID_KEYS),
        "action_token": _first(table, _ACTION_TOKEN_KEYS),
        "seat_number": _first(table, _SEAT_KEYS),
    }


def _candidate_bodies(state: dict[str, Any], decision: Decision) -> list[dict[str, Any]]:
    """Body shapes we'll try for /texas/action, in priority order."""
    table_id = state.get("table_id")
    hand_id = state.get("hand_id")
    token = state.get("action_token")
    seat = state.get("seat_number")
    action = decision.action
    amount = int(decision.amount)

    candidates: list[dict[str, Any]] = []
    # Most-likely shape
    candidates.append({"tableId": table_id, "action": action, "amount": amount})
    # With handId
    if hand_id is not None:
        candidates.append(
            {"tableId": table_id, "handId": hand_id, "action": action, "amount": amount}
        )
    # With seat
    if seat is not None:
        candidates.append(
            {
                "tableId": table_id,
                "seatNumber": seat,
                "action": action,
                "amount": amount,
            }
        )
    # With explicit action token (echo whatever pending-actions sent)
    if token is not None:
        candidates.append({"actionId": token, "action": action, "amount": amount})
    return [c for c in candidates if c.get("tableId") is not None or "actionId" in c]


# ---- bot core ------------------------------------------------------------

class PokerBot:
    def __init__(
        self,
        *,
        client: ArenaClient,
        competition_id: str,
        poll_interval_s: float = 2.0,
        auto_join: bool = True,
        dry_run: bool = False,
    ) -> None:
        self._client = client
        self._comp = competition_id
        self._interval = max(0.5, poll_interval_s)
        self._auto_join = auto_join
        self._dry_run = dry_run
        self._stop = asyncio.Event()
        # remember (table_id, hand_id, action_token) tuples we've already acted on
        self._seen_actions: set[tuple[Any, Any, Any]] = set()

    def request_stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        log.info("poker bot starting", extra={"competition_id": self._comp,
                                              "poll_interval_s": self._interval,
                                              "dry_run": self._dry_run})

        if self._auto_join:
            await self._safe_join()

        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception as exc:
                log.exception("bot tick failed: %s", exc)
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)

        log.info("poker bot stopped")

    async def _safe_join(self) -> None:
        try:
            resp = await self._client.join_lobby(self._comp)
            log.info("lobby join response", extra={"response": resp})
        except ArenaAPIError as exc:
            log.warning("lobby join failed status=%s body=%r", exc.status_code, exc.body)

    async def _tick(self) -> None:
        payload = await self._client.pending_actions(self._comp)
        tables = payload.get("tables") if isinstance(payload, dict) else None
        if not tables:
            return

        log.info("pending actions received", extra={"raw_payload": payload})
        for table in tables:
            if not isinstance(table, dict):
                continue
            await self._handle_table(table)

    async def _handle_table(self, table: dict[str, Any]) -> None:
        state = _extract_state(table)
        dedup_key = (state["table_id"], state["hand_id"], state["action_token"])
        if dedup_key in self._seen_actions and dedup_key != (None, None, None):
            return

        decision = decide(
            hole_cards=state["hole_cards"],
            board_cards=state["board_cards"],
            available_actions=state["available_actions"],
            pot_chips=state["pot_chips"],
            to_call_chips=state["to_call_chips"],
            big_blind=state["big_blind"],
        )
        log.info(
            "decision",
            extra={
                "decision": {"action": decision.action,
                             "amount": decision.amount,
                             "reasoning": decision.reasoning},
                "state": {k: v for k, v in state.items() if k != "raw"},
            },
        )

        if self._dry_run:
            self._seen_actions.add(dedup_key)
            return

        await self._submit_with_fallback(state, decision)
        self._seen_actions.add(dedup_key)

    async def _submit_with_fallback(
        self, state: dict[str, Any], decision: Decision
    ) -> None:
        bodies = _candidate_bodies(state, decision)
        if not bodies:
            log.error("no candidate action body could be built", extra={"state": state})
            return

        last_err: ArenaAPIError | None = None
        for i, body in enumerate(bodies, 1):
            try:
                result = await self._client.submit_action(body)
                log.info(
                    "action accepted (shape %d/%d)",
                    i, len(bodies),
                    extra={"submitted_body": body, "response": result},
                )
                return
            except ArenaAPIError as exc:
                last_err = exc
                log.warning(
                    "action rejected (shape %d/%d) status=%s body=%r submitted=%r",
                    i, len(bodies), exc.status_code, exc.body, body,
                )
                # 400 is "shape wrong" — try next; other statuses won't get better
                if exc.status_code != 400:
                    break
        if last_err is not None:
            log.error(
                "all candidate bodies failed; last status=%s body=%r",
                last_err.status_code, last_err.body,
            )


# ---- entrypoint ----------------------------------------------------------

async def run_bot() -> int:
    creds = load_credentials()
    comp = _env_str("ARENA_COMPETITION_ID", "")
    if not comp:
        log.error("ARENA_COMPETITION_ID is required")
        return 2

    base_url = _env_str("ARENA_BASE_URL", "https://arena.dev.fun/api/arena")
    poll = _env_float("ARENA_POLL_INTERVAL_S", 2.0)
    auto_join = _env_bool("ARENA_AUTO_JOIN", True)
    dry_run = _env_bool("ARENA_DRY_RUN", False)

    async with ArenaClient(creds, base_url=base_url) as client:
        bot = PokerBot(
            client=client,
            competition_id=comp,
            poll_interval_s=poll,
            auto_join=auto_join,
            dry_run=dry_run,
        )

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):
                loop.add_signal_handler(sig, bot.request_stop)

        await bot.run()
    return 0


__all__ = ["PokerBot", "run_bot"]
