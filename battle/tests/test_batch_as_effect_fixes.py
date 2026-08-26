#!/usr/bin/env python3
"""Batch AS effect encoding + on_don_phase tests."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

from battle.effect_library import get_card_entry, reload_effect_library
from battle.engine import _begin_turn
from battle.state import MatchState, PlayerState


def _catalog():
    return json.loads((ROOT / "index" / "cards_by_id.json").read_text())


def test_encodings():
    reload_effect_library(force=True)
    roger = get_card_entry("OP13-003")
    assert roger["abilities"][0]["timing"] == "on_don_phase"
    assert not any(a.get("timing") == "on_don_attached" for a in roger["abilities"])

    jack = get_card_entry("OP13-065")
    excl = str(jack["abilities"][0]["ops"][0].get("exclude_name") or "")
    assert "Jack" in excl or "傑克" in excl
    assert "Shanks" not in excl

    buggy = get_card_entry("OP13-072")
    assert buggy["abilities"][0].get("require_given_don_gte") == 1
    assert len(buggy["abilities"][0]["ops"]) == 1
    assert buggy["abilities"][0]["ops"][0].get("op") == "gain_don"

    inu = get_card_entry("OP13-061")
    ops = inu["abilities"][0]["ops"]
    assert ops[0].get("require_given_don_gte") == 1
    assert ops[1].get("op") == "ko"
    assert not any(o.get("op") == "attach_don" for o in ops)

    gaban = get_card_entry("OP13-067")
    assert gaban["abilities"][0].get("require_leader_trait") is None
    assert gaban["abilities"][0]["ops"][0].get("require_leader_trait")
    assert gaban["abilities"][0]["ops"][2].get("op") == "gain_don"
    assert gaban["abilities"][0]["ops"][2].get("require_leader_trait") is None

    event = get_card_entry("OP13-075")
    assert not any(o.get("op") == "attach_don" for o in event["abilities"][0]["ops"])
    assert event["abilities"][0]["ops"][1].get("require_given_don_gte") == 1


def test_roger_don_phase_attaches_to_leader():
    reload_effect_library(force=True)
    cat = _catalog()
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P0",
        is_ai=False,
        leader_card_id="OP13-003",
        deck=["D"] * 30,
        hand=[],
        life=["L"] * 5,
        don_active=0,
        don_rested=0,
        don_given=0,
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P1",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["E"] * 30,
        hand=[],
        life=["O"] * 5,
        don_active=0,
        don_rested=0,
        don_given=0,
    )
    st = MatchState(
        room_code="AS",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=1,
        players=[p0, p1],
    )
    # Not first player's turn one → gain 2 DON!! then on_don_phase attaches 1 to Leader.
    p0.turns_completed = 1
    _begin_turn(st, 0, lambda c: cat.get(c) or {})
    assert p0.leader_don == 1
    assert p0.don_active == 1  # 2 placed, 1 attached


if __name__ == "__main__":
    from scripts.fix_batch_as_effects import main as fix_main

    fix_main()
    reload_effect_library(force=True)
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all passed")
