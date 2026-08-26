"""Batch-J effect encoding / runtime fixes (any-number DON, if_trashed, this-turn-end)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effects import apply_ops  # noqa: E402
from battle.engine import apply_action, inst_power  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.get("leader0", "OP13-001"),
        deck=list(kwargs.get("deck0", ["A"] * 20)),
        hand=list(kwargs.get("hand0", [])),
        life=["L"] * 4,
        trash=[],
        don_active=int(kwargs.get("don_active0", 0) or 0),
        don_rested=int(kwargs.get("don_rested0", 0) or 0),
        don_given=int(kwargs.get("don_given0", 0) or 0),
        leader_don=int(kwargs.get("leader_don0", 0) or 0),
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
        room_code="J",
        status="playing",
        phase="main",
        turn_seat=kwargs.get("turn_seat", 0),
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
    )


def test_op13_001_any_number_rest_scales_buff():
    reload_effect_library(force=True)
    spec = get_card_entry("OP13-001")["abilities"][0]
    assert spec.get("require_don_active_lte") == 5
    rest, buff = spec["ops"]
    assert rest.get("any_number") is True
    assert not rest.get("as_cost")
    assert buff.get("per_rested_don") == 1

    st = _state(don_active0=3)
    catalog = {
        "OP13-001": {
            "name": "蒙其・D・魯夫",
            "name_en": "Monkey.D.Luffy",
            "card_type": "LEADER",
            "power": "5000",
            "traits_en": ["Straw Hat Crew"],
        },
        "OP01-001": {"name": "F", "card_type": "LEADER", "power": "5000"},
    }.get
    apply_ops(st, 0, [dict(o) for o in spec["ops"]], catalog)
    assert st.pending_choice is not None
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "don"}, catalog)["ok"]
    assert st.players[0].don_rested == 1
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "don"}, catalog)["ok"]
    assert st.players[0].don_rested == 2
    assert apply_action(st, 0, {"type": "skip_choice"}, catalog)["ok"]
    assert st.pending_choice is not None
    assert "leader" in st.pending_choice.options
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "leader"}, catalog)["ok"]
    assert inst_power(st, 0, "leader", catalog) == 5000 + 4000


def test_op05_038_if_trashed_skips_active_don():
    reload_effect_library(force=True)
    ops = next(a["ops"] for a in get_card_entry("OP05-038")["abilities"] if a["timing"] == "counter_event")
    assert ops[2].get("if_trashed") is True

    st = _state(don_active0=0, don_rested0=3, hand0=["H1"])
    catalog = {
        "OP13-001": {"name": "L", "card_type": "LEADER", "power": "5000"},
        "OP01-001": {"name": "F", "card_type": "LEADER", "power": "5000"},
        "H1": {"name": "Hand", "card_type": "CHARACTER"},
    }.get
    apply_ops(st, 0, [dict(o) for o in ops], catalog)
    # Buff first, then trash prompt.
    if st.pending_choice and st.pending_choice.target_kind != "hand_card":
        apply_action(st, 0, {"type": "select_choice", "target_iid": "leader"}, catalog)
    assert st.pending_choice is not None
    assert apply_action(st, 0, {"type": "skip_choice"}, catalog)["ok"]
    assert st.players[0].don_active == 0
    assert st.players[0].don_rested == 3


def test_op05_038_trash_then_active_don():
    reload_effect_library(force=True)
    ops = next(a["ops"] for a in get_card_entry("OP05-038")["abilities"] if a["timing"] == "counter_event")
    st = _state(don_active0=0, don_rested0=3, hand0=["H1"])
    catalog = {
        "OP13-001": {"name": "L", "card_type": "LEADER", "power": "5000"},
        "OP01-001": {"name": "F", "card_type": "LEADER", "power": "5000"},
        "H1": {"name": "Hand", "card_type": "CHARACTER"},
    }.get
    apply_ops(st, 0, [dict(o) for o in ops], catalog)
    if st.pending_choice and st.pending_choice.target_kind != "hand_card":
        apply_action(st, 0, {"type": "select_choice", "target_iid": "leader"}, catalog)
    pick = next(o for o in st.pending_choice.options if o.endswith(":H1"))
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick}, catalog)["ok"]
    assert st.players[0].don_active == 3
    assert "H1" in st.players[0].trash


def test_op08_036_trigger_no_cost_filter():
    reload_effect_library(force=True)
    trig = next(a for a in get_card_entry("OP08-036")["abilities"] if a["timing"] == "trigger")
    op = trig["ops"][0]
    assert op.get("op") == "rest_opponent_character"
    assert op.get("cost_lte") is None
    main = next(a for a in get_card_entry("OP08-036")["abilities"] if a["timing"] == "on_play")
    assert main["ops"][0].get("cost_lte") == 7


def test_op13_027_on_play_not_leader_gated():
    reload_effect_library(force=True)
    abs_ = get_card_entry("OP13-027")["abilities"]
    play = next(a for a in abs_ if a["timing"] == "on_play")
    assert play.get("require_leader_trait") is None
    eot = next(a for a in abs_ if a["timing"] == "end_of_your_turn")
    assert eot.get("require_leader_trait")


def test_op14_031_active_don_once_this_turn():
    reload_effect_library(force=True)
    abs_ = get_card_entry("OP14-031")["abilities"]
    assert not any(a.get("timing") == "end_of_your_turn" for a in abs_)
    play = next(a for a in abs_ if a["timing"] == "on_play")
    kinds = [o.get("op") for o in play["ops"]]
    assert "rest_opponent_character" in kinds
    active = next(o for o in play["ops"] if o.get("op") == "active_don")
    assert active.get("at_end_of_turn") is True
    assert active.get("count") == 5

    st = _state(don_active0=0, don_rested0=5)
    st.players[1].characters.append(CardInst(iid="o1", card_id="O1"))
    catalog = {
        "OP13-001": {"name": "L", "card_type": "LEADER", "power": "5000"},
        "OP01-001": {"name": "F", "card_type": "LEADER", "power": "5000"},
        "O1": {"name": "Opp", "power": "4000", "cost": 4, "card_type": "CHARACTER"},
        "OP14-031": {"name": "娜美", "card_type": "CHARACTER", "cost": 4},
    }.get
    apply_ops(st, 0, [dict(o) for o in play["ops"]], catalog)
    queued = st.players[0].pending_end_of_turn_ops
    assert any(o.get("op") == "active_don" and o.get("count") == 5 for o in queued)


def test_st31_004_per_own_does_not_target_opp_leader():
    reload_effect_library(force=True)
    play = next(a for a in get_card_entry("ST31-004")["abilities"] if a["timing"] == "on_play")
    st = _state(leader0="ST31-001")
    st.players[0].characters.append(CardInst(iid="self", card_id="ST31-004"))
    st.players[1].characters.append(CardInst(iid="opp", card_id="O1"))
    catalog = {
        "ST31-001": {
            "name": "Luffy",
            "card_type": "LEADER",
            "power": "5000",
            "traits_en": ["Straw Hat Crew"],
            "traits": ["草帽一行人"],
        },
        "ST31-004": {
            "name": "Luffy",
            "card_type": "CHARACTER",
            "power": "9000",
            "traits_en": ["Straw Hat Crew"],
            "traits": ["草帽一行人"],
        },
        "OP01-001": {"name": "F", "card_type": "LEADER", "power": "5000"},
        "O1": {"name": "Opp", "power": "5000", "cost": 3, "card_type": "CHARACTER"},
    }.get
    apply_ops(st, 0, [dict(play["ops"][0])], catalog)
    assert st.pending_choice is not None
    assert "opp" in st.pending_choice.options
    assert "leader" not in st.pending_choice.options


def test_op13_040_optional_rest_skip_cancels():
    reload_effect_library(force=True)
    ops = next(a["ops"] for a in get_card_entry("OP13-040")["abilities"] if a["timing"] == "on_play")
    assert ops[0].get("optional") is True and ops[0].get("as_cost") is True
    st = _state(don_active0=2)
    st.players[1].characters.append(CardInst(iid="o1", card_id="O1", rested=True))
    catalog = {
        "OP13-001": {"name": "L", "card_type": "LEADER", "power": "5000"},
        "OP01-001": {"name": "F", "card_type": "LEADER", "power": "5000"},
        "O1": {"name": "Opp", "power": "4000", "cost": 5, "card_type": "CHARACTER"},
    }.get
    apply_ops(st, 0, [dict(o) for o in ops], catalog)
    assert st.pending_choice is not None
    assert apply_action(st, 0, {"type": "skip_choice"}, catalog)["ok"]
    assert st.players[0].don_active == 2
    assert st.pending_choice is None


def test_nami_search_excludes_zh_name():
    reload_effect_library(force=True)
    for cid in ("EB02-017", "OP01-016"):
        op = get_card_entry(cid)["abilities"][0]["ops"][0]
        assert "娜美" in (op.get("exclude_name") or "")


def test_similar_op01_058_trigger_no_cost():
    reload_effect_library(force=True)
    trig = next(a for a in get_card_entry("OP01-058")["abilities"] if a["timing"] == "trigger")
    assert trig["ops"][0].get("cost_lte") is None


def test_similar_this_turn_end_not_perpetual():
    reload_effect_library(force=True)
    abs_ = get_card_entry("OP13-038")["abilities"]
    assert not any(a.get("timing") == "end_of_your_turn" for a in abs_)
    play = next(a for a in abs_ if a["timing"] in {"on_play", "activate_main"})
    assert any(o.get("op") == "active_don" and o.get("at_end_of_turn") for o in play["ops"])
