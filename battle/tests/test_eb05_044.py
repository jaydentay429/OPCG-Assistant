"""EB05-044 Ms. Father's Day: On Play if Leader is Baroque Works and opp has cost 0, opp Leader −1000."""

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
from battle.engine import apply_action, inst_power, printed_power  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    extras = {
        "C0": {"card_id": cid, "card_type": "CHARACTER", "cost": 0, "power": 1000, "name": "Zero"},
        "C1": {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 2000, "name": "One"},
    }
    if cid in extras:
        return extras[cid]
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return row
    return {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _state(*, leader: str, opp_chars: list[CardInst], own_chars: list[CardInst] | None = None) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=leader,
        deck=["X"] * 20,
        hand=["EB05-044"],
        life=["L"] * 5,
        don_active=2,
        don_given=2,
        turns_completed=1,
        characters=list(own_chars or []),
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
        characters=list(opp_chars),
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


def test_eb05_044_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-044")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "EB05-044 abilities dropped on normalize"
    on_play = next(a for a in get_abilities("EB05-044", "on_play"))
    assert "Baroque" in str(on_play.get("require_leader_trait") or "") or "B・W" in str(
        on_play.get("require_leader_trait") or ""
    )
    assert on_play.get("require_opp_char_cost_eq") == 0
    op = on_play["ops"][0]
    assert op.get("op") == "buff"
    assert op.get("amount") == -1000
    assert op.get("target_kind") == "opponent_leader"
    assert op.get("duration") == "turn"
    assert op.get("optional") is False


def test_eb05_044_debuffs_opp_leader_when_gates_met():
    reload_effect_library(force=True)
    st = _state(
        leader="OP14-079",
        opp_chars=[CardInst(iid="z0", card_id="C0", rested=False, summoning_sick=False)],
    )
    before = inst_power(st, 1, "leader", catalog)
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert any(c.card_id == "EB05-044" for c in st.players[0].characters)
    assert inst_power(st, 1, "leader", catalog) == before - 1000
    assert inst_power(st, 0, "leader", catalog) == printed_power(catalog("OP14-079"))


def test_eb05_044_no_debuff_without_opp_cost_0():
    reload_effect_library(force=True)
    st = _state(
        leader="OP14-079",
        opp_chars=[CardInst(iid="o1", card_id="C1", rested=False, summoning_sick=False)],
        own_chars=[CardInst(iid="own0", card_id="C0", rested=False, summoning_sick=False)],
    )
    before = inst_power(st, 1, "leader", catalog)
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert inst_power(st, 1, "leader", catalog) == before


def test_eb05_044_no_debuff_without_baroque_leader():
    reload_effect_library(force=True)
    st = _state(
        leader="OP14-080",
        opp_chars=[CardInst(iid="z0", card_id="C0", rested=False, summoning_sick=False)],
    )
    before = inst_power(st, 1, "leader", catalog)
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, catalog)["ok"]
    assert inst_power(st, 1, "leader", catalog) == before


if __name__ == "__main__":
    test_eb05_044_override_shape()
    test_eb05_044_debuffs_opp_leader_when_gates_met()
    test_eb05_044_no_debuff_without_opp_cost_0()
    test_eb05_044_no_debuff_without_baroque_leader()
    print("OK")
