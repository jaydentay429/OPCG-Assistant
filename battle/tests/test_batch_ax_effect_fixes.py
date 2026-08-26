#!/usr/bin/env python3
"""Batch AX effect encoding tests."""

from __future__ import annotations

from battle.effect_library import get_card_entry, reload_effect_library


def test_encodings():
    reload_effect_library(force=True)

    h = get_card_entry("OP15-084")
    on_play = next(a for a in h["abilities"] if a["timing"] == "on_play")
    on_ko = next(a for a in h["abilities"] if a["timing"] == "on_ko")
    assert on_play.get("require_hand_lte") is None
    assert on_play.get("require_leader_trait")
    assert on_ko.get("require_hand_lte") == 6

    m = get_card_entry("OP06-090")
    assert m["abilities"][0]["ops"][0]["op"] == "trash_to_bottom"
    assert m["abilities"][0]["ops"][0].get("as_cost")
    assert m["abilities"][0]["ops"][1].get("name_exclude") or m["abilities"][0]["ops"][1].get(
        "exclude_name"
    )

    p = get_card_entry("PRB02-013")
    assert p["abilities"][0].get("require_leader_trait") is None
    assert p["abilities"][0]["ops"][0].get("require_leader_trait")
    assert p["abilities"][0]["ops"][1].get("op") == "attach_don"
    assert p["abilities"][0]["ops"][1].get("require_leader_trait") is None

    s = get_card_entry("OP06-098")
    assert s["abilities"][0].get("cost_don") == 1
    assert s["abilities"][0].get("rest_self")
    assert s["abilities"][0]["ops"][0].get("from_zone") == "trash"
    assert s["abilities"][0]["ops"][0].get("cost_lte") == 2
    assert not any(o.get("op") == "rest_character" for o in s["abilities"][0]["ops"])

    o = get_card_entry("OP15-080")
    assert o["abilities"][0].get("require_own_name_contains")
    assert o["abilities"][0].get("require_own_char_power_gte") == 10000


if __name__ == "__main__":
    from scripts.fix_batch_ax_effects import main as fix_main

    fix_main()
    reload_effect_library(force=True)
    test_encodings()
    print("ok test_encodings")
    print("all passed")
