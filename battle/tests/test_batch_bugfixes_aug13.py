"""Regression: Lucy check-then-draw, Cavendish no on-play, Trigger stamp, Stage rest, DON Blocker."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import (  # noqa: E402
    get_abilities,
    reload_effect_library,
    resolve_ability,
    resolve_activate_spec,
    resolve_trigger_ops,
)
from battle.effects import apply_ops, has_blocker, parse_activate_main  # noqa: E402
from battle.engine import apply_action  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402


def _catalog(cid: str) -> dict:
    table = {
        "OP15-002": {
            "card_type": "LEADER",
            "name": "Lucy",
            "power": 5000,
            "life": 4,
            "cost": 0,
            "traits": ["Dressrosa"],
            "effect": "【啟動主要】【每回合1次】在這個回合，若自己發動原本費用3以上的事件卡時，抽1張卡片。",
            "effect_en": "[Activate: Main] [Once Per Turn] If you have activated an Event with a base cost of 3 or more during this turn, draw 1 card.",
        },
        "OP10-045": {
            "card_type": "CHARACTER",
            "name": "Cavendish",
            "cost": 4,
            "power": 6000,
            "effect": "【攻擊時】【每回合1次】抽2張卡片，並廢棄1張自己的手牌。",
        },
        "OP10-059": {
            "card_type": "EVENT",
            "name": "Dressrosa",
            "cost": 1,
            "effect": "【主要】從自己的卡組上面查看5張卡片，公開最多1張擁有《多雷斯羅薩》特徵的角色卡，並加入手牌。之後，將其餘卡片依任意順序放到卡組下面。【觸發器】發動這張卡片的【主要】效果。",
            "traits": [],
        },
        "OP15-053": {
            "card_type": "CHARACTER",
            "name": "Rebecca",
            "cost": 4,
            "power": 5000,
            "effect": "【咚‼×1】這張角色卡獲得【防禦】。【登場時】從自己的卡組上面查看3張卡片…",
        },
        "OP15-057": {
            "card_type": "STAGE",
            "name": "Dressrosa Kingdom",
            "cost": 1,
            "effect": "【對方攻擊時】可將這張舞台卡置為休息狀態，並廢棄1張…",
        },
        "E3": {"card_type": "EVENT", "name": "Big Event", "cost": 3},
        "E2": {"card_type": "EVENT", "name": "Cheap", "cost": 2},
        "DRESS": {"card_type": "CHARACTER", "name": "Local", "cost": 3, "power": 4000, "traits": ["Dressrosa", "多雷斯羅薩"]},
        "FOE": {"card_type": "LEADER", "name": "Foe", "power": 5000, "life": 5, "cost": 0},
    }
    return dict(table.get(cid) or {"card_type": "CHARACTER", "name": cid, "cost": 1, "power": 1000})


def _state(**kw) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="me",
        is_ai=False,
        leader_card_id=kw.get("leader", "OP15-002"),
        deck=list(kw.get("deck", ["D"] * 30)),
        hand=list(kw.get("hand", [])),
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
        turns_completed=1,
    )
    for ch in kw.get("chars", []):
        p0.characters.append(ch)
    for st in kw.get("stages", []):
        p0.stages.append(st)
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


def test_lucy_check_then_draw():
    reload_effect_library(force=True)
    spec = resolve_activate_spec("OP15-002", _catalog("OP15-002"))
    assert spec and spec["ops"][0]["op"] == "draw"
    assert int(spec["ops"][0].get("require_event_activated_cost_gte") or 0) == 3
    parsed = parse_activate_main(_catalog("OP15-002"))
    assert parsed and parsed["ops"][0].get("require_event_activated_cost_gte") == 3

    st = _state(hand=["E3"], deck=["X"] * 20)
    # Play event cost 3
    r = apply_action(st, 0, {"type": "play_card", "hand_index": 0}, _catalog, None)
    assert r.get("ok"), r
    assert 3 in st.players[0].event_activated_costs
    hand_before = len(st.players[0].hand)
    r = apply_action(st, 0, {"type": "activate_main", "source_iid": "leader"}, _catalog, None)
    assert r.get("ok"), r
    assert len(st.players[0].hand) == hand_before + 1


def test_lucy_no_draw_without_event():
    reload_effect_library(force=True)
    st = _state(hand=[], deck=["X"] * 20)
    hand_before = len(st.players[0].hand)
    r = apply_action(st, 0, {"type": "activate_main", "source_iid": "leader"}, _catalog, None)
    assert r.get("ok"), r
    assert len(st.players[0].hand) == hand_before


def test_cavendish_no_on_play():
    reload_effect_library(force=True)
    st = _state(leader="FOE", hand=["OP10-045"], deck=["X"] * 20)

    def ask_llm(*_a, **_k):
        raise AssertionError("LLM must not invent on_play for curated when_attacking card")

    before = len(st.players[0].hand)
    r = apply_action(st, 0, {"type": "play_card", "hand_index": 0}, _catalog, ask_llm)
    assert r.get("ok"), r
    # Played character: hand -1, no draws from false on_play
    assert len(st.players[0].characters) == 1
    assert len(st.players[0].hand) == before - 1
    pending = resolve_ability(st, 0, "OP10-045", "x", "on_play", _catalog("OP10-045"), ask_llm, allow_llm=True)
    assert pending is None


def test_trigger_activates_main_search():
    reload_effect_library(force=True)
    ops = resolve_trigger_ops("OP10-059", _catalog("OP10-059"))
    assert ops and ops[0].get("op") == "activate_timing"
    deck = ["DRESS", "Z", "Z", "Z", "Z"] + ["Z"] * 20
    st = _state(leader="FOE", deck=deck)
    logs = apply_ops(
        st,
        0,
        [{"op": "activate_timing", "timing": "on_play", "card_id": "OP10-059", "source_iid": "OP10-059"}],
        _catalog,
    )
    assert any(l.get("key") == "play.log.effect_applied" for l in logs) or st.pending_search
    assert st.pending_search is not None or "DRESS" in st.players[0].hand


def test_op10_059_search_excludes_events_and_stages():
    """Paper: add up to 1 Dressrosa *Character* — Events/Stages with the trait are ineligible."""
    reload_effect_library(force=True)
    abs_ = get_abilities("OP10-059")
    assert abs_ and abs_[0]["ops"][0].get("card_type") == "character"

    def catalog(cid: str) -> dict:
        table = {
            "OP10-059": {
                "card_type": "EVENT",
                "name": "I won't let anyone have it!",
                "traits": ["多雷斯羅薩"],
                "traits_en": ["Dressrosa"],
                "effect": _catalog("OP10-059")["effect"],
            },
            "OP15-059": {
                "card_type": "EVENT",
                "name": "Watch me, Ace!!!",
                "traits": ["多雷斯羅薩"],
                "traits_en": ["Dressrosa"],
            },
            "OP15-060": {
                "card_type": "STAGE",
                "name": "Dressrosa Kingdom",
                "traits": ["多雷斯羅薩"],
                "traits_en": ["Dressrosa"],
            },
            "OP10-022": {
                "card_type": "EVENT",
                "name": "Fire Fist",
                "traits": ["白鬍子海賊團"],
                "traits_en": ["Whitebeard Pirates"],
            },
            "CHAR-D": {
                "card_type": "CHARACTER",
                "name": "Rebecca",
                "traits": ["多雷斯羅薩"],
                "traits_en": ["Dressrosa"],
            },
        }
        return dict(table.get(cid) or {"card_type": "CHARACTER", "name": cid})

    deck = ["OP10-059", "OP10-022", "OP15-059", "OP15-060", "CHAR-D"] + ["Z"] * 10
    st = _state(leader="FOE", deck=deck)
    apply_ops(
        st,
        0,
        [{**abs_[0]["ops"][0], "card_id": "OP10-059", "source_iid": "OP10-059"}],
        catalog,
    )
    assert st.pending_search is not None
    # Only the Dressrosa Character at index 4 is eligible.
    assert st.pending_search.eligible == [4]
    assert st.pending_search.revealed[4] == "CHAR-D"


def test_rebecca_don_blocker():
    reload_effect_library(force=True)
    inst = CardInst(iid="c1", card_id="OP15-053", don_attached=0)
    assert not has_blocker(_catalog("OP15-053"), inst)
    inst.don_attached = 1
    assert has_blocker(_catalog("OP15-053"), inst)


def test_stage_rest_self():
    reload_effect_library(force=True)
    stage = CardInst(iid="s1", card_id="OP15-057", rested=False)
    st = _state(leader="OP15-002", stages=[stage], hand=["E2"])
    logs = apply_ops(
        st,
        0,
        [
            {"op": "rest_character", "target_kind": "self", "source_iid": "s1", "optional": True, "as_cost": True},
            {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "card_type": "event_or_stage"},
        ],
        _catalog,
    )
    assert st.players[0].stages[0].rested
    assert any(l.get("key") == "play.log.rests_self" for l in logs)


if __name__ == "__main__":
    test_lucy_check_then_draw()
    test_lucy_no_draw_without_event()
    test_cavendish_no_on_play()
    test_trigger_activates_main_search()
    test_rebecca_don_blocker()
    test_stage_rest_self()
    print("ok")
