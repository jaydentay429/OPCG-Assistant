"""EB05-022 Octopako: [On K.O.] Draw 2 cards."""

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
from battle.effects import apply_ops  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return row
    return {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000, "traits": []}


def _state() -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP01-060",
        deck=["A", "B", "C", "D", "E"],
        hand=["H1"],
        life=["L"] * 5,
        don_active=2,
        don_given=2,
        turns_completed=1,
        characters=[CardInst(iid="octo", card_id="EB05-022", rested=False, summoning_sick=False)],
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
        turn_seat=1,
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
        rng_seed=1,
    )


def test_eb05_022_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-022")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "EB05-022 abilities dropped on normalize"
    ab = next(a for a in get_abilities("EB05-022", "on_ko"))
    assert ab["ops"][0].get("op") == "draw"
    assert ab["ops"][0].get("count") == 2


def test_eb05_022_on_ko_draws_two():
    reload_effect_library(force=True)
    st = _state()
    apply_ops(
        st,
        1,
        [{"op": "ko", "target_kind": "opponent_character", "target_iid": "octo", "optional": False}],
        catalog,
    )
    assert not any(c.iid == "octo" for c in st.players[0].characters)
    assert "EB05-022" in st.players[0].trash
    assert st.players[0].hand == ["H1", "A", "B"]
    assert st.players[0].deck[:3] == ["C", "D", "E"]


if __name__ == "__main__":
    test_eb05_022_override_shape()
    test_eb05_022_on_ko_draws_two()
    print("OK")
