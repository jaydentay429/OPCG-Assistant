"""Regression: OP16-032 Hancock On Play rest-lock must bar attacking.

Attack declaration rests the attacker (7-1-1). Paper 「無法置為休息狀態」
until the opponent's next End Phase therefore also forbids declaring an
attack with the locked Character.

Bug report (user_26): Hancock locked OP14-027 Shanks; after the victim's
turn started they could still rest and attack.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effects import apply_ops  # noqa: E402
from battle.engine import _clear_turn_duration_effects, apply_action, legal_actions  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text())


def catalog(cid: str):
    return dict(_CARDS.get(cid) or {"cost": 1, "name": cid, "power": 5000, "card_type": "CHARACTER"})


def _state() -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["X"] * 20,
        hand=[],
        life=["L"] * 5,
        characters=[CardInst(iid="hancock", card_id="OP16-032", rested=False)],
        turns_completed=1,
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
            CardInst(iid="shanks", card_id="OP14-027", rested=False, summoning_sick=False),
            CardInst(iid="other", card_id="OP01-016", rested=False, summoning_sick=False),
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


def _lock_shanks(st: MatchState) -> None:
    op = {
        "op": "deny_rest",
        "count": 1,
        "optional": True,
        "target_kind": "opponent_character",
        "duration": "until_opp_turn_end",
        "target_iid": "shanks",
    }
    apply_ops(st, 0, [op], catalog)
    assert "shanks" in st.player(1).deny_rest_until_opp_end_iids


def test_op16_032_deny_rest_survives_hancock_end_phase() -> None:
    st = _state()
    _lock_shanks(st)
    st.turn_seat = 0
    _clear_turn_duration_effects(st)
    assert "shanks" in st.player(1).deny_rest_until_opp_end_iids


def test_op16_032_deny_rest_blocks_attack_on_victim_turn() -> None:
    st = _state()
    _lock_shanks(st)
    st.turn_seat = 0
    _clear_turn_duration_effects(st)
    st.turn_seat = 1
    st.phase = "main"

    acts = legal_actions(st, 1, catalog)
    attack_from = {a.get("attacker_iid") for a in acts if a.get("type") == "attack"}
    assert "shanks" not in attack_from
    assert "other" in attack_from
    assert "leader" in attack_from

    blocked = apply_action(
        st,
        1,
        {"type": "attack", "attacker_iid": "shanks", "target_iid": "leader"},
        catalog,
    )
    assert blocked.get("ok") is False
    shanks = next(c for c in st.player(1).characters if c.iid == "shanks")
    assert shanks.rested is False


def test_op16_032_deny_rest_clears_at_victim_end_phase() -> None:
    st = _state()
    _lock_shanks(st)
    st.turn_seat = 0
    _clear_turn_duration_effects(st)
    st.turn_seat = 1
    _clear_turn_duration_effects(st)
    assert "shanks" not in st.player(1).deny_rest_until_opp_end_iids
