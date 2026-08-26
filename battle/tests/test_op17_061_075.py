"""OP17-061..075 encoding / runtime (Animal Kingdom package)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import ability_is_runnable, get_card_entry, reload_effect_library  # noqa: E402
from battle.engine import effective_counter
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

IDS = [f"OP17-{i:03d}" for i in range(61, 76)]


def _state(*, hand0: list[str] | None = None) -> MatchState:
    st = MatchState(room_code="t", status="playing", turn_seat=0)
    st.players = [
        PlayerState(seat=0, user_id="u0", username="p0", is_ai=False, leader_card_id="L", hand=list(hand0 or [])),
        PlayerState(seat=1, user_id="u1", username="p1", is_ai=False, leader_card_id="L2"),
    ]
    return st


def _cat(extra: dict | None = None):
    base = {
        "NOCTR": {"name": "No Counter", "cost": "3", "power": "4000", "counter": "0", "card_type": "CHARACTER"},
        "CTR2": {"name": "Has Counter", "cost": "3", "power": "4000", "counter": "2000", "card_type": "CHARACTER"},
    }
    if extra:
        base.update(extra)

    def catalog(cid: str):
        return base.get(cid) or {"name": cid, "cost": "3", "power": "4000", "counter": "0", "card_type": "CHARACTER"}

    return catalog


def test_op17_061_to_075_runnable():
    reload_effect_library(force=True)
    for cid in IDS:
        if cid in {"OP17-070"}:
            continue
        abilities = get_card_entry(cid)["abilities"]
        bad = [a for a in abilities if a.get("ops") and not ability_is_runnable(a)]
        assert not bad, f"{cid} still has unrunnable abilities: {bad}"


def test_op17_061_lead_performers():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-061")
    on_play = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    assert on_play["ops"][0].get("op") == "return_don"
    assert on_play["ops"][1].get("op") == "add_life"
    assert "Animal Kingdom" in str(on_play.get("require_leader_trait") or "")
    act = next(a for a in entry["abilities"] if a["timing"] == "activate_main")
    assert act["ops"][0].get("target_kind") == "self"
    assert "King" in str(act["ops"][1].get("name_contains") or "")


def test_op17_062_kaido_return_don():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-062")
    assert any(a.get("timing") == "your_turn" for a in entry["abilities"])
    ret = next(a for a in entry["abilities"] if a["timing"] == "on_don_returned")
    assert ret["ops"][0].get("op") == "gain_don"
    assert ret["ops"][1].get("op") == "active_don"
    assert ret.get("require_your_turn") is True


def test_op17_063_hand_counter_no_printed_counter():
    reload_effect_library(force=True)
    hc = next(a for a in get_card_entry("OP17-063")["abilities"] if a["timing"] == "hand_cost")
    op = hc["ops"][0]
    assert op.get("require_no_counter") is True
    assert op.get("add") is True

    st = _state(hand0=["NOCTR", "CTR2"])
    st.players[0].characters.append(CardInst(iid="k", card_id="OP17-063"))
    cat = _cat({"OP17-063": {"name": "Kaido", "cost": "8", "power": "9000", "counter": "0", "card_type": "CHARACTER"}})
    assert effective_counter(st, 0, "NOCTR", cat) == 1000
    assert effective_counter(st, 0, "CTR2", cat) == 2000

    act = next(a for a in get_card_entry("OP17-063")["abilities"] if a["timing"] == "activate_main")
    assert act.get("require_played_this_turn") is True
    assert act["ops"][2].get("same_target_as_prior") is True


def test_op17_064_072_blocker_and_battle_buff():
    reload_effect_library(force=True)
    for cid, amt in (("OP17-064", 2000), ("OP17-072", 1000)):
        entry = get_card_entry(cid)
        assert any(a.get("timing") == "your_turn" for a in entry["abilities"])
        ctr = next(a for a in entry["abilities"] if a["timing"] == "on_opponent_attack")
        assert ctr["ops"][1].get("target_kind") == "own_leader_or_character"
        assert ctr["ops"][1].get("duration") == "battle"
        assert ctr["ops"][1].get("amount") == amt


def test_op17_065_queen():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-065")
    assert any(
        a.get("timing") == "your_turn" and any(o.get("keyword") == "banish" for o in a.get("ops") or [])
        for a in entry["abilities"]
    )
    on_play = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    assert on_play["ops"][0].get("op") == "return_don"
    assert on_play["ops"][2].get("count") == 2


def test_op17_066_067_cost10_gate():
    reload_effect_library(force=True)
    for cid, op_name in (("OP17-066", "trash_hand"), ("OP17-067", "rest_opponent_character")):
        on_play = next(a for a in get_card_entry(cid)["abilities"] if a["timing"] == "on_play")
        assert int(on_play.get("require_own_char_cost_gte") or 0) == 10
        assert any(o.get("op") == op_name for o in on_play["ops"])


def test_op17_068_sasaki():
    reload_effect_library(force=True)
    atk = next(a for a in get_card_entry("OP17-068")["abilities"] if a["timing"] == "when_attacking")
    assert atk["ops"][1].get("as_rested") is True
    assert atk["ops"][1].get("count") == 2
    assert "Animal Kingdom" in str(atk.get("require_leader_trait") or "")


def test_op17_069_jack():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-069")
    assert any(
        a.get("timing") == "your_turn"
        and any(o.get("keyword") == "rush_character" for o in a.get("ops") or [])
        for a in entry["abilities"]
    )
    on_play = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    assert on_play["ops"][1].get("amount") == -2000


def test_op17_071_whos_who_trigger_split():
    reload_effect_library(force=True)
    entry = get_card_entry("OP17-071")
    on_play = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    assert on_play["ops"][0].get("op") == "return_don"
    assert not any(o.get("op") == "play_from_hand" for o in on_play["ops"])
    trig = next(a for a in entry["abilities"] if a["timing"] == "trigger")
    assert trig["ops"][0].get("self_card") is True


def test_op17_073_074_don():
    reload_effect_library(force=True)
    hawkins = next(a for a in get_card_entry("OP17-073")["abilities"] if a["timing"] == "on_play")
    assert hawkins["ops"][1].get("as_rested") is not True
    yamato = get_card_entry("OP17-074")
    assert any(a.get("timing") == "your_turn" for a in yamato["abilities"])
    play74 = next(a for a in yamato["abilities"] if a["timing"] == "on_play")
    assert play74["ops"][0].get("as_rested") is True


def test_op17_075_drake():
    reload_effect_library(force=True)
    on_play = next(a for a in get_card_entry("OP17-075")["abilities"] if a["timing"] == "on_play")
    assert on_play["ops"][0].get("count") == 2
    assert on_play["ops"][1].get("owner") == "opponent"
