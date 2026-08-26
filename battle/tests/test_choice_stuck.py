"""Regression: effect choices must not crash or leave the AI unable to act."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.ai import run_ai_until_human  # noqa: E402
from battle.effects import apply_ops  # noqa: E402
from battle.engine import legal_actions  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402


def _state() -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["A"] * 20,
        hand=["H1", "H2"],
        life=["L"] * 5,
    )
    p1 = PlayerState(
        seat=1,
        user_id="ai",
        username="AI",
        is_ai=True,
        leader_card_id="OP01-001",
        deck=["B"] * 20,
        hand=["H3", "H4"],
        life=["L"] * 5,
    )
    return MatchState(
        room_code="TEST",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
        rng_seed=1,
    )


def catalog(cid: str) -> dict:
    return {
        "cost": 1,
        "power": 5000,
        "name": cid,
        "traits_en": ["Straw Hat Crew"],
        "card_type": "CHARACTER",
    }


def test_allow_attack_active_choice_includes_options():
    st = _state()
    st.players[0].characters = [
        CardInst(iid="a", card_id="A"),
        CardInst(iid="b", card_id="B"),
        CardInst(iid="c", card_id="C"),
    ]
    apply_ops(st, 0, [{"op": "allow_attack_active", "count": 1, "optional": True}], catalog)
    assert st.pending_choice is not None
    assert st.pending_choice.options == ["a", "b", "c"]
    assert {"type": "select_choice", "target_iid": "a"} in legal_actions(st, 0, catalog)


def test_opponent_choose_one_ai_resolves():
    st = _state()
    apply_ops(
        st,
        0,
        [
            {
                "op": "choose_one",
                "chooser": "opponent",
                "options": [
                    {"id": "a", "label": "Draw", "ops": [{"op": "draw", "count": 1}]},
                    {"id": "b", "label": "DON", "ops": [{"op": "gain_don", "count": 1}]},
                ],
            }
        ],
        catalog,
    )
    assert st.pending_choice is not None
    assert st.pending_choice.seat == 1
    assert st.pending_choice.option_labels["opt:0"] == "Draw"
    # Human must wait — no end_turn while opponent chooses.
    assert all(a.get("type") == "concede" for a in legal_actions(st, 0, catalog))
    run_ai_until_human(st, catalog)
    assert st.pending_choice is None
