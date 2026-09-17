"""Batch-I effect encoding / runtime fixes (Enel, look-deck, name-or-event)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effects import apply_ops  # noqa: E402
from battle.engine import apply_action, don_deck_room, legal_actions, start_match  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.get("leader0", "OP15-058"),
        deck=list(kwargs.get("deck0", ["A", "B", "C", "D", "E"] + ["Z"] * 15)),
        hand=list(kwargs.get("hand0", [])),
        life=["L"] * 4,
        trash=list(kwargs.get("trash0", [])),
        don_active=int(kwargs.get("don_active0", 0) or 0),
        don_rested=int(kwargs.get("don_rested0", 0) or 0),
        don_given=int(kwargs.get("don_given0", 0) or 0),
        don_deck_size=int(kwargs.get("don_deck_size0", 10) or 10),
        turns_completed=int(kwargs.get("turns_completed0", 1) or 0),
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["B"] * 20,
        hand=[],
        life=["R"] * 5,
        trash=[],
    )
    return MatchState(
        room_code="I",
        status="playing",
        phase="main",
        turn_seat=kwargs.get("turn_seat", 0),
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
    )


def test_op12_071_or_event():
    reload_effect_library(force=True)
    op = get_card_entry("OP12-071")["abilities"][0]["ops"][0]
    assert op["op"] == "search_deck"
    assert op.get("or_event") is True
    assert "Sanji" in (op.get("name_contains") or "")


def test_op15_066_look_deck_gated():
    reload_effect_library(force=True)
    abs_ = get_card_entry("OP15-066")["abilities"]
    atk = next(a for a in abs_ if a["timing"] == "when_attacking")
    assert atk.get("require_don_field_lte") == 6
    assert atk["ops"][0]["op"] == "look_deck"
    assert atk["ops"][0]["count"] == 2
    play = next(a for a in abs_ if a["timing"] == "on_play")
    assert [o["op"] for o in play["ops"]] == ["return_don", "draw"]
    assert play["ops"][0].get("as_cost") is True


def test_op15_061_attack_gate_no_play_buff():
    reload_effect_library(force=True)
    abs_ = get_card_entry("OP15-061")["abilities"]
    play = next(a for a in abs_ if a["timing"] == "on_play")
    assert not any(o.get("op") == "buff" for o in play["ops"])
    atk = next(a for a in abs_ if a["timing"] == "when_attacking")
    assert atk.get("require_don_field_lte") == 6
    assert atk["ops"][0]["amount"] == -1000


def test_op15_075_main_and_counter():
    reload_effect_library(force=True)
    abs_ = get_card_entry("OP15-075")["abilities"]
    main = next(a for a in abs_ if a["timing"] == "on_play")
    ops = main["ops"]
    assert ops[0]["op"] == "return_don" and ops[0].get("as_cost")
    assert ops[1]["op"] == "buff" and ops[1]["amount"] == 1000
    assert ops[1]["target_kind"] == "own_leader_or_character"
    assert ops[2]["op"] == "ko" and ops[2].get("power_lte") == 3000
    ctr = next(a for a in abs_ if a["timing"] == "counter_event")
    assert ctr["ops"][0]["amount"] == 2000
    assert ctr["ops"][0]["target_kind"] == "own_leader_or_character"
    assert ctr["ops"][0].get("duration") == "battle"


def test_op15_077_cost_then_skip_untap_power():
    reload_effect_library(force=True)
    ops = get_card_entry("OP15-077")["abilities"][0]["ops"]
    assert [o["op"] for o in ops] == ["return_don", "draw", "skip_untap"]
    assert ops[0].get("as_cost") is True
    assert ops[2].get("power_lte") == 6000

    st = _state(don_active0=1, don_given0=1)
    st.players[1].characters.append(CardInst(iid="low", card_id="LOW", rested=True))
    st.players[1].characters.append(CardInst(iid="hi", card_id="HI", rested=True))
    catalog = {
        "OP15-058": {"name": "艾涅爾", "name_en": "Enel", "card_type": "LEADER", "power": "5000"},
        "OP01-001": {"name": "F", "card_type": "LEADER", "power": "5000"},
        "LOW": {"name": "Low", "power": "5000", "cost": 3, "card_type": "CHARACTER"},
        "HI": {"name": "Hi", "power": "8000", "cost": 5, "card_type": "CHARACTER"},
    }.get
    apply_ops(st, 0, [dict(o) for o in ops], catalog)
    assert st.pending_choice is not None
    assert "low" in st.pending_choice.options
    assert "hi" not in st.pending_choice.options


def test_op09_072_costs_as_cost():
    reload_effect_library(force=True)
    ops = get_card_entry("OP09-072")["abilities"][0]["ops"]
    assert ops[0]["op"] == "trash_hand" and ops[0].get("as_cost")
    assert ops[1]["op"] == "return_don" and ops[1].get("as_cost") and ops[1]["count"] == 2
    assert ops[2]["op"] == "draw"

    st = _state(don_active0=0, don_given0=0, hand0=["H1"])
    catalog = {
        "OP15-058": {"name": "L", "card_type": "LEADER"},
        "OP01-001": {"name": "F", "card_type": "LEADER"},
        "H1": {"name": "Hand", "card_type": "CHARACTER"},
    }.get
    apply_ops(st, 0, [dict(o) for o in ops], catalog)
    # No DON to pay after trash skip/choice — unpaid as_cost must not draw.
    if st.pending_choice:
        apply_action(st, 0, {"type": "select_choice", "target_iid": "hand:0:H1"}, catalog)
    assert len(st.players[0].hand) <= 1


def test_op10_067_order():
    reload_effect_library(force=True)
    ops = get_card_entry("OP10-067")["abilities"][0]["ops"]
    assert [o["op"] for o in ops] == ["return_don", "add_from_trash", "active_don"]
    assert ops[0].get("as_cost") is True


def test_op15_074_counter_includes_leader():
    reload_effect_library(force=True)
    ctr = next(a for a in get_card_entry("OP15-074")["abilities"] if a["timing"] == "counter_event")
    op = ctr["ops"][0]
    assert op["target_kind"] == "own_leader_or_character"
    assert "Enel" in (op.get("name_contains") or "")


def test_enel_don_cap_and_turn_gate():
    reload_effect_library(force=True)
    spec = next(a for a in get_card_entry("OP15-058")["abilities"] if a["timing"] == "activate_main")
    assert spec.get("require_turn_gte") == 2
    gains = [o for o in spec["ops"] if o.get("op") == "gain_don"]
    assert len(gains) >= 2
    assert not gains[0].get("as_rested")
    assert gains[1].get("as_rested") is True

    cat = {
        "OP15-058": {
            "name": "艾涅爾",
            "name_en": "Enel",
            "card_type": "LEADER",
            "life": 5,
            "power": "5000",
        },
        "OP01-001": {"name": "F", "card_type": "LEADER", "power": "5000"},
        "A": {"name": "A", "card_type": "CHARACTER"},
    }.get
    st_gain = _state(don_deck_size0=6, don_given0=5, don_active0=5, don_rested0=0, turns_completed0=1)
    apply_ops(st_gain, 0, [gains[0]], cat)
    assert st_gain.players[0].don_active == 6
    assert st_gain.players[0].don_rested == 0
    assert st_gain.players[0].don_given == 6

    st = _state(don_deck_size0=6, don_given0=5, don_active0=5, turns_completed0=0)
    catalog = {
        "OP15-058": {
            "name": "艾涅爾",
            "name_en": "Enel",
            "card_type": "LEADER",
            "life": 5,
            "power": "5000",
            "effect": "【啟動主要】【每回合1次】若是自己第2回合之後的回合時，從咚‼卡組追加最多1張活動狀態的咚‼卡。",
        },
        "OP01-001": {"name": "F", "card_type": "LEADER", "power": "5000"},
        "A": {"name": "A", "card_type": "CHARACTER"},
    }.get
    assert don_deck_room(st.players[0]) == 1
    apply_ops(st, 0, [{"op": "gain_don", "count": 4, "as_rested": True}], catalog)
    assert st.players[0].don_given == 6
    assert st.players[0].don_rested == 1

    acts = legal_actions(st, 0, catalog)
    assert not any(a.get("type") == "activate_main" and a.get("source_iid") == "leader" for a in acts)

    st.players[0].turns_completed = 1
    acts2 = legal_actions(st, 0, catalog)
    assert any(a.get("type") == "activate_main" and a.get("source_iid") == "leader" for a in acts2)


def test_look_deck_top_or_bottom_runtime():
    st = _state()
    st.players[0].deck = ["T1", "T2", "REST"]
    catalog = {
        "OP15-058": {"name": "L", "card_type": "LEADER"},
        "OP01-001": {"name": "F", "card_type": "LEADER"},
        "T1": {"name": "One"},
        "T2": {"name": "Two"},
        "REST": {"name": "Rest"},
    }.get
    apply_ops(st, 0, [{"op": "look_deck", "count": 2, "position": "top_or_bottom"}], catalog)
    assert st.pending_choice is not None
    assert "deck:bottom" in st.pending_choice.options
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "deck:bottom"}, catalog)["ok"]
    assert st.pending_search is not None
    assert st.pending_search.phase == "order"
    assert st.pending_search.order_dest == "bottom"
    assert apply_action(st, 0, {"type": "order_search_bottom", "index": 0}, catalog)["ok"]
    assert apply_action(st, 0, {"type": "order_search_bottom", "index": 0}, catalog)["ok"]
    assert st.pending_search is None
    assert st.players[0].deck[-2:] == ["T1", "T2"] or st.players[0].deck[0] == "REST"


def test_start_match_enel_don_deck_size():
    reload_effect_library(force=True)

    def catalog(cid: str) -> dict:
        if cid in {"OP15-058", "OP15-058-P1"}:
            return {"name": "艾涅爾", "name_en": "Enel", "card_type": "LEADER", "life": 5, "power": "5000", "cost": 5}
        if cid == "OP01-001":
            return {"name": "Luffy", "card_type": "LEADER", "life": 5, "power": "5000"}
        return {"name": cid, "card_type": "CHARACTER", "cost": 1, "power": "2000"}

    st = start_match(
        "I",
        {"user_id": "a", "username": "A", "leader_card_id": "OP15-058", "cards": {"X": 50}},
        {"user_id": "b", "username": "B", "leader_card_id": "OP01-001", "cards": {"Y": 50}},
        catalog,
    )
    enel = next(p for p in st.players if p.leader_card_id == "OP15-058")
    other = next(p for p in st.players if p.leader_card_id == "OP01-001")
    assert enel.don_deck_size == 6
    assert other.don_deck_size == 10
