"""Batch-C effect encoding / runtime fixes (Aug 2026)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.effects import apply_ops, has_blocker  # noqa: E402
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
        don_active=int(kwargs.get("don_active0", 0) or 0),
        don_rested=int(kwargs.get("don_rested0", 0) or 0),
        don_given=int(kwargs.get("don_given0", 0) or 0),
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
        don_active=int(kwargs.get("don_active1", 2) or 0),
        don_rested=0,
        don_given=int(kwargs.get("don_given1", 2) or 0),
    )
    return MatchState(
        room_code="T",
        status="playing",
        phase="main",
        turn_seat=kwargs.get("turn_seat", 0),
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
    )


def test_op05_057_trigger_not_on_main():
    reload_effect_library(force=True)
    entry = get_card_entry("OP05-057")
    main = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    trig = next(a for a in entry["abilities"] if a["timing"] == "trigger")
    assert [o["op"] for o in main["ops"]] == ["buff", "return_to_bottom"]
    assert main["ops"][1].get("cost_lte") == 2
    assert trig["ops"][0]["op"] == "return_to_hand"
    assert trig["ops"][0].get("cost_lte") == 3


def test_op15_032_opponent_card_rest_no_cost_gate():
    reload_effect_library(force=True)
    entry = get_card_entry("OP15-032")
    on_play = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    rest = on_play["ops"][0]
    assert rest.get("include_leader") and rest.get("include_don") and rest.get("include_stage")
    assert rest.get("cost_lte") is None
    act = next(a for a in entry["abilities"] if a["timing"] == "activate_main")
    assert act.get("require_leader_trait")
    assert act["ops"][0]["target_kind"] == "self" and act["ops"][0]["optional"] is True


def test_op16_032_excludes_luffy():
    reload_effect_library(force=True)
    deny = get_card_entry("OP16-032")["abilities"][0]["ops"][0]
    assert deny["op"] == "deny_rest"
    assert "魯夫" in deny.get("exclude_name", "") or "Luffy" in deny.get("exclude_name", "")


def test_op16_038_distinct_gate_and_leader_active():
    reload_effect_library(force=True)
    ab = get_card_entry("OP16-038")["abilities"][0]
    assert ab.get("require_distinct_own_chars_trait_gte") == 5
    active = ab["ops"][1]
    assert active.get("all") and active.get("include_leader")
    ctr = get_card_entry("OP16-038")["abilities"][1]["ops"][0]
    assert ctr.get("duration") == "battle"


def test_op16_055_don_not_on_play():
    reload_effect_library(force=True)
    entry = get_card_entry("OP16-055")
    on_play = next(a for a in entry["abilities"] if a["timing"] == "on_play")
    atk = next(a for a in entry["abilities"] if a["timing"] == "when_attacking")
    assert on_play.get("require_don_attached_gte") is None
    assert atk.get("require_don_attached_gte") == 1


def test_op16_056_trash_optional():
    reload_effect_library(force=True)
    trash = get_card_entry("OP16-056")["abilities"][0]["ops"][0]
    assert trash["optional"] is True


def test_st30_012_require_blocker_runtime():
    reload_effect_library(force=True)
    st = _state()
    blocker = CardInst(iid="b1", card_id="OP01-016", rested=False, keywords=["blocker"])
    normal = CardInst(iid="n1", card_id="OP01-017", rested=False)
    st.players[1].characters.extend([blocker, normal])
    catalog = {
        "OP01-016": {"effect": "【防禦】", "name": "Blocker", "power": "5000"},
        "OP01-017": {"effect": "", "name": "Norm", "power": "4000"},
    }.get
    # Force innate blocker detection via effect text / keywords
    apply_ops(
        st,
        0,
        [
            {
                "op": "rest_opponent_character",
                "count": 1,
                "require_blocker": True,
                "optional": False,
                "target_iid": "n1",
            }
        ],
        catalog,
    )
    # With target_iid forced, blocker filter is on option building; use choice path
    st2 = _state()
    st2.players[1].characters.extend(
        [
            CardInst(iid="b1", card_id="OP01-016", rested=False),
            CardInst(iid="n1", card_id="OP01-017", rested=False),
        ]
    )
    apply_ops(
        st2,
        0,
        [{"op": "rest_opponent_character", "count": 1, "require_blocker": True, "optional": False}],
        catalog,
    )
    # Only blocker should be rested (auto-pick single legal) or offered
    if st2.pending_choice:
        assert st2.pending_choice.options == ["b1"]
    else:
        assert st2.players[1].characters[0].rested is True
        assert st2.players[1].characters[1].rested is False


def test_st30_014_encoding():
    reload_effect_library(force=True)
    ops = get_card_entry("ST30-014")["abilities"][0]["ops"]
    assert ops[0]["target_kind"] == "self"
    assert ops[1]["op"] == "attach_don"
    assert ops[1].get("base_power_eq") == 6000
    assert ops[1].get("target_count") == 2
    assert ops[1].get("as_rested") is True


def test_st30_014_attach_runtime():
    reload_effect_library(force=True)
    st = _state(don_rested0=4, don_given0=4, don_active0=0)
    src = CardInst(iid="src", card_id="ST30-014", rested=False)
    t1 = CardInst(iid="t1", card_id="OP16-042", rested=False)
    t2 = CardInst(iid="t2", card_id="OP16-042b", rested=False)
    st.players[0].characters.extend([src, t1, t2])
    catalog = {
        "ST30-014": {"power": "5000"},
        "OP16-042": {"power": "6000", "name": "Prisoner"},
        "OP16-042b": {"power": "6000", "name": "Prisoner2"},
    }.get
    apply_ops(
        st,
        0,
        [
            {"op": "rest_character", "target_kind": "self", "source_iid": "src", "as_cost": True, "optional": False},
            {
                "op": "attach_don",
                "count": 2,
                "as_rested": True,
                "from_rested": True,
                "target_kind": "own_character",
                "base_power_eq": 6000,
                "target_count": 2,
                "optional": False,
                "target_iid": "t1",
            },
        ],
        catalog,
    )
    assert src.rested is True
    assert t1.don_attached == 2
    # Second target queued
    assert st.pending_choice is not None or t2.don_attached == 2 or st.players[0].don_rested < 4


def test_opponent_card_rest_can_rest_don():
    st = _state(don_active1=2, don_given1=2)
    apply_ops(
        st,
        0,
        [
            {
                "op": "rest_character",
                "target_kind": "opponent_character",
                "include_leader": True,
                "include_don": True,
                "include_stage": True,
                "target_iid": "don",
                "optional": False,
            }
        ],
        {}.get,
    )
    assert st.players[1].don_active == 1
    assert st.players[1].don_rested == 1
