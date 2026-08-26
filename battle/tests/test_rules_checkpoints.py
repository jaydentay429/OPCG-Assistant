"""Tests for official rules checkpoints wired into the battle engine."""

from __future__ import annotations

from battle.engine import apply_action, legal_actions, start_match
from battle.rules.catalog import RULES, get_rule, rules_by_status
from battle.rules.checkpoints import combatants_present, concede, rule_process
from battle.rules import timings
from battle.state import CardInst, MatchState, PendingAttack, PlayerState


def _catalog(cid: str) -> dict:
    base = {
        "card_id": cid,
        "name": cid,
        "name_en": cid,
        "cost": 2,
        "power": 4000,
        "card_type_en": "CHARACTER",
        "traits_en": [],
        "effect": "",
        "effect_en": "",
    }
    if cid == "LDR":
        return {**base, "card_type_en": "LEADER", "life": 5, "power": 5000}
    if cid == "BLK":
        return {
            **base,
            "effect": "【防禦】【阻擋時】抽1張卡片。",
            "effect_en": "[Blocker] [On Block] Draw 1 card.",
            "keywords": ["blocker"],
        }
    if cid == "EOT":
        return {
            **base,
            "effect": "【我方的回合結束時】抽1張卡片。",
            "effect_en": "[End of Your Turn] Draw 1 card.",
        }
    if cid == "OATK":
        return {
            **base,
            "effect": "【對方的攻擊時】這張角色卡力量值+1000。",
            "effect_en": "[On Your Opponent's Attack] This Character gains +1000 power.",
        }
    return base


def _state_two_players() -> MatchState:
    state = MatchState(room_code="RULES", status="playing", phase="main", turn_seat=0, first_seat=0)
    state.players = [
        PlayerState(
            seat=0,
            user_id="u0",
            username="P0",
            is_ai=False,
            leader_card_id="LDR",
            deck=["D1", "D2", "D3", "D4", "D5"],
            hand=[],
            characters=[],
            turns_completed=1,
            don_active=5,
            don_given=5,
        ),
        PlayerState(
            seat=1,
            user_id="u1",
            username="P1",
            is_ai=False,
            leader_card_id="LDR",
            deck=["E1", "E2", "E3"],
            hand=[],
            characters=[],
            turns_completed=1,
            don_active=5,
            don_given=5,
        ),
    ]
    return state


def test_catalog_has_core_battle_rules():
    for rid in ("6-6-1-1", "7-1-3-1-3", "1-2-3", "9-2-1", "7-1-2-2"):
        assert get_rule(rid) is not None
        assert get_rule(rid).status in {"implemented", "partial"}
    assert "end_of_your_turn" in timings.TIMING_RULE_REFS
    assert len(RULES) >= 20


def test_concede_immediate_loss():
    state = _state_two_players()
    r = concede(state, 0)
    assert r["ok"]
    assert state.status == "finished"
    assert state.winner_seat == 1
    assert any(e.get("key") == "play.log.concedes" for e in state.log)


def test_concede_action_legal():
    state = _state_two_players()
    actions = legal_actions(state, 0, _catalog)
    assert any(a.get("type") == "concede" for a in actions)
    r = apply_action(state, 0, {"type": "concede"}, _catalog)
    assert r["ok"]
    assert state.winner_seat == 1


def test_end_turn_fires_end_of_your_turn_draw():
    state = _state_two_players()
    # Character with end-of-turn draw
    state.players[0].characters = [CardInst(iid="eot1", card_id="EOT")]
    hand_before = len(state.players[0].hand)
    deck_before = len(state.players[0].deck)
    r = apply_action(state, 0, {"type": "end_turn"}, _catalog)
    assert r["ok"]
    # End phase completed → next player's turn
    assert state.turn_seat == 1
    assert state.phase == "main"
    # Drew from end-of-turn (before next player's begin_turn which draws for seat 1)
    assert len(state.players[0].hand) == hand_before + 1
    assert len(state.players[0].deck) == deck_before - 1


def test_combatants_present_and_cancel():
    state = _state_two_players()
    state.players[0].characters = [CardInst(iid="atk", card_id="X")]
    state.players[1].characters = [CardInst(iid="def", card_id="Y", rested=True)]
    state.attack = PendingAttack(
        attacker_seat=0,
        attacker_iid="atk",
        target_iid="def",
        declared_power=4000,
    )
    state.phase = "counter"
    assert combatants_present(state)
    # Remove attacker mid-battle
    state.players[0].characters.clear()
    assert not combatants_present(state)
    r = apply_action(state, 1, {"type": "pass_counter"}, _catalog)
    assert r["ok"]
    assert state.attack is None
    assert state.phase == "main"
    assert any(e.get("key") == "play.log.battle_cancelled" for e in state.log)


def test_on_block_draw():
    state = _state_two_players()
    state.players[0].characters = [CardInst(iid="atk", card_id="X")]
    state.players[0].turns_completed = 1
    state.players[1].characters = [CardInst(iid="blk", card_id="BLK")]
    state.players[1].deck = ["Z1", "Z2"]
    state.attack = PendingAttack(
        attacker_seat=0,
        attacker_iid="atk",
        target_iid="leader",
        declared_power=4000,
    )
    state.phase = "block"
    hand_before = len(state.players[1].hand)
    r = apply_action(state, 1, {"type": "block", "blocker_iid": "blk"}, _catalog)
    assert r["ok"]
    assert state.attack and state.attack.blocker_iid == "blk"
    # On Block draw 1
    assert len(state.players[1].hand) == hand_before + 1


def test_rule_process_deck_empty():
    state = _state_two_players()
    state.players[0].deck = []
    rule_process(state)
    assert state.status == "finished"
    assert state.winner_seat == 1


def test_timings_constants_match_schema():
    from battle.effect_schema import TIMINGS

    for t in (
        timings.END_OF_YOUR_TURN,
        timings.END_OF_OPPONENT_TURN,
        timings.ON_BLOCK,
        timings.ON_OPPONENT_ATTACK,
        timings.TURN_START,
        timings.MAIN_START,
        timings.ON_DON_ATTACHED,
    ):
        assert t in TIMINGS


def test_catalog_has_no_missing_and_tracks_timings():
    assert rules_by_status("missing") == []
    for rid in (
        "8-1-3-1-1",
        "10-2-1",
        "10-2-2",
        "10-2-5",
        "10-2-6",
        "6-2-2",
        "6-5-1",
        "10-2-9",
        "10-2-10",
        "10-2-11",
    ):
        assert get_rule(rid) is not None
        assert get_rule(rid).status in {"implemented", "partial"}


def test_simultaneous_deck_out_lower_seat_loses_first():
    state = _state_two_players()
    state.players[0].deck = []
    state.players[1].deck = []
    rule_process(state)
    assert state.status == "finished"
    # Lower seat processed first → seat 0 loses → seat 1 wins
    assert state.winner_seat == 1


def test_power_override_survives_eot_clears_on_own_turn():
    from battle.engine import _begin_turn, _clear_turn_duration_effects

    state = _state_two_players()
    state.players[0].deck = ["D"] * 10
    state.players[1].deck = ["D"] * 10
    ch = CardInst(iid="c1", card_id="X", power_override=7000, base_power_override=5000, cannot_be_ko=True)
    state.players[0].characters = [ch]
    _clear_turn_duration_effects(state)
    assert ch.power_override == 7000
    assert ch.base_power_override is None
    assert ch.cannot_be_ko is False
    _begin_turn(state, 0, _catalog)
    assert ch.power_override is None
