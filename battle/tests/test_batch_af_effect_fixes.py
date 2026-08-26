"""Batch-AF effect encoding fixes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402


def setup_module() -> None:
    reload_effect_library()


def test_st13_001_place_on_life_cost_filters() -> None:
    ab = get_card_entry("ST13-001")["abilities"][0]
    assert ab.get("require_don_attached_gte") == 1 and ab.get("once") is True
    cost, buff = ab["ops"]
    assert cost["op"] == "place_on_life"
    assert cost.get("as_cost") is True
    assert cost.get("cost_gte") == 3 and cost.get("power_gte") == 7000
    assert cost.get("face") == "up" and cost.get("position") == "top"
    assert buff["op"] == "buff" and buff.get("amount") == 2000
    assert buff.get("optional") is True and buff.get("duration") == "next_turn"


def test_st13_001_schema_keeps_power_gte() -> None:
    entry = normalize_card_entry(
        "ST13-001",
        {
            "version": 1,
            "abilities": [
                {
                    "timing": "activate_main",
                    "ops": [
                        {
                            "op": "place_on_life",
                            "owner": "self",
                            "as_cost": True,
                            "optional": True,
                            "cost_gte": 3,
                            "power_gte": 7000,
                            "face": "up",
                            "position": "top",
                            "target_kind": "own_character",
                        }
                    ],
                }
            ],
        },
    )
    op = entry["abilities"][0]["ops"][0]
    assert op.get("power_gte") == 7000 and op.get("as_cost") is True


def test_eb03_053_single_on_play_with_life_gate() -> None:
    abs_ = get_card_entry("EB03-053")["abilities"]
    assert len([a for a in abs_ if a["timing"] == "on_play"]) == 1
    ops = next(a for a in abs_ if a["timing"] == "on_play")["ops"]
    assert ops[0]["op"] == "attach_don"
    assert ops[1]["op"] == "life_to_hand"
    assert ops[1].get("require_opp_life_gte") == 3
    assert ops[1].get("owner") == "opponent"


def test_op09_108_rev_army_bilingual() -> None:
    ab = get_card_entry("OP09-108")["abilities"][0]
    trait = str(ab.get("require_leader_trait") or "")
    assert "Revolutionary" in trait and "革命" in trait
    assert ab.get("require_total_life_lte") == 5


def test_eb04_002_reveal_and_exclude() -> None:
    op = get_card_entry("EB04-002")["abilities"][0]["ops"][0]
    assert op.get("reveal_adds") is True
    assert "Bonney" in str(op.get("exclude_name") or "") or "波妮" in str(op.get("exclude_name") or "")


def test_op13_016_reveal_cost_filter() -> None:
    ab = get_card_entry("OP13-016")["abilities"][0]
    assert "Sabo" in str(ab.get("require_leader_name") or "")
    op = ab["ops"][0]
    assert op.get("cost_gte") == 3 and op.get("reveal_adds") is True


def test_op14_104_choose_optional() -> None:
    op = get_card_entry("OP14-104")["abilities"][0]["ops"][0]
    assert op["op"] == "choose_one" and op.get("optional") is True


def test_eb04_007_rush_character_gate() -> None:
    act = next(a for a in get_card_entry("EB04-007")["abilities"] if a["timing"] == "activate_main")
    assert act.get("require_opp_char_power_gte") == 8000
    assert act["ops"][0].get("keyword") == "rush_character"


if __name__ == "__main__":
    setup_module()
    test_st13_001_place_on_life_cost_filters()
    test_st13_001_schema_keeps_power_gte()
    test_eb03_053_single_on_play_with_life_gate()
    test_op09_108_rev_army_bilingual()
    test_eb04_002_reveal_and_exclude()
    test_op13_016_reveal_cost_filter()
    test_op14_104_choose_optional()
    test_eb04_007_rush_character_gate()
    print("ok")
