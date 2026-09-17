"""EB05-047 Ripley: static +12 cost; On Play may trash 1 to play a cost≤2 Character from trash."""

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
from battle.engine import apply_action, effective_character_cost  # noqa: E402
from battle.state import MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    if cid == "C2":
        return {"card_id": cid, "card_type": "CHARACTER", "cost": 2, "power": 2000, "name": "Small"}
    if cid == "C3":
        return {"card_id": cid, "card_type": "CHARACTER", "cost": 3, "power": 3000, "name": "Mid"}
    if cid == "FILL":
        return {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "Fill"}
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return row
    return {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000, "traits": []}


def _state(*, hand: list[str], trash: list[str]) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="ST02-001",
        deck=["X"] * 20,
        hand=list(hand),
        life=["L"] * 5,
        trash=list(trash),
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


def test_eb05_047_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-047")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "EB05-047 abilities dropped on normalize"
    by_t = {a["timing"]: a for a in abs_}
    assert "your_turn" in by_t and "opponent_turn" in by_t and "on_play" in by_t
    for timing in ("your_turn", "opponent_turn"):
        op = by_t[timing]["ops"][0]
        assert op.get("op") == "grant_cost"
        assert op.get("amount") == 12
        assert op.get("target_kind") == "self"
    on_play = next(a for a in get_abilities("EB05-047", "on_play"))
    assert on_play["ops"][0].get("op") == "trash_hand"
    assert on_play["ops"][0].get("optional") is True
    assert on_play["ops"][0].get("as_cost") is True
    play = on_play["ops"][1]
    assert play.get("op") == "play_from_hand"
    assert play.get("from_zone") == "trash"
    assert play.get("cost_lte") == 2
    assert play.get("card_type") == "character"
    assert play.get("optional") is True


def test_eb05_047_static_plus_12_cost():
    reload_effect_library(force=True)
    st = _state(hand=["EB05-047", "FILL"], trash=[])
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    # Optional On Play: skip the trash cost so we only check the static +12.
    if st.pending_choice is not None:
        assert apply_action(st, 0, {"type": "skip_choice"}, catalog)["ok"]
    ripple = next(c for c in st.players[0].characters if c.card_id == "EB05-047")
    assert effective_character_cost(st, 0, ripple, catalog) == 16
    st.turn_seat = 1
    assert effective_character_cost(st, 0, ripple, catalog) == 16


def test_eb05_047_on_play_trash_then_play_cost_2_from_trash():
    reload_effect_library(force=True)
    st = _state(hand=["EB05-047", "FILL"], trash=["C2", "C3"])
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert any(c.card_id == "EB05-047" for c in st.players[0].characters)
    ch = st.pending_choice
    assert ch is not None
    filler = next((o for o in (ch.options or []) if "FILL" in str(o)), None)
    assert filler
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": filler}, catalog)["ok"]
    assert "FILL" in st.players[0].trash
    ch = st.pending_choice
    assert ch is not None
    opts = ch.options or []
    assert any(str(o).endswith(":C2") or o == "C2" for o in opts)
    assert not any(str(o).endswith(":C3") or o == "C3" for o in opts)
    pick = next(o for o in opts if str(o).endswith(":C2") or o == "C2")
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick}, catalog)["ok"]
    assert any(c.card_id == "C2" for c in st.players[0].characters)
    assert "C2" not in st.players[0].trash
    assert "C3" in st.players[0].trash
    assert st.pending_choice is None


def test_eb05_047_skip_trash_skips_play_from_trash():
    reload_effect_library(force=True)
    st = _state(hand=["EB05-047", "FILL"], trash=["C2"])
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert st.pending_choice is not None
    assert apply_action(st, 0, {"type": "skip_choice"}, catalog)["ok"]
    assert not any(c.card_id == "C2" for c in st.players[0].characters)
    assert "C2" in st.players[0].trash
    assert "FILL" in st.players[0].hand


if __name__ == "__main__":
    test_eb05_047_override_shape()
    test_eb05_047_static_plus_12_cost()
    test_eb05_047_on_play_trash_then_play_cost_2_from_trash()
    test_eb05_047_skip_trash_skips_play_from_trash()
    print("OK")
