"""Batch-T effect encoding fixes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402


def setup_module() -> None:
    reload_effect_library()


def test_st21_001_attach_to_character() -> None:
    ab = get_card_entry("ST21-001")["abilities"][0]
    op = ab["ops"][0]
    assert op.get("target_kind") == "own_character"
    assert op.get("as_rested") is True and op.get("from_rested") is True
    assert ab.get("require_don_attached_gte") == 1


def test_op05_008_attach_leader_or_character() -> None:
    op = get_card_entry("OP05-008")["abilities"][0]["ops"][0]
    assert op.get("target_kind") == "own_leader_or_character"
    assert op.get("from_rested") is True


def test_op06_018_main_not_ko() -> None:
    play = next(a for a in get_card_entry("OP06-018")["abilities"] if a["timing"] == "on_play")
    ops = play["ops"]
    assert [o["op"] for o in ops] == ["buff", "buff"]
    assert ops[0].get("amount") == 3000 and ops[0].get("duration") == "turn"
    assert ops[1].get("amount") == 1000 and ops[1].get("require_opp_char_power_gte") == 7000
    trig = next(a for a in get_card_entry("OP06-018")["abilities"] if a["timing"] == "trigger")
    assert trig["ops"][0]["op"] == "ko"
    assert trig["ops"][0].get("optional") is True


def test_st21_015_rush_both_turns() -> None:
    rush = {
        a["timing"]
        for a in get_card_entry("ST21-015")["abilities"]
        if a.get("require_don_attached_gte") == 2
    }
    assert rush >= {"your_turn", "opponent_turn"}
    on_ko = next(a for a in get_card_entry("ST21-015")["abilities"] if a["timing"] == "on_ko")
    assert "索隆" in str(on_ko["ops"][0].get("exclude_name") or "")


def test_st31_004_rush_both_and_per_straw() -> None:
    rush = {
        a["timing"]
        for a in get_card_entry("ST31-004")["abilities"]
        if a.get("require_given_don_gte") == 3
    }
    assert rush >= {"your_turn", "opponent_turn"}
    play = next(a for a in get_card_entry("ST31-004")["abilities"] if a["timing"] == "on_play")
    op = play["ops"][0]
    assert op.get("per_choose") is True
    assert op.get("target_kind") == "opponent_character"
    assert "Straw Hat" in str(op.get("per_own_trait") or "")


def test_op13_015_luffy_includes_leader() -> None:
    op = get_card_entry("OP13-015")["abilities"][0]["ops"][0]
    assert op.get("target_kind") == "own_leader_or_character"
    assert op.get("duration") == "turn"
    assert "Luffy" in str(op.get("name_contains") or "")


def test_st21_009_straw_trait() -> None:
    op = get_card_entry("ST21-009")["abilities"][0]["ops"][0]
    assert op.get("from_rested") is True
    assert "Straw Hat" in str(op.get("trait_contains") or "")


if __name__ == "__main__":
    setup_module()
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all ok")
