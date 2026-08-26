"""When this Character becomes rested (e.g. OP14-027 Jack via OP14-020 cost)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_abilities, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_ability  # noqa: E402
from battle.effects import apply_ops  # noqa: E402
from battle.engine import _fire_self_rested, inst_power  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402


def _catalog(cid: str) -> dict:
    table = {
        "OP14-027": {
            "card_id": "OP14-027",
            "card_type": "CHARACTER",
            "name": "Jack",
            "cost": 5,
            "power": 6000,
            "effect": "【我方回合中】這張角色卡置為休息狀態時，將最多1張對手原本力量值7000以下的角色卡置為休息狀態。",
            "effect_en": "[Your Turn] When this Character becomes rested, rest up to 1 of your opponent's Characters with 7000 base power or less.",
        },
        "OP14-032": {
            "card_id": "OP14-032",
            "card_type": "CHARACTER",
            "name": "Rest Cost4",
            "cost": 4,
            "power": 5000,
            "effect_en": "[Your Turn] When this Character becomes rested, rest up to 1 of your opponent's Characters with a cost of 4 or less.",
        },
        "WEAK": {"card_id": "WEAK", "card_type": "CHARACTER", "name": "Weak", "cost": 3, "power": 5000},
        "STRONG": {"card_id": "STRONG", "card_type": "CHARACTER", "name": "Strong", "cost": 7, "power": 9000},
        "L0": {"card_id": "L0", "card_type": "LEADER", "name": "L0", "power": 5000},
        "L1": {"card_id": "L1", "card_type": "LEADER", "name": "L1", "power": 5000},
    }
    return dict(table.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000})


def _state() -> MatchState:
    p0 = PlayerState(seat=0, user_id="u0", username="p0", is_ai=False, leader_card_id="L0", hand=[], deck=["D"] * 10)
    p1 = PlayerState(seat=1, user_id="u1", username="p1", is_ai=False, leader_card_id="L1", hand=[], deck=["D"] * 10)
    return MatchState(room_code="t", status="playing", phase="main", turn_seat=0, players=[p0, p1])


def test_op14_027_library_has_self_rested_and_power_filter():
    reload_effect_library(force=True)
    abs_ = get_abilities("OP14-027", "your_turn")
    assert abs_
    ab = abs_[0]
    assert ab.get("trigger_on") == "self_rested"
    op = ab["ops"][0]
    assert op.get("op") == "rest_opponent_character"
    assert op.get("base_power_lte") == 7000
    assert op.get("optional") is True


def test_normalize_auto_tags_self_rested_from_summary():
    ab = normalize_ability(
        {
            "timing": "your_turn",
            "summary": "When this Character becomes rested, draw 1.",
            "ops": [{"op": "draw", "count": 1}],
            "status": "compiled",
            "confidence": 0.9,
        }
    )
    assert ab is not None
    assert ab.get("trigger_on") == "self_rested"


def test_rest_as_cost_fires_jack_rest_opp():
    reload_effect_library(force=True)
    st = _state()
    jack = CardInst(iid="jack", card_id="OP14-027", rested=False)
    weak = CardInst(iid="weak", card_id="WEAK", rested=False)
    strong = CardInst(iid="strong", card_id="STRONG", rested=False)
    st.players[0].characters = [jack]
    st.players[1].characters = [weak, strong]

    apply_ops(
        st,
        0,
        [
            {
                "op": "rest_character",
                "target_kind": "own_character",
                "target_iid": "jack",
                "as_cost": True,
                "optional": True,
                "card_id": "OP14-020",
                "source_iid": "leader",
            }
        ],
        _catalog,
    )
    assert jack.rested is True
    # Sole eligible target (base ≤7000) is auto-rested; 9000 base is excluded.
    assert weak.rested is True
    assert strong.rested is False


def test_fire_self_rested_direct():
    reload_effect_library(force=True)
    st = _state()
    jack = CardInst(iid="jack", card_id="OP14-027", rested=True)
    weak = CardInst(iid="weak", card_id="WEAK", rested=False)
    st.players[0].characters = [jack]
    st.players[1].characters = [weak]
    _fire_self_rested(st, 0, "jack", _catalog)
    assert weak.rested is True or (
        st.pending_choice is not None and "weak" in (st.pending_choice.options or [])
    )


def test_op14_027_aura_while_rested_on_opp_turn():
    reload_effect_library(force=True)
    st = _state()
    st.turn_seat = 1  # opponent's turn relative to Jack's controller
    jack = CardInst(iid="jack", card_id="OP14-027", rested=True)
    weak = CardInst(iid="weak", card_id="WEAK", rested=False)
    st.players[0].characters = [jack]
    st.players[1].characters = [weak]
    assert inst_power(st, 1, "weak", _catalog) == 4000  # 5000 - 1000
    jack.rested = False
    assert inst_power(st, 1, "weak", _catalog) == 5000
