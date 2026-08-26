"""OP14-120 Crocodile — On Play deny+conditional draw; On K.O. trash+play self."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, reload_effect_library, resolve_ability  # noqa: E402
from battle.effects import apply_ops  # noqa: E402
from battle.engine import (  # noqa: E402
    _character_denied_attack,
    _clear_turn_duration_effects,
    apply_action,
)
from battle.rules import timings as rule_timings  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402


def _catalog(cid: str) -> dict:
    import json

    cards = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    return cards.get(cid) or {"card_id": cid, "card_type": "Character", "cost": 1, "power": 1000}


def _state() -> MatchState:
    return MatchState(
        room_code="T",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=2,
        players=[
            PlayerState(
                seat=0,
                user_id="u0",
                username="P1",
                is_ai=False,
                leader_card_id="OP01-001",
                deck=["DRAW"] * 20,
                hand=[],
                trash=[],
                characters=[],
                don_active=10,
                turns_completed=1,
            ),
            PlayerState(
                seat=1,
                user_id="u1",
                username="P2",
                is_ai=False,
                leader_card_id="OP01-001",
                deck=["D"] * 20,
                hand=[],
                trash=[],
                characters=[],
                don_active=10,
                turns_completed=1,
            ),
        ],
    )


def test_op14_120_abilities_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("OP14-120")
    by_t = {a["timing"]: a for a in entry.get("abilities") or []}
    assert "on_play" in by_t and "on_ko" in by_t
    on_play = by_t["on_play"]["ops"]
    assert on_play[0]["op"] == "deny_attack"
    assert on_play[0].get("cost_lte") == 9
    assert on_play[0].get("duration") == "until_opp_turn_end"
    assert on_play[1]["op"] == "draw"
    assert on_play[1].get("require_opp_char_cost_0_or_gte") == 8
    on_ko = by_t["on_ko"]["ops"]
    assert on_ko[0].get("op") == "trash_hand" and on_ko[0].get("as_cost")
    assert on_ko[1].get("op") == "play_from_hand"
    assert on_ko[1].get("self_card") is True
    assert on_ko[1].get("from_zone") == "trash"


def test_op14_120_deny_survives_own_end_clears_on_opp_end():
    st = _state()
    foe_ch = CardInst(iid="f1", card_id="OP01-016", summoning_sick=False)
    st.players[1].characters = [foe_ch]
    apply_ops(
        st,
        0,
        [
            {
                "op": "deny_attack",
                "target_iid": "f1",
                "duration": "until_opp_turn_end",
            }
        ],
        _catalog,
    )
    assert _character_denied_attack(st.players[1], "f1")
    # End of granter's turn: restriction must remain.
    st.turn_seat = 0
    _clear_turn_duration_effects(st)
    assert _character_denied_attack(st.players[1], "f1")
    # End of restricted player's turn: restriction clears.
    st.turn_seat = 1
    _clear_turn_duration_effects(st)
    assert not _character_denied_attack(st.players[1], "f1")


def test_op14_120_conditional_draw():
    st = _state()
    hand0 = len(st.players[0].hand)
    # No qualifying opponent Character → no draw.
    apply_ops(
        st,
        0,
        [{"op": "draw", "count": 1, "require_opp_char_cost_0_or_gte": 8}],
        _catalog,
    )
    assert len(st.players[0].hand) == hand0
    # Cost 8+ opponent Character → draw.
    st.players[1].characters = [CardInst(iid="big", card_id="OP14-120")]
    apply_ops(
        st,
        0,
        [{"op": "draw", "count": 1, "require_opp_char_cost_0_or_gte": 8}],
        _catalog,
    )
    assert len(st.players[0].hand) == hand0 + 1


def test_op14_120_on_ko_plays_self_from_trash():
    reload_effect_library(force=True)
    st = _state()
    st.players[0].hand = ["FILLER"]
    st.players[0].trash = ["OP14-120"]
    pending = resolve_ability(
        st,
        0,
        "OP14-120",
        "gone",
        rule_timings.ON_KO,
        _catalog("OP14-120"),
        None,
        allow_llm=False,
        catalog=_catalog,
    )
    assert pending and pending.ops
    apply_ops(st, 0, pending.ops, _catalog)
    assert st.pending_choice is not None
    pick = st.pending_choice.options[0]
    r = apply_action(st, 0, {"type": "select_choice", "target_iid": pick}, _catalog)
    assert r["ok"]
    # Optional trash cost confirmed; then this Character is played from trash.
    assert "FILLER" in st.players[0].trash
    assert any(c.card_id == "OP14-120" for c in st.players[0].characters)
    assert "OP14-120" not in st.players[0].trash
    assert len(st.players[0].hand) == 0


def test_op14_120_on_ko_decline_cost_skips_revive():
    reload_effect_library(force=True)
    st = _state()
    st.players[0].hand = ["A", "B"]
    st.players[0].trash = ["OP14-120"]
    pending = resolve_ability(
        st,
        0,
        "OP14-120",
        "gone",
        rule_timings.ON_KO,
        _catalog("OP14-120"),
        None,
        allow_llm=False,
        catalog=_catalog,
    )
    apply_ops(st, 0, pending.ops, _catalog)
    assert st.pending_choice is not None
    r = apply_action(st, 0, {"type": "skip_choice"}, _catalog)
    assert r["ok"]
    assert st.players[0].trash == ["OP14-120"]
    assert st.players[0].characters == []
    assert st.players[0].hand == ["A", "B"]
