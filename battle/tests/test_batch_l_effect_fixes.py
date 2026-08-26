"""Batch-L effect encoding / runtime (SWORD auras, on_opp_ko, any-leave, Navy gates)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effects import apply_ops, live_keywords  # noqa: E402
from battle.engine import inst_power  # noqa: E402
from battle.leave_replace import confirm_replace_if_pending, try_replace_leave  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.get("leader0", "OP11-001"),
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
        room_code="L",
        status="playing",
        phase="main",
        turn_seat=kwargs.get("turn_seat", 1),
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
    )


def _cat(extra: dict | None = None):
    base = {
        "OP11-001": {
            "name": "克比",
            "name_en": "Koby",
            "card_type": "LEADER",
            "power": "5000",
            "traits_en": ["Navy"],
            "traits": ["海軍"],
        },
        "OP01-001": {"name": "F", "card_type": "LEADER", "power": "5000"},
        "EB03-041": {
            "name": "孔雀",
            "name_en": "Kujyaku",
            "card_type": "CHARACTER",
            "power": "5000",
            "cost": "5",
            "traits_en": ["SWORD", "Navy"],
            "traits": ["SWORD", "海軍"],
        },
        "SWORD6": {
            "name": "Hibari",
            "card_type": "CHARACTER",
            "power": "4000",
            "cost": "6",
            "traits_en": ["SWORD"],
            "traits": ["SWORD"],
        },
        "SWORD7": {
            "name": "Big",
            "card_type": "CHARACTER",
            "power": "6000",
            "cost": "7",
            "traits_en": ["SWORD"],
            "traits": ["SWORD"],
        },
        "NAVY_B": {
            "name": "Doll",
            "card_type": "CHARACTER",
            "power": "5000",
            "cost": "4",
            "colors": ["black"],
            "colors_en": ["black"],
            "traits_en": ["Navy"],
            "traits": ["海軍"],
        },
        "RIPPER": {
            "name": "梨帕",
            "name_en": "Ripper",
            "card_type": "CHARACTER",
            "power": "4000",
            "cost": "3",
            "colors": ["black"],
            "colors_en": ["black"],
            "traits_en": ["Navy"],
            "traits": ["海軍"],
        },
        "EB04-003": {
            "name": "斯摩格＆達絲琪",
            "card_type": "CHARACTER",
            "power": "6000",
            "cost": "5",
            "traits_en": ["Navy"],
            "traits": ["海軍"],
        },
        "EB04-044": {
            "name": "克比",
            "name_en": "Koby",
            "card_type": "CHARACTER",
            "power": "5000",
            "cost": "4",
            "traits_en": ["Navy"],
            "traits": ["海軍"],
        },
        "OPP": {"name": "Opp", "card_type": "CHARACTER", "power": "3000", "cost": "2"},
        "HAND": {"name": "Hand", "card_type": "CHARACTER", "power": "2000", "cost": "1"},
        "OP11-096": {
            "name": "梨帕",
            "name_en": "Ripper",
            "card_type": "CHARACTER",
            "power": "4000",
            "cost": "3",
            "colors": ["black"],
            "colors_en": ["black"],
            "traits_en": ["Navy"],
            "traits": ["海軍"],
            "effect": "若場上有除了「梨帕」以外自己黑色擁有《海軍》特徵的角色卡時，這張角色卡獲得【防禦】。",
        },
    }
    if extra:
        base.update(extra)
    return base.get


def test_eb03_041_sword_aura_includes_self_and_cost_cap():
    reload_effect_library(force=True)
    ab = next(a for a in get_card_entry("EB03-041")["abilities"] if a.get("timing") == "opponent_turn")
    op = ab["ops"][0]
    assert op.get("all") is True
    assert op.get("cost_lte") == 6
    assert "SWORD" in str(op.get("trait_contains") or "")

    st = _state(turn_seat=1)
    st.players[0].characters.extend(
        [
            CardInst(iid="self", card_id="EB03-041"),
            CardInst(iid="ok", card_id="SWORD6"),
            CardInst(iid="hi", card_id="SWORD7"),
        ]
    )
    cat = _cat()
    assert inst_power(st, 0, "self", cat) == 7000
    assert inst_power(st, 0, "ok", cat) == 6000
    assert inst_power(st, 0, "hi", cat) == 6000
    st.turn_seat = 0
    assert inst_power(st, 0, "self", cat) == 5000


def test_eb04_003_navy_leader_base_7000_opp_turn():
    reload_effect_library(force=True)
    ab = next(a for a in get_card_entry("EB04-003")["abilities"] if a.get("timing") == "opponent_turn")
    op = ab["ops"][0]
    assert op.get("op") == "set_base_power"
    assert op.get("amount") == 7000
    assert op.get("target_kind") == "leader"

    st = _state(turn_seat=1, leader0="OP11-001")
    st.players[0].characters.append(CardInst(iid="sm", card_id="EB04-003"))
    cat = _cat()
    assert inst_power(st, 0, "leader", cat) == 7000
    st.turn_seat = 0
    assert inst_power(st, 0, "leader", cat) == 5000


def test_op11_008_minus_6000_leader_gate_on_buff_only():
    reload_effect_library(force=True)
    ab = get_card_entry("OP11-008")["abilities"][0]
    assert ab.get("require_leader_trait") in (None, "")
    buff = next(o for o in ab["ops"] if o.get("op") == "buff")
    assert buff.get("amount") == -6000
    assert buff.get("require_leader_trait")


def test_op11_082_trash_deck_not_navy_gated():
    reload_effect_library(force=True)
    ab = get_card_entry("OP11-082")["abilities"][0]
    assert ab.get("require_leader_trait") in (None, "")
    kinds = [o.get("op") for o in ab["ops"]]
    assert "trash_deck_top" in kinds
    allow = next(o for o in ab["ops"] if o.get("op") == "allow_attack_active")
    assert allow.get("require_leader_trait")
    assert allow.get("optional") is True


def test_op11_092_exclude_helmeppo_and_stamp_played_iid():
    reload_effect_library(force=True)
    ops = get_card_entry("OP11-092")["abilities"][0]["ops"]
    play = next(o for o in ops if o.get("op") == "play_from_hand")
    assert "貝魯梅柏" in str(play.get("exclude_name") or "")
    assert "Bellemere" not in str(play.get("exclude_name") or "")
    ret = next(o for o in ops if o.get("op") == "return_to_bottom")
    assert ret.get("effect_played_only") is True
    assert ret.get("at_end_of_turn") is True

    st = _state(turn_seat=0)
    st.players[0]._last_effect_played_iids = ["played1"]
    apply_ops(st, 0, [dict(ret)], _cat())
    queued = st.players[0].pending_end_of_turn_ops
    assert queued
    assert queued[0].get("target_iid") == "played1"
    assert queued[0].get("at_end_of_turn") in (None, False)


def test_op11_096_blocker_needs_other_black_navy():
    reload_effect_library(force=True)
    abs_ = get_card_entry("OP11-096")["abilities"]
    assert {a.get("timing") for a in abs_} >= {"your_turn", "opponent_turn"}
    for a in abs_:
        assert a.get("require_other_chars_trait")
        assert a.get("require_chars_color") == "black"
        assert "梨帕" in str(a.get("require_other_exclude_name") or "")

    st = _state(turn_seat=0)
    rip = CardInst(iid="rip", card_id="OP11-096")
    st.players[0].characters.append(rip)
    cat = _cat()
    info = cat("OP11-096")
    assert "blocker" not in live_keywords(info, rip, state=st, owner_seat=0, catalog=cat)

    st.players[0].characters.append(CardInst(iid="nav", card_id="NAVY_B"))
    assert "blocker" in live_keywords(info, rip, state=st, owner_seat=0, catalog=cat)
    st.turn_seat = 1
    assert "blocker" in live_keywords(info, rip, state=st, owner_seat=0, catalog=cat)


def test_op11_099_search_rest_to_trash():
    reload_effect_library(force=True)
    op = get_card_entry("OP11-099")["abilities"][0]["ops"][0]
    assert op.get("trash_rest") is True
    assert op.get("order_bottom") is False
    assert "我可是" in str(op.get("exclude_name") or "") or "Navy Officer" in str(op.get("exclude_name") or "")


def test_op11_004_exclude_kujyaku_zh():
    reload_effect_library(force=True)
    op = next(
        o
        for a in get_card_entry("OP11-004")["abilities"]
        if a.get("timing") == "on_play"
        for o in a["ops"]
        if o.get("op") == "search_deck"
    )
    assert "孔雀" in str(op.get("exclude_name") or "")


def test_eb04_044_on_opp_ko_draw_once():
    reload_effect_library(force=True)
    draw_ab = next(
        a
        for a in get_card_entry("EB04-044")["abilities"]
        if any(o.get("on_opp_ko") for o in (a.get("ops") or []))
    )
    assert draw_ab.get("timing") == "your_turn"

    st = _state(turn_seat=0, hand0=[], leader0="OP11-001")
    st.players[0].characters.append(CardInst(iid="koby", card_id="EB04-044"))
    st.players[1].characters.append(CardInst(iid="opp", card_id="OPP"))
    cat = _cat()
    apply_ops(st, 0, [{"op": "ko", "target_iid": "opp", "target_kind": "opponent_character", "optional": False}], cat)
    assert not any(c.iid == "opp" for c in st.players[1].characters)
    assert len(st.players[0].hand) == 1


def test_eb04_044_replace_leave_on_bounce():
    reload_effect_library(force=True)
    st = _state(turn_seat=1, hand0=["HAND"], leader0="OP11-001")
    koby = CardInst(iid="koby", card_id="EB04-044")
    st.players[0].characters.append(koby)
    cat = _cat()
    ok = try_replace_leave(st, 0, koby, by_opponent=True, catalog=cat, by_ko=False)
    assert ok is True
    confirm_replace_if_pending(st, cat)
    assert any(c.iid == "koby" for c in st.players[0].characters)
    assert "HAND" in st.players[0].trash


def test_allow_attack_active_skippable_with_one_target():
    st = _state(turn_seat=0)
    st.players[0].characters.append(CardInst(iid="sw", card_id="SWORD6"))
    apply_ops(
        st,
        0,
        [
            {
                "op": "allow_attack_active",
                "count": 1,
                "target_kind": "own_character",
                "trait_contains": "SWORD",
                "optional": True,
            }
        ],
        _cat(),
    )
    assert st.pending_choice is not None
    assert st.pending_choice.optional is True
    assert "sw" in st.pending_choice.options
