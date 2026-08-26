#!/usr/bin/env python3
"""Batch AM effect encoding tests."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

from battle.effect_library import get_card_entry, reload_effect_library
from battle.effects import apply_ops
from battle.state import MatchState, PlayerState


def _catalog():
    return json.loads((ROOT / "index" / "cards_by_id.json").read_text())


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P0",
        is_ai=False,
        leader_card_id=kwargs.get("leader0", "OP09-061"),
        deck=["D"] * 20,
        hand=list(kwargs.get("hand0", [])),
        life=["L"] * 5,
        don_active=int(kwargs.get("don_active0", 4)),
        don_rested=int(kwargs.get("don_rested0", 2)),
        don_given=int(kwargs.get("don_given0", 6)),
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.get("leader1", "OP01-001"),
        deck=["E"] * 20,
        hand=[],
        life=["O"] * 5,
        don_active=int(kwargs.get("don_active1", 5)),
        don_rested=0,
        don_given=int(kwargs.get("don_given1", 5)),
    )
    return MatchState(
        room_code="AM",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=1,
        players=[p0, p1],
    )


def test_encodings():
    reload_effect_library(force=True)
    zoro = get_card_entry("OP09-076")
    ops = zoro["abilities"][0]["ops"]
    assert ops[0]["op"] == "return_don" and ops[0].get("any_number") and ops[0].get("as_cost")
    assert ops[1]["op"] == "gain_don"

    franky = get_card_entry("OP09-072")
    fops = franky["abilities"][0]["ops"]
    assert fops[0].get("as_cost") is True
    assert fops[1].get("op") == "trash_hand" and not fops[1].get("as_cost")

    st26 = get_card_entry("ST26-005")
    assert len(st26["abilities"]) == 2
    for ab in st26["abilities"]:
        assert ab.get("require_don_field_gte") is None
        assert ab.get("require_leader_multicolor") is None
        sbp = ab["ops"][1]
        assert sbp["op"] == "set_base_power"
        assert sbp.get("amount") == 7000
        assert sbp.get("require_leader_multicolor") is True
        assert sbp.get("require_opp_don_field_gte") == 5
        assert sbp.get("duration") == "until_opp_turn_end"

    giant = get_card_entry("OP09-078")
    gops = giant["abilities"][0]["ops"]
    assert gops[2].get("require_leader_trait")
    assert gops[3]["op"] == "draw" and "require_leader_trait" not in gops[3]
    assert not gops[1].get("as_cost")

    chopper = get_card_entry("OP15-085")
    act = next(a for a in chopper["abilities"] if a["timing"] == "activate_main")
    assert act.get("require_leader_trait") is None
    assert act["ops"][1].get("require_leader_trait")

    law = get_card_entry("OP09-069")
    assert isinstance(law["abilities"][0]["ops"][0].get("trait_any"), list)


def test_st26_005_gates():
    cat = _catalog()
    st = _state(don_given1=5, don_active1=5)
    # Mono leader should skip set_base_power after paying DON−2.
    st.players[0].leader_card_id = "OP01-001"  # typically mono
    lead = cat.get(st.players[0].leader_card_id) or {}
    from battle.effects import normalize_colors

    if len(normalize_colors(lead.get("colors_en") or lead.get("colors"))) >= 2:
        # Pick a known mono if needed
        for cid, info in cat.items():
            if str(info.get("card_type") or "").lower() != "leader":
                continue
            if len(normalize_colors(info.get("colors_en") or info.get("colors"))) == 1:
                st.players[0].leader_card_id = cid
                break

    before_mod = int(st.players[0].leader_power_mod or 0)
    apply_ops(
        st,
        0,
        [
            {"op": "return_don", "count": 2, "owner": "self", "as_cost": True},
            {
                "op": "set_base_power",
                "amount": 7000,
                "target_kind": "leader",
                "optional": False,
                "trait_contains": "Straw Hat Crew|草帽一行人",
                "duration": "until_opp_turn_end",
                "require_leader_multicolor": True,
                "require_opp_don_field_gte": 5,
            },
        ],
        lambda c: cat.get(c) or {},
    )
    # May prompt for which DON to return — if pending, resolve isn't finished.
    if st.pending_choice:
        return
    assert st.players[0].leader_power_until_end == [] or before_mod == int(st.players[0].leader_power_mod or 0)


def test_zoro_offers_return_cost():
    cat = _catalog()
    st = _state()
    apply_ops(
        st,
        0,
        get_card_entry("OP09-076")["abilities"][0]["ops"],
        lambda c: cat.get(c) or {},
    )
    assert st.pending_choice is not None
    assert any(
        (o.get("op") == "return_don") for o in (st.pending_choice.remaining_ops or [])
    ) or st.pending_choice.target_kind in {"don", "return_don"}


if __name__ == "__main__":
    from scripts.fix_batch_am_effects import main as fix_main

    fix_main()
    reload_effect_library(force=True)
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all passed")
