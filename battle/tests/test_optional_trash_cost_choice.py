"""Optional as_cost trash_hand must ask even with a sole eligible card (e.g. OP16-092)."""

from __future__ import annotations

from battle.effects import apply_ops
from battle.engine import apply_action
from battle.state import MatchState, PlayerState


def _catalog(cid: str) -> dict:
    table = {
        "C8": {"card_id": "C8", "card_type": "CHARACTER", "cost": 8, "name": "Big"},
        "C9": {"card_id": "C9", "card_type": "CHARACTER", "cost": 9, "name": "Bigger"},
        "C3": {"card_id": "C3", "card_type": "CHARACTER", "cost": 3, "name": "Small"},
        "E1": {"card_id": "E1", "card_type": "EVENT", "cost": 1, "name": "Event"},
    }
    return dict(table.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1})


def _state(*, hand: list[str]) -> MatchState:
    p0 = PlayerState(seat=0, user_id="u0", username="p0", is_ai=False, leader_card_id="L0", hand=list(hand), deck=["D"] * 10)
    p1 = PlayerState(seat=1, user_id="u1", username="p1", is_ai=False, leader_card_id="L1", hand=[], deck=["D"] * 10)
    return MatchState(room_code="t", status="playing", phase="main", turn_seat=0, players=[p0, p1])


_ROBIN_OPS = [
    {
        "op": "trash_hand",
        "count": 1,
        "optional": True,
        "as_cost": True,
        "card_type": "character",
        "cost_gte": 8,
        "owner": "self",
    },
    {"op": "draw", "count": 2},
]


def test_optional_cost_sole_eligible_offers_choice():
    st = _state(hand=["C8", "C3", "E1"])
    apply_ops(st, 0, list(_ROBIN_OPS), _catalog)
    assert st.pending_choice is not None
    assert st.pending_choice.optional is True
    assert st.pending_choice.purpose == "trash"
    assert len(st.pending_choice.options) == 1
    assert st.pending_choice.options[0].endswith(":C8")
    assert "C8" in st.players[0].hand
    assert "C8" not in st.players[0].trash


def test_optional_cost_skip_cancels_draw():
    st = _state(hand=["C8", "C3"])
    deck_before = list(st.players[0].deck)
    apply_ops(st, 0, list(_ROBIN_OPS), _catalog)
    assert st.pending_choice is not None
    assert apply_action(st, 0, {"type": "skip_choice"}, _catalog)["ok"]
    assert st.pending_choice is None
    assert "C8" in st.players[0].hand
    assert st.players[0].deck == deck_before


def test_optional_cost_pay_then_draw():
    st = _state(hand=["C8", "C3"])
    apply_ops(st, 0, list(_ROBIN_OPS), _catalog)
    pick = st.pending_choice.options[0]
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick}, _catalog)["ok"]
    assert "C8" in st.players[0].trash
    assert len(st.players[0].hand) >= 2


def test_mandatory_sole_eligible_still_auto():
    st = _state(hand=["C8", "C3"])
    apply_ops(
        st,
        0,
        [{"op": "trash_hand", "count": 1, "optional": False, "card_type": "character", "cost_gte": 8}],
        _catalog,
    )
    assert st.pending_choice is None
    assert "C8" in st.players[0].trash
