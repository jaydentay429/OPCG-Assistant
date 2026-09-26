"""OP18-086 Goldberg: static +12 cost; On K.O. KO up to 1 opponent Character cost≤4."""

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

from battle.effect_library import get_abilities, get_card_entry, reload_effect_library  # noqa: E402
from battle.engine import apply_action, apply_battle_character_ko, effective_character_cost  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return dict(row)
    extras = {
        "C4": {
            "card_id": "C4",
            "card_type": "CHARACTER",
            "cost": 4,
            "power": 5000,
            "name": "Four",
            "colors": ["黑"],
            "colors_en": ["Black"],
        },
        "C5": {
            "card_id": "C5",
            "card_type": "CHARACTER",
            "cost": 5,
            "power": 6000,
            "name": "Five",
            "colors": ["黑"],
            "colors_en": ["Black"],
        },
    }
    return extras.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _state() -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP09-061",
        deck=["X"] * 20,
        hand=["OP18-086"],
        life=["L"] * 5,
        don_active=10,
        don_given=10,
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
            CardInst(iid="oc4", card_id="C4", summoning_sick=False),
            CardInst(iid="oc5", card_id="C5", summoning_sick=False),
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
        rng_seed=1,
    )


def test_op18_086_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("OP18-086")
    abs_ = [a for a in (entry.get("abilities") or []) if a.get("ops")]
    assert abs_, "abilities dropped"
    by_t = {}
    for a in abs_:
        by_t.setdefault(a["timing"], a)
    for timing in ("your_turn", "opponent_turn"):
        op = by_t[timing]["ops"][0]
        assert op.get("op") == "grant_cost"
        assert op.get("amount") == 12
        assert op.get("target_kind") == "self"
    ko = next(a for a in get_abilities("OP18-086", "on_ko"))
    op = ko["ops"][0]
    assert op["op"] == "ko"
    assert op.get("target_kind") == "opponent_character"
    assert op.get("cost_lte") == 4
    assert op.get("optional") is True


def test_static_plus_12_cost():
    reload_effect_library(force=True)
    st = _state()
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    gold = next(c for c in st.players[0].characters if c.card_id == "OP18-086")
    assert effective_character_cost(st, 0, gold, catalog) == 15
    st.turn_seat = 1
    assert effective_character_cost(st, 0, gold, catalog) == 15


def test_on_ko_can_ko_opp_cost4_not_cost5():
    reload_effect_library(force=True)
    st = _state()
    st.players[0].hand = []
    gold = CardInst(iid="gold", card_id="OP18-086", summoning_sick=False)
    st.players[0].characters = [gold]
    apply_battle_character_ko(st, 0, gold, catalog)
    assert "OP18-086" in st.players[0].trash
    ch = st.pending_choice
    assert ch is not None
    assert "oc4" in ch.options
    assert "oc5" not in ch.options
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "oc4"}, catalog)["ok"]
    assert all(c.iid != "oc4" for c in st.players[1].characters)
    assert "C4" in st.players[1].trash
    assert any(c.iid == "oc5" for c in st.players[1].characters)


def test_on_ko_skip_keeps_opp_board():
    reload_effect_library(force=True)
    st = _state()
    st.players[0].hand = []
    gold = CardInst(iid="gold", card_id="OP18-086", summoning_sick=False)
    st.players[0].characters = [gold]
    apply_battle_character_ko(st, 0, gold, catalog)
    assert st.pending_choice is not None
    assert apply_action(st, 0, {"type": "skip_choice"}, catalog)["ok"]
    assert {c.iid for c in st.players[1].characters} == {"oc4", "oc5"}
