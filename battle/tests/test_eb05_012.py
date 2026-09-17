"""EB05-012 Camie: On Play rest up to 1 opponent Character cost≤6."""

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
    extras = {
        "C4": {"card_id": cid, "card_type": "CHARACTER", "cost": 4, "power": 4000, "name": "Own"},
        "C5": {"card_id": cid, "card_type": "CHARACTER", "cost": 5, "power": 5000, "name": "Mid"},
        "C6": {"card_id": cid, "card_type": "CHARACTER", "cost": 6, "power": 6000, "name": "Edge"},
        "C7": {"card_id": cid, "card_type": "CHARACTER", "cost": 7, "power": 7000, "name": "High"},
    }
    if cid in extras:
        return extras[cid]
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return row
    return {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _state() -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="ST02-001",
        deck=["X"] * 20,
        hand=["EB05-012"],
        life=["L"] * 5,
        don_active=3,
        don_given=3,
        turns_completed=1,
        characters=[CardInst(iid="own4", card_id="C4", rested=False, summoning_sick=False)],
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
        characters=[
            CardInst(iid="opp5", card_id="C5", rested=False, summoning_sick=False),
            CardInst(iid="opp6", card_id="C6", rested=False, summoning_sick=False),
            CardInst(iid="opp7", card_id="C7", rested=False, summoning_sick=False),
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


def test_eb05_012_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-012")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "EB05-012 abilities dropped on normalize"
    on_play = next(a for a in get_abilities("EB05-012", "on_play"))
    op = on_play["ops"][0]
    assert op.get("op") == "rest_opponent_character"
    assert op.get("optional") is True
    assert op.get("cost_lte") == 6
    assert op.get("count") == 1


def test_eb05_012_on_play_rests_opp_cost_6_not_7_or_own():
    reload_effect_library(force=True)
    st = _state()
    p0, p1 = st.players
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert any(c.card_id == "EB05-012" for c in p0.characters)
    ch = st.pending_choice
    assert ch is not None
    opts = ch.options or []
    assert "opp5" in opts
    assert "opp6" in opts
    assert "opp7" not in opts
    assert "own4" not in opts
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "opp6"}, catalog)["ok"]
    assert next(c for c in p1.characters if c.iid == "opp6").rested
    assert not next(c for c in p1.characters if c.iid == "opp5").rested
    assert not next(c for c in p1.characters if c.iid == "opp7").rested
    assert not next(c for c in p0.characters if c.iid == "own4").rested


if __name__ == "__main__":
    test_eb05_012_override_shape()
    test_eb05_012_on_play_rests_opp_cost_6_not_7_or_own()
    print("OK")
