#!/usr/bin/env python3
"""Batch BA effect encoding tests."""

from __future__ import annotations

from battle.effect_library import get_card_entry, reload_effect_library


def test_encodings():
    reload_effect_library(force=True)

    lim = get_card_entry("OP09-037")
    on_play = next(a for a in lim["abilities"] if a["timing"] == "on_play")
    eoy = next(a for a in lim["abilities"] if a["timing"] == "end_of_your_turn")
    assert on_play.get("require_rested_own_chars_gte") is None
    assert on_play["ops"][0].get("op") == "search_deck"
    assert eoy.get("require_rested_own_chars_gte") == 3

    nw = get_card_entry("OP10-024")
    assert nw["abilities"][0].get("require_rested_own_chars_gte") is None
    assert nw["abilities"][0]["ops"][0].get("require_rested_own_chars_gte") == 2
    assert nw["abilities"][0]["ops"][1].get("cost_lte") == 3
    assert nw["abilities"][0]["ops"][1].get("op") == "ko"

    mh = get_card_entry("OP10-029")
    assert mh["abilities"][0]["ops"][0].get("op") == "set_character_active"
    assert mh["abilities"][0]["ops"][0].get("trait_contains") == "ODYSSEY"
    assert mh["abilities"][0]["ops"][0].get("cost_lte") == 5
    assert not any(o.get("op") == "rest_opponent_character" for o in mh["abilities"][0]["ops"])

    eb = get_card_entry("EB03-037")
    op0 = eb["abilities"][0]["ops"][0]
    assert op0.get("trait_contains") == "ODYSSEY"
    assert op0.get("include_leader")
    assert op0.get("duration") == "until_opp_turn_end"

    ad = get_card_entry("P-078-P1")
    assert ad["abilities"][0].get("require_rested_own_chars_trait") == "ODYSSEY"


if __name__ == "__main__":
    from scripts.fix_batch_ba_effects import main as fix_main

    fix_main()
    reload_effect_library(force=True)
    test_encodings()
    print("ok test_encodings")
    print("all passed")
