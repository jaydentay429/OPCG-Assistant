"""OP18-056 Mr.13 & Miss. Friday: DON!!×1 +1000; On Play bottom other own B・W → opponent discards 1."""

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
from battle.engine import _confirm_effect, apply_action, inst_power  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return dict(row)
    extras = {
        "BW": {
            "card_id": "BW",
            "card_type": "CHARACTER",
            "cost": 2,
            "power": 3000,
            "name": "Monday",
            "traits": ["B・W"],
            "traits_en": ["Baroque Works"],
        },
        "NOBW": {
            "card_id": "NOBW",
            "card_type": "CHARACTER",
            "cost": 2,
            "power": 3000,
            "name": "Nami",
            "traits": ["草帽一行人"],
        },
        "H1": {"card_id": "H1", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "Hand1"},
        "H2": {"card_id": "H2", "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "Hand2"},
    }
    return extras.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _state(*, extra_own: list[tuple[str, str]] | None = None, opp_hand: list[str] | None = None) -> MatchState:
    own = extra_own if extra_own is not None else [("bw", "BW"), ("oth", "NOBW")]
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP18-022",
        deck=["BOT"] * 20,
        hand=["OP18-056"],
        life=["L"] * 5,
        don_active=5,
        don_given=5,
        turns_completed=1,
        characters=[CardInst(iid=iid, card_id=cid, summoning_sick=False) for iid, cid in own],
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["Y"] * 20,
        hand=list(opp_hand if opp_hand is not None else ["H1", "H2"]),
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


def _finish_confirm(st: MatchState) -> None:
    if st.pending_effect is not None:
        _confirm_effect(st, 0, True, catalog)


def test_op18_056_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("OP18-056")
    abs_ = [a for a in (entry.get("abilities") or []) if a.get("ops")]
    assert abs_, "abilities dropped"
    on_play = next(a for a in get_abilities("OP18-056", "on_play"))
    ops = on_play["ops"]
    assert ops[0]["op"] == "return_to_bottom"
    assert ops[0].get("as_cost") is True
    assert ops[0].get("exclude_self") is True
    assert ops[0].get("target_kind") == "own_character"
    assert "B・W" in str(ops[0].get("trait_contains") or "")
    assert ops[1]["op"] == "trash_hand"
    assert ops[1].get("owner") == "opponent"
    don = [a for a in abs_ if a.get("require_don_attached_gte") == 1]
    assert {a["timing"] for a in don} >= {"your_turn", "opponent_turn"}
    assert all(o.get("op") == "buff_self" and o.get("amount") == 1000 for a in don for o in a["ops"])


def test_on_play_bottoms_other_bw_then_opp_discards():
    reload_effect_library(force=True)
    st = _state()
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _finish_confirm(st)
    ch = st.pending_choice
    assert ch is not None
    assert "bw" in ch.options
    assert "oth" not in ch.options
    self_iid = next(c.iid for c in st.players[0].characters if c.card_id == "OP18-056")
    assert self_iid not in ch.options
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "bw"}, catalog)["ok"]
    assert all(c.iid != "bw" for c in st.players[0].characters)
    assert st.players[0].deck[-1] == "BW"
    ch2 = st.pending_choice
    assert ch2 is not None
    assert ch2.seat == 1
    assert len(ch2.options) == 2
    pick = ch2.options[0]
    assert apply_action(st, 1, {"type": "select_choice", "target_iid": pick}, catalog)["ok"]
    assert len(st.players[1].hand) == 1
    assert len(st.players[1].trash) == 1


def test_on_play_skip_does_not_discard():
    reload_effect_library(force=True)
    st = _state()
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _finish_confirm(st)
    assert st.pending_choice is not None
    assert apply_action(st, 0, {"type": "skip_choice"}, catalog)["ok"]
    assert any(c.iid == "bw" for c in st.players[0].characters)
    assert st.players[1].hand == ["H1", "H2"]
    assert st.pending_choice is None


def test_on_play_no_other_bw_is_noop():
    reload_effect_library(force=True)
    st = _state(extra_own=[("oth", "NOBW")])
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    _finish_confirm(st)
    assert st.pending_choice is None
    assert st.players[1].hand == ["H1", "H2"]
    assert any(c.card_id == "OP18-056" for c in st.players[0].characters)


def test_don_x1_extra_power():
    reload_effect_library(force=True)
    st = _state(extra_own=[])
    st.players[0].hand = []
    st.players[0].characters = [CardInst(iid="m13", card_id="OP18-056", don_attached=1, summoning_sick=False)]
    # Printed 3000 + attached DON 1000 (own turn) + DON!!×1 ability 1000.
    assert inst_power(st, 0, "m13", catalog) == 5000
    st.turn_seat = 1
    # Opponent turn: attached DON does not count; DON!!×1 ability still applies.
    assert inst_power(st, 0, "m13", catalog) == 4000
