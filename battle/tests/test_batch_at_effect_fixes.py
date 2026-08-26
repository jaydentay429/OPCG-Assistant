#!/usr/bin/env python3
"""Batch AT effect encoding tests."""

from __future__ import annotations

from battle.effect_library import get_card_entry, reload_effect_library


def test_encodings():
    reload_effect_library(force=True)

    d = get_card_entry("OP14-060")
    assert d["abilities"][0]["timing"] == "on_opponent_attack"
    assert d["abilities"][0]["ops"][0]["op"] == "return_don"
    assert d["abilities"][0]["ops"][0].get("as_cost")
    assert d["abilities"][0]["ops"][1]["op"] == "redirect_attack"
    assert d["abilities"][0]["ops"][1].get("include_leader")
    assert d["abilities"][0].get("once")

    v = get_card_entry("OP14-061")
    assert any(a.get("op") == "replace_leave" for a in v["abilities"] for a in [a] for a in a.get("ops") or []) or any(
        o.get("op") == "replace_leave" for a in v["abilities"] for o in (a.get("ops") or [])
    )
    wa = next(a for a in v["abilities"] if a["timing"] == "when_attacking")
    assert not wa.get("once")
    assert not any(o.get("op") == "buff_self" for o in wa["ops"])
    assert wa["ops"][1]["target_kind"] == "opponent_character"

    t = get_card_entry("OP14-068")
    assert len(t["abilities"]) == 1
    assert t["abilities"][0]["timing"] == "on_don_returned"
    assert t["abilities"][0].get("require_opponent_turn")

    m = get_card_entry("OP14-074")
    assert not m["abilities"][0]["ops"][0].get("as_rested")
    assert m["abilities"][1]["ops"][2].get("as_rested")

    e = get_card_entry("OP10-078")
    main = e["abilities"][0]["ops"][0]
    ctr = e["abilities"][1]["ops"][0]
    assert main["top_n"] == ctr["top_n"] == 3
    assert "Donquixote" in str(ctr.get("trait_contains") or "")
    assert ctr.get("exclude_name")


if __name__ == "__main__":
    from scripts.fix_batch_at_effects import main as fix_main

    fix_main()
    reload_effect_library(force=True)
    test_encodings()
    print("ok test_encodings")
    print("all passed")
