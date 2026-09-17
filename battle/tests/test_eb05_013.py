"""EB05-013 Shirley: [On Opp Attack] once, may rest 1 DON!!: Fish-Man/Merfolk Leader +2000 battle."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_abilities, get_card_entry, reload_effect_library, resolve_ability  # noqa: E402
from battle.engine import _confirm_effect, _run_pending_effect, apply_action, inst_power  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return row
    return {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _state(*, leader: str = "OP06-020", don_active: int = 2) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id=leader,
        deck=["D"] * 20,
        hand=[],
        life=["L"] * 5,
        don_active=don_active,
        don_given=don_active,
        turns_completed=1,
        characters=[CardInst(iid="shirley", card_id="EB05-013", rested=False, summoning_sick=False)],
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
        phase="block",
        turn_seat=1,
        first_seat=0,
        turn_number=2,
        players=[p0, p1],
        rng_seed=1,
    )


def test_eb05_013_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-013")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "EB05-013 abilities dropped on normalize"
    ab = next(a for a in get_abilities("EB05-013", "on_opponent_attack"))
    assert ab.get("once") is True
    assert "Fish-Man" in str(ab.get("require_leader_trait") or "")
    assert ab["ops"][0].get("op") == "rest_don"
    assert ab["ops"][0].get("as_cost") is True
    assert ab["ops"][0].get("optional") is True
    assert ab["ops"][1].get("op") == "buff"
    assert ab["ops"][1].get("amount") == 2000
    assert ab["ops"][1].get("target_kind") == "leader"
    assert ab["ops"][1].get("duration") == "battle"


def test_eb05_013_rest_don_buffs_fish_man_leader():
    reload_effect_library(force=True)
    st = _state(leader="OP06-020", don_active=2)
    before = inst_power(st, 0, "leader", catalog)
    pending = resolve_ability(
        st,
        0,
        "EB05-013",
        "shirley",
        "on_opponent_attack",
        catalog("EB05-013"),
        None,
        allow_llm=False,
        catalog=catalog,
    )
    assert pending is not None and pending.ops
    _run_pending_effect(st, pending, catalog)
    # Optional 「可以」→ confirm, then rest 1 DON!! cost.
    assert st.pending_effect is not None
    _confirm_effect(st, 0, True, catalog)
    assert st.pending_choice is not None
    assert "don" in (st.pending_choice.options or []) or "don:active" in (st.pending_choice.options or [])
    tok = "don" if "don" in (st.pending_choice.options or []) else "don:active"
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": tok}, catalog)["ok"]
    assert st.players[0].don_active == 1
    assert st.players[0].don_rested >= 1
    after = inst_power(st, 0, "leader", catalog)
    assert after == before + 2000


def test_eb05_013_gated_without_fish_man_leader():
    reload_effect_library(force=True)
    st = _state(leader="OP08-058", don_active=2)
    pending = resolve_ability(
        st,
        0,
        "EB05-013",
        "shirley",
        "on_opponent_attack",
        catalog("EB05-013"),
        None,
        allow_llm=False,
        catalog=catalog,
    )
    # Gate should block the ability (no pending / empty ops).
    assert pending is None or not pending.ops
