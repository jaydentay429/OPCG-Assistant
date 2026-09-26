"""Regression test: ST32-002 (Kouzuki Oden)'s deny-rest On-Play effect must
prevent the targeted opponent Character from activating [Blocker], since
Blocker requires resting the card as its cost and "cannot be rested" is an
absolute restriction (paper text: "無法置為休息狀態" / EN: "cannot be
rested"), not merely immunity to opponent-controlled rest effects.

Bug report: after ST32-002 denies rest on an opponent's Character (e.g.
OP16-045 Crocodile, [Blocker], base cost 4 <= 6), that Character could still
be offered as a legal blocker in legal_actions(), letting it rest itself via
Blocker despite the restriction.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if "battle" not in sys.modules:
    pkg = types.ModuleType("battle")
    pkg.__path__ = [str(ROOT / "battle")]
    sys.modules["battle"] = pkg

from battle.effect_library import reload_effect_library  # noqa: E402
from battle.effects import apply_ops  # noqa: E402
from battle.engine import apply_action, legal_actions  # noqa: E402
from battle.state import CardInst, MatchState, PendingAttack, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text())


def catalog(cid: str):
    return dict(_CARDS.get(cid) or {"cost": 1, "name": cid, "power": 5000, "card_type": "CHARACTER"})


def _state() -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP12-020",
        deck=["X"] * 20,
        hand=[],
        life=["L"] * 5,
        characters=[],
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["Y"] * 20,
        hand=[],
        life=["M"] * 5,
        characters=[
            CardInst(iid="croc", card_id="OP16-045", rested=False),  # [Blocker], cost 4
            CardInst(iid="other", card_id="OP16-045", rested=False),  # untouched [Blocker]
        ],
    )
    return MatchState(
        room_code="T",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
    )


def test_st32_002_deny_rest_blocks_blocker_activation() -> None:
    st = _state()
    p1 = st.player(1)

    # Mirror ST32-002's compiled on_play op (see index/card_effects.json):
    # {"op": "deny_rest", "target_kind": "opponent_character", "base_cost_lte": 6,
    #  "duration": "until_opp_turn_end"}
    op = {
        "op": "deny_rest",
        "count": 1,
        "target_kind": "opponent_character",
        "base_cost_lte": 6,
        "duration": "until_opp_turn_end",
        "target_iid": "croc",
    }
    apply_ops(st, 0, [op], catalog)
    assert "croc" in p1.deny_rest_until_opp_end_iids

    # Seat 0 attacks seat 1's leader; seat 1 is offered block choices.
    st.phase = "block"
    st.attack = PendingAttack(
        attacker_seat=0,
        attacker_iid="leader",
        target_iid="leader",
        declared_power=5000,
        combat_entered=True,
    )

    acts = legal_actions(st, 1, catalog)
    offered = {a.get("blocker_iid") for a in acts if a.get("type") == "block"}

    assert "croc" not in offered, "deny-rested Blocker must not be offerable as a block"
    assert "other" in offered, "non-targeted Blocker must still be offerable"


def _play_state() -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP12-020",
        deck=["X"] * 20,
        hand=["ST32-002"],
        life=["L"] * 5,
        don_active=8,
        don_given=8,
        turns_completed=1,
        characters=[],
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["Y"] * 20,
        hand=[],
        life=["M"] * 5,
        characters=[
            CardInst(iid="croc", card_id="OP16-045", rested=False, summoning_sick=False),
            CardInst(iid="other", card_id="OP16-045", rested=False, summoning_sick=False),
        ],
        turns_completed=1,
    )
    return MatchState(
        room_code="T",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=3,
        players=[p0, p1],
    )


def _drain_controller(st: MatchState) -> None:
    for _ in range(12):
        if st.pending_effect and st.pending_effect.seat == 0:
            assert apply_action(st, 0, {"type": "confirm_effect", "accept": True}, catalog)["ok"]
            continue
        break


def test_st32_002_play_path_lock_blocks_crocodile_blocker() -> None:
    reload_effect_library(force=True)
    st = _play_state()
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _drain_controller(st)
    assert st.pending_choice is not None, f"expected deny-rest choice, got {st.pending_choice}"
    assert "croc" in (st.pending_choice.options or [])
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "croc"}, catalog)["ok"]
    _drain_controller(st)
    assert "croc" in st.player(1).deny_rest_until_opp_end_iids, (
        f"lock missing; self={st.player(0).deny_rest_until_opp_end_iids} "
        f"foe={st.player(1).deny_rest_until_opp_end_iids} "
        f"turn={st.player(0).deny_rest_iids}/{st.player(1).deny_rest_iids}"
    )

    atk = apply_action(st, 0, {"type": "attack", "attacker_iid": "leader", "target_iid": "leader"}, catalog)
    assert atk.get("ok") is True, atk
    _drain_controller(st)
    assert st.phase == "block"
    acts = legal_actions(st, 1, catalog)
    offered = {a.get("blocker_iid") for a in acts if a.get("type") == "block"}
    assert "croc" not in offered
    assert "other" in offered
    blocked = apply_action(st, 1, {"type": "block", "blocker_iid": "croc"}, catalog)
    assert blocked.get("ok") is False
    croc = next(c for c in st.player(1).characters if c.iid == "croc")
    assert croc.rested is False
