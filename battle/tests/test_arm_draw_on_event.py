"""OP15-002 Lucy: Activate Main draws if Event base cost ≥3 already activated this turn."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import reload_effect_library, resolve_activate_spec  # noqa: E402
from battle.engine import apply_action  # noqa: E402
from battle.state import MatchState, PlayerState  # noqa: E402


def _catalog(cid: str) -> dict:
    table = {
        "LUCY": {"card_type": "LEADER", "name": "Lucy", "power": 5000, "life": 4, "cost": 0},
        "FOE": {"card_type": "LEADER", "name": "Foe", "power": 5000, "life": 5, "cost": 0},
        "E2": {"card_type": "EVENT", "name": "Cheap Event", "cost": 2},
        "E3": {"card_type": "EVENT", "name": "Big Event", "cost": 3},
        "E4": {"card_type": "EVENT", "name": "Bigger Event", "cost": 4},
        "C1": {"card_type": "CHARACTER", "name": "Char", "cost": 3, "power": 4000},
    }
    return dict(table.get(cid) or {"card_type": "CHARACTER", "name": cid, "cost": 1, "power": 1000})


def _state(*, hand: list[str]) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="me",
        is_ai=False,
        leader_card_id="OP15-002",
        deck=["D"] * 30,
        hand=list(hand),
        life=["L"] * 4,
        don_active=10,
        don_given=10,
        turns_completed=1,
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="foe",
        is_ai=False,
        leader_card_id="FOE",
        deck=["B"] * 20,
        hand=[],
        life=["M"] * 5,
    )
    return MatchState(
        room_code="T",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
        rng_seed=1,
    )


def test_override_is_check_then_draw():
    reload_effect_library(force=True)
    spec = resolve_activate_spec("OP15-002", {"effect": ""})
    assert spec is not None
    ops = spec.get("ops") or []
    assert ops and ops[0].get("op") == "draw"
    assert int(ops[0].get("require_event_activated_cost_gte") or 0) == 3
    assert not any(o.get("op") == "arm_draw_on_event" for o in ops)


def _lucy_info() -> dict:
    return {
        "card_type": "LEADER",
        "name": "Lucy",
        "power": 5000,
        "life": 4,
        "cost": 0,
        "effect": "【啟動主要】【每回合1次】在這個回合，若自己發動原本費用3以上的事件卡時，抽1張卡片。",
        "effect_en": "[Activate: Main] [Once Per Turn] If you have activated an Event with a base cost of 3 or more during this turn, draw 1 card.",
    }


def test_event_then_activate_draws():
    reload_effect_library(force=True)
    st = _state(hand=["E3", "E2"])

    def catalog(cid: str):
        if cid == "OP15-002":
            return _lucy_info()
        return _catalog(cid)

    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert 3 in st.players[0].event_activated_costs
    hand_before = len(st.players[0].hand)
    deck_before = len(st.players[0].deck)
    assert apply_action(st, 0, {"type": "activate_main", "source_iid": "leader"}, catalog)["ok"]
    assert len(st.players[0].hand) == hand_before + 1
    assert len(st.players[0].deck) == deck_before - 1
    assert st.players[0].leader_once_used is True


def test_activate_without_event_no_draw():
    reload_effect_library(force=True)
    st = _state(hand=["E2"])

    def catalog(cid: str):
        if cid == "OP15-002":
            return _lucy_info()
        return _catalog(cid)

    hand_before = len(st.players[0].hand)
    assert apply_action(st, 0, {"type": "activate_main", "source_iid": "leader"}, catalog)["ok"]
    assert len(st.players[0].hand) == hand_before


def test_cost2_event_then_activate_no_draw():
    reload_effect_library(force=True)
    st = _state(hand=["E2"])

    def catalog(cid: str):
        if cid == "OP15-002":
            return _lucy_info()
        return _catalog(cid)

    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    hand_before = len(st.players[0].hand)
    assert apply_action(st, 0, {"type": "activate_main", "source_iid": "leader"}, catalog)["ok"]
    assert len(st.players[0].hand) == hand_before


if __name__ == "__main__":
    test_override_is_check_then_draw()
    test_event_then_activate_draws()
    test_activate_without_event_no_draw()
    test_cost2_event_then_activate_no_draw()
    print("ok")
