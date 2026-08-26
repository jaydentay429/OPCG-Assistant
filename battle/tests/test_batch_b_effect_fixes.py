"""Batch-B effect encoding / rest-replace fixes (Aug 2026)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effects import (  # noqa: E402
    _parse_replace_leave_ops,
    apply_ops,
    has_blocker,
)
from battle.leave_replace import confirm_replace_if_pending, try_replace_rest  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.get("leader0", "OP01-001"),
        deck=["A"] * 20,
        hand=list(kwargs.get("hand0", [])),
        life=list(kwargs.get("life0", ["L1", "L2"])),
        trash=[],
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-002",
        deck=["B"] * 20,
        hand=[],
        life=["R"] * 5,
        trash=[],
    )
    st = MatchState(
        room_code="T",
        status="playing",
        phase="main",
        turn_seat=kwargs.get("turn_seat", 1),
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
    )
    return st


def test_parse_prb02_replace_rest():
    ops = _parse_replace_leave_ops(
        "若這張角色卡因對手角色卡的效果將置為休息狀態時，可以替換成將1張自己其他的角色卡置為休息狀態。"
    )
    assert len(ops) == 1
    assert ops[0]["op"] == "replace_rest"
    assert ops[0]["cost"] == "rest_other_character"


def test_op12_118_requires_eight_rested_cards():
    reload_effect_library(force=True)
    entry = get_card_entry("OP12-118")
    ab = next(a for a in entry["abilities"] if a.get("timing") == "on_play")
    assert ab.get("require_rested_cards_gte") == 8
    assert any(o.get("op") == "trash_hand" for o in ab["ops"])


def test_op13_031_continuous_blocker_not_on_play_gate():
    reload_effect_library(force=True)
    entry = get_card_entry("OP13-031")
    on_play = next(a for a in entry["abilities"] if a.get("timing") == "on_play")
    cont = next(a for a in entry["abilities"] if a.get("timing") == "your_turn")
    assert on_play.get("require_life_lte") is None
    assert cont.get("require_life_lte") == 1
    assert any(o.get("op") == "grant_keyword" and o.get("keyword") == "blocker" for o in cont["ops"])
    assert not any(o.get("op") == "grant_keyword" for o in on_play["ops"])


def test_op13_031_blocker_respects_life_with_state():
    reload_effect_library(force=True)
    st = _state(life0=["L1", "L2"])  # 2 life → no Blocker
    victim = CardInst(iid="v1", card_id="OP13-031")
    st.players[0].characters.append(victim)
    cat_map = {
        "OP13-031": {
            "effect": "若自己的生命值卡在1張以下時，這張角色卡獲得【防禦】。",
            "name": "x",
        }
    }
    cat = cat_map.get
    assert has_blocker(cat_map["OP13-031"], victim, state=st, owner_seat=0, catalog=cat) is False
    st.players[0].life = ["L1"]
    assert has_blocker(cat_map["OP13-031"], victim, state=st, owner_seat=0, catalog=cat) is True


def test_prb02_replace_rest_runtime():
    reload_effect_library(force=True)
    st = _state(turn_seat=1)
    shield = CardInst(iid="s1", card_id="PRB02-006", rested=False)
    other = CardInst(iid="o1", card_id="OP01-016", rested=False)
    st.players[0].characters.extend([shield, other])
    catalog = {
        "PRB02-006": {"name": "Jinbe", "power": "5000", "traits": [], "traits_en": []},
        "OP01-016": {"name": "Ally", "power": "3000", "traits": [], "traits_en": []},
    }.get
    assert try_replace_rest(
        st, 0, shield, by_opponent_character_effect=True, catalog=catalog
    )
    confirm_replace_if_pending(st, catalog)
    assert shield.rested is False
    assert other.rested is True


def test_prb02_rest_via_opp_character_effect_hooks():
    reload_effect_library(force=True)
    st = _state(turn_seat=1)
    shield = CardInst(iid="s1", card_id="PRB02-006", rested=False)
    other = CardInst(iid="o1", card_id="OP01-016", rested=False)
    st.players[0].characters.extend([shield, other])
    attacker = CardInst(iid="atk", card_id="OP01-025", rested=False)
    st.players[1].characters.append(attacker)
    catalog = {
        "PRB02-006": {"name": "Jinbe", "power": "5000", "traits": [], "traits_en": []},
        "OP01-016": {"name": "Ally", "power": "3000", "traits": [], "traits_en": []},
        "OP01-025": {"name": "Resty", "power": "4000", "traits": [], "traits_en": []},
    }.get
    apply_ops(
        st,
        1,
        [
            {
                "op": "rest_character",
                "target_kind": "opponent_character",
                "target_iid": "s1",
                "source_iid": "atk",
                "optional": False,
            }
        ],
        catalog,
    )
    confirm_replace_if_pending(st, catalog)
    assert shield.rested is False
    assert other.rested is True


def test_counter_buff_duration_battle():
    reload_effect_library(force=True)
    for cid in ("OP14-119", "OP14-098", "OP15-074"):
        entry = get_card_entry(cid)
        buffs = [
            o
            for a in entry["abilities"]
            if a.get("timing") in {"counter_event", "on_opponent_attack"}
            for o in a.get("ops") or []
            if o.get("op") in {"buff", "buff_self"}
        ]
        assert buffs, cid
        assert all(o.get("duration") == "battle" for o in buffs), cid


def test_st24_002_search_any_card_type():
    reload_effect_library(force=True)
    entry = get_card_entry("ST24-002")
    search = next(
        o
        for a in entry["abilities"]
        for o in a.get("ops") or []
        if o.get("op") == "search_deck"
    )
    assert "card_type" not in search


def test_op14_023_set_active_mandatory():
    reload_effect_library(force=True)
    entry = get_card_entry("OP14-023")
    ab = entry["abilities"][0]
    assert ab["ops"][0]["optional"] is False


def test_st24_004_also_skip_untap():
    reload_effect_library(force=True)
    entry = get_card_entry("ST24-004")
    rest = next(o for a in entry["abilities"] for o in a["ops"] if o.get("op") == "rest_character")
    assert rest.get("also_skip_untap") is True
    st = _state()
    foe_ch = CardInst(iid="f1", card_id="OP01-016", rested=False)
    st.players[1].characters.append(foe_ch)
    src = CardInst(iid="src", card_id="ST24-004", rested=False)
    st.players[0].characters.append(src)
    catalog = {"OP01-016": {}, "ST24-004": {}}.get
    apply_ops(
        st,
        0,
        [
            {
                "op": "rest_character",
                "target_kind": "opponent_character",
                "target_iid": "f1",
                "source_iid": "src",
                "also_skip_untap": True,
                "optional": False,
            }
        ],
        catalog,
    )
    assert foe_ch.rested is True
    assert "f1" in st.players[1].skip_untap_iids


def test_op06_038_second_buff_same_target():
    reload_effect_library(force=True)
    entry = get_card_entry("OP06-038")
    ab = next(a for a in entry["abilities"] if a.get("timing") == "counter_event")
    assert ab["ops"][1].get("same_target_as_prior") is True
    assert ab["ops"][1].get("require_rested_cards_gte") == 8
    st = _state()
    # 8 rested cards: leader + 7 chars
    st.players[0].leader_rested = True
    for i in range(7):
        st.players[0].characters.append(CardInst(iid=f"r{i}", card_id="OP01-016", rested=True))
    target = CardInst(iid="t1", card_id="OP01-017", rested=False)
    st.players[0].characters.append(target)
    catalog = {"OP01-016": {}, "OP01-017": {}}.get
    apply_ops(
        st,
        0,
        [
            {
                "op": "buff",
                "amount": 2000,
                "target_kind": "own_leader_or_character",
                "target_iid": "t1",
                "duration": "battle",
            },
            {
                "op": "buff",
                "amount": 2000,
                "same_target_as_prior": True,
                "duration": "battle",
                "require_rested_cards_gte": 8,
            },
        ],
        catalog,
    )
    until = int(getattr(target, "power_mod", 0) or 0)
    assert until == 4000
