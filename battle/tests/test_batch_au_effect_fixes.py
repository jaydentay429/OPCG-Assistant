#!/usr/bin/env python3
"""Batch AU effect encoding tests."""

from __future__ import annotations

from battle.effect_library import get_card_entry, reload_effect_library


def test_encodings():
    reload_effect_library(force=True)

    s = get_card_entry("OP10-001")
    aura = next(a for a in s["abilities"] if a["timing"] == "opponent_turn")
    assert aura["ops"][0].get("all")
    assert "Navy" in str(aura["ops"][0].get("trait_contains") or "")
    assert aura["ops"][0].get("target_kind") == "own_character"

    k = get_card_entry("OP15-009")
    assert not any(a.get("once") for a in k["abilities"])
    op = k["abilities"][0]["ops"][0]
    assert op["op"] == "replace_leave"
    assert op["target"] == "own_filtered"
    assert op["cost"] == "self_power_minus"
    assert op.get("apply_to") == "leader"
    assert op.get("base_power_lte") == 7000
    assert not any(o.get("op") == "buff" for a in k["abilities"] for o in a["ops"])

    b = get_card_entry("OP12-118")
    assert b["abilities"][0].get("require_rested_cards_gte") is None
    assert b["abilities"][0]["ops"][0].get("require_rested_cards_gte") == 8
    assert b["abilities"][0]["ops"][2].get("op") == "active_don"
    assert b["abilities"][0]["ops"][2].get("require_rested_cards_gte") is None

    m = get_card_entry("OP12-030")
    assert not any(
        o.get("op") == "grant_keyword" for a in m["abilities"] for o in (a.get("ops") or [])
    )
    assert any(o.get("op") == "active_don" for a in m["abilities"] for o in a["ops"])


if __name__ == "__main__":
    from scripts.fix_batch_au_effects import main as fix_main

    fix_main()
    reload_effect_library(force=True)
    test_encodings()
    print("ok test_encodings")
    print("all passed")
