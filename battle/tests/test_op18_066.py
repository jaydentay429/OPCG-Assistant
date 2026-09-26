"""OP18-066 Zambai: Activate Main KO own Stage cost≤5 → this Character gains Rush this turn."""

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
from battle.effects import has_rush  # noqa: E402
from battle.engine import apply_action, legal_actions  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return dict(row)
    extras = {
        "ST5": {
            "card_id": "ST5",
            "card_type": "STAGE",
            "cost": 5,
            "name": "Small Stage",
            "colors": ["紫"],
            "colors_en": ["Purple"],
        },
        "ST6": {
            "card_id": "ST6",
            "card_type": "STAGE",
            "cost": 6,
            "name": "Big Stage",
            "colors": ["紫"],
            "colors_en": ["Purple"],
        },
    }
    return extras.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _state(*, stages: list[tuple[str, str]] | None = None, opp_stages: list[tuple[str, str]] | None = None) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="OP09-061",
        deck=["X"] * 20,
        hand=[],
        life=["L"] * 5,
        don_active=5,
        don_given=5,
        turns_completed=1,
        characters=[CardInst(iid="zam", card_id="OP18-066", rested=False, summoning_sick=True)],
        stages=[CardInst(iid=iid, card_id=cid, summoning_sick=False) for iid, cid in (stages or [("st5", "ST5")])],
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
        stages=[CardInst(iid=iid, card_id=cid, summoning_sick=False) for iid, cid in (opp_stages or [("ost", "ST5")])],
        characters=[CardInst(iid="opp", card_id="ST18-001", rested=False, summoning_sick=False)],
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


def _finish_confirm(st: MatchState) -> None:
    if st.pending_effect is not None:
        assert apply_action(st, 0, {"type": "confirm_effect", "accept": True}, catalog)["ok"]


def test_op18_066_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("OP18-066")
    abs_ = [a for a in (entry.get("abilities") or []) if a.get("ops")]
    assert abs_, "abilities dropped"
    act = next(a for a in get_abilities("OP18-066", "activate_main"))
    ko = act["ops"][0]
    assert ko["op"] == "ko"
    assert ko.get("as_cost") is True
    assert ko.get("target_kind") == "own_stage"
    assert ko.get("cost_lte") == 5
    grant = act["ops"][1]
    assert grant["op"] == "grant_keyword"
    assert grant.get("keyword") == "rush"
    assert grant.get("target_kind") == "self"
    assert grant.get("duration") == "turn"


def test_activate_kos_own_cost5_stage_and_gains_rush():
    reload_effect_library(force=True)
    st = _state()
    acts = legal_actions(st, 0, catalog)
    assert any(a.get("type") == "activate_main" and a.get("source_iid") == "zam" for a in acts)
    assert not any(a.get("type") == "attack" and a.get("attacker_iid") == "zam" for a in acts)
    assert apply_action(st, 0, {"type": "activate_main", "source_iid": "zam"}, catalog)["ok"]
    _finish_confirm(st)
    ch = st.pending_choice
    assert ch is not None
    assert "st5" in ch.options
    assert "ost" not in ch.options
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "st5"}, catalog)["ok"]
    assert st.players[0].stages == []
    assert "ST5" in st.players[0].trash
    zam = next(c for c in st.players[0].characters if c.iid == "zam")
    assert has_rush(catalog("OP18-066"), zam, state=st, owner_seat=0, catalog=catalog)
    assert zam.summoning_sick is False
    acts2 = legal_actions(st, 0, catalog)
    assert any(a.get("type") == "attack" and a.get("attacker_iid") == "zam" for a in acts2)


def test_cost6_stage_not_eligible():
    reload_effect_library(force=True)
    st = _state(stages=[("st6", "ST6")])
    assert apply_action(st, 0, {"type": "activate_main", "source_iid": "zam"}, catalog)["ok"]
    _finish_confirm(st)
    assert st.pending_choice is None
    assert st.players[0].stages and st.players[0].stages[0].iid == "st6"
    zam = next(c for c in st.players[0].characters if c.iid == "zam")
    assert not has_rush(catalog("OP18-066"), zam, state=st, owner_seat=0, catalog=catalog)
    assert zam.summoning_sick is True


def test_skip_keeps_stage_no_rush():
    reload_effect_library(force=True)
    st = _state()
    assert apply_action(st, 0, {"type": "activate_main", "source_iid": "zam"}, catalog)["ok"]
    _finish_confirm(st)
    assert st.pending_choice is not None
    assert apply_action(st, 0, {"type": "skip_choice"}, catalog)["ok"]
    assert any(s.iid == "st5" for s in st.players[0].stages)
    zam = next(c for c in st.players[0].characters if c.iid == "zam")
    assert not has_rush(catalog("OP18-066"), zam, state=st, owner_seat=0, catalog=catalog)
    assert zam.summoning_sick is True
