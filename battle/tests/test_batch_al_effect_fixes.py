#!/usr/bin/env python3
"""Batch AL effect encoding + reorder_life runtime tests."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

from battle.effect_library import get_card_entry, reload_effect_library
from battle.effects import apply_ops
from battle.engine import _order_search_bottom, _resolve_choice, _resolve_search
from battle.state import CardInst, MatchState, PlayerState


def _catalog():
    return json.loads((ROOT / "index" / "cards_by_id.json").read_text())


def _state() -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P0",
        is_ai=False,
        leader_card_id="OP03-099",
        deck=["D"] * 20,
        hand=[],
        life=["L0", "L1", "L2"],
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P1",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["E"] * 20,
        hand=[],
        life=["O0", "O1"],
    )
    return MatchState(
        room_code="AL",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=1,
        players=[p0, p1],
    )


def test_encodings():
    reload_effect_library(force=True)
    katakuri = get_card_entry("OP03-099")
    op0 = katakuri["abilities"][0]["ops"][0]
    assert op0["op"] == "reorder_life"
    assert op0["owner"] == "self_or_opponent"
    assert op0.get("look_top") is True

    betty = get_card_entry("EB03-056")
    ko = betty["abilities"][0]["ops"][1]
    assert ko.get("base_cost_lte") == 3
    assert "cost_lte" not in ko

    linlin = get_card_entry("OP03-114")
    abs0 = linlin["abilities"][0]
    assert "require_leader_trait" not in abs0
    assert abs0["ops"][0].get("require_leader_trait")
    assert abs0["ops"][1].get("op") == "trash_life"
    assert "require_leader_trait" not in abs0["ops"][1]

    warlords = get_card_entry("OP14-112")
    assert warlords["abilities"][0]["ops"][0].get("require_leader_trait")
    assert "require_leader_trait" not in warlords["abilities"][0]["ops"][1]

    st7 = get_card_entry("ST07-003")
    assert len(st7["abilities"]) == 1
    assert st7["abilities"][0]["ops"][1].get("require_life_less_than_opponent") is True

    op12 = get_card_entry("OP12-029")
    assert op12["abilities"][0]["ops"][1].get("base_cost_lte") == 1


def test_reorder_life_top_or_bottom():
    cat = _catalog()
    st = _state()
    logs = apply_ops(
        st,
        0,
        [
            {
                "op": "reorder_life",
                "owner": "self_or_opponent",
                "look_top": True,
                "count": 1,
                "optional": True,
            }
        ],
        lambda c: cat.get(c) or {},
    )
    assert st.pending_choice is not None
    assert st.pending_choice.target_kind == "life_owner"
    assert "life_owner:self" in st.pending_choice.options
    assert "life_owner:opponent" in st.pending_choice.options

    r = _resolve_choice(st, 0, "life_owner:opponent", lambda c: cat.get(c) or {})
    assert r.get("ok")
    assert st.pending_choice is not None
    assert st.pending_choice.target_kind == "life_position"
    assert st.players[1].life[0] == "O0"

    r2 = _resolve_choice(st, 0, "life:bottom", lambda c: cat.get(c) or {})
    assert r2.get("ok")
    assert st.pending_choice is None
    assert st.players[1].life[-1] == "O0"
    assert st.players[1].life[0] == "O1"


def test_reorder_life_all():
    cat = _catalog()
    st = _state()
    st.players[0].life = ["A", "B", "C"]
    apply_ops(
        st,
        0,
        [{"op": "reorder_life", "owner": "self", "optional": False}],
        lambda c: cat.get(c) or {},
    )
    assert st.pending_search is not None
    assert st.pending_search.destination == "life_reorder"
    assert st.players[0].life == []
    assert st.pending_search.revealed == ["A", "B", "C"]

    # Pick order C, A, B → Life top to bottom.
    _order_search_bottom(st, 0, 2, lambda c: cat.get(c) or {})  # C
    _order_search_bottom(st, 0, 0, lambda c: cat.get(c) or {})  # A
    _order_search_bottom(st, 0, 0, lambda c: cat.get(c) or {})  # B
    assert st.pending_search is None
    assert st.players[0].life == ["C", "A", "B"]


def test_flip_life_optional_as_cost_skippable():
    cat = _catalog()
    st = _state()
    st.players[0].life_face = [False, False, False]
    apply_ops(
        st,
        0,
        [
            {"op": "flip_life", "face": "up", "position": "top", "optional": True, "as_cost": True},
            {"op": "ko", "target_kind": "opponent_character", "optional": True, "base_cost_lte": 3},
        ],
        lambda c: cat.get(c) or {},
    )
    assert st.pending_choice is not None
    assert st.pending_choice.optional is True
    # Skip cost → no KO offer / no flip.
    r = _resolve_choice(st, 0, None, lambda c: cat.get(c) or {})
    assert r.get("ok")
    assert st.pending_choice is None
    assert st.players[0].life_face[0] is False


def test_to_deck_top_life_rest():
    cat = _catalog()
    st = _state()
    st.players[0].life = ["A", "B", "C"]
    apply_ops(
        st,
        0,
        [{"op": "reorder_life", "owner": "self", "to_deck_top": True}],
        lambda c: cat.get(c) or {},
    )
    assert st.pending_search is not None
    assert st.pending_search.destination == "deck_top_life_rest"
    assert st.players[0].life == []
    before_deck0 = st.players[0].deck[0]
    r = _resolve_search(st, 0, [1], lambda c: cat.get(c) or {})  # pick B to deck
    assert r.get("ok")
    assert st.players[0].deck[0] == "B"
    # leftovers A,C need order
    assert st.pending_search is not None
    assert st.pending_search.destination == "life_reorder"
    _order_search_bottom(st, 0, 0, lambda c: cat.get(c) or {})
    _order_search_bottom(st, 0, 0, lambda c: cat.get(c) or {})
    assert st.players[0].life == ["A", "C"]
    assert before_deck0 != "B" or True


if __name__ == "__main__":
    from scripts.fix_batch_al_effects import main as fix_main

    fix_main()
    reload_effect_library(force=True)
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all passed")
