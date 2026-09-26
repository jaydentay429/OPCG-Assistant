"""OP14-033 Perona: On Play deny_rest up to 2 opponent cost≤5 Characters."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.engine import apply_action  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return dict(row)
    extras = {
        "L0": {"card_id": "L0", "card_type": "LEADER", "name": "Me", "power": 5000, "life": 5},
        "L1": {"card_id": "L1", "card_type": "LEADER", "name": "Opp", "power": 5000, "life": 5},
        "C3": {"card_id": "C3", "card_type": "CHARACTER", "name": "Small", "cost": 3, "power": 4000},
        "C4": {"card_id": "C4", "card_type": "CHARACTER", "name": "Mid", "cost": 4, "power": 5000},
        "C5": {"card_id": "C5", "card_type": "CHARACTER", "name": "Five", "cost": 5, "power": 6000},
        "C6": {"card_id": "C6", "card_type": "CHARACTER", "name": "Big", "cost": 6, "power": 7000},
    }
    return dict(extras.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000})


def _state(*, hand_id: str = "OP14-033") -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="p0",
        is_ai=False,
        leader_card_id="L0",
        hand=[hand_id],
        deck=["D"] * 30,
        life=["X"] * 5,
        don_active=10,
        turns_completed=1,
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="p1",
        is_ai=False,
        leader_card_id="L1",
        hand=[],
        deck=["D"] * 30,
        life=["X"] * 5,
    )
    p1.characters = [
        CardInst(iid="oc3", card_id="C3", summoning_sick=False),
        CardInst(iid="oc4", card_id="C4", summoning_sick=False),
        CardInst(iid="oc5", card_id="C5", summoning_sick=False),
        CardInst(iid="oc6", card_id="C6", summoning_sick=False),
    ]
    return MatchState(room_code="t", status="playing", phase="main", turn_seat=0, players=[p0, p1])


def test_encoding_deny_rest_count_2():
    reload_effect_library(force=True)
    for cid in ("OP14-033", "OP14-033-P1", "OP14-033-P2"):
        entry = get_card_entry(cid)
        on_play = next(a for a in (entry.get("abilities") or []) if a.get("timing") == "on_play")
        op = on_play["ops"][0]
        assert op["op"] == "deny_rest"
        assert op.get("count") == 2
        assert op.get("cost_lte") == 5
        assert op.get("target_kind") == "opponent_character"
        assert op.get("duration") == "until_opp_turn_end"


def test_on_play_picks_two_cost_lte_5():
    reload_effect_library(force=True)
    st = _state()
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    ch = st.pending_choice
    assert ch is not None
    assert set(ch.options) == {"oc3", "oc4", "oc5"}
    assert "oc6" not in ch.options
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "oc3"}, catalog)["ok"]
    locked = st.players[1].deny_rest_until_opp_end_iids
    assert "oc3" in locked
    ch2 = st.pending_choice
    assert ch2 is not None, "must offer a second pick when count is 2"
    assert "oc3" not in ch2.options
    assert set(ch2.options) == {"oc4", "oc5"}
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "oc5"}, catalog)["ok"]
    locked = st.players[1].deny_rest_until_opp_end_iids
    assert set(locked) == {"oc3", "oc5"}
    assert st.pending_choice is None
    assert "oc4" not in locked
    assert "oc6" not in locked


def test_on_play_two_eligible_picks_both():
    reload_effect_library(force=True)
    st = _state()
    st.players[1].characters = [
        CardInst(iid="oc3", card_id="C3", summoning_sick=False),
        CardInst(iid="oc4", card_id="C4", summoning_sick=False),
    ]
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert st.pending_choice is not None
    assert set(st.pending_choice.options) == {"oc3", "oc4"}
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "oc4"}, catalog)["ok"]
    locked = st.players[1].deny_rest_until_opp_end_iids
    assert "oc4" in locked
    # Second remaining target auto-applies when only one is left.
    if st.pending_choice is not None:
        pick = st.pending_choice.options[0]
        assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick}, catalog)["ok"]
    assert set(st.players[1].deny_rest_until_opp_end_iids) == {"oc3", "oc4"}


def test_on_play_skip_second_keeps_one():
    reload_effect_library(force=True)
    st = _state()
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "oc3"}, catalog)["ok"]
    assert "oc3" in st.players[1].deny_rest_until_opp_end_iids
    assert st.pending_choice is not None
    assert apply_action(st, 0, {"type": "skip_choice"}, catalog)["ok"]
    assert st.players[1].deny_rest_until_opp_end_iids == ["oc3"]
    assert st.pending_choice is None
