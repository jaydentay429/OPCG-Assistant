#!/usr/bin/env python3
"""Batch AP effect encoding tests."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

from battle.effect_library import get_card_entry, reload_effect_library
from battle.effects import (
    _extract_require_life_lte_from_text,
    _extract_require_opp_life_lte_from_text,
    apply_ops,
    detect_keywords,
)
from battle.state import CardInst, MatchState, PlayerState


def _catalog():
    return json.loads((ROOT / "index" / "cards_by_id.json").read_text())


def test_life_text_extractors():
    zh = "【登場時】若對手的生命值卡在3張以下時，抽4張卡片。"
    assert _extract_require_life_lte_from_text(zh) is None
    assert _extract_require_opp_life_lte_from_text(zh) == 3
    own = "若自己的生命值卡在1張以下時，這張角色卡獲得【防禦】。"
    assert _extract_require_life_lte_from_text(own) == 1


def test_encodings():
    reload_effect_library(force=True)
    kaido = get_card_entry("OP05-118")
    ab = kaido["abilities"][0]
    assert ab.get("require_opp_life_lte") == 3
    assert ab.get("require_life_lte") is None

    igaram = get_card_entry("OP04-002")
    a0 = igaram["abilities"][0]
    assert a0.get("rest_self") is True
    assert a0["ops"][0].get("require_leader_active") is True
    assert "Alabasta" in str(a0["ops"][1].get("trait_contains") or "")

    brook = get_card_entry("OP11-056")
    assert brook["abilities"][0]["ops"][0].get("base_cost_eq") == 1

    assert "blocker" in detect_keywords(_catalog()["OP10-011"])
    assert "double_attack" in detect_keywords(_catalog()["EB04-023"])

    p155 = get_card_entry("P-155")
    atk = next(a for a in p155["abilities"] if a["timing"] == "when_attacking")
    assert atk.get("require_life_lte") is None
    assert atk.get("require_opp_life_lte") is None
    trig = next(a for a in p155["abilities"] if a["timing"] == "trigger")
    assert trig.get("require_opp_life_lte") == 3


def test_leader_as_cost_requires_active():
    cat = _catalog()
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P0",
        is_ai=False,
        leader_card_id="OP04-001",
        deck=["D"] * 20,
        hand=[],
        life=["L"] * 5,
        don_active=2,
        don_rested=0,
        don_given=2,
    )
    p0.leader_rested = True
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
        don_rested=0,
        don_given=0,
    )
    st = MatchState(
        room_code="AP",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=1,
        players=[p0, p1],
    )
    hand_before = len(p0.hand)
    apply_ops(
        st,
        0,
        [
            {
                "op": "buff",
                "amount": -5000,
                "target_kind": "leader",
                "optional": True,
                "as_cost": True,
                "duration": "turn",
                "require_leader_active": True,
            },
            {"op": "draw", "count": 1},
        ],
        lambda c: cat.get(c) or {},
    )
    assert len(p0.hand) == hand_before  # draw aborted — cost unpaid


if __name__ == "__main__":
    from scripts.fix_batch_ap_effects import main as fix_main

    fix_main()
    reload_effect_library(force=True)
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all passed")
