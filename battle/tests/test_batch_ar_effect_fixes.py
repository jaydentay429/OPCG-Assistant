#!/usr/bin/env python3
"""Batch AR effect encoding tests."""

from __future__ import annotations

from battle.effect_library import get_card_entry, reload_effect_library
from battle.effects import _hand_card_matches_play_op


def test_encodings():
    reload_effect_library(force=True)
    buggy = get_card_entry("ST30-011")
    op = buggy["abilities"][0]["ops"][0]
    assert op.get("base_power_eq") == 6000
    assert op.get("base_power_gte") is None

    mihawk = get_card_entry("ST12-003")
    ab = mihawk["abilities"][0]
    assert ab.get("require_chars_lte") == 2
    play = ab["ops"][0]
    assert play.get("trait_or_attribute") is True
    assert "Slash" in str(play.get("attribute") or "")

    luffy = get_card_entry("OP13-118")
    ops = luffy["abilities"][0]["ops"]
    assert ops[0].get("op") == "active_don"
    assert ops[0].get("require_leader_multicolor") is True
    assert ops[1].get("op") == "cannot_play_from_hand"
    assert luffy["abilities"][0].get("require_leader_multicolor") is None

    ivan = get_card_entry("ST12-010")
    assert ivan["abilities"][0]["ops"][0].get("to_top_or_bottom") is True

    st09 = get_card_entry("ST30-009")
    assert st09["abilities"][0]["ops"][0].get("then_draw") == 1
    assert st09["abilities"][0]["ops"][0].get("base_power_eq") == 6000


def test_trait_or_attribute_hand_match():
    op = {
        "card_type": "character",
        "cost_lte": 4,
        "trait_contains": "Muggy Kingdom|西凱阿爾王國",
        "attribute": "Slash|斬|斩",
        "trait_or_attribute": True,
    }
    slash_only = {
        "card_type": "Character",
        "cost": 3,
        "attributes_en": ["Slash"],
        "traits_en": [],
        "name_en": "Zoro",
    }
    muggy_only = {
        "card_type": "Character",
        "cost": 3,
        "attributes_en": ["Strike"],
        "traits_en": ["Muggy Kingdom"],
        "name_en": "Foo",
    }
    neither = {
        "card_type": "Character",
        "cost": 3,
        "attributes_en": ["Strike"],
        "traits_en": ["Navy"],
        "name_en": "Bar",
    }
    assert _hand_card_matches_play_op(slash_only, op)
    assert _hand_card_matches_play_op(muggy_only, op)
    assert not _hand_card_matches_play_op(neither, op)


if __name__ == "__main__":
    from scripts.fix_batch_ar_effects import main as fix_main

    fix_main()
    reload_effect_library(force=True)
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all passed")
