#!/usr/bin/env python3
"""Batch AO effect encoding + skip_untap tests."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

from battle.effect_library import get_card_entry, reload_effect_library
from battle.effects import apply_ops, detect_keywords
from battle.state import CardInst, MatchState, PlayerState


def _catalog():
    return json.loads((ROOT / "index" / "cards_by_id.json").read_text())


def _state() -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P0",
        is_ai=False,
        leader_card_id="OP07-019",
        deck=["D"] * 20,
        hand=[],
        life=["L"] * 5,
        don_active=3,
        don_rested=2,
        don_given=5,
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P1",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["E"] * 20,
        hand=[],
        life=["O"] * 5,
        don_active=0,
        don_rested=3,
        don_given=3,
    )
    p1.leader_rested = True
    p1.characters = [
        CardInst(iid="c1", card_id="OP01-003", rested=True),
        CardInst(iid="c2", card_id="OP01-004", rested=False),
    ]
    return MatchState(
        room_code="AO",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=1,
        players=[p0, p1],
    )


def test_encodings():
    reload_effect_library(force=True)
    smoker = get_card_entry("OP10-030")
    assert not any(
        o.get("op") == "grant_keyword" and o.get("keyword") == "banish"
        for a in smoker["abilities"]
        for o in a.get("ops") or []
    )
    assert "banish" in detect_keywords(_catalog()["OP10-030"])

    st24 = get_card_entry("ST24-002")
    assert "超新星" in str(st24["abilities"][0]["ops"][0].get("trait_contains") or "")

    dof = get_card_entry("OP04-031")
    op = dof["abilities"][0]["ops"][0]
    assert op.get("include_leader") is True
    assert not op.get("include_don")

    bonney = get_card_entry("OP07-026")
    bop = bonney["abilities"][0]["ops"][0]
    assert bop.get("include_don") is True or "or_don" in str(bop.get("target_kind") or "")


def test_skip_untap_doflamingo_options_no_don():
    cat = _catalog()
    st = _state()
    apply_ops(
        st,
        0,
        [
            {
                "op": "skip_untap",
                "count": 3,
                "target_kind": "opponent_character_rested",
                "optional": True,
                "include_leader": True,
            }
        ],
        lambda c: cat.get(c) or {},
    )
    assert st.pending_choice is not None
    opts = st.pending_choice.options
    assert "leader" in opts
    assert "c1" in opts
    assert "don" not in opts  # Leader+Characters only, not DON!!


def test_skip_untap_bonney_includes_don():
    cat = _catalog()
    st = _state()
    apply_ops(
        st,
        0,
        [
            {
                "op": "skip_untap",
                "count": 1,
                "target_kind": "opponent_character_or_don_rested",
                "optional": True,
                "include_don": True,
            }
        ],
        lambda c: cat.get(c) or {},
    )
    assert st.pending_choice is not None
    assert "don" in st.pending_choice.options


if __name__ == "__main__":
    from scripts.fix_batch_ao_effects import main as fix_main

    fix_main()
    reload_effect_library(force=True)
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all passed")
