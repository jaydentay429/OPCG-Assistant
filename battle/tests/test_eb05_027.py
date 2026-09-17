"""EB05-027 Hibari: On Play draw 3, trash 2; then up to 1 Character cost≤2 to owner's deck bottom."""

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
        "C2": {"card_id": cid, "card_type": "CHARACTER", "cost": 2, "power": 2000, "name": "Low"},
        "C3": {"card_id": cid, "card_type": "CHARACTER", "cost": 3, "power": 3000, "name": "Mid"},
        "H1": {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "Hand1"},
        "H2": {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000, "name": "Hand2"},
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
        leader_card_id="ST03-001",
        deck=["D0", "D1", "D2", "D3", "D4"] + ["X"] * 15,
        hand=["EB05-027", "H1", "H2"],
        life=["L"] * 5,
        don_active=5,
        don_given=5,
        turns_completed=1,
        characters=[CardInst(iid="own2", card_id="C2", rested=False, summoning_sick=False)],
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
            CardInst(iid="opp2", card_id="C2", rested=False, summoning_sick=False),
            CardInst(iid="opp3", card_id="C3", rested=False, summoning_sick=False),
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


def _pick_hand(st: MatchState) -> str:
    ch = st.pending_choice
    assert ch is not None
    opts = ch.options or []
    assert opts
    return opts[0]


def test_eb05_027_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-027")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "EB05-027 abilities dropped on normalize"
    on_play = next(a for a in get_abilities("EB05-027", "on_play"))
    ops = on_play["ops"]
    assert ops[0].get("op") == "draw" and ops[0].get("count") == 3
    assert ops[1].get("op") == "trash_hand"
    assert ops[1].get("count") == 2
    assert ops[1].get("optional") is False
    assert ops[1].get("owner") == "self"
    bot = ops[2]
    assert bot.get("op") == "return_to_bottom"
    assert bot.get("optional") is True
    assert bot.get("target_kind") == "any_character"
    assert bot.get("cost_lte") == 2


def test_eb05_027_on_play_draw_trash_then_bottom_opp_cost_2():
    reload_effect_library(force=True)
    st = _state()
    p0, p1 = st.players
    opp_deck_before = list(p1.deck)
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert any(c.card_id == "EB05-027" for c in p0.characters)
    # Draw 3 then mandatory trash 2.
    assert st.pending_choice is not None
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": _pick_hand(st)}, catalog)["ok"]
    assert st.pending_choice is not None
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": _pick_hand(st)}, catalog)["ok"]
    assert len(p0.hand) == 3
    assert len(p0.trash) == 2
    ch = st.pending_choice
    assert ch is not None
    opts = ch.options or []
    assert "own2" in opts
    assert "opp2" in opts
    assert "opp3" not in opts
    hibari = next(c for c in p0.characters if c.card_id == "EB05-027")
    assert hibari.iid not in opts
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "opp2"}, catalog)["ok"]
    assert not any(c.iid == "opp2" for c in p1.characters)
    assert p1.deck[-1] == "C2"
    assert len(p1.deck) == len(opp_deck_before) + 1
    assert any(c.iid == "opp3" for c in p1.characters)
    assert any(c.iid == "own2" for c in p0.characters)


if __name__ == "__main__":
    test_eb05_027_override_shape()
    test_eb05_027_on_play_draw_trash_then_bottom_opp_cost_2()
    print("OK")
