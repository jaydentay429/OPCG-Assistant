"""EB05-023 Osome: [On Play] may trash 2 Events from hand, draw 3."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_abilities, get_card_entry, reload_effect_library  # noqa: E402
from battle.engine import apply_action  # noqa: E402
from battle.state import MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return row
    extra = {
        "E1": {"card_id": "E1", "card_type": "EVENT", "name": "Event1", "cost": 1},
        "E2": {"card_id": "E2", "card_type": "EVENT", "name": "Event2", "cost": 2},
        "C1": {"card_id": "C1", "card_type": "CHARACTER", "name": "Char", "cost": 3, "power": 4000},
    }
    return extra.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _state(*, hand: list[str]) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="ST22-001",
        deck=["D"] * 20,
        hand=list(hand),
        life=["L"] * 5,
        don_active=2,
        don_given=2,
        turns_completed=1,
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-003",
        deck=["B"] * 20,
        hand=[],
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


def test_eb05_023_override_on_play():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-023")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "EB05-023 abilities dropped on normalize"
    on_play = next(a for a in get_abilities("EB05-023", "on_play"))
    assert on_play["ops"][0].get("op") == "trash_hand"
    assert on_play["ops"][0].get("count") == 2
    assert on_play["ops"][0].get("card_type") == "event"
    assert on_play["ops"][0].get("as_cost") is True
    assert on_play["ops"][1].get("op") == "draw"
    assert on_play["ops"][1].get("count") == 3


def test_eb05_023_trash_two_events_draws_three():
    reload_effect_library(force=True)
    st = _state(hand=["EB05-023", "E1", "E2", "C1"])
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert any(c.card_id == "EB05-023" for c in st.players[0].characters)
    assert st.pending_choice is not None
    opts = st.pending_choice.options or []
    assert any(o.endswith(":E1") for o in opts)
    assert any(o.endswith(":E2") for o in opts)
    assert not any(o.endswith(":C1") for o in opts)
    e1 = next(o for o in opts if o.endswith(":E1"))
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": e1}, catalog)["ok"]
    if st.pending_choice is not None:
        opts2 = st.pending_choice.options or []
        e2 = next(o for o in opts2 if o.endswith(":E2"))
        assert apply_action(st, 0, {"type": "select_choice", "target_iid": e2}, catalog)["ok"]
    assert st.pending_choice is None
    assert st.players[0].hand.count("E1") == 0
    assert st.players[0].hand.count("E2") == 0
    assert "C1" in st.players[0].hand
    assert len(st.players[0].hand) == 4
    assert st.players[0].trash.count("E1") == 1
    assert st.players[0].trash.count("E2") == 1


def test_eb05_023_skip_without_events():
    reload_effect_library(force=True)
    st = _state(hand=["EB05-023", "C1"])
    deck_before = len(st.players[0].deck)
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    if st.pending_choice is not None:
        assert apply_action(st, 0, {"type": "skip_choice"}, catalog)["ok"]
    assert st.pending_choice is None
    assert len(st.players[0].deck) == deck_before
    assert "C1" in st.players[0].hand
