"""EB05-057 Nojiko: Activate attach rested DON!! to Special/Wisdom; Trigger play Trigger ≤6000 if Life≤2."""

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

from battle.effect_library import (  # noqa: E402
    get_abilities,
    get_card_entry,
    reload_effect_library,
    resolve_ability,
)
from battle.engine import _confirm_effect, _run_pending_effect, apply_action, legal_actions  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

_CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def catalog(cid: str) -> dict:
    extras = {
        "LEAD_WIS": {
            "card_id": cid,
            "card_type": "LEADER",
            "name": "WisLead",
            "attributes": ["知"],
            "attributes_en": ["Wisdom"],
            "colors": ["黃"],
            "power": 5000,
        },
        "C_WIS": {
            "card_id": cid,
            "card_type": "CHARACTER",
            "cost": 3,
            "power": 4000,
            "name": "WisChar",
            "attributes": ["知"],
            "attributes_en": ["Wisdom"],
        },
        "C_STR": {
            "card_id": cid,
            "card_type": "CHARACTER",
            "cost": 3,
            "power": 4000,
            "name": "StrChar",
            "attributes": ["打"],
            "attributes_en": ["Strike"],
        },
        "C_TRIG": {
            "card_id": cid,
            "card_type": "CHARACTER",
            "cost": 4,
            "power": 6000,
            "name": "TrigOk",
            "trigger": "[Trigger] Draw 1",
            "trigger_en": "[Trigger] Draw 1",
        },
        "C_TRIG_HI": {
            "card_id": cid,
            "card_type": "CHARACTER",
            "cost": 5,
            "power": 7000,
            "name": "TrigHi",
            "trigger": "[Trigger] Draw 1",
            "trigger_en": "[Trigger] Draw 1",
        },
        "C_NO_TRIG": {
            "card_id": cid,
            "card_type": "CHARACTER",
            "cost": 3,
            "power": 5000,
            "name": "Plain",
            "effect": "",
        },
    }
    if cid in extras:
        return extras[cid]
    row = _CARDS.get(cid) or _CARDS.get(str(cid))
    if isinstance(row, dict):
        return row
    return {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000}


def _state(*, life: list[str], hand: list[str], don_rested: int = 1) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="LEAD_WIS",
        deck=["X"] * 20,
        hand=list(hand),
        life=list(life),
        don_active=2,
        don_rested=don_rested,
        don_given=3,
        turns_completed=1,
        characters=[
            CardInst(iid="nojiko", card_id="EB05-057", rested=False, summoning_sick=False),
            CardInst(iid="wis", card_id="C_WIS", rested=False, summoning_sick=False),
            CardInst(iid="str", card_id="C_STR", rested=False, summoning_sick=False),
        ],
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


def test_eb05_057_override_shape():
    reload_effect_library(force=True)
    entry = get_card_entry("EB05-057")
    abs_ = [a for a in entry["abilities"] if a.get("ops")]
    assert abs_, "EB05-057 abilities dropped on normalize"
    act = next(a for a in get_abilities("EB05-057", "activate_main"))
    assert act.get("once") is True
    op = act["ops"][0]
    assert op.get("op") == "attach_don"
    assert op.get("from_rested") is True
    assert op.get("target_kind") == "own_leader_or_character"
    blob = str(op.get("attr_contains") or op.get("attribute") or "")
    assert "Wisdom" in blob or "知" in blob
    assert "Special" in blob or "特" in blob
    trig = next(a for a in get_abilities("EB05-057", "trigger"))
    assert trig.get("require_life_lte") == 2
    play = trig["ops"][0]
    assert play.get("op") == "play_from_hand"
    assert play.get("power_lte") == 6000
    assert play.get("require_trigger") is True
    assert play.get("from_zone") == "hand"


def test_eb05_057_activate_attaches_rested_don_to_wisdom_only():
    reload_effect_library(force=True)
    st = _state(life=["L"] * 5, hand=[], don_rested=1)
    acts = legal_actions(st, 0, catalog)
    assert any(a.get("type") == "activate_main" and a.get("source_iid") == "nojiko" for a in acts)
    assert apply_action(st, 0, {"type": "activate_main", "source_iid": "nojiko"}, catalog)["ok"]
    ch = st.pending_choice
    assert ch is not None
    opts = ch.options or []
    assert "leader" in opts
    assert "wis" in opts
    assert "nojiko" in opts  # Wisdom
    assert "str" not in opts
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "wis"}, catalog)["ok"]
    assert st.players[0].don_rested == 0
    wis = next(c for c in st.players[0].characters if c.iid == "wis")
    assert wis.don_attached == 1
    assert st.players[0].characters[0].once_used is True


def test_eb05_057_trigger_plays_6000_trigger_when_life_lte_2():
    reload_effect_library(force=True)
    st = _state(life=["L1", "L2"], hand=["C_TRIG", "C_TRIG_HI", "C_NO_TRIG"], don_rested=0)
    pending = resolve_ability(
        st,
        0,
        "EB05-057",
        "nojiko",
        "trigger",
        catalog("EB05-057"),
        None,
        allow_llm=False,
        catalog=catalog,
    )
    assert pending is not None and pending.ops
    _run_pending_effect(st, pending, catalog)
    if st.pending_effect is not None:
        _confirm_effect(st, 0, True, catalog)
    ch = st.pending_choice
    assert ch is not None
    opts = ch.options or []
    assert any("C_TRIG" in str(o) and "C_TRIG_HI" not in str(o) for o in opts)
    assert not any("C_TRIG_HI" in str(o) for o in opts)
    assert not any("C_NO_TRIG" in str(o) for o in opts)
    pick = next(o for o in opts if "C_TRIG" in str(o) and "C_TRIG_HI" not in str(o))
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick}, catalog)["ok"]
    assert any(c.card_id == "C_TRIG" for c in st.players[0].characters)
    assert "C_TRIG" not in st.players[0].hand
    assert "C_TRIG_HI" in st.players[0].hand


def test_eb05_057_trigger_gated_when_life_over_2():
    reload_effect_library(force=True)
    st = _state(life=["L"] * 3, hand=["C_TRIG"], don_rested=0)
    pending = resolve_ability(
        st,
        0,
        "EB05-057",
        "nojiko",
        "trigger",
        catalog("EB05-057"),
        None,
        allow_llm=False,
        catalog=catalog,
    )
    assert pending is None
    assert not any(c.card_id == "C_TRIG" for c in st.players[0].characters)


if __name__ == "__main__":
    test_eb05_057_override_shape()
    test_eb05_057_activate_attaches_rested_don_to_wisdom_only()
    test_eb05_057_trigger_plays_6000_trigger_when_life_lte_2()
    test_eb05_057_trigger_gated_when_life_over_2()
    print("OK")
