"""Batch-S effect encoding fixes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_ability  # noqa: E402


def setup_module() -> None:
    reload_effect_library()


def test_op07_059_skip_untap_targets() -> None:
    ops = get_card_entry("OP07-059")["abilities"][0]["ops"]
    assert ops[0]["op"] == "return_don"
    assert ops[1].get("target_kind") == "leader"
    assert ops[1].get("require_rested") is True
    assert ops[1].get("require_chars_trait_gte") == 3
    assert ops[2].get("target_kind") == "opponent_character"
    assert get_card_entry("OP07-059")["abilities"][0].get("require_chars_trait_gte") is None


def test_eb04_033_ko_needs_foxy_count() -> None:
    ko = get_card_entry("EB04-033")["abilities"][0]["ops"][1]
    assert ko["op"] == "ko"
    assert ko.get("require_chars_trait_gte") == 3
    assert "Foxy" in str(ko.get("require_chars_trait") or "")


def test_op07_071_all_debuff() -> None:
    aura = next(a for a in get_card_entry("OP07-071")["abilities"] if a["timing"] == "opponent_turn")
    assert aura["ops"][0].get("all") is True
    assert aura.get("require_leader_trait")


def test_op10_075_draw_gate_not_ability() -> None:
    ab = get_card_entry("OP10-075")["abilities"][0]
    assert ab.get("require_don_field_deficit_gte") is None
    assert ab["ops"][1].get("require_don_field_deficit_gte") == 0


def test_op13_076_given_don() -> None:
    play = next(a for a in get_card_entry("OP13-076")["abilities"] if a["timing"] == "on_play")
    assert play.get("require_don_attached_gte") is None
    assert play["ops"][1].get("require_given_don_gte") == 1


def test_st34_004_trash_not_as_cost() -> None:
    ops = get_card_entry("ST34-004")["abilities"][0]["ops"]
    assert ops[0]["op"] == "return_don" and ops[0].get("as_cost")
    trash = ops[1]
    assert trash["op"] == "trash_hand"
    assert trash.get("optional") is True
    assert trash.get("as_cost") is None


def test_op07_060_bilingual() -> None:
    ab = get_card_entry("OP07-060")["abilities"][0]
    assert "Foxy" in str(ab.get("require_leader_trait") or "")
    assert "Itomimizu" in str(ab.get("require_no_other_name") or "") or "線蚯蚓" in str(
        ab.get("require_no_other_name") or ""
    )


def test_schema_skip_untap_require_rested() -> None:
    ab = normalize_ability(
        {
            "timing": "when_attacking",
            "ops": [{"op": "skip_untap", "target_kind": "leader", "require_rested": True}],
        }
    )
    assert ab["ops"][0].get("require_rested") is True


if __name__ == "__main__":
    setup_module()
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all ok")
