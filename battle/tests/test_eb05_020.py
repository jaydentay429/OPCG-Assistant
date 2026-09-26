"""EB05-020 I Am Shirahoshi!!: Main may rest Leader Shirahoshi, then draw 2."""

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
from battle.state import MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return row
    return {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _state(*, leader: str) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=leader,
        deck=["D0", "D1", "D2", "D3", "D4"] + ["X"] * 15,
        hand=["EB05-020"],
        life=["L"] * 5,
        don_active=1,
        don_given=1,
        turns_completed=1,
        leader_rested=False,
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


def test_eb05_020_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-020")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "EB05-020 abilities dropped on normalize"
    ab = next(a for a in get_abilities("EB05-020", "on_play"))
    assert "白星" in str(ab.get("require_leader_name") or "") or "Shirahoshi" in str(
        ab.get("require_leader_name") or ""
    )
    rest, draw = ab["ops"]
    assert rest.get("op") == "rest_character"
    assert rest.get("as_cost") is True
    assert rest.get("optional") is True
    assert rest.get("target_kind") == "leader"
    assert rest.get("include_leader") is True
    assert draw.get("op") == "draw" and draw.get("count") == 2


def test_eb05_020_rest_shirahoshi_draws_2():
    reload_effect_library(force=True)
    st = _state(leader="OP11-022")
    p0 = st.players[0]
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert "EB05-020" in p0.trash
    assert "EB05-020" not in p0.hand
    assert st.pending_choice is not None
    assert "leader" in (st.pending_choice.options or [])
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "leader"}, catalog)["ok"]
    assert p0.leader_rested is True
    assert st.pending_choice is None
    assert p0.hand == ["D0", "D1"]
    assert len(p0.deck) == 18


def test_eb05_020_skip_rest_does_not_draw():
    reload_effect_library(force=True)
    st = _state(leader="OP11-022")
    p0 = st.players[0]
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert st.pending_choice is not None
    assert apply_action(st, 0, {"type": "skip_choice"}, catalog)["ok"]
    assert p0.leader_rested is False
    assert p0.hand == []
    assert len(p0.deck) == 20
    assert "EB05-020" in p0.trash


def test_eb05_020_other_leader_does_not_draw():
    reload_effect_library(force=True)
    st = _state(leader="OP11-021")
    p0 = st.players[0]
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert st.pending_choice is None
    assert p0.leader_rested is False
    assert p0.hand == []
    assert "EB05-020" in p0.trash


if __name__ == "__main__":
    test_eb05_020_override_shape()
    test_eb05_020_rest_shirahoshi_draws_2()
    test_eb05_020_skip_rest_does_not_draw()
    test_eb05_020_other_leader_does_not_draw()
    print("OK")
