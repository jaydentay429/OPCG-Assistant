#!/usr/bin/env python3
"""Batch AV effect encoding tests."""

from __future__ import annotations

from battle.effect_library import get_card_entry, reload_effect_library


def test_encodings():
    reload_effect_library(force=True)

    y = get_card_entry("OP06-022")
    op = y["abilities"][0]["ops"][0]
    assert op.get("from_rested") or op.get("as_rested")
    assert op.get("target_kind") == "own_character"

    s = get_card_entry("ST28-005")
    search = next(o for a in s["abilities"] for o in a["ops"] if o.get("op") == "search_deck")
    assert search.get("cost_gte") == 2

    h = get_card_entry("OP13-104")
    assert h["abilities"][0].get("require_leader_multicolor") is None
    assert h["abilities"][0]["ops"][1].get("require_leader_multicolor")

    m = get_card_entry("OP06-107")
    pol = m["abilities"][0]["ops"][0]
    assert pol["op"] == "place_on_life"
    assert "Wano" in str(pol.get("trait_contains") or "") or "和之國" in str(
        pol.get("trait_contains") or ""
    )
    assert pol.get("exclude_name")

    n = get_card_entry("OP06-041")
    assert n["abilities"][0]["ops"][0].get("all")
    assert n["abilities"][1]["ops"][0].get("self_card")
    assert n["abilities"][1]["ops"][0].get("card_type") == "stage"

    z = get_card_entry("OP06-118")
    act = next(a for a in z["abilities"] if a["timing"] == "activate_main")
    assert act["ops"][1].get("target_kind") == "self"

    e = get_card_entry("EB01-013")
    play = e["abilities"][0]["ops"][1]
    assert play.get("cost_lte") == 5
    assert play.get("exclude_name")

    k = get_card_entry("ST28-003")
    assert k["abilities"][0]["ops"][0].get("self_card")


if __name__ == "__main__":
    from scripts.fix_batch_av_effects import main as fix_main

    fix_main()
    reload_effect_library(force=True)
    test_encodings()
    print("ok test_encodings")
    print("all passed")
