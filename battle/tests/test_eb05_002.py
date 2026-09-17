"""EB05-002 Doll: On Play look 5, add up to 2 Navy cost≥2, rest bottom; then trash 1 hand."""

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
        leader_card_id="OP02-001",
        deck=list(deck),
        hand=list(hand),
        life=["L"] * 5,
        don_active=5,
        don_given=5,
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


def test_eb05_002_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-002")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "EB05-002 abilities dropped on normalize"
    ab = next(a for a in get_abilities("EB05-002", "on_play"))
    ops = ab["ops"]
    assert ops[0].get("op") == "search_deck"
    assert ops[0].get("top_n") == 5
    assert ops[0].get("max_add") == 2
    assert ops[0].get("cost_gte") == 2
    assert "Navy" in str(ops[0].get("trait_contains") or "") or "海軍" in str(ops[0].get("trait_contains") or "")
    assert ops[0].get("destination") == "hand"
    assert ops[0].get("order_bottom") is True
    assert ops[1].get("op") == "trash_hand"
    assert ops[1].get("count") == 1
    assert ops[1].get("optional") is False
    assert ops[1].get("owner") == "self"


def test_eb05_002_on_play_search_navy_then_trash_hand():
    reload_effect_library(force=True)
    # Top 5: Navy 2c, Navy 1c, Navy 2c, non-Navy 4c, junk.
    st = _state(
        hand=["EB05-002", "OP01-016"],
        deck=["OP02-100", "OP02-097", "OP02-107", "OP01-016", "X", "Y"],
    )
    p0 = st.players[0]
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert any(c.card_id == "EB05-002" for c in p0.characters)
    assert st.pending_search is not None
    assert set(st.pending_search.eligible) == {0, 2}
    assert apply_action(st, 0, {"type": "select_search", "index": 0}, catalog)["ok"]
    assert apply_action(st, 0, {"type": "select_search", "index": 2}, catalog)["ok"]
    assert apply_action(st, 0, {"type": "confirm_search"}, catalog)["ok"]
    _finish_bottom_order(st)
    assert "OP02-100" in p0.hand
    assert "OP02-107" in p0.hand
    assert "OP02-097" not in p0.hand
    assert "OP02-097" in p0.deck
    assert st.pending_choice is not None
    opts = st.pending_choice.options or []
    filler = next((o for o in opts if "OP01-016" in str(o)), opts[0])
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": filler}, catalog)["ok"]
    assert st.pending_choice is None
    assert "OP01-016" in p0.trash or "OP02-100" in p0.trash or "OP02-107" in p0.trash
    assert len(p0.hand) == 2
    assert any(c.card_id == "EB05-002" for c in p0.characters)


if __name__ == "__main__":
    test_eb05_002_override_shape()
    test_eb05_002_on_play_search_navy_then_trash_hand()
    print("OK")
