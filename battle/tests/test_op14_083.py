"""OP14-083 Ms. Wednesday — trash self, then −3000 to a 0-cost opponent Character."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.ai import run_ai_until_human  # noqa: E402
from battle.effect_library import lookup_runnable_ability, reload_effect_library  # noqa: E402
from battle.effects import _parse_set_cost_ops, _parse_trash_self_power_debuff  # noqa: E402
from battle.engine import apply_action  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402

TEXT_CN = "【啟動主要】可將這張角色卡放置在廢棄區：最多1張對手費用0的角色卡，在這個回合，力量值-3000。"
TEXT_EN = (
    "[Activate: Main] You may trash this Character: "
    "Give up to 1 of your opponent's 0 cost Characters −3000 power during this turn."
)


def _state() -> MatchState:
    return MatchState(
        room_code="T",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=2,
        players=[
            PlayerState(
                seat=0,
                user_id="u0",
                username="P1",
                is_ai=False,
                leader_card_id="OP01-001",
                deck=["A"] * 20,
                hand=[],
                life=["L"] * 5,
            ),
            PlayerState(
                seat=1,
                user_id="u1",
                username="P2",
                is_ai=False,
                leader_card_id="OP01-001",
                deck=["B"] * 20,
                hand=[],
                life=["L"] * 5,
            ),
        ],
        rng_seed=1,
    )


def catalog(cid: str) -> dict:
    if cid == "OP14-083":
        return {
            "cost": 1,
            "power": 1000,
            "name": "Ms. Wednesday",
            "card_type": "CHARACTER",
            "effect": TEXT_CN,
            "effect_en": TEXT_EN,
        }
    if cid == "Z5":
        return {"cost": 5, "power": 6000, "name": cid, "card_type": "CHARACTER"}
    return {"cost": 0, "power": 4000, "name": cid, "card_type": "CHARACTER"}


def test_parser_not_set_cost():
    assert _parse_set_cost_ops(TEXT_CN) == []
    ops = _parse_trash_self_power_debuff(TEXT_CN)
    assert ops[0]["op"] == "trash"
    assert ops[1]["op"] == "buff"
    assert ops[1]["cost_eq"] == 0
    assert ops[1]["amount"] == -3000


def test_override_and_activate_filters_cost_eq():
    reload_effect_library(force=True)
    ab = lookup_runnable_ability("OP14-083", "activate_main")
    assert ab is not None
    buff = next(o for o in ab["ops"] if o.get("op") == "buff")
    assert buff.get("cost_eq") == 0

    st = _state()
    st.players[0].turns_completed = 1
    st.players[0].characters = [CardInst(iid="w", card_id="OP14-083", rested=False, summoning_sick=False)]
    st.players[1].characters = [
        CardInst(iid="z0", card_id="Z0"),
        CardInst(iid="z1", card_id="Z1"),
        CardInst(iid="z5", card_id="Z5"),
    ]
    apply_action(st, 0, {"type": "activate_main", "source_iid": "w"}, catalog)
    assert "OP14-083" in st.players[0].trash
    assert st.pending_choice is not None
    assert set(st.pending_choice.options) == {"z0", "z1"}
    apply_action(st, 0, {"type": "select_choice", "target_iid": "z0"}, catalog)
    assert next(c for c in st.players[1].characters if c.iid == "z0").power_mod == -3000
    assert next(c for c in st.players[1].characters if c.iid == "z5").power_mod == 0


def test_ai_finishes_choice():
    reload_effect_library(force=True)
    st = _state()
    st.players[1].is_ai = True
    st.turn_seat = 1
    st.players[1].turns_completed = 1
    st.players[1].characters = [CardInst(iid="w", card_id="OP14-083", rested=False, summoning_sick=False)]
    st.players[0].characters = [
        CardInst(iid="z0", card_id="Z0"),
        CardInst(iid="z1", card_id="Z1"),
    ]
    apply_action(st, 1, {"type": "activate_main", "source_iid": "w"}, catalog)
    run_ai_until_human(st, catalog, max_steps=8)
    assert st.pending_choice is None
    assert any(c.power_mod == -3000 for c in st.players[0].characters)


if __name__ == "__main__":
    test_parser_not_set_cost()
    test_override_and_activate_filters_cost_eq()
    test_ai_finishes_choice()
    print("ok")
