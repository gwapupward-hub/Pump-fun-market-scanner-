"""Pure poker decision logic. No I/O.

This is intentionally a small, tight-passive heuristic — not a serious solver.
The point is to play recognisable poker so the arena recorded hands look
sensible while we iterate on the action submission protocol.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, cast

log = logging.getLogger(__name__)

Action = Literal["fold", "check", "call", "bet", "raise", "all-in"]

_RANK_VAL: dict[str, int] = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
    "T": 10, "J": 11, "Q": 12, "K": 13, "A": 14,
}


@dataclass(frozen=True, slots=True)
class Decision:
    action: Action
    amount: int = 0
    reasoning: str = ""


def _parse_card(c: str) -> tuple[int, str]:
    """e.g. 'Ah' -> (14, 'h'). Raises KeyError on bad rank."""
    return _RANK_VAL[c[0].upper()], c[1].lower()


def _is_pocket_pair(hole: list[str]) -> bool:
    if len(hole) != 2:
        return False
    return _parse_card(hole[0])[0] == _parse_card(hole[1])[0]


def _hole_strength(hole: list[str]) -> str:
    """Classify two hole cards as premium / strong / speculative / junk."""
    if len(hole) != 2:
        return "junk"
    (r1, s1), (r2, s2) = _parse_card(hole[0]), _parse_card(hole[1])
    hi, lo = max(r1, r2), min(r1, r2)
    suited = s1 == s2
    pair = r1 == r2

    if pair and hi >= 10:
        return "premium"            # TT+
    if pair and hi >= 7:
        return "strong"             # 77-99
    if pair:
        return "speculative"        # 22-66
    if hi == 14 and lo >= 13:
        return "premium"            # AK
    if hi == 14 and lo >= 10:
        return "strong"             # AQ, AJ, AT
    if hi == 13 and lo >= 11:
        return "strong"             # KQ, KJ
    if suited and hi == 14:
        return "speculative"        # any suited ace
    if suited and (hi - lo) <= 2 and lo >= 5:
        return "speculative"        # suited connectors / 1-gappers, 5+
    return "junk"


def _hits_board(hole: list[str], board: list[str]) -> bool:
    """Cheap: any hole-card rank appears on the board (i.e. at least a pair)."""
    hole_ranks = {_parse_card(c)[0] for c in hole}
    board_ranks = {_parse_card(c)[0] for c in board}
    return bool(hole_ranks & board_ranks)


def decide(
    *,
    hole_cards: list[str],
    board_cards: list[str],
    available_actions: list[str],
    pot_chips: int,
    to_call_chips: int,
    big_blind: int = 2,
) -> Decision:
    """Pick an action from the legal set. Never returns an action that is not in
    `available_actions` — falls back to check > fold > call > the first legal one.

    `pot_chips` is the pot size BEFORE the call. `to_call_chips` is what we'd
    need to put in to continue; 0 means we can check.
    """
    legal = {a.lower() for a in available_actions}

    def fallback(reason: str) -> Decision:
        for a in ("check", "fold", "call"):
            if a in legal:
                amt = to_call_chips if a == "call" else 0
                return Decision(a, amt, f"fallback ({reason})")
        # absolute last resort: pick anything legal
        if available_actions:
            return Decision(cast(Action, available_actions[0].lower()), 0, f"forced ({reason})")
        return Decision("check", 0, f"no legal actions ({reason})")

    if not hole_cards:
        return fallback("no hole cards visible")
    try:
        strength = _hole_strength(hole_cards)
    except (KeyError, IndexError):
        return fallback("unparseable hole cards")

    street = len(board_cards)  # 0=pre, 3=flop, 4=turn, 5=river

    # ---- preflop ----
    if street == 0:
        if strength == "premium":
            target = max(big_blind * 3, to_call_chips * 3)
            if "raise" in legal:
                return Decision("raise", target, "premium preflop, 3x raise")
            if "bet" in legal:
                return Decision("bet", target, "premium preflop, 3x bet")
            if "call" in legal:
                return Decision("call", to_call_chips, "premium, calling")
            return fallback("premium with no aggressive action")
        if strength == "strong":
            if to_call_chips <= big_blind * 3 and "call" in legal:
                return Decision("call", to_call_chips, "strong hand, small raise size")
            if to_call_chips == 0 and "check" in legal:
                return Decision("check", 0, "strong hand, free flop")
            return fallback("strong vs big raise")
        if strength == "speculative":
            if to_call_chips == 0 and "check" in legal:
                return Decision("check", 0, "speculative, free flop")
            if to_call_chips <= big_blind and "call" in legal:
                return Decision("call", to_call_chips, "speculative, cheap call")
            return fallback("speculative vs raise")
        return fallback("junk preflop")

    # ---- postflop ----
    try:
        made_hand = _is_pocket_pair(hole_cards) or _hits_board(hole_cards, board_cards)
    except (KeyError, IndexError):
        return fallback("unparseable board")

    pot_odds = to_call_chips / max(pot_chips + to_call_chips, 1) if to_call_chips else 0.0

    if made_hand:
        if to_call_chips == 0 and "bet" in legal:
            size = max(big_blind * 2, pot_chips // 2)
            return Decision("bet", size, "made hand, half-pot value bet")
        if to_call_chips > 0 and "call" in legal and pot_odds < 0.4:
            return Decision("call", to_call_chips, f"made hand, pot odds {pot_odds:.2f}")
        if "check" in legal:
            return Decision("check", 0, "made hand, pot control")
        return fallback("made hand vs big bet")

    # nothing made
    if to_call_chips == 0 and "check" in legal:
        return Decision("check", 0, "missed, check")
    if to_call_chips <= big_blind and street == 3 and "call" in legal:
        return Decision("call", to_call_chips, "tiny flop bet, peel one")
    return fallback("missed, facing a bet")


__all__ = ["Action", "Decision", "decide"]
