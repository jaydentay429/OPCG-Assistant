"""OP14-020 Activate Main: rest cost always; DON/cannot-play only if either field has cost≥5."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_abilities, reload_effect_library  # noqa: E402
from battle.engine import apply_action, legal_actions  # noqa: E402
from battle.state import CardInst, MatchState, PlayerState  # noqa: E402


def _catalog(cid: str) -> dict:
    table = {
        "OP14-020": {
            "card_id": "OP14-020",
            "card_type": "LEADER",
            "name": "Mihawk",
            "power": 5000,
            "life": 5,
            "effect": "【啟動主要】【每回合1次】可將1張自己的卡片置為休息狀態：若場上有費用5以上的角色卡時，將最多3張自己的咚‼卡置為活動狀態。之後，在這個回合，自己無法使角色卡登場。",
        },
        "C3": {"card_id": "C3", "card_type": "CHARACTER", "name": "Small", "cost": 3, "power": 4000},
        "C5": {"card_id": "C5", "card_type": "CHARACTER", "name": "Big", "cost": 5, "power": 6000},
        "ST1": {"card_id": "ST1", "card_type": "STAGE", "name": "Stage", "cost": 1},
        "L1": {"card_id": "L1", "card_type": "LEADER", "name": "Opp", "power": 5000},
    }
    return dict(table.get(cid) or {"card_id": cid, "card_type": "CHARACTER", "cost": 1, "power": 1000})


def _state(*, cost5_own: bool = False, cost5_opp: bool = False, with_stage: bool = False) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="p0",
        is_ai=False,
        leader_card_id="OP14-020",
        hand=["C3"],
        deck=["D"] * 20,
        life=["X"] * 5,
    )
    p1 = PlayerState(
        seat=1, user_id="u1", username="p1", is_ai=False, leader_card_id="L1", hand=[], deck=["D"] * 20, life=["X"] * 5
    )
    p0.don_active = 2
    p0.don_rested = 3
    p0.turns_completed = 1
    if cost5_own:
        p0.characters = [CardInst(iid="c5", card_id="C5", rested=False, summoning_sick=False)]
    else:
        p0.characters = [CardInst(iid="c3", card_id="C3", rested=False, summoning_sick=False)]
    if cost5_opp:
        p1.characters = [CardInst(iid="oc5", card_id="C5", rested=False, summoning_sick=False)]
    if with_stage:
        p0.stages = [CardInst(iid="st1", card_id="ST1", rested=False, summoning_sick=False)]
    return MatchState(room_code="t", status="playing", phase="main", turn_seat=0, players=[p0, p1])


def test_op14_020_encoding_gate_on_active_don_and_cannot_play():
    reload_effect_library(force=True)
    ab = next(a for a in get_abilities("OP14-020") if a.get("timing") == "activate_main")
    assert ab.get("require_field_char_cost_gte") is None
    active = next(o for o in ab["ops"] if o.get("op") == "active_don")
    assert active.get("require_field_char_cost_gte") == 5
    cannot = next(o for o in ab["ops"] if o.get("op") == "cannot_play_from_hand")
    assert cannot.get("require_field_char_cost_gte") == 5
    rest = next(o for o in ab["ops"] if o.get("op") == "rest_character")
    assert rest.get("as_cost") is True
    assert rest.get("include_leader") is True
    assert rest.get("include_don") is True
    assert rest.get("include_stage") is True


def test_activate_offers_leader_character_stage_and_don():
    reload_effect_library(force=True)
    st = _state(with_stage=True)
    assert apply_action(st, 0, {"type": "activate_main", "source_iid": "leader"}, _catalog)["ok"]
    assert st.pending_choice is not None
    opts = set(st.pending_choice.options)
    assert "leader" in opts
    assert "c3" in opts
    assert "st1" in opts
    assert "don" in opts
    # Once is deferred until rest cost is paid.
    assert st.players[0].leader_once_used is False
    assert st.pending_choice.mark_once is True


def test_activate_can_rest_stage_as_cost():
    reload_effect_library(force=True)
    st = _state(cost5_own=True, with_stage=True)
    assert apply_action(st, 0, {"type": "activate_main", "source_iid": "leader"}, _catalog)["ok"]
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": "st1"}, _catalog)["ok"]
    assert st.players[0].stages[0].rested is True
    assert st.players[0].don_rested == 0  # stood up to 3 rested DON!!
    assert st.players[0].leader_once_used is True


def test_activate_without_cost5_rest_only_no_don_no_cannot_play():
    """FAQ: neither field has cost≥5 → may rest, but no active DON!! and no cannot-play."""
    reload_effect_library(force=True)
    st = _state()
    acts = legal_actions(st, 0, _catalog)
    assert any(a.get("type") == "activate_main" and a.get("source_iid") == "leader" for a in acts)
    r = apply_action(st, 0, {"type": "activate_main", "source_iid": "leader"}, _catalog)
    assert r.get("ok"), r
    assert st.pending_choice is not None
    pick = "c3" if "c3" in st.pending_choice.options else st.pending_choice.options[0]
    rested_before = st.players[0].don_rested
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick}, _catalog)["ok"]
    if pick != "don":
        assert st.players[0].don_rested == rested_before
    assert not st.players[0].cannot_play_rules
    assert st.players[0].leader_once_used is True


def test_activate_with_own_cost5_stands_don_and_blocks_play():
    reload_effect_library(force=True)
    st = _state(cost5_own=True)
    assert apply_action(st, 0, {"type": "activate_main", "source_iid": "leader"}, _catalog)["ok"]
    assert st.pending_choice is not None
    pick = "c5" if "c5" in st.pending_choice.options else st.pending_choice.options[0]
    before_rested = st.players[0].don_rested
    before_active = st.players[0].don_active
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick}, _catalog)["ok"]
    assert st.players[0].don_rested == before_rested - min(3, before_rested)
    assert st.players[0].don_active == before_active + min(3, before_rested)
    assert st.players[0].cannot_play_rules
    assert any(str(r.get("card_type") or "") == "character" for r in st.players[0].cannot_play_rules)


def test_activate_with_opp_cost5_only_still_stands_don():
    """「場上」= either side: opponent cost≥5 is enough."""
    reload_effect_library(force=True)
    st = _state(cost5_opp=True)
    assert apply_action(st, 0, {"type": "activate_main", "source_iid": "leader"}, _catalog)["ok"]
    pick = "c3" if "c3" in st.pending_choice.options else st.pending_choice.options[0]
    before_rested = st.players[0].don_rested
    assert apply_action(st, 0, {"type": "select_choice", "target_iid": pick}, _catalog)["ok"]
    if pick != "don":
        assert st.players[0].don_rested == before_rested - min(3, before_rested)
    assert st.players[0].cannot_play_rules


def test_decline_rest_does_not_burn_once():
    reload_effect_library(force=True)
    st = _state()
    assert apply_action(st, 0, {"type": "activate_main", "source_iid": "leader"}, _catalog)["ok"]
    assert apply_action(st, 0, {"type": "skip_choice"}, _catalog)["ok"]
    assert st.players[0].leader_once_used is False
    assert st.players[0].don_rested == 3
    assert not st.players[0].cannot_play_rules
