"""Batch-AD effect encoding fixes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402


def setup_module() -> None:
    reload_effect_library()


def test_op11_021_fish_trait_and_optional_don() -> None:
    ops = get_card_entry("OP11-021")["abilities"][0]["ops"]
    assert "Fish-Man" in str(ops[0].get("trait_contains") or "") or "魚人" in str(ops[0].get("trait_contains") or "")
    assert ops[1]["op"] == "active_don" and ops[1].get("optional") is True


def test_op06_025_exclude_camie_bilingual() -> None:
    op = get_card_entry("OP06-025")["abilities"][0]["ops"][0]
    assert "Camie" in str(op.get("exclude_name") or "") and "海咪" in str(op.get("exclude_name") or "")
    assert op.get("reveal_adds") is True


def test_op06_033_choose_cost_then_ko() -> None:
    ops = get_card_entry("OP06-033")["abilities"][0]["ops"]
    assert ops[0]["op"] == "choose_one" and ops[0].get("as_cost") and ops[0].get("optional")
    assert len(ops[0]["options"]) >= 2
    assert ops[1]["op"] == "ko" and "rested" in str(ops[1].get("target_kind") or "")


def test_eb04_015_rest_card_cost() -> None:
    ops = get_card_entry("EB04-015")["abilities"][0]["ops"]
    rest = ops[0]
    assert rest["op"] == "rest_character" and rest.get("as_cost") and rest.get("include_don")
    play = ops[1]
    assert play["op"] == "play_from_hand" and play.get("color") == "green"
    assert "Fish-Man" in str(play.get("require_leader_trait") or "") or "魚人" in str(
        play.get("require_leader_trait") or ""
    )


def test_st24_004_single_on_play_sequential() -> None:
    abs_ = get_card_entry("ST24-004")["abilities"]
    assert len([a for a in abs_ if a["timing"] == "on_play"]) == 1
    ops = abs_[0]["ops"]
    assert ops[0].get("also_skip_untap") is True
    assert ops[1]["op"] == "buff" and ops[1].get("require_opp_rested_chars_gte") == 2


def test_op11_039_fish_trait_buff() -> None:
    ops = get_card_entry("OP11-039")["abilities"][0]["ops"]
    assert "Fish-Man" in str(ops[0].get("trait_contains") or "") or "魚人" in str(ops[0].get("trait_contains") or "")
    trig = next(a for a in get_card_entry("OP11-039")["abilities"] if a["timing"] == "trigger")
    assert trig["ops"][0].get("optional") is True


def test_eb04_020_fish_filters() -> None:
    ops = get_card_entry("EB04-020")["abilities"][0]["ops"]
    assert ops[0].get("trait_contains")
    assert ops[1]["op"] == "set_character_active" and ops[1].get("trait_contains")


def test_op15_032_base_cost_active_gated() -> None:
    act = next(a for a in get_card_entry("OP15-032")["abilities"] if a["timing"] == "activate_main")
    assert act.get("require_leader_trait") is None
    assert act["ops"][1].get("base_cost_lte") == 8
    assert "Straw Hat" in str(act["ops"][1].get("require_leader_trait") or "") or "草帽" in str(
        act["ops"][1].get("require_leader_trait") or ""
    )


def test_op11_030_rest_don_mandatory_with_rest_self() -> None:
    ab = get_card_entry("OP11-030")["abilities"][0]
    assert ab.get("rest_self") is True
    assert ab["ops"][0]["op"] == "rest_don" and ab["ops"][0].get("as_cost")
    assert ab["ops"][0].get("optional") is not True


def test_eb04_016_neptunian_bilingual() -> None:
    ab = next(a for a in get_card_entry("EB04-016")["abilities"] if a["timing"] == "when_attacking")
    trait = str(ab.get("require_chars_trait") or "")
    assert "Neptunian" in trait or "海王" in trait


if __name__ == "__main__":
    setup_module()
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all batch_ad tests passed")
