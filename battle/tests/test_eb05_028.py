"""EB05-028 Boa Hancock: On Play if opp hand ≥9, opponent trashes 4 from their hand."""

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


def _state(*, opp_hand: list[str]) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP14-041",
        deck=["X"] * 20,
        hand=["EB05-028"],
        life=["L"] * 5,
        don_active=4,
        don_given=4,
        turns_completed=1,
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["Y"] * 20,
        hand=list(opp_hand),
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


def _pick_opp_hand(st: MatchState) -> str:
    ch = st.pending_choice
    assert ch is not None
    assert ch.seat == 1
    assert ch.controller_seat == 0
    opts = ch.options or []
    assert opts
    return opts[0]


def test_eb05_028_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-028")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "EB05-028 abilities dropped on normalize"
    on_play = next(a for a in get_abilities("EB05-028", "on_play"))
    op = on_play["ops"][0]
    assert op.get("op") == "trash_hand"
    assert op.get("count") == 4
    assert op.get("optional") is False
    assert op.get("owner") == "opponent"
    assert op.get("require_opp_hand_gte") == 9


def test_eb05_028_on_play_opp_trashes_4_when_hand_9():
    reload_effect_library(force=True)
    opp_ids = [f"H{i}" for i in range(9)]
    st = _state(opp_hand=opp_ids)
    p0, p1 = st.players
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert any(c.card_id == "EB05-028" for c in p0.characters)
    for _ in range(4):
        assert st.pending_choice is not None
        pick = _pick_opp_hand(st)
        assert apply_action(st, 1, {"type": "select_choice", "target_iid": pick}, catalog)["ok"]
    assert st.pending_choice is None
    assert len(p1.hand) == 5
    assert len(p1.trash) == 4
    assert set(p1.trash).isdisjoint(p1.hand)


def test_eb05_028_on_play_skips_when_opp_hand_8():
    reload_effect_library(force=True)
    st = _state(opp_hand=[f"H{i}" for i in range(8)])
    p0, p1 = st.players
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert any(c.card_id == "EB05-028" for c in p0.characters)
    assert st.pending_choice is None
    assert len(p1.hand) == 8
    assert p1.trash == []


if __name__ == "__main__":
    test_eb05_028_override_shape()
    test_eb05_028_on_play_opp_trashes_4_when_hand_9()
    test_eb05_028_on_play_skips_when_opp_hand_8()
    print("OK")
