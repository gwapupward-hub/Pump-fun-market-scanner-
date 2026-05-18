from __future__ import annotations

import pytest

from pump_intel.arena.strategy import Decision, decide

# ---------------------------------------------------------------- preflop


def test_premium_preflop_raises_when_raise_is_legal() -> None:
    d = decide(
        hole_cards=["Ah", "Ks"],
        board_cards=[],
        available_actions=["fold", "call", "raise"],
        pot_chips=3,
        to_call_chips=2,
        big_blind=2,
    )
    assert d.action == "raise"
    assert d.amount >= 6  # at least 3x BB


def test_pocket_aces_preflop_raises() -> None:
    d = decide(
        hole_cards=["As", "Ad"],
        board_cards=[],
        available_actions=["fold", "call", "raise"],
        pot_chips=3,
        to_call_chips=2,
    )
    assert d.action == "raise"


def test_junk_preflop_checks_when_free() -> None:
    d = decide(
        hole_cards=["7c", "2d"],
        board_cards=[],
        available_actions=["check", "raise"],
        pot_chips=4,
        to_call_chips=0,
    )
    assert d.action == "check"


def test_junk_preflop_folds_facing_bet() -> None:
    d = decide(
        hole_cards=["7c", "2d"],
        board_cards=[],
        available_actions=["fold", "call", "raise"],
        pot_chips=10,
        to_call_chips=8,
    )
    assert d.action == "fold"


def test_strong_preflop_calls_small_raise() -> None:
    d = decide(
        hole_cards=["Kh", "Qh"],
        board_cards=[],
        available_actions=["fold", "call", "raise"],
        pot_chips=8,
        to_call_chips=4,
        big_blind=2,
    )
    assert d.action == "call"


def test_strong_preflop_folds_to_big_raise() -> None:
    d = decide(
        hole_cards=["Kh", "Qh"],
        board_cards=[],
        available_actions=["fold", "call", "raise"],
        pot_chips=40,
        to_call_chips=30,
        big_blind=2,
    )
    assert d.action == "fold"


# ---------------------------------------------------------------- postflop


def test_top_pair_bets_when_no_one_has_bet() -> None:
    d = decide(
        hole_cards=["Ah", "Ks"],
        board_cards=["Ad", "9c", "4h"],
        available_actions=["check", "bet"],
        pot_chips=20,
        to_call_chips=0,
        big_blind=2,
    )
    assert d.action == "bet"
    assert d.amount > 0


def test_missed_flop_checks_when_free() -> None:
    d = decide(
        hole_cards=["7c", "2d"],
        board_cards=["Ad", "9c", "Kh"],
        available_actions=["check", "bet"],
        pot_chips=8,
        to_call_chips=0,
    )
    assert d.action == "check"


def test_missed_flop_folds_to_big_bet() -> None:
    d = decide(
        hole_cards=["7c", "2d"],
        board_cards=["Ad", "9c", "Kh"],
        available_actions=["fold", "call", "raise"],
        pot_chips=100,
        to_call_chips=80,
    )
    assert d.action == "fold"


def test_made_hand_calls_with_decent_pot_odds() -> None:
    d = decide(
        hole_cards=["Th", "9h"],
        board_cards=["Td", "5c", "2s"],
        available_actions=["fold", "call", "raise"],
        pot_chips=20,
        to_call_chips=5,
    )
    assert d.action == "call"


# ---------------------------------------------------------------- fallbacks


def test_returns_only_legal_actions() -> None:
    """Never recommend something the server didn't offer."""
    d = decide(
        hole_cards=["As", "Ad"],
        board_cards=[],
        available_actions=["fold"],  # weird game state — only fold available
        pot_chips=5,
        to_call_chips=3,
    )
    assert d.action == "fold"


def test_unparseable_cards_falls_back_safely() -> None:
    d = decide(
        hole_cards=["??", "!!"],
        board_cards=[],
        available_actions=["check", "fold"],
        pot_chips=0,
        to_call_chips=0,
    )
    assert d.action in {"check", "fold"}


def test_no_hole_cards_falls_back() -> None:
    d = decide(
        hole_cards=[],
        board_cards=[],
        available_actions=["check"],
        pot_chips=0,
        to_call_chips=0,
    )
    assert d.action == "check"


def test_no_legal_actions_does_not_crash() -> None:
    d = decide(
        hole_cards=["As", "Ad"],
        board_cards=[],
        available_actions=[],
        pot_chips=0,
        to_call_chips=0,
    )
    assert isinstance(d, Decision)  # something is returned


def test_action_names_case_insensitive() -> None:
    d = decide(
        hole_cards=["As", "Ad"],
        board_cards=[],
        available_actions=["FOLD", "CALL", "RAISE"],
        pot_chips=5,
        to_call_chips=2,
    )
    assert d.action == "raise"


# ---------------------------------------------------------------- credentials


def test_load_credentials_from_explicit_path(tmp_path):
    from pump_intel.arena.credentials import load_credentials

    p = tmp_path / ".arena-credentials"
    p.write_text('{"apiKey":"arena_sk_abc","agentId":"agent_xyz"}')
    creds = load_credentials(p)
    assert creds.api_key == "arena_sk_abc"
    assert creds.agent_id == "agent_xyz"


def test_load_credentials_missing_raises(tmp_path):
    from pump_intel.arena.credentials import load_credentials

    with pytest.raises(FileNotFoundError):
        load_credentials(tmp_path / "nope")


def test_load_credentials_missing_keys_raises(tmp_path):
    from pump_intel.arena.credentials import load_credentials

    p = tmp_path / ".arena-credentials"
    p.write_text('{"apiKey":"x"}')
    with pytest.raises(ValueError):
        load_credentials(p)
