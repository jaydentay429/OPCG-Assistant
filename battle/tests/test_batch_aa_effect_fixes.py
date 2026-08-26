"""Batch-AA effect encoding fixes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402


def setup_module() -> None:
    reload_effect_library()


def test_op11_062_look_then_buff_both_timings() -> None:
    abs_ = get_card_entry("OP11-062")["abilities"]
    assert {a["timing"] for a in abs_} == {"when_attacking", "on_opponent_attack"}
    for ab in abs_:
        assert ab.get("once") is True
        ops = ab["ops"]
        assert ops[0]["op"] == "return_don" and ops[0].get("as_cost") and ops[0]["count"] == 1
        assert ops[1]["op"] == "look_opp_deck"
        assert ops[2]["op"] == "buff_self" and ops[2]["amount"] == 1000
        assert ops[2].get("duration") == "battle"


def test_op07_077_leader_trait_or() -> None:
    ab = get_card_entry("OP07-077")["abilities"][0]
    trait = str(ab.get("require_leader_trait") or "")
    assert "Animal Kingdom" in trait or "百獸" in trait
    assert "Big Mom" in trait or "BIG MOM" in trait
    search = ab["ops"][0]
    assert search.get("top_n") == 5
    st = str(search.get("trait_contains") or "")
    assert "Animal Kingdom" in st or "百獸" in st
    assert "Big Mom" in st or "BIG MOM" in st


def test_op08_077_don2_ko2() -> None:
    ops = get_card_entry("OP08-077")["abilities"][0]["ops"]
    assert ops[0]["op"] == "return_don" and ops[0]["count"] == 2 and ops[0].get("as_cost")
    assert ops[1]["op"] == "ko" and ops[1].get("count") == 2 and ops[1].get("cost_lte") == 6


def test_op11_074_declare_then_rest() -> None:
    ops = get_card_entry("OP11-074")["abilities"][0]["ops"]
    look = next(o for o in ops if o["op"] == "look_opp_deck")
    assert look.get("declare_cost") is True
    rest = next(o for o in ops if o["op"] == "rest_opponent_character")
    assert rest.get("if_declared_cost_match") is True
    assert rest.get("cost_lte") == 4


def test_op11_066_declare_ko_then_don() -> None:
    ops = get_card_entry("OP11-066")["abilities"][0]["ops"]
    assert ops[0].get("declare_cost") is True
    assert ops[1]["op"] == "ko" and ops[1].get("if_declared_cost_match") and ops[1].get("base_cost_lte") == 3
    assert ops[2]["op"] == "gain_don" and ops[2].get("as_rested")
    assert ops[2].get("if_declared_cost_match") is not True


def test_op11_081_declare_ko() -> None:
    on_play = next(a for a in get_card_entry("OP11-081")["abilities"] if a["timing"] == "on_play")
    ops = on_play["ops"]
    assert ops[0].get("declare_cost") is True
    assert ops[1].get("if_declared_cost_match") and ops[1].get("base_cost_lte") == 8


def test_prb02_010_opp_don_gate_and_power() -> None:
    ab = get_card_entry("PRB02-010")["abilities"][0]
    assert ab.get("require_don_field_gte") is None
    assert ab.get("require_opp_don_field_gte") is None
    ops = ab["ops"]
    assert ops[0]["op"] == "return_don" and ops[0].get("as_cost")
    draw = ops[1]
    assert draw.get("require_opp_don_field_gte") == 6
    assert "Big Mom" in str(draw.get("require_leader_trait") or "") or "BIG MOM" in str(
        draw.get("require_leader_trait") or ""
    )
    play = ops[2]
    assert play.get("power_gte") == 6000 and play.get("power_lte") == 8000
    assert play.get("require_opp_don_field_gte") == 6


def test_st34_001_don_return_your_turn_only() -> None:
    abs_ = get_card_entry("ST34-001")["abilities"]
    timings = [a["timing"] for a in abs_]
    assert timings.count("on_don_returned") == 1
    assert "your_turn" not in timings
    don = next(a for a in abs_ if a["timing"] == "on_don_returned")
    assert don.get("require_your_turn") is True
    assert don.get("once") is True
    assert don["ops"][0].get("count") == 2 and don["ops"][0].get("as_rested")


def test_st34_003_search_hand() -> None:
    op = get_card_entry("ST34-003")["abilities"][0]["ops"][0]
    assert op.get("top_n") == 3
    assert op.get("destination") == "hand"
    assert "Big Mom" in str(op.get("trait_contains") or "") or "BIG MOM" in str(op.get("trait_contains") or "")


def test_st34_004_optional_trash_cost() -> None:
    ops = get_card_entry("ST34-004")["abilities"][0]["ops"]
    assert ops[0]["op"] == "return_don" and ops[0]["count"] == 4
    assert ops[1]["op"] == "trash_hand" and ops[1].get("optional") and ops[1].get("as_cost")
    assert ops[3]["op"] == "set_base_power" and ops[3].get("amount") == 0


def test_st34_005_base_power_ko() -> None:
    ops = get_card_entry("ST34-005")["abilities"][0]["ops"]
    assert ops[1].get("base_power_lte") == 2000


def test_op08_062_katakuri_play() -> None:
    ab = get_card_entry("OP08-062")["abilities"][0]
    assert "Big Mom" in str(ab.get("require_leader_trait") or "") or "BIG MOM" in str(
        ab.get("require_leader_trait") or ""
    )
    play = ab["ops"][1]
    assert play.get("cost_gte") == 3 and play.get("cost_lte_opp_don_field") is True
    assert "Katakuri" in str(play.get("name_contains") or "") or "卡塔克利" in str(play.get("name_contains") or "")


if __name__ == "__main__":
    setup_module()
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all batch_aa tests passed")
