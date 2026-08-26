"""Batch-P effect encoding fixes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402


def setup_module() -> None:
    reload_effect_library()


def test_op10_099_blocker_same_target() -> None:
    ab = next(a for a in get_card_entry("OP10-099")["abilities"] if a["timing"] == "end_of_your_turn")
    assert ab["ops"][1]["op"] == "set_character_active"
    grant = ab["ops"][2]
    assert grant["op"] == "grant_keyword"
    assert grant.get("same_target_as_prior") is True
    assert grant.get("keyword") == "blocker"


def test_eb04_059_deficit_on_ability() -> None:
    ab = next(a for a in get_card_entry("EB04-059")["abilities"] if a["timing"] == "on_play")
    assert ab.get("require_chars_deficit_gte") == 1
    kos = [o for o in ab["ops"] if o["op"] == "ko"]
    assert len(kos) == 2
    assert all(o.get("require_chars_deficit_gte") is None for o in kos)


def test_op10_109_trigger_no_opp_life() -> None:
    trig = next(a for a in get_card_entry("OP10-109")["abilities"] if a["timing"] == "trigger")
    assert all(o.get("op") != "trash_life" for o in trig["ops"])
    on_ko = next(a for a in get_card_entry("OP10-109")["abilities"] if a["timing"] == "on_ko")
    assert on_ko["ops"][0]["op"] == "trash_life"
    assert on_ko["ops"][0].get("owner") == "opponent"


def test_op13_113_trigger_activates_on_play() -> None:
    trig = next(a for a in get_card_entry("OP13-113")["abilities"] if a["timing"] == "trigger")
    assert len(trig["ops"]) == 1
    assert trig["ops"][0]["op"] == "activate_timing"
    assert trig["ops"][0]["timing"] == "on_play"
    play = next(a for a in get_card_entry("OP13-113")["abilities"] if a["timing"] == "on_play")
    assert play["ops"][0].get("top_n") == 4
    assert play["ops"][0].get("require_trigger") is True


def test_op15_105_both_turns_no_free_life() -> None:
    entry = get_card_entry("OP15-105")
    timings = {a["timing"] for a in entry["abilities"]}
    assert "your_turn" in timings and "opponent_turn" in timings
    for a in entry["abilities"]:
        ops = a["ops"]
        assert len(ops) == 1
        assert ops[0]["op"] == "replace_leave"
        assert ops[0].get("base_power_lte") == 7000


def test_st36_002_add_life_your_turn() -> None:
    play = next(a for a in get_card_entry("ST36-002")["abilities"] if a["timing"] == "on_play")
    assert play["ops"][0]["op"] == "add_life"
    assert play.get("require_your_turn") is True
    assert "Kid" in str(play.get("require_leader_trait") or "") or "基德" in str(play.get("require_leader_trait") or "")


def test_st36_003_set_base_duration() -> None:
    ab = next(a for a in get_card_entry("ST36-003")["abilities"] if a["timing"] == "trigger")
    assert ab["ops"][0]["op"] == "draw"
    sbp = ab["ops"][1]
    assert sbp["op"] == "set_base_power"
    assert sbp.get("amount") == 7000
    assert sbp.get("duration") == "turn"


def test_st36_005_kid_name_redirect() -> None:
    ab = next(a for a in get_card_entry("ST36-005")["abilities"] if a["timing"] == "on_opponent_attack")
    red = ab["ops"][1]
    assert red["op"] == "redirect_attack"
    assert "尤斯塔斯" in str(red.get("name_contains") or "") or "Kid" in str(red.get("name_contains") or "")
    assert red.get("base_power_gte") == 5000


def test_op08_112_trigger_activate() -> None:
    trig = next(a for a in get_card_entry("OP08-112")["abilities"] if a["timing"] == "trigger")
    assert trig["ops"][0]["op"] == "activate_timing"
