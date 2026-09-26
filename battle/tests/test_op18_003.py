"""OP18-003 Sea Cat: vanilla 5c 6000 / Counter +2000, no runnable abilities."""

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

from battle.effect_library import get_card_entry, reload_effect_library  # noqa: E402
from battle.engine import apply_action  # noqa: E402
from battle.state import MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return dict(row)
    return {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def test_op18_003_catalog_and_empty_abilities():
    reload_effect_library(force=True)
    info = catalog("OP18-003")
    assert info.get("cost") == 5
    assert info.get("power") == 6000
    assert int(info.get("counter") or 0) == 2000
    entry = get_card_entry("OP18-003")
    ops_abs = [a for a in (entry.get("abilities") or []) if a.get("ops")]
    assert ops_abs == []


def test_op18_003_plays_as_character():
    reload_effect_library(force=True)
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["X"] * 20,
        hand=["OP18-003"],
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
        deck=["Y"] * 20,
        hand=[],
        life=["M"] * 5,
    )
    st = MatchState(
        room_code="T",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
        rng_seed=1,
    )
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert any(c.card_id == "OP18-003" for c in st.players[0].characters)
    assert st.players[0].don_active == 0
