#!/usr/bin/env python3
"""Batch AY effect encoding tests."""

from __future__ import annotations

from battle.effect_library import get_card_entry, reload_effect_library


def test_encodings():
    reload_effect_library(force=True)

    b = get_card_entry("EB04-001")
    act = next(a for a in b["abilities"] if a["timing"] == "activate_main")
    assert act.get("require_life_gte") is None
    assert act["ops"][0].get("op") == "buff"
    assert act["ops"][0].get("optional")
    assert act["ops"][1].get("require_life_gte") == 2

    p = get_card_entry("EB04-056")
    timings = {a["timing"] for a in p["abilities"]}
    assert "your_turn" in timings and "opponent_turn" in timings
    assert all(a.get("require_own_name_on_field") for a in p["abilities"])

    o = get_card_entry("OP13-108")
    on_play = next(a for a in o["abilities"] if a["timing"] == "on_play")
    assert on_play.get("require_leader_trait") is None
    assert on_play["ops"][0].get("require_leader_trait")
    assert on_play["ops"][1].get("op") == "life_to_hand"
    assert on_play["ops"][1].get("require_leader_trait") is None

    e = get_card_entry("EB04-008")
    main = next(a for a in e["abilities"] if a["timing"] == "on_play")
    assert len(main["ops"]) == 1
    assert main["ops"][0].get("op") == "buff"
    assert main.get("require_life_lte") == 2

    a = get_card_entry("OP13-007")
    assert a["abilities"][0]["ops"][0].get("from_active")

    s = get_card_entry("EB04-002")
    assert s["abilities"][0]["ops"][0].get("trait_any")

    st = get_card_entry("ST29-016")
    assert st["abilities"][0].get("require_leader_name") is None


if __name__ == "__main__":
    from scripts.fix_batch_ay_effects import main as fix_main

    fix_main()
    reload_effect_library(force=True)
    test_encodings()
    print("ok test_encodings")
    print("all passed")
