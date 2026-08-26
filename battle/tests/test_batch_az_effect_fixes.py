#!/usr/bin/env python3
"""Batch AZ effect encoding tests."""

from __future__ import annotations

from battle.effect_library import get_card_entry, reload_effect_library


def test_encodings():
    reload_effect_library(force=True)

    t = get_card_entry("OP09-081")
    timings = {a["timing"] for a in t["abilities"]}
    assert "your_turn" in timings and "opponent_turn" in timings

    s = get_card_entry("OP09-089")
    ops = s["abilities"][0]["ops"]
    assert ops[0]["op"] == "trash_hand" and ops[0].get("as_cost")
    assert ops[1]["op"] == "trash" and ops[1].get("as_cost")
    assert ops[2]["op"] == "draw" and ops[2].get("require_leader_trait")
    assert ops[3]["op"] == "reduce_cost" and not ops[3].get("require_leader_trait")

    p = get_card_entry("OP10-086")
    act = next(a for a in p["abilities"] if a["timing"] == "activate_main")
    assert act.get("require_played_this_turn")
    assert act.get("require_leader_trait")

    a = get_card_entry("PRB02-015")
    yt = next(x for x in a["abilities"] if x["timing"] == "your_turn")
    assert any(o.get("op") == "grant_keyword" for o in yt["ops"])
    assert any(o.get("op") == "grant_cost" and o.get("amount") == 4 for o in yt["ops"])

    m = get_card_entry("OP09-093")
    act = m["abilities"][0]
    assert act.get("require_played_this_turn") is None
    assert act["ops"][0].get("require_played_this_turn")
    assert act["ops"][0].get("require_leader_trait")
    assert not act["ops"][1].get("require_leader_trait")

    e = get_card_entry("OP09-098")
    assert e["abilities"][0]["ops"][1].get("same_target_as_prior")
    assert e["abilities"][0]["ops"][1].get("cost_lte") == 4


if __name__ == "__main__":
    from scripts.fix_batch_az_effects import main as fix_main

    fix_main()
    reload_effect_library(force=True)
    test_encodings()
    print("ok test_encodings")
    print("all passed")
