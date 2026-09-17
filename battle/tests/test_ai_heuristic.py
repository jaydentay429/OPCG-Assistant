"""Heuristic AI: no infinite Activate: Main, smarter targets, search dest."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from battle.ai import pick_ai_action, step_ai_once, _followup_worth  # noqa: E402
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
        "C1K": {"card_id": "C1K", "card_type": "CHARACTER", "power": 1000, "cost": 1, "counter": 1000, "name": "1k"},
        "ATK4": {"card_id": "ATK4", "card_type": "CHARACTER", "power": 4000, "cost": 3, "name": "Atk4"},
        "ATK5": {"card_id": "ATK5", "card_type": "CHARACTER", "power": 5000, "cost": 4, "name": "Atk5"},
        "ATK6": {"card_id": "ATK6", "card_type": "CHARACTER", "power": 6000, "cost": 5, "name": "Atk6"},
        "ATK8": {"card_id": "ATK8", "card_type": "CHARACTER", "power": 8000, "cost": 5, "name": "Atk8"},
        "BIG8": {"card_id": "BIG8", "card_type": "CHARACTER", "power": 8000, "cost": 8, "name": "Big8"},
        "DROP1": {"card_id": "DROP1", "card_type": "CHARACTER", "power": 2000, "cost": 1, "name": "Drop1"},
        "CHP2": {"card_id": "CHP2", "card_type": "CHARACTER", "power": 2000, "cost": 2, "name": "Chump", "effect": "【Blocker】"},
        "WALL6": {"card_id": "WALL6", "card_type": "CHARACTER", "power": 6000, "cost": 5, "name": "Wall6"},
        "EVNT0": {"card_id": "EVNT0", "card_type": "EVENT", "cost": 4, "name": "BlankEvent", "effect": ""},
        "LEAD4": {"card_id": "LEAD4", "card_type": "LEADER", "power": 4000, "cost": 5, "life": 4, "name": "Lead4"},
        "ZERO8": {"card_id": "ZERO8", "card_type": "CHARACTER", "power": 0, "cost": 8, "name": "Zero8"},
        "ATK3": {"card_id": "ATK3", "card_type": "CHARACTER", "power": 3000, "cost": 3, "name": "Atk3"},
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
    st.players[1].leader_card_id = "OP16-001"
    pick = pick_ai_action(st, 1, _combat_catalog)
    assert pick == {"type": "block", "blocker_iid": None}


def test_stack_counters_when_one_is_not_enough():
    st = _combat_state(phase="counter", life=2, blocker_id=None)
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


def test_counter_equal_power_saves_life():
    """5000 vs 5000 takes life; +1000 Counter makes defender strictly higher."""
    st = _combat_state(phase="counter", life=3, blocker_id=None)
    st.players[0].characters = [CardInst(iid="atk", card_id="ATK5", rested=True, summoning_sick=False)]
    st.attack.attacker_iid = "atk"
    st.attack.declared_power = 5000
    st.players[1].hand = ["C1K"]
    pick = pick_ai_action(st, 1, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "counter"
    assert int(pick.get("counter") or 0) == 1000


def test_counter_1k_does_not_save_1k_deficit():
    """6000 vs 5000 +1000 still ties — attacker wins. Pass instead of wasting the 1k."""
    st = _combat_state(phase="counter", life=4, blocker_id=None)
    st.players[0].characters = [CardInst(iid="atk", card_id="ATK6", rested=True, summoning_sick=False)]
    st.attack.attacker_iid = "atk"
    st.attack.declared_power = 6000
    st.players[1].hand = ["C1K"]
    pick = pick_ai_action(st, 1, _combat_catalog)
    assert pick == {"type": "pass_counter"}


def test_counter_prefers_smaller_card_when_both_save():
    st = _combat_state(phase="counter", life=3, blocker_id=None)
    st.players[0].characters = [CardInst(iid="atk", card_id="ATK5", rested=True, summoning_sick=False)]
    st.attack.attacker_iid = "atk"
    st.attack.declared_power = 5000
    st.players[1].hand = ["C2K", "C1K"]
    pick = pick_ai_action(st, 1, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "counter"
    assert int(pick.get("counter") or 0) == 1000


def test_save_last_don_to_ko_instead_of_1drop():
    st = _match(turn=3, first=False)
    st.players[0].turns_completed = 2
    st.players[0].don_active = 1
    st.players[0].don_given = 5
    st.players[0].hand = ["DROP1"]
    st.players[0].leader_rested = False
    st.players[1].characters = [CardInst(iid="wall", card_id="WALL6", rested=True, summoning_sick=False)]
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "attach_don"


def test_skip_fail_swing_without_when_attacking():
    st = _match(turn=2, first=False)
    st.players[0].turns_completed = 1
    st.players[0].leader_rested = True
    st.players[0].don_active = 0
    st.players[0].hand = []
    st.players[0].characters = [
        CardInst(iid="small", card_id="ATK4", rested=False, summoning_sick=False)
    ]
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") != "attack"


def test_pump_5k_vs_5k_when_opp_has_counter_in_hand():
    st = _match(turn=2, first=False)
    st.players[0].turns_completed = 1
    st.players[0].don_active = 1
    st.players[0].don_given = 3
    st.players[0].hand = ["DROP1"]
    st.players[0].leader_rested = False
    st.players[1].hand = ["C1K", "C1K", "C1K", "C2K"]
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "attach_don"


def test_keep_2k_counter_instead_of_dumping_1drop():
    st = _match(turn=3, first=False)
    st.players[0].turns_completed = 2
    st.players[0].don_active = 1
    st.players[0].don_given = 5
    st.players[0].hand = ["C2K"]
    st.players[0].leader_rested = False
    st.players[0].characters = [CardInst(iid="body", card_id="ATK5", rested=True, summoning_sick=False)]
    st.players[1].hand = ["C1K", "C1K", "C1K"]
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") != "play_card"


def test_blank_event_loses_to_character():
    st = _match(turn=3, first=False)
    st.players[0].turns_completed = 2
    st.players[0].don_active = 4
    st.players[0].hand = ["EVNT0", "ATK5"]
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "play_card"
    assert pick.get("card_id") == "ATK5"


def test_replace_sacrifices_weakest_body():
    st = _match(turn=4, first=False)
    st.players[0].turns_completed = 3
    st.players[0].don_active = 4
    st.players[0].hand = ["ATK5"]
    st.players[0].characters = [
        CardInst(iid="weak", card_id="DROP1", rested=True, summoning_sick=False),
        CardInst(iid="a", card_id="ATK5", rested=True, summoning_sick=False),
        CardInst(iid="b", card_id="ATK5", rested=True, summoning_sick=False),
        CardInst(iid="c", card_id="ATK8", rested=True, summoning_sick=False),
        CardInst(iid="d", card_id="BIG8", rested=True, summoning_sick=False),
    ]
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "play_card"
    assert pick.get("replace_iid") == "weak"


def test_search_early_prefers_2k_over_unplayable_top_end():
    st = _match(turn=2, first=False)
    st.players[0].don_given = 2
    st.players[0].don_active = 2
    st.pending_search = PendingSearch(
        seat=0,
        card_id="OP11-070",
        source_iid="c1",
        revealed=["BIG8", "C2K"],
        eligible=[0, 1],
        max_add=1,
        phase="pick",
        destination="hand",
        summary="Search",
    )
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "select_search"
    assert pick.get("card_id") == "C2K" or (
        int(pick.get("index", -1)) == 1
    )


def test_pump_4k_leader_to_connect_even_if_opp_has_hand():
    """Sabo-style 4k Leader still attaches +1000 to take life vs 5k."""
    st = _match(turn=2, first=False)
    st.players[0].leader_card_id = "LEAD4"
    st.players[0].turns_completed = 1
    st.players[0].don_active = 1
    st.players[0].don_given = 3
    st.players[0].hand = ["DROP1"]
    st.players[0].leader_rested = False
    st.players[1].hand = ["C1K", "C1K", "C1K", "C2K"]
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "attach_don"
    assert pick.get("target_iid") == "leader"


def test_character_does_not_feed_big_blocker():
    st = _match(turn=2, first=False)
    st.players[0].turns_completed = 1
    st.players[0].leader_rested = True
    st.players[0].don_active = 0
    st.players[0].hand = []
    st.players[0].characters = [
        CardInst(iid="atk", card_id="ATK5", rested=False, summoning_sick=False)
    ]
    st.players[1].characters = [
        CardInst(iid="blk", card_id="BLK9", rested=False, summoning_sick=False, keywords=["blocker"])
    ]
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert not (pick.get("type") == "attack" and pick.get("target_iid") == "leader")


def test_behind_on_life_swings_face_not_medium_ko():
    st = _match(turn=2, first=False)
    st.players[0].turns_completed = 1
    st.players[0].life = ["L"] * 4
    st.players[1].life = ["L"] * 5
    st.players[0].leader_rested = False
    st.players[0].don_active = 0
    st.players[0].hand = []
    st.players[1].hand = []
    st.players[1].characters = [
        CardInst(iid="mid", card_id="ATK5", rested=True, summoning_sick=False)
    ]
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "attack"
    assert pick.get("target_iid") == "leader"


def test_luffy_pays_return_don_even_if_ko_fizzles():
    st = _match(turn=3, first=False)
    st.players[0].leader_card_id = "OP09-061"
    st.players[0].don_active = 4
    st.players[0].don_given = 4
    st.pending_choice = PendingChoice(
        seat=0,
        card_id="OP09-077",
        source_iid="c1",
        target_kind="return_don",
        options=["don:active"],
        option_labels={"don:active": "don_active:4"},
        remaining_ops=[
            {"op": "return_don", "count": 2, "owner": "self", "as_cost": True, "optional": True},
            {"op": "ko", "target_kind": "opponent_character", "optional": True, "power_lte": 6000},
        ],
        optional=True,
        purpose="return_don",
        summary="Return 2 DON",
    )
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick == {"type": "select_choice", "target_iid": "don:active"}


def test_non_luffy_skips_return_don_when_followup_fizzles():
    st = _match(turn=3, first=False)
    st.players[0].don_active = 4
    st.players[0].don_given = 4
    st.pending_choice = PendingChoice(
        seat=0,
        card_id="OP09-077",
        source_iid="c1",
        target_kind="return_don",
        options=["don:active"],
        option_labels={"don:active": "don_active:4"},
        remaining_ops=[
            {"op": "return_don", "count": 2, "owner": "self", "as_cost": True, "optional": True},
            {"op": "ko", "target_kind": "opponent_character", "optional": True, "power_lte": 6000},
        ],
        optional=True,
        purpose="return_don",
        summary="Return 2 DON",
    )
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick == {"type": "skip_choice"}


def test_keep_leftover_don_when_already_connecting():
    st = _match(turn=2, first=False)
    st.players[0].turns_completed = 1
    st.players[0].leader_rested = True
    st.players[0].don_active = 2
    st.players[0].hand = []
    st.players[1].hand = []
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") != "attach_don"


def test_last_blocker_stays_up_instead_of_swinging_face():
    st = _match(turn=2, first=False)
    st.players[0].turns_completed = 1
    st.players[0].leader_rested = True
    st.players[0].don_active = 0
    st.players[0].hand = []
    st.players[0].characters = [
        CardInst(iid="blk", card_id="BLK9", rested=False, summoning_sick=False, keywords=["blocker"])
    ]
    st.players[1].life = ["L"] * 5
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert not (pick.get("type") == "attack" and pick.get("attacker_iid") == "blk")


def test_extra_turn_is_valued_and_own_board_wipe_is_penalized():
    st = _match()
    extra = _followup_worth(st, 0, [{"op": "extra_turn"}], _catalog)
    wipe = _followup_worth(
        st,
        0,
        [{"op": "return_to_bottom", "all": True, "target_kind": "own_character", "exclude_self": True}],
        _catalog,
    )
    bounce = _followup_worth(
        st,
        0,
        [{"op": "return_hand", "target_kind": "opponent_character"}],
        _catalog,
    )
    assert extra >= 40
    assert wipe < 0
    st.players[1].characters = [CardInst(iid="e", card_id="ATK5")]
    bounce2 = _followup_worth(
        st,
        0,
        [{"op": "return_hand", "target_kind": "opponent_character"}],
        _catalog,
    )
    assert bounce2 > bounce


def test_activate_main_beats_cheap_1drop_when_ramp_is_live():
    """Enel: DON ramp Activate before spending the last Active DON on a 1-drop."""
    st = _match(turn=3, first=False)
    st.players[0].leader_card_id = "OP15-058"
    st.players[0].turns_completed = 2
    st.players[0].don_active = 1
    st.players[0].don_rested = 0
    st.players[0].don_given = 5
    st.players[0].hand = ["DROP1"]
    st.players[0].characters = [
        CardInst(iid="mid", card_id="ATK5", rested=True, summoning_sick=False)
    ]
    st.players[0].leader_rested = False
    st.players[1].hand = []
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "activate_main"


def test_mihawk_plays_character_before_locking_activate():
    """OP14-020 then forbids playing Characters — develop the 1-drop first."""
    st = _match(turn=3, first=False)
    st.players[0].leader_card_id = "OP14-020"
    st.players[0].turns_completed = 2
    st.players[0].don_active = 1
    st.players[0].don_rested = 2
    st.players[0].don_given = 5
    st.players[0].hand = ["DROP1"]
    st.players[0].characters = [
        CardInst(iid="mid", card_id="ATK6", rested=True, summoning_sick=False)
    ]
    st.players[0].leader_rested = False
    st.players[1].hand = []
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "play_card"
    assert pick.get("card_id") == "DROP1"


def test_activate_skipped_when_field_cost_gate_fails():
    st = _match(turn=3, first=False)
    st.players[0].leader_card_id = "OP14-020"
    st.players[0].turns_completed = 2
    st.players[0].don_active = 1
    st.players[0].don_rested = 2
    st.players[0].hand = ["DROP1"]
    st.players[0].characters = []
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") != "activate_main"


def test_sabo_attaches_don_x1_when_8cost_is_on_field():
    st = _match(turn=4, first=False)
    st.players[0].leader_card_id = "OP13-004"
    st.players[0].life = ["L"] * 3
    st.players[0].turns_completed = 3
    st.players[0].don_active = 1
    st.players[0].don_given = 8
    st.players[0].leader_don = 0
    st.players[0].hand = ["DROP1"]
    st.players[0].characters = [
        CardInst(iid="big", card_id="BIG8", rested=True, summoning_sick=False)
    ]
    st.players[0].leader_rested = False
    st.players[1].hand = []
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "attach_don"
    assert pick.get("target_iid") == "leader"


def test_luffy_attaches_don_x1_when_bodies_exist():
    st = _match(turn=3, first=False)
    st.players[0].leader_card_id = "OP09-061"
    st.players[0].turns_completed = 2
    st.players[0].don_active = 1
    st.players[0].don_given = 5
    st.players[0].leader_don = 0
    st.players[0].hand = ["DROP1"]
    st.players[0].characters = [
        CardInst(iid="body", card_id="ATK5", rested=True, summoning_sick=False)
    ]
    st.players[0].leader_rested = False
    st.players[1].hand = []
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "attach_don"
    assert pick.get("target_iid") == "leader"


def test_luffy_plays_1drop_when_board_is_empty():
    st = _match(turn=2, first=False)
    st.players[0].leader_card_id = "OP09-061"
    st.players[0].turns_completed = 1
    st.players[0].don_active = 1
    st.players[0].don_given = 3
    st.players[0].leader_don = 0
    st.players[0].hand = ["DROP1"]
    st.players[0].characters = []
    st.players[0].leader_rested = False
    st.players[1].hand = []
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "play_card"
    assert pick.get("card_id") == "DROP1"


def test_rest_cost_prefers_rested_don_over_active():
    st = _match()
    st.players[0].don_active = 3
    st.players[0].don_rested = 2
    st.players[0].characters = [
        CardInst(iid="mid", card_id="ATK6", rested=True, summoning_sick=False)
    ]
    st.pending_choice = PendingChoice(
        seat=0,
        card_id="OP14-020",
        source_iid="leader",
        target_kind="own_character",
        options=["don:active", "don:rested", "leader"],
        remaining_ops=[
            {
                "op": "rest_character",
                "target_kind": "own_character",
                "as_cost": True,
                "optional": True,
                "include_don": True,
            },
            {"op": "active_don", "count": 3, "require_field_char_cost_gte": 5},
        ],
        optional=True,
        purpose="rest",
        summary="Rest own card",
    )
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick == {"type": "select_choice", "target_iid": "don:rested"}


def test_return_don_prefers_rested_over_active():
    st = _match(turn=3, first=False)
    st.players[0].leader_card_id = "OP09-061"
    st.players[0].don_active = 4
    st.players[0].don_rested = 2
    st.players[0].don_given = 6
    st.pending_choice = PendingChoice(
        seat=0,
        card_id="OP09-077",
        source_iid="c1",
        target_kind="return_don",
        options=["don:active", "don:rested"],
        option_labels={"don:active": "don_active:4", "don:rested": "don_rested:2"},
        remaining_ops=[
            {"op": "return_don", "count": 2, "owner": "self", "as_cost": True, "optional": True},
            {"op": "ko", "target_kind": "opponent_character", "optional": True, "power_lte": 6000},
        ],
        optional=True,
        purpose="return_don",
        summary="Return 2 DON",
    )
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick == {"type": "select_choice", "target_iid": "don:rested"}


def test_search_prefers_1k_over_offcurve_top_end():
    st = _match(turn=2, first=False)
    st.players[0].don_given = 2
    st.players[0].don_active = 2
    st.pending_search = PendingSearch(
        seat=0,
        card_id="OP11-070",
        source_iid="c1",
        revealed=["BIG8", "C1K"],
        eligible=[0, 1],
        max_add=1,
        phase="pick",
        destination="hand",
        summary="Search",
    )
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "select_search"
    assert pick.get("card_id") == "C1K" or int(pick.get("index", -1)) == 1


def test_ko_followup_ignores_overstat_targets():
    st = _match()
    dead = _followup_worth(
        st,
        0,
        [{"op": "ko", "target_kind": "opponent_character", "power_lte": 4000}],
        _combat_catalog,
    )
    st.players[1].characters = [CardInst(iid="wall", card_id="ATK8")]
    still_dead = _followup_worth(
        st,
        0,
        [{"op": "ko", "target_kind": "opponent_character", "power_lte": 4000}],
        _combat_catalog,
    )
    st.players[1].characters = [CardInst(iid="small", card_id="ATK4")]
    live = _followup_worth(
        st,
        0,
        [{"op": "ko", "target_kind": "opponent_character", "power_lte": 4000}],
        _combat_catalog,
    )
    assert dead == 0
    assert still_dead == 0
    assert live >= 14


def test_counter_passes_instead_of_2k_on_chump():
    st = _combat_state(phase="counter", life=5, blocker_id=None)
    st.players[0].characters = [
        CardInst(iid="atk", card_id="C2K", rested=True, summoning_sick=False)
    ]
    st.players[1].characters = [
        CardInst(iid="chump", card_id="DROP1", rested=True, summoning_sick=False)
    ]
    st.players[1].hand = ["C2K"]
    st.attack.attacker_iid = "atk"
    st.attack.target_iid = "chump"
    st.attack.declared_power = 2000
    pick = pick_ai_action(st, 1, _combat_catalog)
    assert pick == {"type": "pass_counter"}


def test_rush_grant_prefers_summoning_sick():
    st = _match()
    st.players[0].characters = [
        CardInst(iid="ready", card_id="ATK8", rested=False, summoning_sick=False),
        CardInst(iid="sick", card_id="ATK8", rested=False, summoning_sick=True),
    ]
    st.pending_choice = PendingChoice(
        seat=0,
        card_id="OP16-001",
        source_iid="leader",
        target_kind="own_character",
        options=["ready", "sick"],
        remaining_ops=[{"op": "grant_keyword", "keyword": "rush", "optional": True}],
        optional=True,
        purpose="grant_keyword",
        summary="Gain Rush",
    )
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick == {"type": "select_choice", "target_iid": "sick"}


def test_take_life_at_five_instead_of_countering():
    st = _combat_state(phase="counter", life=5, blocker_id=None)
    st.players[1].leader_card_id = "OP16-001"
    st.players[0].characters = [CardInst(iid="atk", card_id="ATK5", rested=True, summoning_sick=False)]
    st.attack.attacker_iid = "atk"
    st.attack.declared_power = 5000
    st.players[1].hand = ["C1K"]
    pick = pick_ai_action(st, 1, _combat_catalog)
    assert pick == {"type": "pass_counter"}


def test_four_life_leader_counters_at_four():
    st = _combat_state(phase="counter", life=4, blocker_id=None)
    st.players[1].leader_card_id = "OP09-061"
    st.players[0].characters = [CardInst(iid="atk", card_id="ATK5", rested=True, summoning_sick=False)]
    st.attack.attacker_iid = "atk"
    st.attack.declared_power = 5000
    st.players[1].hand = ["C1K"]
    pick = pick_ai_action(st, 1, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "counter"


def test_skip_flip_life_when_low():
    st = _match()
    st.players[0].life = ["L", "L"]
    st.pending_choice = PendingChoice(
        seat=0,
        card_id="OP08-058",
        source_iid="leader",
        target_kind="life_position",
        options=["life:top"],
        remaining_ops=[
            {"op": "flip_life", "face": "up", "position": "top", "as_cost": True, "optional": True},
            {"op": "gain_don", "count": 1, "as_rested": True},
        ],
        optional=True,
        purpose="life",
        summary="Flip Life",
    )
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick == {"type": "skip_choice"}


def test_skip_trashing_last_2k_at_low_life():
    st = _match()
    st.players[0].life = ["L", "L"]
    st.players[0].hand = ["C2K"]
    st.pending_choice = PendingChoice(
        seat=0,
        card_id="OP09-062",
        source_iid="leader",
        target_kind="hand",
        options=["hand:0:C2K"],
        remaining_ops=[
            {"op": "trash_hand", "count": 1, "as_cost": True, "optional": True, "require_trigger": True},
            {"op": "gain_don", "count": 1, "as_rested": True},
        ],
        optional=True,
        purpose="trash",
        summary="Trash Trigger",
    )
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick == {"type": "skip_choice"}


def test_pass_cheap_chump_at_full_life():
    st = _combat_state(phase="block", life=5, blocker_id="CHP2")
    st.players[1].leader_card_id = "OP16-001"
    pick = pick_ai_action(st, 1, _combat_catalog)
    assert pick == {"type": "block", "blocker_iid": None}


def test_enel_once_activate_beats_oncurve_5drop():
    """OP15-058 once-per-turn +5 DON must beat playing a vanilla 5-drop when the field body is bigger."""
    st = _match(turn=3, first=False)
    st.players[0].leader_card_id = "OP15-058"
    st.players[0].turns_completed = 2
    st.players[0].don_active = 5
    st.players[0].don_given = 5
    st.players[0].hand = ["ATK5"]
    st.players[0].characters = [
        CardInst(iid="mid", card_id="ATK6", rested=True, summoning_sick=False)
    ]
    st.players[0].leader_rested = False
    st.players[1].hand = []
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "activate_main"


def test_keep_last_don_instead_of_4drop_when_attach_closes():
    st = _match(turn=3, first=False)
    st.players[0].turns_completed = 2
    st.players[0].don_active = 4
    st.players[0].don_given = 4
    st.players[0].hand = ["ATK5"]
    st.players[0].leader_rested = False
    st.players[1].hand = ["C1K", "C1K", "C2K"]
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "attach_don"


def test_behind_still_kos_overstat_attacker():
    st = _match(turn=2, first=False)
    st.players[0].turns_completed = 1
    st.players[0].life = ["L"] * 4
    st.players[1].life = ["L"] * 5
    st.players[0].leader_rested = True
    st.players[0].don_active = 0
    st.players[0].hand = []
    st.players[1].hand = []
    st.players[0].characters = [
        CardInst(iid="atk", card_id="ATK8", rested=False, summoning_sick=False)
    ]
    st.players[1].characters = [
        CardInst(iid="big", card_id="ATK8", rested=True, summoning_sick=False)
    ]
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "attack"
    assert pick.get("target_iid") == "big"


def test_ko_choice_prefers_power_over_blank_8cost():
    st = _match()
    st.players[1].characters = [
        CardInst(iid="blank", card_id="ZERO8"),
        CardInst(iid="threat", card_id="ATK8"),
    ]
    st.pending_choice = PendingChoice(
        seat=0,
        card_id="X",
        source_iid="s",
        target_kind="opponent_character",
        options=["blank", "threat"],
        remaining_ops=[{"op": "ko", "target_kind": "opponent_character"}],
        optional=True,
        purpose="ko",
        summary="KO 1 opponent Character",
    )
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick == {"type": "select_choice", "target_iid": "threat"}


def test_full_board_does_not_replace_8k_with_weaker_body():
    st = _match(turn=4, first=False)
    st.players[0].turns_completed = 3
    st.players[0].don_active = 3
    st.players[0].hand = ["ATK4"]
    st.players[0].leader_rested = False
    st.players[0].characters = [
        CardInst(iid=f"b{i}", card_id="ATK8", rested=True, summoning_sick=False)
        for i in range(5)
    ]
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") != "play_card"


def test_luffy_pumps_attacker_to_connect_before_cost_aura():
    """DON×1 +1 cost must not beat attaching the last DON to take Life."""
    st = _match(turn=3, first=False)
    st.players[0].leader_card_id = "OP09-061"
    st.players[0].turns_completed = 2
    st.players[0].don_active = 1
    st.players[0].don_given = 5
    st.players[0].leader_don = 0
    st.players[0].hand = []
    st.players[0].leader_rested = True
    st.players[0].characters = [
        CardInst(iid="atk", card_id="ATK4", rested=False, summoning_sick=False)
    ]
    st.players[1].hand = []
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "attach_don"
    assert pick.get("target_iid") == "atk"


def test_hold_blocker_for_bigger_second_attack():
    st = _combat_state(phase="block", life=5, blocker_id="CHP2")
    st.players[1].leader_card_id = "OP16-001"
    st.players[0].characters = [
        CardInst(iid="atk", card_id="ATK5", rested=True, summoning_sick=False),
        CardInst(iid="big", card_id="ATK8", rested=False, summoning_sick=False),
    ]
    st.attack.attacker_iid = "atk"
    st.attack.declared_power = 5000
    pick = pick_ai_action(st, 1, _combat_catalog)
    assert pick == {"type": "block", "blocker_iid": None}


def test_hold_counter_for_bigger_second_attack():
    st = _combat_state(phase="counter", life=3, blocker_id=None)
    st.players[1].leader_card_id = "OP09-061"
    st.players[0].characters = [
        CardInst(iid="atk", card_id="ATK5", rested=True, summoning_sick=False),
        CardInst(iid="big", card_id="ATK8", rested=False, summoning_sick=False),
    ]
    st.attack.attacker_iid = "atk"
    st.attack.declared_power = 5000
    st.players[1].hand = ["C1K"]
    pick = pick_ai_action(st, 1, _combat_catalog)
    assert pick == {"type": "pass_counter"}


def test_does_not_dump_2k_as_a_body_when_board_exists():
    st = _match(turn=3, first=False)
    st.players[0].turns_completed = 2
    st.players[0].don_active = 3
    st.players[0].don_given = 5
    st.players[0].hand = ["C2K"]
    st.players[0].leader_rested = False
    st.players[0].characters = [
        CardInst(iid="body", card_id="ATK5", rested=True, summoning_sick=False)
    ]
    st.players[1].hand = []
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") != "play_card"


def test_blank_event_is_not_played_after_attacks():
    st = _match(turn=3, first=False)
    st.players[0].turns_completed = 2
    st.players[0].don_active = 4
    st.players[0].hand = ["EVNT0"]
    st.players[0].leader_rested = True
    st.players[0].characters = []
    st.players[1].hand = []
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") != "play_card"


def test_second_don_to_beat_likely_2k():
    """6k still dies to a 2k; with 4+ cards in hand, pump once more to 7k."""
    st = _match(turn=2, first=False)
    st.players[0].turns_completed = 1
    st.players[0].don_active = 1
    st.players[0].don_given = 4
    st.players[0].leader_don = 1
    st.players[0].hand = []
    st.players[0].leader_rested = False
    st.players[1].hand = ["C1K", "C1K", "C2K", "C2K"]
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "attach_don"
    assert pick.get("target_iid") == "leader"


def test_close_out_races_instead_of_medium_ko():
    st = _match(turn=3, first=False)
    st.players[0].turns_completed = 2
    st.players[0].life = ["L"] * 5
    st.players[1].life = ["L"] * 2
    st.players[0].don_active = 0
    st.players[0].hand = []
    st.players[1].hand = []
    st.players[0].leader_rested = True
    st.players[0].characters = [
        CardInst(iid="a", card_id="ATK5", rested=False, summoning_sick=False),
        CardInst(iid="b", card_id="ATK5", rested=False, summoning_sick=False),
    ]
    st.players[1].characters = [
        CardInst(iid="mid", card_id="ATK5", rested=True, summoning_sick=False)
    ]
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "attack"
    assert pick.get("target_iid") == "leader"


def test_enel_plays_8drop_before_attach4_activate():
    """Play the 8-drop first so Enel's attach-4 lands on it, not the 4k."""
    st = _match(turn=4, first=False)
    st.players[0].leader_card_id = "OP15-058"
    st.players[0].turns_completed = 3
    st.players[0].don_active = 8
    st.players[0].don_given = 8
    st.players[0].don_rested = 4
    st.players[0].hand = ["BIG8"]
    st.players[0].characters = [
        CardInst(iid="small", card_id="ATK4", rested=False, summoning_sick=False)
    ]
    st.players[0].leader_rested = False
    st.players[1].hand = []
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "play_card"
    assert pick.get("card_id") == "BIG8"


def test_enel_attach4_prefers_new_big_body():
    """4 rested DON should sit on the 8-drop, not a ready 4k that connects this turn."""
    st = _match()
    st.players[0].leader_card_id = "OP15-058"
    st.players[0].characters = [
        CardInst(iid="small", card_id="ATK4", rested=False, summoning_sick=False),
        CardInst(iid="big", card_id="BIG8", rested=False, summoning_sick=True),
    ]
    st.pending_choice = PendingChoice(
        seat=0,
        card_id="OP15-058",
        source_iid="leader",
        target_kind="own_character",
        options=["small", "big"],
        remaining_ops=[
            {"op": "attach_don", "count": 4, "as_rested": True, "target_kind": "own_character"}
        ],
        optional=True,
        purpose="attach_don",
        summary="Attach 4 rested DON",
    )
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick == {"type": "select_choice", "target_iid": "big"}


def test_luffy_plays_don_minus_2_even_if_ko_fizzles():
    """OP09-077 with no 6k target still triggers Luffy's +1 active / +1 rested."""
    st = _match(turn=3, first=False)
    st.players[0].leader_card_id = "OP09-061"
    st.players[0].turns_completed = 2
    st.players[0].don_active = 4
    st.players[0].don_given = 4
    st.players[0].hand = ["OP09-077"]
    st.players[0].leader_rested = True
    st.players[1].characters = []
    st.players[1].hand = []
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "play_card"
    assert pick.get("card_id") == "OP09-077"


def test_non_luffy_skips_don_minus_2_when_ko_fizzles():
    st = _match(turn=3, first=False)
    st.players[0].turns_completed = 2
    st.players[0].don_active = 4
    st.players[0].don_given = 4
    st.players[0].hand = ["OP09-077"]
    st.players[0].leader_rested = True
    st.players[1].characters = []
    st.players[1].hand = []
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") != "play_card" or pick.get("card_id") != "OP09-077"


def test_banish_leader_goes_face_instead_of_medium_ko():
    """Robin 【消失】 should trash Life, not spend the swing KOing a 5k."""
    st = _match(turn=2, first=False)
    st.players[0].leader_card_id = "OP09-062"
    st.players[0].turns_completed = 1
    st.players[0].life = ["L"] * 4
    st.players[1].life = ["L"] * 5
    st.players[0].don_active = 0
    st.players[0].hand = []
    st.players[1].hand = []
    st.players[0].leader_rested = False
    st.players[0].characters = []
    st.players[1].characters = [
        CardInst(iid="mid", card_id="ATK5", rested=True, summoning_sick=False)
    ]
    pick = pick_ai_action(st, 0, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "attack"
    assert pick.get("attacker_iid") == "leader"
    assert pick.get("target_iid") == "leader"


def test_counter_event_plus4000_saves_when_2k_does_not():
    st = _combat_state(phase="counter", life=3, blocker_id=None)
    st.players[1].leader_card_id = "OP09-061"
    st.players[1].don_active = 2
    st.players[1].don_rested = 2
    st.players[1].don_given = 4
    st.players[0].characters = [
        CardInst(iid="atk", card_id="ATK8", rested=True, summoning_sick=False)
    ]
    st.attack.attacker_iid = "atk"
    st.attack.declared_power = 8000
    st.players[1].hand = ["OP09-078", "C2K"]
    pick = pick_ai_action(st, 1, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "counter"
    assert pick.get("card_id") == "OP09-078"


def test_counter_prefers_1k_over_plus4000_event_when_both_save():
    st = _combat_state(phase="counter", life=3, blocker_id=None)
    st.players[1].leader_card_id = "OP09-061"
    st.players[1].don_active = 2
    st.players[1].don_rested = 2
    st.players[1].don_given = 4
    st.players[0].characters = [
        CardInst(iid="atk", card_id="ATK5", rested=True, summoning_sick=False)
    ]
    st.attack.attacker_iid = "atk"
    st.attack.declared_power = 5000
    st.players[1].hand = ["OP09-078", "C1K"]
    pick = pick_ai_action(st, 1, _combat_catalog)
    assert pick is not None
    assert pick.get("type") == "counter"
    assert int(pick.get("counter") or 0) == 1000

