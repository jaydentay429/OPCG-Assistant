"""Battle-critical rules catalog from 综合规则 V1.2.0.

Each entry records the official rule id, a short summary, implementation status,
and engine references. Tournament / sleeve / floor rules are intentionally omitted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RuleStatus = Literal["implemented", "partial", "missing"]


@dataclass(frozen=True)
class RuleEntry:
    id: str
    title: str
    summary: str
    status: RuleStatus
    refs: tuple[str, ...] = ()


# Core battle rules we track against the engine. Status reflects wiring after this module.
RULES: dict[str, RuleEntry] = {
    "1-2-1-1-1": RuleEntry(
        "1-2-1-1-1",
        "Defeat: life 0 then Leader damaged",
        "When life is 0 and Leader takes damage, that player loses.",
        "implemented",
        ("battle.rules.checkpoints.rule_process", "battle.engine._deal_one_life_damage"),
    ),
    "1-2-1-1-2": RuleEntry(
        "1-2-1-1-2",
        "Defeat: deck empty",
        "When a player's deck has 0 cards, they lose at the next rule-processing point.",
        "implemented",
        ("battle.rules.checkpoints.rule_process",),
    ),
    "1-2-2": RuleEntry(
        "1-2-2",
        "Deferred defeat via rule processing",
        "Defeat conditions are applied at the next rule-processing point (Ch.9). "
        "If both players would lose simultaneously, the lower seat is processed first (engine simplification).",
        "partial",
        ("battle.rules.checkpoints.rule_process",),
    ),
    "1-2-3": RuleEntry(
        "1-2-3",
        "Concede",
        "A player may concede at any time and loses immediately.",
        "implemented",
        ("battle.rules.checkpoints.concede",),
    ),
    "1-3-1": RuleEntry(
        "1-3-1",
        "Card text overrules comprehensive rules",
        "When card text conflicts with these rules, card text wins.",
        "implemented",
        (),
    ),
    "5-2-1": RuleEntry(
        "5-2-1",
        "Game setup",
        "Shuffle, draw 5, mulligan, place Life, determine first player, start turn.",
        "partial",
        ("battle.engine.start_match", "battle.engine._do_mulligan", "battle.engine._place_life"),
    ),
    "5-2-1-6": RuleEntry(
        "5-2-1-6",
        "Mulligan",
        "First then second player may redraw opening hand once.",
        "implemented",
        ("battle.engine._do_mulligan",),
    ),
    "5-2-1-7": RuleEntry(
        "5-2-1-7",
        "Place Life after mulligan",
        "Life is placed from the top of the deck after mulligan completes.",
        "implemented",
        ("battle.engine._place_life",),
    ),
    "6-2-3": RuleEntry(
        "6-2-3",
        "Refresh: return attached DON!!",
        "Attached DON!! return to cost area as rested, then become active.",
        "implemented",
        ("battle.engine._begin_turn",),
    ),
    "6-2-4": RuleEntry(
        "6-2-4",
        "Refresh: active rested cards",
        "Rested Leader/Characters/Stages become active; clear summoning sickness.",
        "implemented",
        ("battle.engine._begin_turn",),
    ),
    "6-3-1": RuleEntry(
        "6-3-1",
        "Draw phase",
        "Draw 1 except first player's first turn.",
        "implemented",
        ("battle.engine._begin_turn",),
    ),
    "6-4-1": RuleEntry(
        "6-4-1",
        "DON!! phase",
        "Gain 2 DON!! (1 on first player's first turn), capped at 10 given.",
        "implemented",
        ("battle.engine._begin_turn",),
    ),
    "6-5-5-2": RuleEntry(
        "6-5-5-2",
        "DON!! power only on your turn",
        "Attached DON!! raise power only during that player's turn.",
        "implemented",
        ("battle.engine.inst_power",),
    ),
    "6-5-6-1": RuleEntry(
        "6-5-6-1",
        "No attack on first turn",
        "Neither player may attack on their first turn.",
        "implemented",
        ("battle.engine._declare_attack", "battle.engine.legal_actions"),
    ),
    "6-6-1-1": RuleEntry(
        "6-6-1-1",
        "End phase: end-of-turn effects",
        "Resolve 【我方的回合结束时】 then 【对方的回合结束时】.",
        "implemented",
        ("battle.engine._end_turn", "battle.engine._continue_end_phase"),
    ),
    "6-6-1-2": RuleEntry(
        "6-6-1-2",
        "End phase: until end of turn cleanup",
        "Expire this-turn power_mod / base_power_override / cannot_be_ko / battle buffs. "
        "power_override (until start of your next turn) is cleared at your next Refresh, not here.",
        "partial",
        ("battle.engine._clear_turn_duration_effects", "battle.engine._begin_turn"),
    ),
    "6-2-2": RuleEntry(
        "6-2-2",
        "Start of your turn",
        "After Refresh, 【我方的回合开始时】 abilities may fire.",
        "implemented",
        ("battle.engine._begin_turn", "battle.engine._fire_board_timing"),
    ),
    "6-5-1": RuleEntry(
        "6-5-1",
        "Main phase start",
        "At the start of Main, 【主要】/main-start hooks may fire.",
        "implemented",
        ("battle.engine._begin_turn", "battle.engine._fire_board_timing"),
    ),
    "7-1-1": RuleEntry(
        "7-1-1",
        "Declare attack",
        "Rest attacker and declare target; 【攻击时】 resolves before Block step.",
        "implemented",
        ("battle.engine._declare_attack",),
    ),
    "8-1-3-1-1": RuleEntry(
        "8-1-3-1-1",
        "Automatic ability timings",
        "On Play / On Opponent's Attack / On K.O. and similar automatic timings.",
        "implemented",
        ("battle.engine._play_card", "battle.engine._fire_board_timing", "battle.engine._resolve_attack"),
    ),
    "10-2-1": RuleEntry(
        "10-2-1",
        "On Play keyword",
        "When a Character/Event/Stage is played, resolve 【登场时】.",
        "implemented",
        ("battle.engine._play_card",),
    ),
    "10-2-2": RuleEntry(
        "10-2-2",
        "When Attacking keyword",
        "When declaring an attack with this card, resolve 【攻击时】.",
        "implemented",
        ("battle.engine._declare_attack",),
    ),
    "10-2-5": RuleEntry(
        "10-2-5",
        "On K.O. keyword",
        "When this Character is K.O.'d, resolve 【KO时】.",
        "implemented",
        ("battle.engine._resolve_attack",),
    ),
    "10-2-6": RuleEntry(
        "10-2-6",
        "On Block keyword",
        "After declaring Blocker, resolve 【阻挡时】.",
        "implemented",
        ("battle.engine._choose_block",),
    ),
    "10-2-9": RuleEntry(
        "10-2-9",
        "Banish",
        "Keyword Banish: when this card deals damage to Leader, trash the Life card instead of taking it to hand.",
        "implemented",
        ("battle.engine._deal_one_life_damage", "battle.effects.has_banish"),
    ),
    "10-2-10": RuleEntry(
        "10-2-10",
        "Double Attack",
        "Keyword Double Attack: deal an extra Life damage when winning against Leader.",
        "implemented",
        ("battle.engine._resolve_attack", "battle.effects.has_double_attack"),
    ),
    "10-2-11": RuleEntry(
        "10-2-11",
        "When DON!! attached",
        "When DON!! is attached to this card, resolve 【咚附加时】 / on_don_attached.",
        "implemented",
        ("battle.engine._attach_don",),
    ),
    "7-1-1-2": RuleEntry(
        "7-1-1-2",
        "Attack targets",
        "May attack Leader or rested opposing Characters.",
        "implemented",
        ("battle.engine._declare_attack",),
    ),
    "7-1-2-2": RuleEntry(
        "7-1-2-2",
        "On Block",
        "After declaring Blocker, resolve 【阻挡时】 effects.",
        "implemented",
        ("battle.engine._choose_block",),
    ),
    "7-1-3-1-1": RuleEntry(
        "7-1-3-1-1",
        "Counter icons",
        "Trash Character with Counter icon from hand to buff power this battle.",
        "implemented",
        ("battle.engine._play_counter",),
    ),
    "7-1-3-1-3": RuleEntry(
        "7-1-3-1-3",
        "Cancel battle if combatant left",
        "If attacker or attack target left the field after Counter step, skip damage.",
        "implemented",
        ("battle.rules.checkpoints.combatants_present", "battle.engine._resolve_attack"),
    ),
    "9-1-1": RuleEntry(
        "9-1-1",
        "Rule processing basics",
        "Rule processing resolves when specific events occur.",
        "implemented",
        ("battle.rules.checkpoints.rule_process",),
    ),
    "9-2-1": RuleEntry(
        "9-2-1",
        "Rule processing: apply defeats",
        "At rule processing, players who meet defeat conditions lose.",
        "implemented",
        ("battle.rules.checkpoints.rule_process",),
    ),
    "10-1-5": RuleEntry(
        "10-1-5",
        "Trigger choice",
        "Optional Trigger while resolving life damage.",
        "implemented",
        ("battle.engine._deal_one_life_damage", "battle.engine._resolve_trigger"),
    ),
    "10-2-3": RuleEntry(
        "10-2-3",
        "Blocker",
        "Keyword Blocker may redirect an attack by resting.",
        "implemented",
        ("battle.engine.legal_actions", "battle.engine._choose_block"),
    ),
    "10-2-4": RuleEntry(
        "10-2-4",
        "Rush",
        "Rush / Rush Character override summoning sickness for attacks.",
        "implemented",
        ("battle.engine._declare_attack",),
    ),
    "10-2-7": RuleEntry(
        "10-2-7",
        "End of your turn keyword",
        "Fires in end phase for the turn player.",
        "implemented",
        ("battle.engine._continue_end_phase",),
    ),
    "10-2-8": RuleEntry(
        "10-2-8",
        "End of opponent's turn keyword",
        "Fires in end phase for the non-turn player.",
        "implemented",
        ("battle.engine._continue_end_phase",),
    ),
    "3-7-6-1": RuleEntry(
        "3-7-6-1",
        "Character area limit 5",
        "At most 5 Characters; playing a 6th requires replacing one to trash.",
        "implemented",
        ("battle.engine._play_card",),
    ),
}


def get_rule(rule_id: str) -> RuleEntry | None:
    return RULES.get(rule_id)


def rules_by_status(status: RuleStatus) -> list[RuleEntry]:
    return [r for r in RULES.values() if r.status == status]


def all_rule_ids() -> list[str]:
    return sorted(RULES.keys(), key=lambda x: [int(p) if p.isdigit() else p for p in x.split("-")])
