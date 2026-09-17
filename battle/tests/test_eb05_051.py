"""EB05-051 Ahiru: On Play rest opp cost≤total Life; Trigger play this card."""

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
from battle.engine import _resolve_trigger, apply_action  # noqa: E402
from battle.state import CardInst, MatchState, PendingTrigger, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return row
    return {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000, "traits": []}


def _state(*, hand: list[str], life_n: int = 2, phase: str = "main") -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP03-099",
        deck=["D"] * 20,
        hand=list(hand),
        life=["L"] * life_n,
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
        deck=["B"] * 20,
        hand=[],
        life=["M"] * life_n,
        characters=[
            CardInst(iid="low", card_id="OP08-067", rested=False, summoning_sick=False),
            CardInst(iid="mid", card_id="OP01-016", rested=False, summoning_sick=False),
            CardInst(iid="high", card_id="OP02-004", rested=False, summoning_sick=False),
        ],
    )
    return MatchState(
        room_code="T",
        status="playing",
        phase=phase,
        turn_seat=0 if phase == "main" else 1,
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
        rng_seed=1,
    )


def test_eb05_051_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-051")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert len(abs_) >= 2, "EB05-051 abilities dropped on normalize"
    on_play = next(a for a in get_abilities("EB05-051", "on_play"))
    op = on_play["ops"][0]
    assert op.get("op") == "rest_opponent_character"
    assert op.get("optional") is True
    assert op.get("cost_lte_total_life") is True
    trig = next(a for a in get_abilities("EB05-051", "trigger"))
    assert trig["ops"][0].get("op") == "play_from_hand"
    assert trig["ops"][0].get("self_card") is True


def test_eb05_051_on_play_rests_cost_lte_total_life():
    reload_effect_library(force=True)
    # 2+2 Life → threshold 4; cost 3 / 1 eligible, cost 9 not (engine auto-picks if only 1 option).
    st = _state(hand=["EB05-051"], life_n=2)
    p1 = st.players[1]
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert any(c.card_id == "EB05-051" for c in st.players[0].characters)
    assert st.pending_choice is not None
    opts = st.pending_choice.options or []
    assert "low" in opts
    assert "mid" in opts
    assert "high" not in opts
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "low"}, catalog)["ok"]
    low = next(c for c in p1.characters if c.iid == "low")
    mid = next(c for c in p1.characters if c.iid == "mid")
    high = next(c for c in p1.characters if c.iid == "high")
    assert low.rested is True
    assert mid.rested is False
    assert high.rested is False


def test_eb05_051_trigger_plays_this_card():
    reload_effect_library(force=True)
    trig = next(a for a in get_abilities("EB05-051", "trigger"))
    st = _state(hand=["EB05-051", "OP01-016"], life_n=5, phase="trigger")
    st.pending_trigger = PendingTrigger(
        seat=0,
        card_id="EB05-051",
        ops=list(trig["ops"]),
        remaining_hits=0,
        summary=str(trig.get("summary") or "trigger"),
    )
    assert _resolve_trigger(st, 0, True, catalog)["ok"]
    field = {c.card_id for c in st.players[0].characters}
    assert "EB05-051" in field
    assert "OP01-016" in st.players[0].hand
    assert "EB05-051" not in st.players[0].hand


if __name__ == "__main__":
    test_eb05_051_override_shape()
    test_eb05_051_on_play_rests_cost_lte_total_life()
    test_eb05_051_trigger_plays_this_card()
    print("OK")
