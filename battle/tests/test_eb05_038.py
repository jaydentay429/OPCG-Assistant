"""EB05-038 Russian: On Play up to 1 own Senor Pink card +3000 this turn."""

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


def _state(*, field: list[tuple[str, str]] | None = None) -> MatchState:
    chars = [
        CardInst(iid=iid, card_id=cid, rested=False, summoning_sick=False)
        for iid, cid in (field or [])
    ]
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP14-060",
        deck=["D"] * 20,
        hand=["EB05-038"],
        life=["L"] * 5,
        don_active=3,
        don_given=3,
        turns_completed=1,
        characters=chars,
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
        characters=[CardInst(iid="opp_pink", card_id="OP14-065", rested=False, summoning_sick=False)],
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


def test_eb05_038_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-038")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "EB05-038 abilities dropped on normalize"
    ab = next(a for a in get_abilities("EB05-038", "on_play"))
    op = ab["ops"][0]
    assert op.get("op") == "buff"
    assert op.get("amount") == 3000
    assert op.get("optional") is True
    assert op.get("duration") == "turn"
    assert op.get("target_kind") == "own_character"
    assert "粉紅先生" in str(op.get("name_contains") or "") or "Senor" in str(op.get("name_contains") or "")
    assert "粉紅先生" in str(op.get("include_leader_if_name") or "") or "Senor" in str(
        op.get("include_leader_if_name") or ""
    )


def test_eb05_038_on_play_buffs_own_senor_pink_only():
    reload_effect_library(force=True)
    st = _state(field=[("pink", "OP14-065"), ("nami", "OP01-016")])
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert any(c.card_id == "EB05-038" for c in st.players[0].characters)
    assert st.pending_choice is not None
    opts = st.pending_choice.options or []
    assert "pink" in opts
    assert "nami" not in opts
    assert "leader" not in opts
    assert "opp_pink" not in opts
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "pink"}, catalog)["ok"]
    pink = next(c for c in st.players[0].characters if c.iid == "pink")
    nami = next(c for c in st.players[0].characters if c.iid == "nami")
    opp = next(c for c in st.players[1].characters if c.iid == "opp_pink")
    assert pink.power_mod == 3000
    assert nami.power_mod == 0
    assert opp.power_mod == 0


def test_eb05_038_no_pink_does_not_buff():
    reload_effect_library(force=True)
    st = _state(field=[("nami", "OP01-016")])
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert st.pending_choice is None
    nami = next(c for c in st.players[0].characters if c.iid == "nami")
    assert nami.power_mod == 0


if __name__ == "__main__":
    test_eb05_038_override_shape()
    test_eb05_038_on_play_buffs_own_senor_pink_only()
    test_eb05_038_no_pink_does_not_buff()
    print("OK")
