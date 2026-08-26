"""OP15 debuffs must hit opponent characters, not own board."""

from __future__ import annotations

from battle.effects import apply_ops
from battle.engine import inst_power
from battle.state import CardInst, MatchState, PlayerState


def _catalog(cid: str) -> dict:
    table = {
        "ACE": {
            "card_type": "EVENT",
            "name": "Just Watch Me, Ace!!!",
            "cost": 4,
        },
        "FOE": {"card_type": "LEADER", "name": "Foe", "power": 5000, "life": 5, "cost": 0},
        "ME": {"card_type": "LEADER", "name": "Me", "power": 5000, "life": 5, "cost": 0},
        "F1": {"card_type": "CHARACTER", "name": "Foe Char", "cost": 3, "power": 4000},
        "M1": {"card_type": "CHARACTER", "name": "My Char", "cost": 3, "power": 4000},
    }
    return dict(table.get(cid) or {"card_type": "CHARACTER", "name": cid, "cost": 1, "power": 1000})


def _state_with_board() -> MatchState:
    st = MatchState(
        room_code="t",
        status="playing",
        phase="main",
        turn_seat=0,
        players=[
            PlayerState(seat=0, user_id="u0", username="P0", is_ai=False, leader_card_id="ME"),
            PlayerState(seat=1, user_id="u1", username="P1", is_ai=False, leader_card_id="FOE"),
        ],
    )
    p0, p1 = st.players
    p0.characters = [CardInst(iid="m1", card_id="M1")]
    p1.characters = [CardInst(iid="f1", card_id="F1")]
    return st


def test_op15_021_debuff_hits_opponent_not_own():
    st = _state_with_board()
    ops = [{"op": "buff", "amount": -3000, "optional": False, "target_iid": "f1"}]
    apply_ops(st, 0, ops, _catalog)
    assert st.players[0].characters[0].power_mod == 0
    assert st.players[1].characters[0].power_mod == -3000
    assert inst_power(st, 1, "f1", _catalog) == 1000


def test_negative_power_after_debuff():
    st = _state_with_board()
    st.players[1].characters[0].power_mod = -4000
    assert inst_power(st, 1, "f1", _catalog) == 0


def test_negative_power_can_go_below_zero():
    st = _state_with_board()
    st.players[1].characters = [CardInst(iid="z0", card_id="Z0")]
    st.players[1].characters[0].power_mod = -3000

    def cat(cid: str) -> dict:
        if cid == "Z0":
            return {"card_type": "CHARACTER", "name": "Zero", "cost": 0, "power": 0}
        return _catalog(cid)

    assert inst_power(st, 1, "z0", cat) == -3000


def test_missing_target_kind_negative_buff_defaults_to_opponent():
    """Regression for OP15-021-style encodings that omitted target_kind."""
    st = _state_with_board()
    apply_ops(st, 0, [{"op": "buff", "amount": -3000, "optional": False}], _catalog)
    # With only one opponent Character and non-optional missing target_kind,
    # engine should still resolve against opponent (not own board).
    assert st.players[0].characters[0].power_mod == 0
    # Either pending choice on opponent, or applied to foe.
    if st.pending_choice:
        assert st.pending_choice.target_kind == "opponent_character"
        assert "f1" in st.pending_choice.options
        assert "m1" not in st.pending_choice.options
    else:
        assert st.players[1].characters[0].power_mod == -3000


def test_op15_021_library_encoding():
    from battle.effect_library import get_abilities, reload_effect_library

    reload_effect_library(force=True)
    abs_ = get_abilities("OP15-021")
    by_t = {a.get("timing"): a for a in abs_}
    assert "require_trash_gte" not in by_t["on_play"]
    for timing in ("on_play", "counter_event"):
        ops = by_t[timing]["ops"]
        assert ops[0]["op"] == "buff"
        assert ops[0]["amount"] == -3000
        assert ops[0]["target_kind"] == "opponent_character"
        assert ops[0].get("optional") is True
