"""EB05-035 Speed: On Play DON!!−1 look 5 add ≤2 SMILE, then play ≤2 SMILE power≤5000."""

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
        leader_card_id="OP01-091",
        deck=list(deck),
        hand=list(hand),
        life=["L"] * 5,
        don_active=8,
        don_given=8,
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


def test_eb05_035_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-035")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "EB05-035 abilities dropped on normalize"
    ab = next(a for a in get_abilities("EB05-035", "on_play"))
    ops = ab["ops"]
    assert ops[0].get("op") == "return_don"
    assert ops[0].get("count") == 1
    assert ops[0].get("as_cost") is True
    assert ops[1].get("op") == "search_deck"
    assert ops[1].get("top_n") == 5
    assert ops[1].get("max_add") == 2
    assert ops[1].get("order_bottom") is True
    assert ops[1].get("destination") == "hand"
    assert "SMILE" in str(ops[1].get("trait_contains") or "")
    assert ops[2].get("op") == "play_from_hand"
    assert ops[2].get("count") == 2
    assert ops[2].get("power_lte") == 5000
    assert "SMILE" in str(ops[2].get("trait_contains") or "")


def test_eb05_035_on_play_search_then_play_smile():
    reload_effect_library(force=True)
    st = _state(
        hand=["EB05-035", "ST04-009"],
        deck=["OP01-105", "OP01-016", "OP08-083", "OP02-098", "X", "Y"],
    )
    p0 = st.players[0]
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert any(c.card_id == "EB05-035" for c in p0.characters)
    # Optional DON!!−1 on-play confirm
    assert apply_action(st, 0, {"type": "confirm_effect", "accept": True}, catalog)["ok"]
    assert st.pending_choice is not None
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "don:active"}, catalog)["ok"]
    assert st.pending_search is not None
    assert set(st.pending_search.eligible) == {0, 2}
    assert apply_action(st, 0, {"type": "select_search", "index": 0}, catalog)["ok"]
    assert apply_action(st, 0, {"type": "select_search", "index": 2}, catalog)["ok"]
    assert apply_action(st, 0, {"type": "confirm_search"}, catalog)["ok"]
    while st.pending_search is not None and st.pending_search.phase == "order":
        acts = [a for a in legal_actions(st, 0, catalog) if a.get("type") == "order_search_bottom"]
        assert acts
        assert apply_action(st, 0, acts[0], catalog)["ok"]
    assert "OP01-105" in p0.hand
    assert "OP08-083" in p0.hand
    assert "OP01-016" not in p0.hand
    assert "OP01-016" in p0.deck
    # Play two SMILE ≤5000 from hand
    for _ in range(2):
        assert st.pending_choice is not None
        opts = st.pending_choice.options or []
        pick = next(
            o
            for o in opts
            if any(cid in str(o) for cid in ("OP01-105", "OP08-083", "ST04-009"))
        )
        assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick}, catalog)["ok"]
    field = {c.card_id for c in p0.characters}
    assert "EB05-035" in field
    assert "OP01-105" in field
    assert "ST04-009" in field or "OP08-083" in field


if __name__ == "__main__":
    test_eb05_035_override_shape()
    test_eb05_035_on_play_search_then_play_smile()
    print("OK")
