"""OP08-023 Carrot: On Play / When Attacking skip_untap (cost≤7 rested opp Character)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_abilities, reload_effect_library  # noqa: E402
from battle.engine import apply_action, _begin_turn  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402


def _catalog(cid: str) -> dict:
    table = {
        "OP08-023": {
            "card_id": "OP08-023",
            "card_type": "CHARACTER",
            "name": "Carrot",
            "cost": 5,
            "power": 6000,
            "effect": "【登場時】/【攻擊時】最多1張對手休息狀態費用7以下的角色卡，在下一個對手的重整階段無法為活動狀態。",
        },
        "OP08-023-P1": {
            "card_id": "OP08-023-P1",
            "card_type": "CHARACTER",
            "name": "Carrot",
            "cost": 5,
            "power": 6000,
            "effect": "【登場時】/【攻擊時】最多1張對手休息狀態費用7以下的角色卡，在下一個對手的重整階段無法為活動狀態。",
        },
        "L0": {"card_id": "L0", "card_type": "LEADER", "name": "Me", "power": 5000, "life": 5},
        "L1": {"card_id": "L1", "card_type": "LEADER", "name": "Opp", "power": 5000, "life": 5},
        "C3": {"card_id": "C3", "card_type": "CHARACTER", "name": "Small", "cost": 3, "power": 4000},
        "C8": {"card_id": "C8", "card_type": "CHARACTER", "name": "Big", "cost": 8, "power": 8000},
    }
    return dict(table.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000})


def _state(*, hand_id: str = "OP08-023", opp_rested: list[tuple[str, str]] | None = None) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="p0",
        is_ai=False,
        leader_card_id="L0",
        hand=[hand_id],
        deck=["D"] * 30,
        life=["X"] * 5,
    )
    p1 = PlayerState(
        seat=1, user_id="u1", username="p1", is_ai=False, leader_card_id="L1", hand=[], deck=["D"] * 30, life=["X"] * 5
    )
    p0.don_active = 10
    p0.turns_completed = 1
    if opp_rested is None:
        opp_rested = [("oc3", "C3")]
    p1.characters = [
        CardInst(iid=iid, card_id=cid, rested=True, summoning_sick=False) for iid, cid in opp_rested
    ]
    return MatchState(room_code="t", status="playing", phase="main", turn_seat=0, players=[p0, p1])


def test_encoding_skip_untap_only():
    reload_effect_library(force=True)
    for cid in ("OP08-023", "OP08-023-P1", "OP08-023-P2", "OP08-023-R1"):
        for timing in ("on_play", "when_attacking"):
            ab = next(a for a in get_abilities(cid) if a.get("timing") == timing)
            ops = [o.get("op") for o in ab["ops"]]
            assert ops == ["skip_untap"], (cid, timing, ops)
            assert ab["ops"][0].get("cost_lte") == 7


def test_on_play_offers_choice_even_with_one_target():
    reload_effect_library(force=True)
    st = _state()
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, _catalog)["ok"]
    assert st.pending_choice is not None
    assert st.pending_choice.options == ["oc3"]
    assert st.pending_choice.purpose == "skip_untap"
    assert st.players[1].skip_untap_iids == []
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "oc3"}, _catalog)["ok"]
    assert st.players[1].skip_untap_iids == ["oc3"]
    _begin_turn(st, 1, _catalog)
    assert st.players[1].characters[0].rested is True


def test_on_play_no_eligible_target_is_noop():
    reload_effect_library(force=True)
    st = _state(opp_rested=[("oc8", "C8")])
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, _catalog)["ok"]
    assert st.pending_choice is None
    assert st.players[1].skip_untap_iids == []


def test_when_attacking_offers_skip_untap():
    reload_effect_library(force=True)
    st = _state()
    st.players[0].hand = []
    st.players[0].characters = [CardInst(iid="carrot", card_id="OP08-023", rested=False, summoning_sick=False)]
    assert apply_action(st, 0, {"type": "attack", "attacker_iid": "carrot", "target_iid": "leader"}, _catalog)["ok"]
    assert st.pending_choice is not None
    assert "oc3" in st.pending_choice.options


def test_p1_variant_does_not_stand_own_character():
    reload_effect_library(force=True)
    st = _state(hand_id="OP08-023-P1")
    st.players[0].characters = [CardInst(iid="own", card_id="C3", rested=True, summoning_sick=False)]
    assert apply_action(st, 0, {"type": "play_card", "hand_index": 0}, _catalog)["ok"]
    assert st.players[0].characters[0].rested is True  # not wrongly set active
    assert st.pending_choice is not None
