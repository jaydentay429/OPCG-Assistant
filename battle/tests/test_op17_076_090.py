"""OP17-076..090 encoding / runtime (Events + Elbaph package)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import ability_is_runnable, get_card_entry, reload_effect_library  # noqa: E402

IDS = [f"OP17-{i:03d}" for i in range(76, 91)]


def test_op17_076_to_090_runnable():
    reload_effect_library(force=True)
    for cid in IDS:
        if cid in {"OP17-088"}:
            continue
        abilities = get_card_entry(cid)["abilities"]
        bad = [a for a in abilities if a.get("ops") and not ability_is_runnable(a)]
        assert not bad, f"{cid} still has unrunnable abilities: {bad}"


def test_op17_076_event_counter_and_trigger():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-076")
    ctr = next(a for a in entry["abilities"] if a["timing"] == "counter_event")
    assert ctr["ops"][0].get("op") == "trash_hand"
    assert ctr["ops"][1].get("target_kind") == "own_leader_or_character"
    trig = next(a for a in entry["abilities"] if a["timing"] == "trigger")
    assert trig["ops"][0].get("op") == "return_don"
    assert trig["ops"][1].get("count") == 2


def test_op17_077_078_akp_events():
    reload_effect_library(force=True)
    ev77 = get_card_entry("OP17-077")
    main77 = next(a for a in ev77["abilities"] if a["timing"] == "on_play")
    assert main77["ops"][0].get("count") == 3
    assert main77["ops"][2].get("as_rested") is True
    assert "Animal Kingdom" in str(main77.get("require_leader_trait") or "")
    ctr77 = next(a for a in ev77["abilities"] if a["timing"] == "counter_event")
    assert ctr77["ops"][0].get("op") == "return_don"

    ev78 = get_card_entry("OP17-078")
    main78 = next(a for a in ev78["abilities"] if a["timing"] == "on_play")
    assert main78["ops"][0].get("count") == 2
    ctr78 = next(a for a in ev78["abilities"] if a["timing"] == "counter_event")
    assert ctr78["ops"][0].get("amount") == 4000


def test_op17_079_luffy_blocker_aura():
    reload_effect_library(force=True)
    aura = get_card_entry("OP17-079")["abilities"][0]
    assert aura["ops"][0].get("cost_gte") == 12
    assert aura["ops"][0].get("keyword") == "blocker"


def test_op17_080_082_cost12_continuous():
    reload_effect_library(force=True)
    for cid in ("OP17-080", "OP17-082"):
        cont = next(a for a in get_card_entry(cid)["abilities"] if a["timing"] == "your_turn")
        assert int(cont.get("require_field_char_cost_gte") or 0) == 12
        assert cont["ops"][0].get("amount") == 3000


def test_op17_081_gerd():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-081")
    cont = next(a for a in entry["abilities"] if a["timing"] == "your_turn")
    assert "Elbaph" in str(cont.get("require_leader_trait") or "")
    on_play = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    add = next(o for o in on_play["ops"] if o.get("op") == "add_from_trash")
    assert add.get("cost_lte") == 8
    assert "Gerd" in str(add.get("name_exclude") or "")


def test_op17_083_jinbe():
    reload_effect_library(force=True)
    cont = get_card_entry("OP17-083")["abilities"][0]
    assert cont["ops"][0].get("keyword") == "blocker"
    assert cont["ops"][1].get("amount") == 3000


def test_op17_084_chopper_unblockable():
    reload_effect_library(force=True)
    on_play = next(a for a in get_card_entry("OP17-084")["abilities"] if a["timing"] == "on_play")
    assert int(on_play.get("require_field_char_cost_gte") or 0) == 12
    assert on_play["ops"][0].get("keyword") == "blockerless"


def test_op17_085_dorry():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-085")
    assert any(a.get("timing") == "your_turn" for a in entry["abilities"])
    on_play = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    assert on_play["ops"][0].get("from_zone") == "hand_or_trash"
    assert on_play["ops"][1].get("op") == "cannot_play_from_hand"


def test_op17_087_robin_debuff():
    reload_effect_library(force=True)
    on_play = next(a for a in get_card_entry("OP17-087")["abilities"] if a["timing"] == "on_play")
    assert on_play["ops"][0].get("amount") == -3000


def test_op17_089_saul():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-089")
    assert any(a.get("timing") == "your_turn" for a in entry["abilities"])
    search = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    assert search["ops"][0].get("op") == "search_deck"


def test_op17_090_franky():
    reload_effect_library(force=True)
    on_play = next(a for a in get_card_entry("OP17-090")["abilities"] if a["timing"] == "on_play")
    assert int(on_play.get("require_field_char_cost_gte") or 0) == 12
    assert on_play["ops"][0].get("cost_lte") == 2
