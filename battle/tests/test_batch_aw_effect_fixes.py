#!/usr/bin/env python3
"""Batch AW effect encoding tests."""

from __future__ import annotations

from battle.effect_library import get_card_entry, reload_effect_library


def test_encodings():
    reload_effect_library(force=True)

    k = get_card_entry("OP15-001")
    act = next(a for a in k["abilities"] if a["timing"] == "activate_main")
    assert not act["ops"][0].get("all")
    assert act["ops"][0].get("don_attached_gte") == 2
    assert act["ops"][0].get("optional")

    c = get_card_entry("OP15-008")
    act = next(a for a in c["abilities"] if a["timing"] == "activate_main")
    assert act.get("require_played_this_turn")
    assert act["ops"][0].get("per_don_attached") == 1
    assert not act["ops"][0].get("per_rested_don")

    j = get_card_entry("OP15-026")
    act = next(a for a in j["abilities"] if a["timing"] == "activate_main")
    assert act["ops"][0]["op"] == "trash"
    assert act["ops"][1].get("from_owner") == "opponent"
    assert act["ops"][1].get("target_kind") == "opponent_character"

    cat = get_card_entry("OP15-028")
    assert cat["abilities"][0]["ops"][0].get("from_cost_area")
    assert cat["abilities"][0]["ops"][0].get("target_kind") == "opponent_character"

    ku = get_card_entry("OP15-025")
    assert ku["abilities"][0]["ops"][0].get("from_cost_area")
    assert ku["abilities"][0]["ops"][1].get("at_end_of_turn")
    assert ku["abilities"][0]["ops"][1].get("don_attached_gte") == 3
    assert not ku["abilities"][0].get("require_rested_own_chars_gte")

    m = get_card_entry("OP15-027")
    assert m["abilities"][0]["ops"][0].get("don_attached_gte") == 1

    e = get_card_entry("OP08-036")
    trig = next(a for a in e["abilities"] if a["timing"] == "trigger")
    assert not trig["ops"][0].get("all")
    assert trig["ops"][0].get("cost_lte") is None


if __name__ == "__main__":
    from scripts.fix_batch_aw_effects import main as fix_main

    fix_main()
    reload_effect_library(force=True)
    test_encodings()
    print("ok test_encodings")
    print("all passed")
