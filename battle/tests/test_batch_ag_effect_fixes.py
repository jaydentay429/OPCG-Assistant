"""Batch-AG effect encoding fixes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402


def setup_module() -> None:
    reload_effect_library()


def test_op08_098_play_then_life_if_played() -> None:
    ops = get_card_entry("OP08-098")["abilities"][0]["ops"]
    assert ops[0]["op"] == "play_from_hand"
    assert ops[0].get("cost_lte_own_don_field") is True
    assert "香朵拉" in str(ops[0].get("trait_contains") or "")
    assert ops[1]["op"] == "life_to_hand" and ops[1].get("if_played") is True


def test_life_to_hand_schema_keeps_if_played() -> None:
    entry = normalize_card_entry(
        "X",
        {
            "version": 1,
            "abilities": [
                {
                    "timing": "when_attacking",
                    "ops": [{"op": "life_to_hand", "count": 1, "if_played": True, "owner": "self"}],
                }
            ],
        },
    )
    assert entry["abilities"][0]["ops"][0].get("if_played") is True


def test_op15_101_noland_or_shandian() -> None:
    op = get_card_entry("OP15-101")["abilities"][0]["ops"][1]
    assert op.get("name_or_trait") is True
    assert op.get("max_add") == 2
    assert "Noland" in str(op.get("name_contains") or "") or "諾蘭德" in str(op.get("name_contains") or "")
    assert "香朵拉" in str(op.get("trait_contains") or "")


def test_op08_110_play_stage_upper_yard() -> None:
    ops = get_card_entry("OP08-110")["abilities"][0]["ops"]
    assert "神之島" in str(ops[0].get("name_contains") or "") or "Upper Yard" in str(ops[0].get("name_contains") or "")
    assert ops[1].get("card_type") == "stage"


def test_op08_109_kalgara_bilingual_field() -> None:
    ab = get_card_entry("OP08-109")["abilities"][0]
    assert "Kalgara" in str(ab.get("require_own_name_on_field") or "")
    assert "卡爾葛拉" in str(ab.get("require_own_name_on_field") or "")
    assert "香朵拉" in str(ab.get("require_leader_trait") or "")


def test_op08_115_buff_gated_play_always() -> None:
    ab = get_card_entry("OP08-115")["abilities"][0]
    assert ab.get("require_leader_trait") is None
    assert "香朵拉" in str(ab["ops"][0].get("require_leader_trait") or "")
    assert ab["ops"][1].get("card_type") == "stage"
    assert ab["ops"][1].get("require_leader_trait") is None


def test_op15_108_sky_bilingual() -> None:
    op = get_card_entry("OP15-108")["abilities"][0]["ops"][0]
    assert "空島" in str(op.get("trait_contains") or "")
    assert op.get("reveal_adds") is True


def test_op05_117_sky_search() -> None:
    op = get_card_entry("OP05-117")["abilities"][0]["ops"][0]
    assert "空島" in str(op.get("trait_contains") or "")
    assert op.get("top_n") == 5


if __name__ == "__main__":
    setup_module()
    test_op08_098_play_then_life_if_played()
    test_life_to_hand_schema_keeps_if_played()
    test_op15_101_noland_or_shandian()
    test_op08_110_play_stage_upper_yard()
    test_op08_109_kalgara_bilingual_field()
    test_op08_115_buff_gated_play_always()
    test_op15_108_sky_bilingual()
    test_op05_117_sky_search()
    print("ok")
