"""Batch-H effect encoding / runtime fixes (Aug 2026)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effects import apply_ops, has_blockerless, has_rush  # noqa: E402
from battle.engine import apply_action, inst_power  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.get("leader0", "OP12-001"),
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
        room_code="H",
        status="playing",
        phase="main",
        turn_seat=kwargs.get("turn_seat", 0),
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
    )


def test_eb04_002_dual_trait_search():
    reload_effect_library(force=True)
    op = get_card_entry("EB04-002")["abilities"][0]["ops"][0]
    assert op["op"] == "search_deck"
    tc = op.get("trait_contains") or ""
    assert "Egghead" in tc and "Straw Hat" in tc


def test_op14_019_supernovas_or_straw_hat():
    reload_effect_library(force=True)
    op = get_card_entry("OP14-019")["abilities"][0]["ops"][0]
    tc = op.get("trait_contains") or ""
    assert "Supernovas" in tc and "Straw Hat" in tc
    assert op.get("card_type") == "character"


def test_op12_015_given_don_both_turns():
    reload_effect_library(force=True)
    abs_ = get_card_entry("OP12-015")["abilities"]
    static = [a for a in abs_ if a["ops"][0].get("op") == "buff_self"]
    assert {a["timing"] for a in static} >= {"your_turn", "opponent_turn"}
    assert all(a.get("require_given_don_gte") == 2 for a in static)
    assert all(a.get("require_don_attached_gte") is None for a in static)

    st = _state(leader_don0=2, turn_seat=1)
    st.players[0].characters.append(CardInst(iid="luf", card_id="OP12-015"))
    catalog = {
        "OP12-015": {"name": "Luffy", "power": "4000", "cost": 4, "card_type": "CHARACTER", "traits_en": ["Straw Hat Crew"]},
        "OP12-001": {"name": "L", "power": "5000", "card_type": "LEADER"},
        "OP01-001": {"name": "F", "power": "5000", "card_type": "LEADER"},
    }.get
    assert inst_power(st, 0, "luf", catalog) == 6000


def test_st31_004_given_don_rush_and_per_field():
    reload_effect_library(force=True)
    rush = next(a for a in get_card_entry("ST31-004")["abilities"] if a["ops"][0].get("keyword") == "rush")
    assert rush.get("require_given_don_gte") == 3
    on_play = next(a for a in get_card_entry("ST31-004")["abilities"] if a["timing"] == "on_play")
    buff = on_play["ops"][0]
    assert buff.get("per_choose") is True
    assert buff.get("include_leader") is True
    assert buff.get("include_stage") is True

    st = _state(leader_don0=3)
    st.players[0].leader_card_id = "ST31-001"
    luf = CardInst(iid="luf", card_id="ST31-004")
    mate = CardInst(iid="nami", card_id="OP01-016")
    st.players[0].characters.extend([luf, mate])
    catalog = {
        "ST31-004": {"name": "Luffy", "power": "9000", "cost": 7, "card_type": "CHARACTER", "traits_en": ["Straw Hat Crew"]},
        "OP01-016": {"name": "Nami", "power": "2000", "cost": 1, "card_type": "CHARACTER", "traits_en": ["Straw Hat Crew"]},
        "ST31-001": {"name": "Sanji", "power": "5000", "card_type": "LEADER", "traits_en": ["Straw Hat Crew"]},
        "OP01-001": {"name": "F", "power": "5000", "card_type": "LEADER"},
        "OPP": {"name": "X", "power": "5000", "cost": 3, "card_type": "CHARACTER"},
    }.get
    assert has_rush(catalog("ST31-004"), luf, state=st, owner_seat=0, catalog=catalog)

    st.players[1].characters.append(CardInst(iid="opp", card_id="OPP"))
    apply_ops(st, 0, [dict(buff)], catalog)
    # 3 Straw Hat cards (leader + 2 chars) → three −1000 choices (or stacked).
    assert st.pending_choice is not None
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "opp"}, catalog)["ok"]
    # After first pick another choice should remain for remaining stacks.
    assert st.pending_choice is not None or inst_power(st, 1, "opp", catalog) <= 4000


def test_st21_017_debuff_then_gated_ko():
    reload_effect_library(force=True)
    ops = get_card_entry("ST21-017")["abilities"][0]["ops"]
    assert [o["op"] for o in ops] == ["buff", "ko"]
    assert ops[0].get("amount") == -5000
    assert ops[1].get("power_lte") == 2000
    assert ops[1].get("require_own_char_power_gte") == 6000

    st = _state()
    st.players[1].characters.append(CardInst(iid="lo", card_id="LO"))
    catalog = {
        "LO": {"name": "Low", "power": "2000", "cost": 1, "card_type": "CHARACTER"},
        "OP12-001": {"name": "L", "power": "5000", "card_type": "LEADER"},
        "OP01-001": {"name": "F", "power": "5000", "card_type": "LEADER"},
    }.get
    apply_ops(st, 0, [dict(ops[1])], catalog)
    # No own 6000 Character → KO must not fire.
    assert any(c.iid == "lo" for c in st.players[1].characters)


def test_st21_003_targeted_blockerless():
    reload_effect_library(force=True)
    op = get_card_entry("ST21-003")["abilities"][0]["ops"][0]
    assert op["op"] == "grant_keyword"
    assert op.get("keyword") == "blockerless"
    assert op.get("power_gte") == 6000
    assert "Straw Hat" in (op.get("trait_contains") or "")

    st = _state()
    strong = CardInst(iid="st", card_id="STRONG")
    weak = CardInst(iid="wk", card_id="WEAK")
    st.players[0].characters.extend([strong, weak])
    catalog = {
        "STRONG": {
            "name": "Zoro",
            "power": "6000",
            "cost": 4,
            "card_type": "CHARACTER",
            "traits_en": ["Straw Hat Crew"],
        },
        "WEAK": {
            "name": "Nami",
            "power": "2000",
            "cost": 1,
            "card_type": "CHARACTER",
            "traits_en": ["Straw Hat Crew"],
        },
        "OP12-001": {"name": "L", "power": "5000", "card_type": "LEADER"},
        "OP01-001": {"name": "F", "power": "5000", "card_type": "LEADER"},
    }.get
    apply_ops(st, 0, [dict(op)], catalog)
    assert st.pending_choice is not None
    assert "st" in st.pending_choice.options
    assert "wk" not in st.pending_choice.options
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "st"}, catalog)["ok"]
    assert has_blockerless(catalog("STRONG"), strong)
    assert not has_blockerless(catalog("WEAK"), weak)


def test_st31_005_rest_self_and_rested_don():
    reload_effect_library(force=True)
    spec = next(a for a in get_card_entry("ST31-005")["abilities"] if a["timing"] == "activate_main")
    assert spec.get("rest_self") is True
    op = spec["ops"][0]
    assert op.get("from_rested") or op.get("as_rested")
    assert op.get("target_kind") == "own_leader_or_character"


def test_op12_018_rayleigh_and_optional_rest_don():
    reload_effect_library(force=True)
    ops = get_card_entry("OP12-018")["abilities"][0]["ops"]
    assert ops[0].get("include_leader_if_name")
    assert ops[1].get("as_cost") is True and ops[1].get("optional") is True

    st = _state(don_active0=1, leader0="OP02-070")
    st.players[0].characters.append(CardInst(iid="c1", card_id="C1"))
    catalog = {
        "OP02-070": {"name": "席爾巴斯・雷利", "name_en": "Silvers Rayleigh", "power": "5000", "card_type": "LEADER"},
        "C1": {"name": "Mate", "power": "4000", "cost": 3, "card_type": "CHARACTER"},
        "OP01-001": {"name": "F", "power": "5000", "card_type": "LEADER"},
        "OP12-018": {"name": "Haki", "card_type": "EVENT"},
    }.get
    apply_ops(st, 0, [dict(ops[0])], catalog)
    assert st.pending_choice is not None
    assert "leader" in st.pending_choice.options

    st2 = _state(don_active0=1)
    st2.players[1].characters.append(CardInst(iid="o1", card_id="O1"))
    catalog2 = {
        "OP12-001": {"name": "L", "power": "5000", "card_type": "LEADER"},
        "OP01-001": {"name": "F", "power": "5000", "card_type": "LEADER"},
        "O1": {"name": "Opp", "power": "5000", "cost": 3, "card_type": "CHARACTER"},
    }.get
    apply_ops(st2, 0, [dict(ops[1]), dict(ops[2])], catalog2)
    assert st2.pending_choice is not None
    assert apply_action(st2, 0, {"type": "skip_choice"}, catalog2)["ok"]
    assert st2.players[0].don_active == 1
    assert inst_power(st2, 1, "o1", catalog2) == 5000


def test_similar_dual_trait_op05_076():
    reload_effect_library(force=True)
    op = get_card_entry("OP05-076")["abilities"][0]["ops"][0]
    tc = op.get("trait_contains") or ""
    assert "Straw Hat" in tc and "Kid" in tc
