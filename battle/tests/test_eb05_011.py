"""EB05-011 Otohime: If Leader Shirahoshi, may flip Life top face-down: rest opp cost≤5."""

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
from battle.engine import apply_action  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return row
    return {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000, "traits": []}


def _state(*, leader: str, hand: list[str]) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=leader,
        deck=["D"] * 20,
        hand=list(hand),
        life=["L"] * 5,
        life_face=[True] * 5,
        don_active=3,
        don_given=3,
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
        characters=[
            CardInst(iid="low", card_id="OP05-006", rested=False, summoning_sick=False),
            CardInst(iid="mid", card_id="OP01-016", rested=False, summoning_sick=False),
            CardInst(iid="high", card_id="OP02-004", rested=False, summoning_sick=False),
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


def test_eb05_011_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-011")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "EB05-011 abilities dropped on normalize"
    ab = next(a for a in get_abilities("EB05-011", "on_play"))
    assert "白星" in str(ab.get("require_leader_name") or "") or "Shirahoshi" in str(
        ab.get("require_leader_name") or ""
    )
    flip = ab["ops"][0]
    assert flip.get("op") == "flip_life"
    assert flip.get("face") == "down"
    assert flip.get("position") == "top"
    assert flip.get("as_cost") is True
    assert flip.get("optional") is True
    rest = ab["ops"][1]
    assert rest.get("op") == "rest_opponent_character"
    assert rest.get("optional") is True
    assert rest.get("cost_lte") == 5


def test_eb05_011_on_play_flips_life_and_rests_cost_lte_5():
    reload_effect_library(force=True)
    st = _state(leader="OP11-022", hand=["EB05-011"])
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert any(c.card_id == "EB05-011" for c in st.players[0].characters)
    assert st.pending_choice is not None
    assert "life:top" in (st.pending_choice.options or [])
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "life:top"}, catalog)["ok"]
    assert st.players[0].life_face[0] is False
    assert st.pending_choice is not None
    opts = st.pending_choice.options or []
    assert "low" in opts
    assert "mid" in opts
    assert "high" not in opts
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "low"}, catalog)["ok"]
    low = next(c for c in st.players[1].characters if c.iid == "low")
    mid = next(c for c in st.players[1].characters if c.iid == "mid")
    high = next(c for c in st.players[1].characters if c.iid == "high")
    assert low.rested is True
    assert mid.rested is False
    assert high.rested is False


def test_eb05_011_wrong_leader_does_not_fire():
    reload_effect_library(force=True)
    st = _state(leader="OP14-020", hand=["EB05-011"])
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert any(c.card_id == "EB05-011" for c in st.players[0].characters)
    assert st.pending_choice is None
    assert st.players[0].life_face[0] is True
    assert all(not c.rested for c in st.players[1].characters)


def test_eb05_011_skip_flip_does_not_rest():
    reload_effect_library(force=True)
    st = _state(leader="OP11-022", hand=["EB05-011"])
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert apply_action(st, 0, {"type": "skip_choice"}, catalog)["ok"]
    assert st.pending_choice is None
    assert st.players[0].life_face[0] is True
    assert all(not c.rested for c in st.players[1].characters)


if __name__ == "__main__":
    test_eb05_011_override_shape()
    test_eb05_011_on_play_flips_life_and_rests_cost_lte_5()
    test_eb05_011_wrong_leader_does_not_fire()
    test_eb05_011_skip_flip_does_not_rest()
    print("OK")
