"""Heuristic AI: no infinite Activate: Main, smarter targets, search dest."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.ai import pick_ai_action, step_ai_once  # noqa: E402
from battle.engine import legal_actions  # noqa: E402
from battle.state import CardInst, MatchState, PendingAttack, PendingChoice, PendingSearch, PlayerState  # noqa: E402

CARDS = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))


def _catalog(cid: str) -> dict:
    row = CARDS.get(cid) or CARDS.get(str(cid))
    if isinstance(row, dict):
        return row
    return {
        "card_id": cid,
        "id": cid,
        "name": cid,
        "cost": 1,
        "power": 1000,
        "card_type": "CHARACTER",
    }


def _match(*, turn: int = 1, first: bool = True) -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="ai0",
        username="AI0",
        is_ai=True,
        leader_card_id="OP08-058",
        hand=[],
        deck=["OP11-070"] * 20,
        life=["L"] * 5,
        don_active=1,
        don_given=1,
        turns_completed=0 if first else 1,
    )
    p1 = PlayerState(
        seat=1,
        user_id="ai1",
        username="AI1",
        is_ai=True,
        leader_card_id="OP08-058",
        hand=[],
        deck=["OP11-070"] * 20,
        life=["L"] * 5,
        don_active=2,
        don_given=2,
        turns_completed=0,
    )
    return MatchState(
        room_code="AI",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=turn,
        players=[p0, p1],
        rng_seed=1,
    )


def test_self_trash_activate_skipped_without_payoff():
    st = _match()
    st.players[0].characters = [CardInst(iid="c1", card_id="OP08-062", summoning_sick=True)]
    st.pending_choice = PendingChoice(
        seat=0,
        card_id="OP08-062",
        source_iid="c1",
        target_kind="own_character",
        options=["c1"],
        remaining_ops=[
            {"op": "trash", "target_kind": "self", "as_cost": True, "optional": True},
            {
                "op": "play_from_hand",
                "name_contains": "Charlotte Katakuri",
                "card_type": "character",
                "cost_gte": 3,
            },
        ],
        optional=True,
        purpose="trash",
        summary="Trash this Character",
    )
    pick = pick_ai_action(st, 0, _catalog)
    assert pick is not None
    assert pick.get("type") == "skip_choice"


def test_self_trash_activate_pays_when_katakuri_in_hand():
    st = _match()
    st.players[0].hand = ["OP08-063"]
    st.players[1].don_active = 8
    st.players[1].don_given = 8
    st.players[0].characters = [CardInst(iid="c1", card_id="OP08-062", summoning_sick=True)]
    st.pending_choice = PendingChoice(
        seat=0,
        card_id="OP08-062",
        source_iid="c1",
        target_kind="own_character",
        options=["c1"],
        remaining_ops=[
            {"op": "trash", "target_kind": "self", "as_cost": True, "optional": True},
            {
                "op": "play_from_hand",
                "name_contains": "Charlotte Katakuri|夏洛特・卡塔克利",
                "card_type": "character",
                "cost_gte": 3,
            },
        ],
        optional=True,
        purpose="trash",
        summary="Trash this Character",
    )
    pick = pick_ai_action(st, 0, _catalog)
    assert pick == {"type": "select_choice", "target_iid": "c1"}


def test_ko_choice_prefers_higher_cost_enemy():
    st = _match()
    st.players[1].characters = [
        CardInst(iid="small", card_id="OP11-070"),
        CardInst(iid="big", card_id="OP08-063"),
    ]
    st.pending_choice = PendingChoice(
        seat=0,
        card_id="X",
        source_iid="s",
        target_kind="opponent_character",
        options=["small", "big"],
        remaining_ops=[{"op": "ko", "target_kind": "opponent_character"}],
        optional=True,
        purpose="ko",
        summary="KO 1 opponent Character",
    )
    pick = pick_ai_action(st, 0, _catalog)
    assert pick == {"type": "select_choice", "target_iid": "big"}


def test_search_choose_dest_prefers_bottom():
    st = _match()
    st.pending_search = PendingSearch(
        seat=0,
        card_id="OP11-070",
        source_iid="c1",
        revealed=["OP11-067", "OP08-062"],
        eligible=[0, 1],
        max_add=0,
        phase="choose_dest",
        to_top_or_bottom=True,
        summary="Place leftovers",
    )
    pick = pick_ai_action(st, 0, _catalog)
    assert pick == {"type": "select_choice", "target_iid": "deck:bottom"}


def test_op08_062_activate_does_not_loop():
    st = _match()
    st.players[0].characters = [CardInst(iid="c1", card_id="OP08-062", summoning_sick=True, rested=False)]
    # No Katakuri in hand — suicide Activate must not loop the turn.
    st.players[0].hand = ["OP11-070"]
    steps = 0
    for _ in range(40):
        if st.status != "playing":
            break
        before_turn = (st.turn_number, st.turn_seat)
        ok = step_ai_once(st, _catalog, ask_llm=None)
        if not ok:
            break
        steps += 1
        if (st.turn_number, st.turn_seat) != before_turn:
            break
    assert steps < 40
    assert any(c.card_id == "OP08-062" for c in st.players[0].characters)


def test_op14_083_activate_does_not_loop():
    st = _match()
    st.players[0].leader_card_id = "OP14-079"
    st.players[0].characters = [CardInst(iid="c1", card_id="OP14-083", summoning_sick=True, rested=False)]
    st.players[1].characters = [CardInst(iid="e1", card_id="OP08-063", rested=True)]
    st.players[0].hand = []
    steps = 0
    for _ in range(40):
        if st.status != "playing":
            break
        before_turn = (st.turn_number, st.turn_seat)
        ok = step_ai_once(st, _catalog, ask_llm=None)
        if not ok:
            break
        steps += 1
        if (st.turn_number, st.turn_seat) != before_turn:
            break
    assert steps < 40


def test_op14_020_activate_once_then_ends():
    st = _match()
    st.players[0].leader_card_id = "OP14-020"
    st.players[0].hand = []
    st.players[0].don_active = 4
    st.players[0].don_rested = 2
    steps = 0
    activates = 0
    for _ in range(30):
        if st.status != "playing":
            break
        pick = pick_ai_action(st, st.turn_seat, _catalog)
        if pick and pick.get("type") == "activate_main" and pick.get("source_iid") == "leader":
            activates += 1
        before_turn = (st.turn_number, st.turn_seat)
        ok = step_ai_once(st, _catalog, ask_llm=None)
        if not ok:
            break
        steps += 1
        if (st.turn_number, st.turn_seat) != before_turn:
            break
    assert steps < 30
    assert activates <= 1


def test_attack_skips_unwinnable_character():
    st = _match(turn=2, first=False)
    st.players[0].turns_completed = 1
    st.players[0].leader_rested = False
    st.players[0].characters = []
    st.players[1].characters = [CardInst(iid="wall", card_id="OP08-063", rested=True)]
    legal = legal_actions(st, 0, _catalog)
    atk = [a for a in legal if a.get("type") == "attack"]
    if any(a.get("target_iid") == "wall" for a in atk) and any(a.get("target_iid") == "leader" for a in atk):
        pick = pick_ai_action(st, 0, _catalog)
        assert pick is not None
        assert pick.get("target_iid") != "wall"


def _combat_catalog(cid: str) -> dict:
    extra = {
        "BLK9": {"card_id": "BLK9", "card_type": "CHARACTER", "power": 9000, "cost": 4, "name": "Blk9", "effect": "【Blocker】"},
        "BDY8": {"card_id": "BDY8", "card_type": "CHARACTER", "power": 4000, "cost": 8, "name": "Body8", "effect": "【Blocker】"},
        "C2K": {"card_id": "C2K", "card_type": "CHARACTER", "power": 2000, "cost": 1, "counter": 2000, "name": "2k"},
        "ATK8": {"card_id": "ATK8", "card_type": "CHARACTER", "power": 8000, "cost": 5, "name": "Atk8"},
        "BIG8": {"card_id": "BIG8", "card_type": "CHARACTER", "power": 8000, "cost": 8, "name": "Big8"},
    }
    if cid in extra:
        return extra[cid]
    return _catalog(cid)


def _combat_state(*, phase: str, life: int = 5, blocker_id: str | None = "BLK9") -> MatchState:
    st = _match(turn=2, first=False)
    st.phase = phase
    st.turn_seat = 0
    st.players[0].turns_completed = 1
    st.players[1].turns_completed = 1
    st.players[1].life = ["L"] * life
    st.players[0].characters = [CardInst(iid="atk", card_id="ATK8", rested=True, summoning_sick=False)]
    if blocker_id:
        st.players[1].characters = [
            CardInst(iid="blk", card_id=blocker_id, rested=False, summoning_sick=False, keywords=["blocker"])
        ]
    else:
        st.players[1].characters = []
    st.attack = PendingAttack(
        attacker_seat=0,
        attacker_iid="atk",
        target_iid="leader",
        declared_power=8000,
        combat_entered=True,
        combat_phase=phase,
        opp_attack_watchers_done=True,
    )
    return st


def test_block_to_ko_attacker():
    st = _combat_state(phase="block", life=5, blocker_id="BLK9")
    pick = pick_ai_action(st, 1, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "block"
    assert pick.get("blocker_iid") == "blk"


def test_pass_expensive_chump_at_full_life():
    st = _combat_state(phase="block", life=5, blocker_id="BDY8")
    pick = pick_ai_action(st, 1, _combat_catalog)
    assert pick == {"type": "block", "blocker_iid": None}


def test_stack_counters_when_one_is_not_enough():
    st = _combat_state(phase="counter", life=4, blocker_id=None)
    st.players[1].hand = ["C2K", "C2K"]
    pick = pick_ai_action(st, 1, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "counter"
    assert int(pick.get("counter") or 0) == 2000


def test_block_saves_high_cost_character():
    st = _match(turn=2, first=False)
    st.phase = "block"
    st.turn_seat = 0
    st.players[0].characters = [CardInst(iid="atk", card_id="ATK8", rested=True, summoning_sick=False)]
    st.players[1].characters = [
        CardInst(iid="big", card_id="BIG8", rested=True, summoning_sick=False),
        CardInst(iid="blk", card_id="BLK9", rested=False, summoning_sick=False, keywords=["blocker"]),
    ]
    st.attack = PendingAttack(
        attacker_seat=0,
        attacker_iid="atk",
        target_iid="big",
        declared_power=8000,
        combat_entered=True,
        combat_phase="block",
        opp_attack_watchers_done=True,
    )
    pick = pick_ai_action(st, 1, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "block"
    assert pick.get("blocker_iid") == "blk"
