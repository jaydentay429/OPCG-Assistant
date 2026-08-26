"""OP17-106..119 encoding / runtime (Big Mom remainder + Rocks/Loki)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import ability_is_runnable, get_card_entry, reload_effect_library  # noqa: E402
from battle.engine import effective_counter  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

IDS = [f"OP17-{i:03d}" for i in range(106, 120)]


def test_op17_106_to_119_runnable():
    reload_effect_library(force=True)
    for cid in IDS:
        abilities = get_card_entry(cid)["abilities"]
        bad = [a for a in abilities if a.get("ops") and not ability_is_runnable(a)]
        assert not bad, f"{cid} still has unrunnable abilities: {bad}"


def test_op17_106_smoothie():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-106")
    on_play = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    assert on_play.get("require_your_turn") is True
    assert on_play["ops"][0].get("op") == "rest_don"
    assert on_play["ops"][-1].get("owner") == "opponent"
    assert any(a.get("timing") == "trigger" for a in entry["abilities"])


def test_op17_108_brulee_trigger():
    reload_effect_library(force=True)
    trig = next(a for a in get_card_entry("OP17-108")["abilities"] if a["timing"] == "trigger")
    assert trig["ops"][0].get("op") == "rest_character"
    assert trig["ops"][0].get("cost_lte") == 6


def test_op17_109_draw_after_trigger_cost():
    reload_effect_library(force=True)
    on_play = next(a for a in get_card_entry("OP17-109")["abilities"] if a["timing"] == "on_play")
    assert on_play["ops"][0].get("require_trigger") is True
    assert on_play["ops"][1].get("count") == 3


def test_op17_110_perospero():
    reload_effect_library(force=True)
    on_play = next(a for a in get_card_entry("OP17-110")["abilities"] if a["timing"] == "on_play")
    assert on_play.get("require_your_turn") is True
    assert on_play["ops"][1].get("keyword") == "rush"
    assert any(a.get("timing") == "trigger" for a in get_card_entry("OP17-110")["abilities"])


def test_op17_111_reveal_then_ko():
    reload_effect_library(force=True)
    on_play = next(a for a in get_card_entry("OP17-111")["abilities"] if a["timing"] == "on_play")
    assert on_play["ops"][0].get("op") == "reveal_hand"
    assert on_play["ops"][0].get("require_trigger") is True
    assert on_play["ops"][1].get("cost_lte") == 1


def test_op17_112_linlin_aura_and_choose():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-112")
    aura = next(a for a in entry["abilities"] if a["timing"] == "your_turn")
    sbp = aura["ops"][0]
    assert sbp.get("op") == "set_base_power"
    assert sbp.get("base_power_eq") == 4000
    assert sbp.get("require_trigger") is True
    on_play = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    assert on_play["ops"][1].get("op") == "choose_one"


def test_op17_114_sweet_generals():
    reload_effect_library(force=True)
    on_play = next(a for a in get_card_entry("OP17-114")["abilities"] if a["timing"] == "on_play")
    assert on_play.get("require_your_turn") is True
    assert on_play["ops"][0].get("op") == "rest_don"
    assert on_play["ops"][-1].get("count") == 2
    assert any(a.get("timing") == "trigger" for a in get_card_entry("OP17-114")["abilities"])


def test_op17_115_event_main_and_counter():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-115")
    main = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    assert main["ops"][0].get("keyword") == "blockerless"
    assert main["ops"][0].get("target_kind") == "leader"
    ctr = next(a for a in entry["abilities"] if a["timing"] == "counter_event")
    assert ctr["ops"][0].get("amount") == 4000
    assert "Linlin" in str(ctr["ops"][0].get("name_contains") or "")


def test_op17_116_fulgora():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-116")
    main = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    assert main["ops"][1].get("target_kind") == "opponent_stage"
    ctr = next(a for a in entry["abilities"] if a["timing"] == "counter_event")
    assert ctr.get("require_own_trigger_chars_gte") == 2


def test_op17_117_maser_saber():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-117")
    ctr = next(a for a in entry["abilities"] if a["timing"] == "counter_event")
    assert ctr["ops"][0].get("amount") == 3000
    trig = next(a for a in entry["abilities"] if a["timing"] == "trigger")
    assert trig["ops"][0].get("op") == "choose_one"
    assert trig["ops"][0].get("chooser") == "opponent"


def test_op17_118_xebec():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-118")
    hc = next(a for a in entry["abilities"] if a["timing"] == "hand_cost")
    assert hc.get("require_hand_only_chars_no_counter") is True
    play = next(a for a in entry["abilities"] if a["timing"] == "on_play")["ops"][1]
    assert play.get("different_names") is True
    assert play.get("total_cost_lte") == 9


def test_op17_118_hand_counter_gate():
    reload_effect_library(force=True)

    def _cat(cid: str):
        base = {
            "OP17-118": {"name": "Rocks.D.Xebec", "card_type": "CHARACTER", "cost": "10", "power": "12000"},
            "R1": {"name": "Rock A", "card_type": "CHARACTER", "cost": "3", "power": "4000"},
            "R2": {"name": "Rock B", "card_type": "CHARACTER", "cost": "4", "power": "5000", "counter": "1000"},
        }
        return base.get(cid, {"name": cid, "card_type": "CHARACTER", "cost": "1", "power": "1000"})

    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP01-001",
        hand=["R1", "R2"],
    )
    p1 = PlayerState(seat=1, user_id="u1", username="P2", is_ai=False, leader_card_id="OP01-001")
    st = MatchState(room_code="test", players=[p0, p1])
    assert effective_counter(st, 0, "OP17-118", _cat) == 0
    st.players[0].hand = ["R1", "OP17-118"]
    assert effective_counter(st, 0, "OP17-118", _cat) == 2000


def test_op17_119_loki():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-119")
    assert any(a.get("timing") == "opponent_turn" for a in entry["abilities"])
    on_play = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    assert on_play["ops"][0].get("total_cost_lte") == 4
    assert not any(a.get("timing") == "on_play" and a["ops"][0].get("op") == "grant_cost" for a in entry["abilities"])
