"""Batch-E effect encoding / runtime fixes (Aug 2026)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library, resolve_activate_spec  # noqa: E402
from battle.effects import apply_ops  # noqa: E402
from battle.engine import _blocker_denied, inst_power  # noqa: E402
from battle.leave_replace import confirm_replace_if_pending, try_replace_leave  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402


def _state(**kwargs) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.get("leader0", "OP09-001"),
        deck=["A"] * 20,
        hand=list(kwargs.get("hand0", [])),
        life=["L1", "L2"],
        trash=[],
        don_active=int(kwargs.get("don_active0", 0) or 0),
        don_rested=0,
        don_given=int(kwargs.get("don_given0", 0) or 0),
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
        room_code="T",
        status="playing",
        phase="main",
        turn_seat=kwargs.get("turn_seat", 0),
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
    )


def test_op09_001_single_optional_buff():
    reload_effect_library(force=True)
    ops = get_card_entry("OP09-001")["abilities"][0]["ops"]
    assert len(ops) == 1
    assert ops[0]["optional"] is True and ops[0]["duration"] == "turn"


def test_op09_004_no_on_play_aura_only():
    reload_effect_library(force=True)
    timings = [a["timing"] for a in get_card_entry("OP09-004")["abilities"]]
    assert "on_play" not in timings
    assert "your_turn" in timings and "opponent_turn" in timings

    st = _state()
    st.players[0].characters.append(CardInst(iid="j1", card_id="OP09-004"))
    st.players[1].characters.append(CardInst(iid="c1", card_id="C1"))
    catalog = {
        "OP09-004": {"name": "Jack", "power": "8000", "cost": 4, "card_type": "CHARACTER"},
        "C1": {"name": "A", "power": "5000", "cost": 3, "card_type": "CHARACTER"},
        "OP09-001": {"name": "L", "power": "5000", "card_type": "LEADER"},
        "OP01-001": {"name": "F", "power": "5000", "card_type": "LEADER"},
    }.get
    assert inst_power(st, 1, "c1", catalog) == 4000


def test_op09_011_rest_self_buff_only():
    reload_effect_library(force=True)
    spec = resolve_activate_spec("OP09-011", {})
    assert spec.get("rest_self") is True
    assert [o["op"] for o in spec["ops"]] == ["buff"]
    assert spec["ops"][0].get("duration") == "turn"
    assert spec["ops"][0].get("optional") is True


def test_op09_014_targeted_deny_blocker():
    reload_effect_library(force=True)
    op = get_card_entry("OP09-014")["abilities"][0]["ops"][0]
    assert op["op"] == "deny_blocker"
    assert op.get("target_kind") == "opponent_character"
    assert op.get("power_lte") == 4000

    st = _state()
    low = CardInst(iid="lo", card_id="LOW")
    high = CardInst(iid="hi", card_id="HI")
    st.players[1].characters.extend([low, high])
    catalog = {
        "LOW": {"name": "Low", "power": "3000", "cost": 2, "card_type": "CHARACTER"},
        "HI": {"name": "Hi", "power": "5000", "cost": 3, "card_type": "CHARACTER"},
        "OP09-001": {"name": "L", "power": "5000", "card_type": "LEADER"},
        "OP01-001": {"name": "F", "power": "5000", "card_type": "LEADER"},
    }.get
    apply_ops(
        st,
        0,
        [
            {
                "op": "deny_blocker",
                "duration": "turn",
                "target_kind": "opponent_character",
                "optional": False,
                "target_iid": "lo",
            }
        ],
        catalog,
    )
    assert _blocker_denied(st, 0, low, catalog) is True
    assert _blocker_denied(st, 0, high, catalog) is False


def test_op09_018_total_power_ko_budget():
    reload_effect_library(force=True)
    ko = get_card_entry("OP09-018")["abilities"][0]["ops"][0]
    assert ko.get("count") == 2 and ko.get("total_power_lte") == 4000
    assert get_card_entry("OP05-007")["abilities"][0]["ops"][0].get("total_power_lte") == 4000

    st = _state()
    a = CardInst(iid="a", card_id="A2")
    b = CardInst(iid="b", card_id="B2")
    c = CardInst(iid="c", card_id="C5")
    st.players[1].characters.extend([a, b, c])
    catalog = {
        "A2": {"name": "A", "power": "2000", "cost": 1, "card_type": "CHARACTER"},
        "B2": {"name": "B", "power": "2000", "cost": 1, "card_type": "CHARACTER"},
        "C5": {"name": "C", "power": "5000", "cost": 3, "card_type": "CHARACTER"},
        "OP09-001": {"name": "L", "power": "5000", "card_type": "LEADER"},
        "OP01-001": {"name": "F", "power": "5000", "card_type": "LEADER"},
    }.get
    apply_ops(
        st,
        0,
        [
            {
                "op": "ko",
                "target_kind": "opponent_character",
                "optional": False,
                "count": 2,
                "total_power_lte": 4000,
                "target_iid": "a",
            }
        ],
        catalog,
    )
    assert "A2" in st.players[1].trash
    # Second pick offered with remaining budget 2000
    assert st.pending_choice is not None
    assert "b" in st.pending_choice.options
    assert "c" not in st.pending_choice.options


def test_op16_018_replace_leave_hand_power():
    reload_effect_library(force=True)
    for ab in get_card_entry("OP16-018")["abilities"]:
        op = ab["ops"][0]
        assert op["op"] == "replace_leave"
        assert op.get("hand_card_type") == "character"
        assert op.get("hand_power_gte") == 6000

    st = _state(hand0=["WEAK", "STRONG"], leader0="OP01-001")
    victim = CardInst(iid="v1", card_id="ALLY")
    shield = CardInst(iid="s1", card_id="OP16-018")
    st.players[0].characters.extend([victim, shield])
    catalog = {
        "OP16-018": {"name": "Rockstar", "power": "5000", "cost": 4, "card_type": "CHARACTER", "traits_en": ["Red-Haired Pirates"]},
        "ALLY": {"name": "Beck", "power": "5000", "cost": 3, "card_type": "CHARACTER", "traits_en": ["Red-Haired Pirates"]},
        "WEAK": {"name": "W", "power": "4000", "cost": 2, "card_type": "CHARACTER"},
        "STRONG": {"name": "S", "power": "7000", "cost": 5, "card_type": "CHARACTER"},
        "OP01-001": {"name": "L", "power": "5000", "card_type": "LEADER"},
    }.get
    ok = try_replace_leave(st, 0, victim, by_opponent=True, catalog=catalog)
    assert ok is True
    confirm_replace_if_pending(st, catalog)
    assert "STRONG" in st.players[0].trash
    assert "WEAK" in st.players[0].hand
    assert any(c.iid == "v1" for c in st.players[0].characters)


def test_prb02_002_replace_and_attack_duration():
    reload_effect_library(force=True)
    entry = get_card_entry("PRB02-002")
    replace = next(a for a in entry["abilities"] if a["timing"] == "your_turn")
    assert replace["ops"][0]["op"] == "replace_leave"
    assert replace["ops"][0]["cost"] == "self_power_minus"
    atk = next(a for a in entry["abilities"] if a["timing"] == "when_attacking")
    assert atk["ops"][0].get("duration") == "turn"
    assert not atk.get("once")

    st = _state(leader0="OP01-001")
    law = CardInst(iid="law", card_id="PRB02-002")
    st.players[0].characters.append(law)
    catalog = {
        "PRB02-002": {"name": "Law", "power": "6000", "cost": 5, "card_type": "CHARACTER"},
        "OP01-001": {"name": "L", "power": "5000", "card_type": "LEADER"},
    }.get
    ok = try_replace_leave(st, 0, law, by_opponent=True, catalog=catalog)
    assert ok is True
    confirm_replace_if_pending(st, catalog)
    assert law.power_mod == -2000
    assert any(c.iid == "law" for c in st.players[0].characters)
