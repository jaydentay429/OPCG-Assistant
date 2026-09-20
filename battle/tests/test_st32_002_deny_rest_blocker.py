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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effects import apply_ops  # noqa: E402
from battle.engine import legal_actions  # noqa: E402
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
