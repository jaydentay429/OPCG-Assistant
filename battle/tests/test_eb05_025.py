"""EB05-025 Domino: On Play look 3 Impel Down to hand; Trigger activates On Play."""

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
from battle.engine import _resolve_trigger, apply_action, legal_actions  # noqa: E402
from battle.state import MatchState, PendingTrigger, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return row
    return {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000, "traits": []}


def _state(*, hand: list[str], deck: list[str], phase: str = "main") -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP01-060",
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
        phase=phase,
        turn_seat=0 if phase == "main" else 1,
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
        rng_seed=1,
    )


def _finish_search_to_hand(st: MatchState, *, pick_index: int) -> None:
    assert st.pending_search is not None
    assert apply_action(st, 0, {"type": "select_search", "index": pick_index}, catalog)["ok"]
    if st.pending_search is not None and st.pending_search.phase == "pick":
        assert apply_action(st, 0, {"type": "confirm_search"}, catalog)["ok"]
    while st.pending_search is not None and st.pending_search.phase == "order":
        acts = [a for a in legal_actions(st, 0, catalog) if a.get("type") == "order_search_bottom"]
        assert acts
        assert apply_action(st, 0, acts[0], catalog)["ok"]


def test_eb05_025_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-025")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert len(abs_) >= 2, "EB05-025 abilities dropped on normalize"
    on_play = next(a for a in get_abilities("EB05-025", "on_play"))
    op = on_play["ops"][0]
    assert op.get("op") == "search_deck"
    assert op.get("top_n") == 3
    assert op.get("max_add") == 1
    assert op.get("order_bottom") is True
    assert op.get("destination") == "hand"
    assert "Impel Down" in str(op.get("trait_contains") or "") or "推進城" in str(
        op.get("trait_contains") or ""
    )
    trig = next(a for a in get_abilities("EB05-025", "trigger"))
    assert trig["ops"][0].get("op") == "activate_timing"
    assert trig["ops"][0].get("timing") == "on_play"


def test_eb05_025_on_play_look3_impel_down():
    reload_effect_library(force=True)
    # OP02-085 Magellan Impel Down; OP01-016 Straw Hat; OP02-086 Jailer Beast Impel Down
    st = _state(
        hand=["EB05-025"],
        deck=["OP02-085", "OP01-016", "OP02-098", "X", "Y"],
    )
    p0 = st.players[0]
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert any(c.card_id == "EB05-025" for c in p0.characters)
    assert st.pending_search is not None
    assert st.pending_search.eligible == [0]
    _finish_search_to_hand(st, pick_index=0)
    assert "OP02-085" in p0.hand
    assert "OP01-016" not in p0.hand
    assert "OP01-016" in p0.deck
    assert "OP02-098" in p0.deck


def test_eb05_025_trigger_activates_on_play():
    reload_effect_library(force=True)
    trig = next(a for a in get_abilities("EB05-025", "trigger"))
    st = _state(
        hand=["EB05-025"],
        deck=["OP02-085", "OP01-016", "OP02-098", "X", "Y"],
        phase="trigger",
    )
    p0 = st.players[0]
    st.pending_trigger = PendingTrigger(
        seat=0,
        card_id="EB05-025",
        ops=list(trig["ops"]),
        remaining_hits=0,
        summary=str(trig.get("summary") or "trigger"),
    )
    assert _resolve_trigger(st, 0, True, catalog)["ok"]
    assert st.pending_search is not None
    assert st.pending_search.eligible == [0]
    _finish_search_to_hand(st, pick_index=0)
    assert "OP02-085" in p0.hand
    assert "OP01-016" in p0.deck


if __name__ == "__main__":
    test_eb05_025_override_shape()
    test_eb05_025_on_play_look3_impel_down()
    test_eb05_025_trigger_activates_on_play()
    print("OK")
