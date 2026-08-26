"""DON!! attach visuals: no free detach; −DON chooses source."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effects import apply_ops  # noqa: E402
from battle.engine import apply_action, legal_actions, _don_on_field  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

CATALOG = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    return CATALOG.get(cid) or {"cost": 1, "power": 5000, "name": cid, "name_en": cid, "type": "CHARACTER"}


def _state(**kwargs) -> MatchState:
    ch = CardInst(iid="c1", card_id=kwargs.get("char0", "OP01-016"), rested=False, don_attached=0)
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=kwargs.get("leader0", "OP01-001"),
        deck=["D"] * 20,
        hand=["H1"],
        life=["L"] * 5,
        characters=[ch],
        don_active=int(kwargs.get("don_active", 3)),
        don_rested=int(kwargs.get("don_rested", 1)),
        don_given=int(kwargs.get("don_given", 5)),
        leader_don=int(kwargs.get("leader_don", 0)),
    )
    if kwargs.get("char_don"):
        ch.don_attached = int(kwargs["char_don"])
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["B"] * 20,
        hand=["O1"],
        life=["M"] * 5,
    )
    return MatchState(
        room_code="T",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
        rng_seed=1,
    )


def test_remove_don_ok_until_attack():
    """May reclaim attached DON!! until that unit attacks; locked after attack."""
    st = _state(don_active=2, don_rested=0, don_given=2)
    st.players[0].turns_completed = 1
    assert apply_action(st, 0, {"type": "attach_don", "target_iid": "c1"}, catalog)["ok"]
    assert st.players[0].characters[0].don_attached == 1
    kinds = {a.get("type") for a in legal_actions(st, 0, catalog)}
    assert "remove_don" in kinds
    assert apply_action(st, 0, {"type": "remove_don", "target_iid": "c1"}, catalog)["ok"]
    assert st.players[0].characters[0].don_attached == 0
    assert st.players[0].don_active == 2

    assert apply_action(st, 0, {"type": "attach_don", "target_iid": "c1"}, catalog)["ok"]
    # Attack with the character → lock reclaim.
    ch = st.players[0].characters[0]
    ch.summoning_sick = False
    ch.rested = False
    st.players[1].characters = [CardInst(iid="foe", card_id="OP01-016", rested=True)]
    r_atk = apply_action(st, 0, {"type": "attack", "attacker_iid": "c1", "target_iid": "foe"}, catalog)
    assert r_atk["ok"], r_atk.get("error")
    assert "c1" in st.players[0].attacked_this_turn_iids
    # Combat may pause; force back to main for legal_actions.
    st.phase = "main"
    st.attack = None
    st.turn_seat = 0
    kinds2 = {a.get("type") for a in legal_actions(st, 0, catalog)}
    assert not any(a.get("type") == "remove_don" and a.get("target_iid") == "c1" for a in legal_actions(st, 0, catalog))
    assert "remove_don" not in {a.get("type") for a in legal_actions(st, 0, catalog) if a.get("target_iid") == "c1"}
    assert not apply_action(st, 0, {"type": "remove_don", "target_iid": "c1"}, catalog)["ok"]
    assert st.players[0].characters[0].don_attached == 1


def test_return_don_offers_choice_across_sources():
    st = _state(don_active=1, don_rested=1, don_given=4, leader_don=1, char_don=1)
    assert _don_on_field(st.players[0]) == 4
    apply_ops(
        st,
        0,
        [{"op": "return_don", "count": 1, "as_cost": True, "owner": "self"}],
        catalog,
    )
    assert st.pending_choice is not None
    assert st.pending_choice.target_kind == "return_don"
    opts = set(st.pending_choice.options)
    assert "don:active" in opts
    assert "don:rested" in opts
    assert "don:leader" in opts
    assert any(o.startswith("don:char:") for o in opts)

    # Pick attached character DON — must not stand back up as active.
    char_tok = next(o for o in st.pending_choice.options if o.startswith("don:char:"))
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": char_tok}, catalog)["ok"]
    assert st.players[0].characters[0].don_attached == 0
    assert st.players[0].don_active == 1  # unchanged
    assert st.players[0].don_given == 3


def test_return_don_auto_when_single_source():
    st = _state(don_active=0, don_rested=0, don_given=2, leader_don=2, char_don=0)
    apply_ops(st, 0, [{"op": "return_don", "count": 1, "as_cost": True}], catalog)
    assert st.pending_choice is None
    assert st.players[0].leader_don == 1
    assert st.players[0].don_given == 1
