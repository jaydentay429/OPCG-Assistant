"""EB05-037 Black Maria: On Play look 3, add up to 1 Animal Kingdom Pirates, rest bottom."""

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
from battle.engine import apply_action, legal_actions  # noqa: E402
from battle.state import MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return row
    return {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000, "traits": []}


def _state(*, hand: list[str], deck: list[str]) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP14-060",
        deck=list(deck),
        hand=list(hand),
        life=["L"] * 5,
        don_active=1,
        don_given=1,
        turns_completed=1,
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
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


def _finish_bottom_order(st: MatchState) -> None:
    while st.pending_search is not None and st.pending_search.phase == "order":
        acts = [a for a in legal_actions(st, 0, catalog) if a.get("type") == "order_search_bottom"]
        assert acts
        assert apply_action(st, 0, acts[0], catalog)["ok"]


def test_eb05_037_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-037")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "EB05-037 abilities dropped on normalize"
    ab = next(a for a in get_abilities("EB05-037", "on_play"))
    op = ab["ops"][0]
    assert op.get("op") == "search_deck"
    assert op.get("top_n") == 3
    assert op.get("max_add") == 1
    trait = str(op.get("trait_contains") or "")
    assert "Animal Kingdom" in trait or "百獸海賊團" in trait
    assert op.get("destination") == "hand"
    assert op.get("order_bottom") is True


def test_eb05_037_on_play_search_animal_kingdom():
    reload_effect_library(force=True)
    # Top 3: Animal Kingdom, non-trait, Animal Kingdom — only trait cards eligible.
    st = _state(
        hand=["EB05-037"],
        deck=["OP04-052", "OP01-016", "OP04-051", "Y", "Z"],
    )
    p0 = st.players[0]
    deck_before = list(p0.deck)
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert any(c.card_id == "EB05-037" for c in p0.characters)
    assert st.pending_search is not None
    assert set(st.pending_search.eligible) == {0, 2}
    assert st.pending_search.reveal_adds is True
    assert apply_action(st, 0, {"type": "select_search", "index": 0}, catalog)["ok"]
    _finish_bottom_order(st)
    assert "OP04-052" in p0.hand
    assert "OP04-051" in p0.deck
    assert "OP01-016" in p0.deck
    assert p0.deck[-2:] == ["OP04-051", "OP01-016"] or set(p0.deck[-2:]) == {"OP04-051", "OP01-016"}
    assert len(p0.deck) == len(deck_before) - 1
    assert st.pending_search is None


def test_eb05_037_on_play_may_add_none():
    reload_effect_library(force=True)
    st = _state(
        hand=["EB05-037"],
        deck=["OP04-052", "OP01-016", "OP04-051", "Y"],
    )
    p0 = st.players[0]
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert st.pending_search is not None
    assert apply_action(st, 0, {"type": "skip_search"}, catalog)["ok"]
    _finish_bottom_order(st)
    assert "OP04-052" not in p0.hand
    assert "OP04-052" in p0.deck
    assert "OP04-051" in p0.deck
    assert "OP01-016" in p0.deck
    assert st.pending_search is None


if __name__ == "__main__":
    test_eb05_037_override_shape()
    test_eb05_037_on_play_search_animal_kingdom()
    test_eb05_037_on_play_may_add_none()
    print("OK")
