"""OP16-001 Ace: Activate Main grants Rush; parallel OP16-001-P2 must resolve the same."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import (  # noqa: E402
    get_card_entry,
    reload_effect_library,
    resolve_activate_spec,
)
from battle.engine import apply_action, legal_actions  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid)
    if row:
        return dict(row)
    return {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _state(leader_id: str) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=leader_id,
        deck=["X"] * 30,
        hand=[],
        life=["L"] * 5,
        don_active=10,
        don_given=10,
        characters=[
            CardInst(iid="wb", card_id="OP16-003", summoning_sick=True),
        ],
        turns_completed=1,
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="P2",
        is_ai=False,
        leader_card_id="OP01-001",
        deck=["Y"] * 30,
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


def _rush_op(cid: str) -> dict:
    entry = get_card_entry(cid)
    ab = next(a for a in entry["abilities"] if a.get("timing") == "activate_main")
    op = ab["ops"][0]
    assert op.get("op") == "grant_keyword"
    assert op.get("keyword") == "rush"
    assert op.get("power_gte") == 8000
    assert op.get("name_or_trait") is True
    return op


def test_op16_001_and_p2_have_activate_rush():
    reload_effect_library(force=True)
    for cid in ("OP16-001", "OP16-001-P1", "OP16-001-P2"):
        spec = resolve_activate_spec(cid, catalog(cid))
        assert spec, f"{cid} activate_main must resolve"
        _rush_op(cid)


def test_op16_001_p2_grants_rush_to_8cost_whitebeard():
    """Live bug: Ace P2 leader could not Activate Main after playing 8c Whitebeard."""
    reload_effect_library(force=True)
    st = _state("OP16-001-P2")
    acts = legal_actions(st, 0, catalog)
    assert any(a.get("type") == "activate_main" and a.get("source_iid") == "leader" for a in acts)
    r = apply_action(st, 0, {"type": "activate_main", "source_iid": "leader"}, catalog)
    assert r["ok"]
    assert st.pending_choice is not None
    assert "wb" in (st.pending_choice.options or [])
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "wb"}, catalog)["ok"]
    kw = st.players[0].characters[0].turn_keywords or []
    assert "rush" in kw
    assert st.players[0].leader_once_used is True


def test_missing_parallel_inherits_base_activate():
    reload_effect_library(force=True)
    spec = resolve_activate_spec(
        "OP16-001-P99",
        {"card_type": "LEADER", "effect": "【啟動主要】【每回合1次】"},
    )
    assert spec
    assert any(o.get("op") == "grant_keyword" and o.get("keyword") == "rush" for o in spec.get("ops") or [])


if __name__ == "__main__":
    test_op16_001_and_p2_have_activate_rush()
    test_op16_001_p2_grants_rush_to_8cost_whitebeard()
    test_missing_parallel_inherits_base_activate()
    print("OK")
