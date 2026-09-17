"""OP11-040 Luffy: turn-start look 5, add Straw Hat, then top or bottom in any order."""

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

from battle.effect_library import get_abilities, get_card_entry, reload_effect_library, resolve_ability  # noqa: E402
from battle.engine import _confirm_effect, _run_pending_effect, apply_action, legal_actions, public_view  # noqa: E402
from battle.state import MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    extras = {
        "SH1": {
            "card_id": "SH1",
            "card_type": "CHARACTER",
            "name": "Luffy",
            "traits": ["草帽一行人"],
            "traits_en": ["Straw Hat Crew"],
            "cost": 1,
            "power": 2000,
        },
        "NAVY": {
            "card_id": "NAVY",
            "card_type": "CHARACTER",
            "name": "Marine",
            "traits": ["海軍"],
            "cost": 1,
            "power": 1000,
        },
    }
    if cid in extras:
        return extras[cid]
    if cid.startswith("X"):
        return extras["NAVY"] | {"card_id": cid, "name": cid}
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
        leader_card_id="OP11-040",
        deck=["SH1", "X1", "X2", "X3", "X4"] + ["Z"] * 15,
        hand=[],
        life=["L"] * 3,
        don_active=8,
        don_given=10,
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


def _start_search(st: MatchState) -> None:
    pending = resolve_ability(
        st, 0, "OP11-040", "leader", "turn_start", catalog("OP11-040"), None, allow_llm=False, catalog=catalog
    )
    assert pending is not None and pending.ops
    _run_pending_effect(st, pending, catalog)
    if st.pending_effect is not None:
        _confirm_effect(st, 0, True, catalog)


def test_op11_040_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("OP11-040")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "OP11-040 abilities dropped on normalize"
    on_start = next(a for a in get_abilities("OP11-040", "turn_start"))
    assert on_start.get("optional") is True
    assert on_start.get("require_don_field_gte") == 8
    op = on_start["ops"][0]
    assert op.get("op") == "search_deck"
    assert op.get("top_n") == 5
    assert op.get("max_add") == 1
    assert op.get("to_top_or_bottom") is True
    trait = str(op.get("trait_contains") or "")
    assert "Straw Hat" in trait or "草帽" in trait


def test_op11_040_pick_then_choose_dest_then_order_top():
    reload_effect_library(force=True)
    st = _state()
    rest = list(st.players[0].deck[5:])
    _start_search(st)
    ps = st.pending_search
    assert ps is not None
    assert ps.phase == "pick"
    assert 0 in ps.eligible
    assert apply_action(st, 0, {"type": "select_search", "index": 0}, catalog)["ok"]
    assert "SH1" in st.players[0].hand
    ps = st.pending_search
    assert ps is not None
    assert ps.phase == "choose_dest"
    assert set(ps.revealed) == {"X1", "X2", "X3", "X4"}
    view = public_view(st, 0, catalog)
    assert view["pending_search"]["phase"] == "choose_dest"
    assert view["pending_search"]["to_top_or_bottom"] is True
    kinds = {(a.get("type"), a.get("target_iid")) for a in legal_actions(st, 0, catalog)}
    assert ("select_choice", "deck:top") in kinds
    assert ("select_choice", "deck:bottom") in kinds
    assert not any(a.get("type") == "select_search" for a in legal_actions(st, 0, catalog))
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "deck:top"}, catalog)["ok"]
    ps = st.pending_search
    assert ps is not None
    assert ps.phase == "order"
    assert ps.order_dest == "top"
    leftovers = list(ps.revealed)
    for _ in leftovers:
        assert apply_action(st, 0, {"type": "order_search_bottom", "index": 0}, catalog)["ok"]
    assert st.pending_search is None
    assert st.players[0].deck[:4] == leftovers
    assert st.players[0].deck[4:] == rest


def test_op11_040_skip_add_still_asks_dest():
    reload_effect_library(force=True)
    st = _state()
    _start_search(st)
    assert apply_action(st, 0, {"type": "skip_search"}, catalog)["ok"]
    ps = st.pending_search
    assert ps is not None
    assert ps.phase == "choose_dest"
    assert "SH1" not in st.players[0].hand
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "deck:bottom"}, catalog)["ok"]
    assert st.pending_search is not None
    assert st.pending_search.phase == "order"
    assert st.pending_search.order_dest == "bottom"


if __name__ == "__main__":
    test_op11_040_override_shape()
    test_op11_040_pick_then_choose_dest_then_order_top()
    test_op11_040_skip_add_still_asks_dest()
    print("OK")
