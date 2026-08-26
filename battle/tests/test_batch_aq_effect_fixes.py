#!/usr/bin/env python3
"""Batch AQ effect encoding + multi-ability / opp-life-left tests."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

from battle.effect_library import get_card_entry, reload_effect_library, resolve_ability
from battle.engine import effective_play_cost, fire_life_leave
from battle.state import CardInst, MatchState, PlayerState, new_iid


def _catalog():
    return json.loads((ROOT / "index" / "cards_by_id.json").read_text())


def _state() -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P0",
        is_ai=False,
        leader_card_id="OP15-098",
        deck=["D"] * 20,
        hand=["P-120"],
        life=["L1", "L2", "L3"],
        don_active=2,
        don_rested=4,
        don_given=6,
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P1",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["E"] * 20,
        hand=[],
        life=["O1", "O2"],
        don_active=0,
        don_rested=0,
        don_given=0,
    )
    return MatchState(
        room_code="AQ",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=1,
        players=[p0, p1],
    )


def test_encodings():
    reload_effect_library(force=True)
    gan = get_card_entry("OP15-102")
    rest = next(a for a in gan["abilities"] if a["timing"] == "on_play")
    assert rest["ops"][0].get("cost_lte_opp_life") is True
    assert next(a for a in gan["abilities"] if a["timing"] == "hand_cost").get(
        "require_own_char_power_gte"
    ) == 7000

    nirvana = get_card_entry("OP05-102")
    assert nirvana["abilities"][0]["ops"][0].get("cost_lte_opp_life") is True

    gum = get_card_entry("OP15-116")
    assert gum["abilities"][0].get("require_leader_trait") is None
    assert "草帽" in str(gum["abilities"][0]["ops"][0].get("require_leader_trait") or "")

    p120 = get_card_entry("P-120")
    assert p120["abilities"][0].get("require_opp_life_left_this_turn") is True

    op10 = get_card_entry("OP10-110")
    on_play = next(a for a in op10["abilities"] if a["timing"] == "on_play")
    assert on_play.get("require_life_lte") is None
    assert on_play["ops"][0].get("cost_lte_opp_life") is True


def test_resolve_ability_picks_opp_blocker_not_just_rush():
    reload_effect_library(force=True)
    cat = _catalog()
    st = _state()
    st.players[0].characters = [
        CardInst(iid="luffy", card_id="OP15-119", rested=False, don_attached=0)
    ]
    # Even with don field ≥6 (Rush ability first), blocker watcher must resolve.
    pending = resolve_ability(
        st,
        0,
        "OP15-119",
        "luffy",
        "your_turn",
        cat["OP15-119"],
        None,
        allow_llm=False,
        catalog=lambda c: cat.get(c) or {},
        trigger_on="opp_blocker",
    )
    assert pending is not None
    assert any(o.get("op") == "reveal_life" for o in pending.ops)


def test_p120_hand_cost_after_opp_life_leave():
    reload_effect_library(force=True)
    cat = _catalog()
    st = _state()
    before = effective_play_cost(st, 0, "P-120", lambda c: cat.get(c) or {})
    assert before == 6
    # Opponent Life leaves → P0 gets the discount.
    st.players[1].life.pop()
    fire_life_leave(st, 1, lambda c: cat.get(c) or {})
    assert st.players[0].opp_life_left_this_turn is True
    after = effective_play_cost(st, 0, "P-120", lambda c: cat.get(c) or {})
    assert after == 4


if __name__ == "__main__":
    from scripts.fix_batch_aq_effects import main as fix_main

    fix_main()
    reload_effect_library(force=True)
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all passed")
