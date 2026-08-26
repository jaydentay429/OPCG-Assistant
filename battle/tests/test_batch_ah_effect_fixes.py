"""Batch-AH effect encoding fixes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402


def setup_module() -> None:
    reload_effect_library()


def test_op13_002_ace_damage_and_own_char_ko() -> None:
    abs_ = get_card_entry("OP13-002")["abilities"]
    assert any(a["timing"] == "on_life_damage" and a.get("once") for a in abs_)
    ko = [a for a in abs_ if a.get("on_own_char_ko")]
    assert len(ko) == 2
    assert all(a.get("require_victim_base_power_gte") == 6000 for a in ko)
    assert not any(a["timing"] == "on_ko" for a in abs_)


def test_op08_044_reveal_wb_cost() -> None:
    ops = get_card_entry("OP08-044")["abilities"][0]["ops"]
    assert ops[0]["op"] == "reveal_hand" and ops[0].get("as_cost")
    assert ops[0].get("count") == 2
    assert "白鬍子" in str(ops[0].get("trait_includes") or ops[0].get("trait_contains") or "")


def test_op13_054_draw_gated_attach_always() -> None:
    ops = get_card_entry("OP13-054")["abilities"][0]["ops"]
    assert ops[0]["op"] == "draw" and ops[0].get("require_life_lte") == 3
    assert ops[1]["op"] == "attach_don" and ops[1].get("from_rested") is True
    assert get_card_entry("OP13-054")["abilities"][0].get("require_life_lte") is None


def test_op08_047_bounce_any_cost6() -> None:
    ops = get_card_entry("OP08-047")["abilities"][0]["ops"]
    assert ops[0].get("as_cost") and ops[0].get("exclude_self")
    assert ops[0].get("cost_lte") is None
    assert ops[1].get("target_kind") == "any_character" and ops[1].get("cost_lte") == 6


def test_op16_020_rest_don_and_reveal() -> None:
    ops = get_card_entry("OP16-020")["abilities"][0]["ops"]
    assert ops[0]["op"] == "rest_don" and ops[0].get("as_cost")
    assert ops[1]["op"] == "reveal_hand" and ops[1].get("power_eq") == 8000
    assert ops[2]["op"] == "draw"


def test_op14_018_live_field_power() -> None:
    ab = get_card_entry("OP14-018")["abilities"][0]
    assert ab.get("require_field_char_power_gte") == 8000
    assert ab.get("require_field_char_base_power_gte") is None


def test_st22_015_newgate_bilingual() -> None:
    ab = get_card_entry("ST22-015")["abilities"][0]
    assert "白鬍子" in str(ab.get("require_leader_trait") or "")
    assert "紐蓋特" in str(ab["ops"][0].get("name_contains") or "") or "Newgate" in str(
        ab["ops"][0].get("name_contains") or ""
    )


def test_st22_002_izo_exclude() -> None:
    op = get_card_entry("ST22-002")["abilities"][0]["ops"][0]
    assert "以藏" in str(op.get("exclude_name") or "") or "Izo" in str(op.get("exclude_name") or "")
    assert "白鬍子" in str(op.get("trait_contains") or "")


if __name__ == "__main__":
    setup_module()
    test_op13_002_ace_damage_and_own_char_ko()
    test_op08_044_reveal_wb_cost()
    test_op13_054_draw_gated_attach_always()
    test_op08_047_bounce_any_cost6()
    test_op16_020_rest_don_and_reveal()
    test_op14_018_live_field_power()
    test_st22_015_newgate_bilingual()
    test_st22_002_izo_exclude()
    print("ok")
