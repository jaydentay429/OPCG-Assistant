#!/usr/bin/env python3
"""Batch AN effect encoding tests."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

from battle.effect_library import get_card_entry, reload_effect_library
from battle.effects import apply_ops
from battle.engine import fire_life_leave
from battle.state import CardInst, MatchState, PlayerState


def _catalog():
    return json.loads((ROOT / "index" / "cards_by_id.json").read_text())


def _state() -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P0",
        is_ai=False,
        leader_card_id="OP05-098",
        deck=["D"] * 20,
        hand=["H1", "H2"],
        life=[],
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P1",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["E"] * 20,
        hand=[],
        life=["O"] * 3,
    )
    return MatchState(
        room_code="AN",
        status="playing",
        phase="main",
        turn_seat=1,  # opponent's turn
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
    )


def test_encodings():
    reload_effect_library(force=True)
    enel = get_card_entry("OP05-098")
    ab = enel["abilities"][0]
    assert ab.get("on_life_leave") is True
    assert ab.get("on_life_leave_from") == "self"
    assert ab.get("require_life_lte") == 0
    assert ab.get("once") is True
    assert ab["timing"] == "opponent_turn"

    bolt = get_card_entry("EB01-059")
    trig = next(a for a in bolt["abilities"] if a["timing"] == "trigger")
    assert trig["ops"][0].get("cost_lte_total_life") is True
    assert trig["ops"][0].get("optional") is True

    op04 = get_card_entry("OP04-112")
    assert op04["abilities"][0]["ops"][0].get("cost_lte_total_life") is True
    assert op04["abilities"][0]["ops"][1].get("require_life_lte") == 1

    st29 = get_card_entry("ST29-013")
    assert st29["abilities"][0]["ops"][0].get("cost_lte_total_life") is True

    eb02 = get_card_entry("EB02-052")
    timings = {a["timing"] for a in eb02["abilities"]}
    assert "your_turn" in timings and "opponent_turn" in timings
    atk = next(a for a in eb02["abilities"] if a["timing"] == "when_attacking")
    assert atk["ops"][2].get("duration") == "turn"

    luffy = get_card_entry("EB04-061")
    hc = next(a for a in luffy["abilities"] if a["timing"] == "hand_cost")
    assert hc["ops"][0].get("amount") == -1


def test_enel_life_leave_fires_at_zero():
    cat = _catalog()
    st = _state()
    # Life already 0 after leave — fire watcher for seat 0.
    fire_life_leave(st, 0, lambda c: cat.get(c) or {})
    # Should have added life and/or pending trash choice.
    assert len(st.players[0].life) == 1 or st.pending_choice is not None


def test_enel_life_leave_skips_when_not_zero():
    cat = _catalog()
    st = _state()
    st.players[0].life = ["L1"]  # still 1 life after leave from 2→1
    before = list(st.players[0].life)
    fire_life_leave(st, 0, lambda c: cat.get(c) or {})
    assert st.players[0].life == before
    assert st.pending_choice is None


if __name__ == "__main__":
    from scripts.fix_batch_an_effects import main as fix_main

    fix_main()
    reload_effect_library(force=True)
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all passed")
