#!/usr/bin/env python3
"""Batch BB effect encoding tests."""

from __future__ import annotations

from battle.effect_library import get_card_entry, reload_effect_library


def test_encodings():
    reload_effect_library(force=True)

    luffy = get_card_entry("OP13-118")
    ops = luffy["abilities"][0]["ops"]
    assert ops[0]["op"] == "active_don"
    assert ops[0].get("require_leader_multicolor")
    assert ops[1]["op"] == "cannot_play_from_hand"
    assert not ops[1].get("require_leader_multicolor")

    eb = get_card_entry("EB03-052")
    ops = eb["abilities"][0]["ops"]
    assert ops[0]["op"] == "trash"
    assert ops[1]["op"] == "add_life"
    assert ops[1].get("require_leader_name")
    assert ops[2]["op"] == "buff"
    assert not ops[2].get("require_leader_name")

    sh = get_card_entry("OP11-022")
    play = sh["abilities"][2]["ops"][2]
    assert play.get("name_or_trait")
    assert play.get("cost_lte_own_don_field")

    p = get_card_entry("OP12-102")
    aura = next(
        a
        for a in p["abilities"]
        if a.get("timing") == "opponent_turn" and a.get("require_no_other_name")
    )
    assert aura.get("require_no_other_base_cost_eq") == 2

    s = get_card_entry("OP11-036")
    assert s["abilities"][0]["ops"][0].get("name_or_trait")

    h = get_card_entry("OP11-115")
    assert h["abilities"][0]["ops"][0].get("duration") == "battle"
    assert h["abilities"][1]["ops"][0].get("optional")

    scale = get_card_entry("EB04-011")
    assert not any(
        a.get("timing") in {"your_turn", "opponent_turn"} for a in scale["abilities"]
    )
    assert scale["abilities"][0]["ops"][0].get("then_trash_equal")


if __name__ == "__main__":
    from scripts.fix_batch_bb_effects import main as fix_main

    fix_main()
    reload_effect_library(force=True)
    test_encodings()
    print("ok test_encodings")
    print("all passed")
