"""OP17-091..105 encoding / runtime (Elbaph remainder + Big Mom package)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import ability_is_runnable, get_card_entry, reload_effect_library  # noqa: E402

IDS = [f"OP17-{i:03d}" for i in range(91, 106)]


def test_op17_091_to_105_runnable():
    reload_effect_library(force=True)
    for cid in IDS:
        if cid in {"OP17-100"}:
            continue
        abilities = get_card_entry(cid)["abilities"]
        bad = [a for a in abilities if a.get("ops") and not ability_is_runnable(a)]
        assert not bad, f"{cid} still has unrunnable abilities: {bad}"


def test_op17_091_brook():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-091")
    assert any(a.get("timing") == "opponent_turn" for a in entry["abilities"])
    on_play = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    assert on_play["ops"][0].get("owner") == "opponent"
    assert int(on_play.get("require_field_char_cost_gte") or 0) == 12


def test_op17_092_brogy_mirrors_dorry():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-092")
    assert any(a.get("timing") == "opponent_turn" for a in entry["abilities"])
    on_play = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    assert "Dorry" in str(on_play["ops"][0].get("name_contains") or "")
    assert on_play["ops"][1].get("op") == "cannot_play_from_hand"


def test_op17_093_luffy_rush_and_trash_play():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-093")
    rush = next(a for a in entry["abilities"] if a["timing"] == "your_turn")
    assert rush["ops"][0].get("keyword") == "rush"
    on_play = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    assert on_play["ops"][0].get("op") == "draw"
    assert on_play["ops"][1].get("from_zone") == "trash"
    assert on_play.get("require_field_char_cost_gte") is None


def test_op17_094_rodo():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-094")
    assert all(a["ops"][0].get("amount") == 12 for a in entry["abilities"])
    assert "Elbaph" in str(entry["abilities"][0].get("require_leader_trait") or "")


def test_op17_095_zoro_replace():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-095")
    rep = next(
        a
        for a in entry["abilities"]
        if a["timing"] == "your_turn" and any(o.get("op") == "replace_leave" for o in a.get("ops") or [])
    )
    op = rep["ops"][0]
    assert op.get("trigger") == "opp_remove"
    assert op.get("target") == "own_filtered"
    assert op.get("trash_count") == 3


def test_op17_096_event():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-096")
    ctr = next(a for a in entry["abilities"] if a["timing"] == "counter_event")
    assert int(ctr.get("require_field_char_cost_gte") or 0) == 12
    trig = next(a for a in entry["abilities"] if a["timing"] == "trigger")
    assert trig["ops"][0].get("op") == "add_from_trash"


def test_op17_097_098_events():
    reload_effect_library(force=True)
    main97 = next(a for a in get_card_entry("OP17-097")["abilities"] if a["timing"] == "on_play")
    assert main97["ops"][0].get("all") is True
    assert main97["ops"][0].get("amount") == -1
    main98 = next(a for a in get_card_entry("OP17-098")["abilities"] if a["timing"] == "on_play")
    assert main98["ops"][0].get("count") == 6
    assert main98["ops"][1].get("count") == 2


def test_op17_101_caribou():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-101")
    act = next(a for a in entry["abilities"] if a["timing"] == "activate_main")
    assert act["ops"][1].get("amount") == -3000
    trig = next(a for a in entry["abilities"] if a["timing"] == "trigger")
    assert trig["ops"][1].get("cost_lte") == 5


def test_op17_102_oven():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-102")
    ko = next(a for a in entry["abilities"] if a["timing"] == "on_ko")
    assert ko["ops"][0].get("power_lte") == 4000
    assert "Oven" in str(ko["ops"][0].get("exclude_name") or "")
    assert any(a.get("timing") == "trigger" for a in entry["abilities"])


def test_op17_103_104_your_turn_on_play():
    reload_effect_library(force=True)
    for cid in ("OP17-103", "OP17-104"):
        on_play = next(a for a in get_card_entry(cid)["abilities"] if a["timing"] == "on_play")
        assert on_play.get("require_your_turn") is True
        assert "Big Mom" in str(on_play.get("require_leader_trait") or "")
        assert on_play["ops"][0].get("op") in {"add_life", "rest_don"}


def test_op17_105_chiffon():
    reload_effect_library(force=True)
    on_play = next(a for a in get_card_entry("OP17-105")["abilities"] if a["timing"] == "on_play")
    assert on_play["ops"][0].get("require_trigger") is True
    assert on_play["ops"][1].get("op") == "return_to_hand"
    assert on_play["ops"][1].get("require_trigger") is True


def test_op17_079_blocker_both_turns():
    reload_effect_library(force=True)
    timings = {a["timing"] for a in get_card_entry("OP17-079")["abilities"]}
    assert timings == {"your_turn", "opponent_turn"}
