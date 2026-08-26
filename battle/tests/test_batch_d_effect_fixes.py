"""Batch-D effect encoding / runtime fixes (Aug 2026)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effects import apply_ops  # noqa: E402
from battle.leave_replace import confirm_replace_if_pending, try_replace_leave  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.get("leader0", "OP15-020"),
        deck=["A"] * 20,
        hand=list(kwargs.get("hand0", [])),
        life=list(kwargs.get("life0", ["L1", "L2"])),
        trash=[],
        don_active=int(kwargs.get("don_active0", 0) or 0),
        don_rested=0,
        don_given=0,
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
    st = MatchState(
        room_code="T",
        status="playing",
        phase="main",
        turn_seat=kwargs.get("turn_seat", 0),
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
    )
    for cid in kwargs.get("stages0", []) or []:
        st.players[0].stages.append(CardInst(iid=f"s0-{cid}", card_id=cid, rested=False))
    for cid in kwargs.get("stages1", []) or []:
        st.players[1].stages.append(CardInst(iid=f"s1-{cid}", card_id=cid, rested=False))
    return st


def test_op15_020_leader_turn_and_trash_gated_ko():
    reload_effect_library(force=True)
    ab = get_card_entry("OP15-020")["abilities"][0]
    ops = ab["ops"]
    assert ops[0]["op"] == "buff" and ops[0]["duration"] == "turn"
    assert ops[1]["duration"] == "until_opp_turn_end"
    assert ops[2]["op"] == "trash_hand" and ops[2]["count"] == 2 and ops[2]["optional"] is True
    assert ops[3]["op"] == "ko" and ops[3].get("require_trash_hand_gte") == 2

    st = _state(hand0=["H1", "H2", "H3"])
    victim = CardInst(iid="v1", card_id="C0", rested=False, power_mod=-5000)
    st.players[1].characters.append(victim)
    catalog = {
        "OP15-020": {"card_type": "CHARACTER", "name": "X", "power": 5000, "cost": 5},
        "C0": {"card_type": "CHARACTER", "name": "Victim", "power": 5000, "cost": 3},
        "H1": {"card_type": "CHARACTER", "name": "H1", "cost": 1},
        "H2": {"card_type": "CHARACTER", "name": "H2", "cost": 1},
        "H3": {"card_type": "CHARACTER", "name": "H3", "cost": 1},
    }.get

    # No trash paid → KO gated off.
    apply_ops(
        st,
        0,
        [{"op": "ko", "target_kind": "opponent_character", "optional": True, "power_lte": 0, "if_trash_hand": True, "require_trash_hand_gte": 2}],
        catalog,
    )
    assert any(c.iid == "v1" for c in st.players[1].characters)

    setattr(st.players[0], "_last_trash_hand_count", 2)
    apply_ops(
        st,
        0,
        [
            {
                "op": "ko",
                "target_kind": "opponent_character",
                "optional": False,
                "power_lte": 0,
                "if_trash_hand": True,
                "require_trash_hand_gte": 2,
                "target_iid": "v1",
            }
        ],
        catalog,
    )
    assert not any(c.iid == "v1" for c in st.players[1].characters)
    assert "C0" in st.players[1].trash


def test_op15_014_event_replace_no_once():
    reload_effect_library(force=True)
    entry = get_card_entry("OP15-014")
    for ab in entry["abilities"]:
        if ab.get("timing") in {"your_turn", "opponent_turn"}:
            assert not ab.get("once")
            op = ab["ops"][0]
            assert op["op"] == "replace_leave"
            assert op.get("hand_card_type") == "event"

    st = _state(hand0=["EV1", "CH1"], leader0="OP01-001")
    victim = CardInst(iid="v1", card_id="OP15-014", rested=False)
    st.players[0].characters.append(victim)
    catalog = {
        "OP15-014": {"card_type": "CHARACTER", "name": "Saver", "power": 5000, "cost": 4},
        "EV1": {"card_type": "EVENT", "name": "Event", "cost": 1},
        "CH1": {"card_type": "CHARACTER", "name": "Char", "cost": 1, "power": 1000},
    }.get
    ok = try_replace_leave(st, 0, victim, by_opponent=True, catalog=catalog)
    assert ok is True
    confirm_replace_if_pending(st, catalog)
    assert "EV1" in st.players[0].trash
    assert "CH1" in st.players[0].hand
    assert any(c.iid == "v1" for c in st.players[0].characters)


def test_op15_014_replace_fails_without_event():
    st = _state(hand0=["CH1"], leader0="OP01-001")
    victim = CardInst(iid="v1", card_id="OP15-014", rested=False)
    st.players[0].characters.append(victim)
    catalog = {
        "OP15-014": {"card_type": "CHARACTER", "name": "Saver", "power": 5000, "cost": 4},
        "CH1": {"card_type": "CHARACTER", "name": "Char", "cost": 1, "power": 1000},
    }.get
    ok = try_replace_leave(st, 0, victim, by_opponent=True, catalog=catalog)
    assert ok is False
    assert "CH1" in st.players[0].hand


def test_op15_054_returns_stage():
    reload_effect_library(force=True)
    choose = get_card_entry("OP15-054")["abilities"][0]["ops"][0]
    opt1 = next(o for o in choose["options"] if o["id"] == "opt1")
    rth = opt1["ops"][0]
    assert rth["op"] == "return_to_hand"
    assert rth["target_kind"] == "any_stage"
    assert rth["card_type"] == "stage"

    st = _state(stages1=["STG1"])
    stage_iid = st.players[1].stages[0].iid
    catalog = {
        "STG1": {"card_type": "STAGE", "name": "Arena", "cost": 1},
    }.get
    apply_ops(
        st,
        0,
        [
            {
                "op": "return_to_hand",
                "target_kind": "any_stage",
                "card_type": "stage",
                "optional": False,
                "target_iid": stage_iid,
            }
        ],
        catalog,
    )
    assert not st.players[1].stages
    assert "STG1" in st.players[1].hand


def test_op15_057_and_019_durations():
    reload_effect_library(force=True)
    atk = next(a for a in get_card_entry("OP15-057")["abilities"] if a["timing"] == "on_opponent_attack")
    buff = next(o for o in atk["ops"] if o["op"] == "buff")
    assert buff.get("duration") == "battle"

    trig = next(a for a in get_card_entry("OP15-019")["abilities"] if a["timing"] == "trigger")
    assert trig["ops"][0].get("duration") == "turn"
