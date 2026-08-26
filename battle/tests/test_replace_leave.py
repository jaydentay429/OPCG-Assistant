"""Tests for replace_leave shields (ST09-010 / OP15-098)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effects import _parse_replace_leave_ops, apply_ops  # noqa: E402
from battle.leave_replace import confirm_replace_if_pending, try_replace_leave  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.get("leader0", "OP15-098"),
        deck=["A"] * 20,
        hand=list(kwargs.get("hand0", [])),
        life=list(kwargs.get("life0", ["L1", "L2", "L3"])),
        trash=[],
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["B"] * 20,
        hand=[],
        life=["R"] * 5,
        trash=[],
    )
    st = MatchState(
        room_code="T",
        status="playing",
        phase="main",
        turn_seat=1,
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
    )
    return st


def test_parse_st09_ace():
    ops = _parse_replace_leave_ops(
        "[Once Per Turn] If this Character would be K.O.'d, you may trash 1 card "
        "from the top or bottom of your Life cards instead."
    )
    assert len(ops) == 1
    assert ops[0]["op"] == "replace_leave"
    assert ops[0]["cost"] == "trash_life"
    assert ops[0]["once"] is True


def test_parse_op15_luffy():
    ops = _parse_replace_leave_ops(
        "If your {Sky Island} type Character with 6000 base power or more would be "
        "removed from the field by your opponent, you may add 1 card from the top "
        "of your Life cards to your hand instead."
    )
    assert ops[0]["trait_contains"] == "Sky Island"
    assert ops[0]["base_power_gte"] == 6000
    assert ops[0]["cost"] == "life_to_hand"


def test_try_replace_leave_ace_trashes_life():
    st = _state()
    ace = CardInst(iid="ace1", card_id="ST09-010", rested=False)
    st.players[0].characters.append(ace)
    catalog = {
        "ST09-010": {"name": "Ace", "power": "5000", "traits": [], "traits_en": []},
        "OP15-098": {"name": "Luffy", "power": "5000", "traits": [], "traits_en": []},
    }.get

    ok = try_replace_leave(st, 0, ace, by_opponent=True, catalog=catalog)
    assert ok is True
    confirm_replace_if_pending(st, catalog)
    assert any(c.iid == "ace1" for c in st.players[0].characters)
    assert len(st.players[0].life) == 2
    assert "L1" in st.players[0].trash
    assert ace.once_used is True


def test_effect_ko_respects_replace_leave():
    st = _state()
    ace = CardInst(iid="ace1", card_id="ST09-010")
    st.players[0].characters.append(ace)
    catalog = lambda cid: {
        "ST09-010": {"name": "Ace", "power": "5000", "traits": [], "traits_en": []},
        "X": {"name": "X", "power": "1000", "traits": [], "traits_en": []},
    }.get(cid, {})

    apply_ops(
        st,
        1,
        [{"op": "ko", "target_iid": "ace1", "target_kind": "opponent_character"}],
        catalog,
    )
    confirm_replace_if_pending(st, catalog)
    assert any(c.iid == "ace1" for c in st.players[0].characters)
    assert len(st.players[0].life) == 2
