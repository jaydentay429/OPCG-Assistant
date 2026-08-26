"""Structured effect schema: timings, ops vocabulary, and validators."""

from __future__ import annotations

import re
from typing import Any

TIMINGS = frozenset(
    {
        "on_play",
        "activate_main",
        "trigger",
        "when_attacking",
        "on_block",
        "on_opponent_attack",
        "on_own_leader_battle",
        "on_ko",
        "on_life_damage",
        "end_of_your_turn",
        "end_of_opponent_turn",
        "turn_start",
        "main_start",
        "your_turn",
        "opponent_turn",
        "don_attached",
        "counter_event",
        "on_don_attached",
        "on_don_phase",
        "on_don_returned",
        "hand_cost",
        "on_event",
        "on_trigger",
        "on_opp_event",
        "on_opp_trigger",
        "on_opponent_play",
        "end_of_battle",
        "on_game_start",
    }
)

ABILITY_STATUSES = frozenset({"compiled", "verified", "needs_review", "unsupported"})

# Ops the engine can execute (or pause for targeting / search).
ALLOWED_OPS = frozenset(
    {
        "draw",
        "gain_don",
        "set_don",
        "equalize_don_to_opponent",
        "extra_turn",
        "rest_opponent_character",
        "rest_character",
        "buff",
        "buff_self",
        "set_base_power_from_opponent_leader",
        "set_base_power_from_character",
        "set_base_power_from_attacker",
        "set_base_power",
        "swap_base_power",
        "set_power_equal_opponent_leader",
        "continuous_base_from_own_leader_printed",
        "ko",
        "ko_lowest_opponent",
        "search_deck",
        "play_from_hand",
        "trash",
        "return_to_hand",
        "return_to_bottom",
        "add_life",
        "deal_life_damage",
        "rest_don",
        "active_don",
        "return_don",
        "return_attached_don",
        "attach_don",
        "set_character_active",
        "grant_keyword",
        "grant_attribute",
        "cannot_be_ko",
        "cannot_be_rested",
        "cannot_be_removed",
        "trash_hand",
        "trash_deck_top",
        "reduce_cost",
        "buff_all_own",
        "static_reduce_opp_cost",
        "hand_cost_reduce",
        "choose_target",
        "deny_blocker",
        "allow_attack_active",
        "replace_battle_ko",
        "win_game",
        "arm_untap_on_char_battle",
        "arm_draw_on_event",
        "cannot_attack_char_base_cost_lte",
        "rest_opponent_char_or_don",
        "cannot_take_life",
        "skip_untap",
        "reorder_life",
        "negate_effects",
        "negate_on_play",
        "opponent_hand_to_bottom",
        "trash_to_bottom",
        "cannot_attack",
        "cannot_active_don_by_character",
        "cannot_draw_by_effect",
        "taunt",
        "activate_timing",
        "add_from_trash",
        "cannot_play_from_hand",
        "hand_to_deck",
        "reveal_opp_hand",
        "reveal_hand",
        "grant_cost",
        "redirect_attack",
        "trash_hand_down_to",
        "life_to_hand",
        "deny_attack",
        "deny_rest",
        "set_cost",
        "choose_one",
        "attack_tax",
        "trash_life",
        "hand_to_life",
        "flip_life",
        "place_on_life",
        "replace_leave",
        "replace_rest",
        "play_characters_rested",
        "cannot_attack_leader",
        "look_deck",
        "look_opp_deck",
        "look_life",
        "reveal_life",
        "hand_counter",
        "rule_don_deck_size",
        "rule_deckout_end_of_turn",
        "rule_ban_events_cost_gte",
        "unsupported",
    }
)

# Ops that require a concrete target before apply (or open pending_choice).
TARGETED_OPS = frozenset(
    {
        "ko",
        "rest_character",
        "buff",
        "return_to_hand",
        "trash",
        "choose_target",
    }
)

# Target pool kinds for pending_choice / choose_target.
TARGET_KINDS = frozenset(
    {
        "opponent_character",
        "opponent_character_active",
        "opponent_character_rested",
        "opponent_stage",
        "own_stage",
        "any_stage",
        "own_character",
        "own_character_or_leader",
        "any_character",
        "leader",
        "hand_card",
        "effect_option",
        "life_position",
        "own_leader_or_character",
        "opponent_leader_or_character",
        "self",
    }
)

# Board / event gates shared across timings (On Play, Trigger, Counter, …).
_ABILITY_GATE_INTS = (
    ("require_don_attached_gte", 0, 10),
    ("require_hand_gte", 0, 20),
    ("require_hand_lte", 0, 20),
    ("require_chars_gte", 0, 5),
    ("require_chars_lte", 0, 5),
    ("require_chars_base_power_eq", 0, 20000),
    ("require_life_gte", 0, 10),
    ("require_life_lte", 0, 10),
    ("require_opp_life_lte", 0, 10),
    ("require_opp_life_gte", 0, 10),
    ("require_total_life_lte", 0, 20),
    ("require_deck_lte", 0, 60),
    ("require_opp_rested_chars_gte", 0, 20),
    ("require_trash_gte", 0, 60),
    ("require_trash_events_gte", 0, 60),
    ("require_own_char_power_gte", 0, 20000),
    ("require_own_char_base_power_gte", 0, 20000),
    ("require_opp_char_base_power_gte", 0, 20000),
    ("require_victim_base_power_gte", 0, 20000),
    ("require_leader_power_lte", -20000, 20000),
    ("require_don_field_deficit_gte", 0, 10),
    ("require_don_field_gte", 0, 20),
    ("require_don_active_gte", 0, 20),
    ("require_either_don_field_gte", 0, 20),
    ("require_either_don_field_lte", 0, 20),
    ("require_either_life_lte", 0, 10),
    ("require_either_life_gte", 0, 10),
    ("require_field_char_base_power_gte", 0, 20000),
    ("require_field_char_power_gte", 0, 20000),
    ("require_chars_trait_gte", 0, 5),
    ("require_distinct_own_chars_trait_gte", 0, 10),
    ("require_rested_own_chars_gte", 0, 10),
    ("require_opp_hand_gte", 0, 20),
    ("require_field_char_cost_eq", 0, 10),
    ("require_field_char_cost_0_or_gte", 0, 10),
    ("require_opp_don_field_gte", 0, 20),
    ("require_don_field_lte", 0, 20),
    ("require_don_field_0_or_gte", 0, 20),
    ("require_opp_char_power_gte", 0, 20000),
    ("require_opp_leader_power_gte", 0, 20000),
    ("require_turn_gte", 0, 20),
    ("require_own_name_gte", 0, 10),
    ("require_given_don_gte", 0, 20),
    ("require_opp_given_don_gte", 0, 20),
    ("require_life_plus_hand_lte", 0, 20),
    ("require_opp_char_cost_eq", 0, 10),
    ("require_opp_chars_count_lte", 0, 10),
    ("require_other_own_char_power_gte", 0, 20000),
    ("require_chars_base_cost_gte", 0, 10),
    ("require_chars_base_cost_count_gte", 0, 5),
    ("require_chars_base_cost_count_lte", 0, 10),
    ("require_chars_base_power_gte", 0, 20000),
    ("require_chars_base_power_count_gte", 0, 10),
    ("require_field_chars_cost_gte", 0, 10),
    ("require_field_chars_cost_count_gte", 0, 10),
    ("require_field_char_cost_gte", 0, 12),
    ("require_own_char_cost_gte", 0, 12),
    ("require_own_trigger_chars_gte", 0, 10),
    ("require_opp_chars_count_gte", 0, 10),
    ("require_chars_cost_sum_gte", 0, 50),
    ("require_chars_deficit_gte", 0, 10),
    ("require_rested_cards_gte", 0, 20),
    ("require_don_active_lte", 0, 20),
    ("require_no_own_char_cost_gte", 0, 10),
)

_EVENT_TIMINGS = frozenset(
    {
        "on_play",
        "on_ko",
        "on_life_damage",
        "when_attacking",
        "on_block",
        "on_opponent_attack",
        "on_own_leader_battle",
        "trigger",
        "counter_event",
        "activate_main",
        "end_of_your_turn",
        "end_of_opponent_turn",
        "main_start",
        "turn_start",
        "your_turn",
        "opponent_turn",
        "don_attached",
        "on_don_attached",
        "on_don_returned",
        "hand_cost",
        "on_event",
        "on_trigger",
        "on_opp_event",
        "on_opp_trigger",
        "on_opponent_play",
        "end_of_battle",
        "on_game_start",
    }
)


def _copy_ability_gates(raw: dict[str, Any], out: dict[str, Any]) -> None:
    for key, lo, hi in _ABILITY_GATE_INTS:
        if raw.get(key) is not None:
            try:
                out[key] = max(lo, min(hi, int(raw.get(key) or 0)))
            except (TypeError, ValueError):
                pass
    if raw.get("require_life_less_than_opponent"):
        out["require_life_less_than_opponent"] = True
    if raw.get("require_life_lte_opponent"):
        out["require_life_lte_opponent"] = True
    if raw.get("require_other_chars_trait"):
        out["require_other_chars_trait"] = str(raw.get("require_other_chars_trait"))[:40]
    if raw.get("on_hand_trashed_by_effect"):
        out["on_hand_trashed_by_effect"] = True
    if raw.get("require_hand_trashed_by_effect_this_turn"):
        out["require_hand_trashed_by_effect_this_turn"] = True
    if raw.get("require_opp_life_left_this_turn"):
        out["require_opp_life_left_this_turn"] = True
    if raw.get("require_effect_source_trait"):
        out["require_effect_source_trait"] = str(raw.get("require_effect_source_trait"))[:40]
    if raw.get("require_all_chars_trait"):
        out["require_all_chars_trait"] = str(raw.get("require_all_chars_trait"))[:40]
    if raw.get("require_chars_trait"):
        out["require_chars_trait"] = str(raw.get("require_chars_trait"))[:40]
    if raw.get("require_distinct_own_chars_trait"):
        out["require_distinct_own_chars_trait"] = str(raw.get("require_distinct_own_chars_trait"))[:40]
    if raw.get("require_chars_color"):
        out["require_chars_color"] = str(raw.get("require_chars_color")).strip().lower()[:20]
    if raw.get("require_other_exclude_name"):
        out["require_other_exclude_name"] = str(raw.get("require_other_exclude_name"))[:80]
    if raw.get("about_to_leave"):
        out["about_to_leave"] = True
    if raw.get("require_leader_trait"):
        # Allow OR lists like "Land of Wano|Whitebeard Pirates".
        out["require_leader_trait"] = str(raw.get("require_leader_trait"))[:80]
    if raw.get("require_leader_name"):
        out["require_leader_name"] = str(raw.get("require_leader_name"))[:120]
    if raw.get("deck_ban_event_cost_gte") is not None:
        try:
            out["deck_ban_event_cost_gte"] = max(0, min(10, int(raw.get("deck_ban_event_cost_gte") or 0)))
        except (TypeError, ValueError):
            pass
    if raw.get("require_no_other_name"):
        out["require_no_other_name"] = str(raw.get("require_no_other_name"))[:80]
    if raw.get("require_no_other_base_cost_eq") is not None:
        try:
            out["require_no_other_base_cost_eq"] = max(
                0, min(10, int(raw.get("require_no_other_base_cost_eq") or 0))
            )
        except (TypeError, ValueError):
            pass
    if raw.get("require_own_name_contains"):
        out["require_own_name_contains"] = str(raw.get("require_own_name_contains"))[:120]
    if raw.get("require_own_name_on_field"):
        out["require_own_name_on_field"] = str(raw.get("require_own_name_on_field"))[:60]
    if raw.get("require_own_name_all") is not None:
        raw_all = raw.get("require_own_name_all")
        if isinstance(raw_all, list):
            out["require_own_name_all"] = [str(x)[:80] for x in raw_all if str(x).strip()][:6]
        elif isinstance(raw_all, str) and raw_all.strip():
            out["require_own_name_all"] = [x.strip()[:80] for x in raw_all.split(";") if x.strip()][:6]
    if raw.get("require_no_own_name_on_field"):
        out["require_no_own_name_on_field"] = str(raw.get("require_no_own_name_on_field"))[:60]
    if raw.get("require_rested_own_chars_trait"):
        out["require_rested_own_chars_trait"] = str(raw.get("require_rested_own_chars_trait"))[:40]
    if raw.get("require_your_turn"):
        out["require_your_turn"] = True
    if raw.get("require_hand_only_chars_no_counter"):
        out["require_hand_only_chars_no_counter"] = True
    if raw.get("on_char_leave_by_own_effect"):
        out["on_char_leave_by_own_effect"] = True
    if raw.get("on_char_rested_by_own_effect"):
        out["on_char_rested_by_own_effect"] = True
    if raw.get("require_played_this_turn"):
        out["require_played_this_turn"] = True
    if raw.get("require_activated_this_turn"):
        out["require_activated_this_turn"] = True
    if raw.get("on_own_trait_leave_or_ko"):
        out["on_own_trait_leave_or_ko"] = str(raw.get("on_own_trait_leave_or_ko"))[:40]
    if raw.get("on_any_leave"):
        out["on_any_leave"] = True
    if raw.get("on_return_don_gte") is not None:
        try:
            out["on_return_don_gte"] = max(1, min(10, int(raw.get("on_return_don_gte") or 1)))
        except (TypeError, ValueError):
            pass
    if raw.get("require_summoning_sick"):
        out["require_summoning_sick"] = True
    if raw.get("on_ko_by_opp_effect"):
        out["on_ko_by_opp_effect"] = True
    if raw.get("on_own_play_character"):
        out["on_own_play_character"] = True
    if raw.get("on_hand_trash_by_own_effect"):
        out["on_hand_trash_by_own_effect"] = True
    if raw.get("on_life_leave"):
        out["on_life_leave"] = True
        src = str(raw.get("on_life_leave_from") or "either").strip().lower()
        if src in {"either", "self", "opponent"}:
            out["on_life_leave_from"] = src
        else:
            out["on_life_leave_from"] = "either"
    if raw.get("require_played_has_trigger"):
        out["require_played_has_trigger"] = True
    if raw.get("require_played_from_trash"):
        out["require_played_from_trash"] = True
    if raw.get("require_played_trait"):
        out["require_played_trait"] = str(raw.get("require_played_trait"))[:80]
    if raw.get("require_played_base_cost_gte") is not None:
        try:
            out["require_played_base_cost_gte"] = max(0, min(10, int(raw.get("require_played_base_cost_gte") or 0)))
        except (TypeError, ValueError):
            pass
    if raw.get("or_played_by_character_effect"):
        out["or_played_by_character_effect"] = True
    if raw.get("require_played_by_character_effect"):
        out["require_played_by_character_effect"] = True
    if raw.get("vs_leader_only") or raw.get("require_vs_leader"):
        out["vs_leader_only"] = True
    if raw.get("require_source_cost_gte") is not None:
        try:
            out["require_source_cost_gte"] = max(0, min(30, int(raw.get("require_source_cost_gte") or 0)))
        except (TypeError, ValueError):
            pass
    if raw.get("require_no_name_on_field"):
        out["require_no_name_on_field"] = str(raw.get("require_no_name_on_field"))[:60]
    if raw.get("on_opp_blocker_or_event"):
        out["on_opp_blocker_or_event"] = True
    if raw.get("on_opp_blocker"):
        out["on_opp_blocker"] = True
    if raw.get("also_on_opp_trigger"):
        out["also_on_opp_trigger"] = True
    if raw.get("on_own_trait_ko"):
        out["on_own_trait_ko"] = str(raw.get("on_own_trait_ko"))[:80]
    if raw.get("on_own_char_ko") or raw.get("on_own_character_ko"):
        out["on_own_char_ko"] = True
    if raw.get("require_victim_attr") or raw.get("require_victim_attribute"):
        out["require_victim_attr"] = str(
            raw.get("require_victim_attr") or raw.get("require_victim_attribute") or ""
        ).strip()[:40]
    if raw.get("require_victim_without_keyword"):
        out["require_victim_without_keyword"] = str(raw.get("require_victim_without_keyword")).strip().lower()[:40]
    if raw.get("require_don_rested_gte") is not None:
        try:
            out["require_don_rested_gte"] = max(0, min(20, int(raw.get("require_don_rested_gte") or 0)))
        except (TypeError, ValueError):
            pass
    if raw.get("require_don_field_0_or_gte") is not None:
        try:
            out["require_don_field_0_or_gte"] = max(0, min(20, int(raw.get("require_don_field_0_or_gte") or 0)))
        except (TypeError, ValueError):
            pass
    if raw.get("on_return_don_from_field_gte") is not None:
        try:
            out["on_return_don_from_field_gte"] = max(1, min(10, int(raw.get("on_return_don_from_field_gte") or 1)))
        except (TypeError, ValueError):
            pass
    if raw.get("require_opponent_turn"):
        out["require_opponent_turn"] = True
    if raw.get("require_all_don_rested"):
        out["require_all_don_rested"] = True
    if raw.get("require_source_active"):
        out["require_source_active"] = True
    if raw.get("require_source_rested"):
        out["require_source_rested"] = True
    if raw.get("require_play_no_base_effect_from_hand"):
        out["require_play_no_base_effect_from_hand"] = True
    if raw.get("require_source_power_gte") is not None:
        try:
            out["require_source_power_gte"] = max(0, min(20000, int(raw.get("require_source_power_gte") or 0)))
        except (TypeError, ValueError):
            pass
    if raw.get("on_ko_caused_by_battle"):
        out["on_ko_caused_by_battle"] = True
    if raw.get("characters_enter_rested"):
        out["characters_enter_rested"] = True
    if raw.get("on_opp_play_character"):
        out["on_opp_play_character"] = True
    if raw.get("cannot_play_by_effect_from_hand"):
        out["cannot_play_by_effect_from_hand"] = True
    if raw.get("on_opp_ko"):
        out["on_opp_ko"] = True
    if raw.get("on_life_damage"):
        out["on_life_damage"] = True
    if raw.get("require_leader_multicolor"):
        out["require_leader_multicolor"] = True
    if raw.get("require_leader_monocolor"):
        out["require_leader_monocolor"] = True
    if raw.get("require_leader_color"):
        out["require_leader_color"] = str(raw.get("require_leader_color"))[:40]
    if raw.get("require_leader_name_or_multicolor"):
        out["require_leader_name_or_multicolor"] = True
    if raw.get("require_leader_name_or_trait"):
        out["require_leader_name_or_trait"] = True
    if raw.get("require_trash_names_all"):
        out["require_trash_names_all"] = str(raw.get("require_trash_names_all"))[:120]
    if raw.get("require_leader_attribute"):
        out["require_leader_attribute"] = str(raw.get("require_leader_attribute"))[:40]
    if raw.get("require_opp_leader_attribute"):
        out["require_opp_leader_attribute"] = str(raw.get("require_opp_leader_attribute"))[:40]
    if raw.get("trigger_on"):
        ton = str(raw.get("trigger_on") or "").strip().lower()
        if ton in {"self_rested", "board"}:
            out["trigger_on"] = ton


_SELF_RESTED_SUMMARY = re.compile(
    r"(?:when this(?: Character)? becomes rested|這張角色卡置為休息狀態時|这张角色卡置为休息状态时)",
    re.I,
)


def normalize_ability(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    timing = str(raw.get("timing") or "").strip().lower()
    if timing not in TIMINGS:
        return None
    status = str(raw.get("status") or "compiled").strip().lower()
    if status not in ABILITY_STATUSES:
        status = "needs_review"
    ops_in = raw.get("ops")
    if not isinstance(ops_in, list):
        ops_in = []
    ops = [o for o in (sanitize_op(x) for x in ops_in) if o]
    if status == "unsupported" and not ops:
        ops = [{"op": "unsupported"}]
    conf = raw.get("confidence")
    try:
        confidence = float(conf) if conf is not None else 0.5
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))
    out: dict[str, Any] = {
        "timing": timing,
        "summary": str(raw.get("summary") or "")[:240],
        "ops": ops,
        "status": status,
        "confidence": confidence,
    }
    if raw.get("once"):
        out["once"] = True
    # Optional activation (可以發動) — resolved via pending_effect confirm, not auto-fire.
    if raw.get("optional") is not None:
        out["optional"] = bool(raw.get("optional"))
    # Activate: Main cost metadata (optional). rest_self also kept on On Play / When Attacking colon-costs.
    if timing == "activate_main":
        out["cost_don"] = max(0, min(10, int(raw.get("cost_don") or 0)))
        out["rest_self"] = bool(raw.get("rest_self"))
        out["once"] = bool(raw.get("once"))
        if raw.get("require_char_power_gte"):
            try:
                out["require_char_power_gte"] = max(0, int(raw.get("require_char_power_gte") or 0))
            except (TypeError, ValueError):
                pass
    elif timing == "main_start" and raw.get("cost_don"):
        out["cost_don"] = max(0, min(10, int(raw.get("cost_don") or 0)))
    elif timing in {
        "on_play",
        "when_attacking",
        "opponent_turn",
        "your_turn",
        "on_opponent_attack",
        "on_own_leader_battle",
        "on_block",
        "end_of_your_turn",
        "main_start",
    } and raw.get("rest_self"):
        out["rest_self"] = True
    # Shared gates for event + continuous timings.
    if timing in _EVENT_TIMINGS:
        _copy_ability_gates(raw, out)
    if timing in {"your_turn", "opponent_turn", "don_attached", "hand_cost", "on_don_attached", "on_don_phase", "on_don_returned"}:
        if raw.get("hand_color"):
            out["hand_color"] = str(raw.get("hand_color"))[:20]
        if raw.get("hand_card_type"):
            out["hand_card_type"] = str(raw.get("hand_card_type"))[:20]
        if raw.get("on_any_own_don_attach"):
            out["on_any_own_don_attach"] = True
        _copy_ability_gates(raw, out)
    if timing in {"end_of_your_turn", "end_of_opponent_turn", "your_turn", "opponent_turn"}:
        if raw.get("on_opponent_event"):
            out["on_opponent_event"] = True
        if raw.get("on_char_leave_by_own_effect"):
            out["on_char_leave_by_own_effect"] = True
        if raw.get("on_char_rested_by_own_effect"):
            out["on_char_rested_by_own_effect"] = True
    # Untimed attack restrictions evaluated continuously from the ability.
    if raw.get("require_opp_chars_base_power_gte") is not None:
        try:
            out["require_opp_chars_base_power_gte"] = max(
                0, min(20000, int(raw.get("require_opp_chars_base_power_gte") or 0))
            )
        except (TypeError, ValueError):
            pass
    if raw.get("require_opp_chars_count_gte") is not None:
        try:
            out["require_opp_chars_count_gte"] = max(0, min(10, int(raw.get("require_opp_chars_count_gte") or 0)))
        except (TypeError, ValueError):
            pass
    if raw.get("while_rested"):
        out["while_rested"] = True
    if raw.get("negated_when_hand_trashed"):
        out["negated_when_hand_trashed"] = True
    # 「這張角色卡置為休息狀態時」/ When this becomes rested → only fire via _fire_self_rested.
    if timing == "your_turn" and not out.get("trigger_on") and _SELF_RESTED_SUMMARY.search(out.get("summary") or ""):
        out["trigger_on"] = "self_rested"
    return out


def sanitize_op(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("op") or "").strip()
    if kind not in ALLOWED_OPS:
        return None
    op: dict[str, Any] = {"op": kind}
    purpose = str(raw.get("purpose") or "").strip().lower()
    if purpose in {
        "ko",
        "trash",
        "buff",
        "rest",
        "return_hand",
        "bottom",
        "play",
        "attach_don",
        "choose_effect",
        "life",
        "general",
    }:
        op["purpose"] = purpose
    if kind in {"draw", "gain_don", "set_don", "rest_opponent_character", "ko_lowest_opponent", "deal_life_damage", "add_life", "active_don"}:
        op["count"] = max(0, min(5, int(raw.get("count") or 1)))
    if kind == "equalize_don_to_opponent":
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "extra_turn":
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "return_don":
        if raw.get("any_number"):
            op["any_number"] = True
            op["count"] = max(1, min(10, int(raw.get("count") or 10)))
        else:
            op["count"] = max(0, min(10, int(raw.get("count") or 1)))
        owner = str(raw.get("owner") or "self").strip().lower()
        if owner in {"self", "opponent"}:
            op["owner"] = owner
        if raw.get("active_only"):
            op["active_only"] = True
    if kind == "rest_don":
        if raw.get("any_number"):
            op["any_number"] = True
            op["count"] = max(1, min(10, int(raw.get("count") or 10)))
        else:
            op["count"] = max(0, min(10, int(raw.get("count") or 1)))
        owner = str(raw.get("owner") or "self").strip().lower()
        if owner in {"self", "opponent"}:
            op["owner"] = owner
    if kind == "return_attached_don":
        op["count"] = max(1, min(10, int(raw.get("count") or 1)))
        if raw.get("as_cost"):
            op["as_cost"] = True
        if raw.get("optional") is not None:
            op["optional"] = bool(raw.get("optional"))
    if kind in {"rest_don", "return_don"} and raw.get("as_cost"):
        op["as_cost"] = True
    if kind in {"rest_don", "return_don"} and raw.get("optional") is not None:
        op["optional"] = bool(raw.get("optional"))
    if kind in {"add_life", "deal_life_damage"} and raw.get("optional") is not None:
        op["optional"] = bool(raw.get("optional"))
    if kind in {"add_life", "deal_life_damage"}:
        owner = str(raw.get("owner") or "").strip().lower()
        if owner in {"self", "opponent"}:
            op["owner"] = owner
        pos = str(raw.get("position") or "").strip().lower()
        if pos in {"top", "bottom"}:
            op["position"] = pos
        if raw.get("require_leader_trait"):
            op["require_leader_trait"] = str(raw.get("require_leader_trait"))[:40]
        if raw.get("require_leader_attribute"):
            op["require_leader_attribute"] = str(raw.get("require_leader_attribute"))[:40]
        if raw.get("require_life_lte") is not None:
            try:
                op["require_life_lte"] = max(0, min(10, int(raw.get("require_life_lte") or 0)))
            except (TypeError, ValueError):
                pass
    if kind == "active_don" and raw.get("optional") is not None:
        op["optional"] = bool(raw.get("optional"))
    if kind == "active_don" and raw.get("all"):
        op["all"] = True
        op["count"] = max(1, min(20, int(raw.get("count") or 10)))
    if kind == "active_don" and raw.get("if_trashed"):
        op["if_trashed"] = True
    if kind == "active_don" and raw.get("at_end_of_turn"):
        op["at_end_of_turn"] = True
    if kind == "active_don" and raw.get("require_field_char_cost_gte") is not None:
        try:
            op["require_field_char_cost_gte"] = max(0, min(10, int(raw.get("require_field_char_cost_gte") or 0)))
        except (TypeError, ValueError):
            pass
    if kind == "active_don" and raw.get("summary"):
        op["summary"] = str(raw.get("summary"))[:160]
    if kind == "draw":
        if raw.get("require_leader_trait"):
            op["require_leader_trait"] = str(raw.get("require_leader_trait"))[:80]
        if raw.get("require_life_lte") is not None:
            try:
                op["require_life_lte"] = max(0, min(10, int(raw.get("require_life_lte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("require_life_gte") is not None:
            try:
                op["require_life_gte"] = max(0, min(10, int(raw.get("require_life_gte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("require_leader_trait"):
            op["require_leader_trait"] = str(raw.get("require_leader_trait"))[:80]
        if raw.get("require_field_char_cost_eq") is not None:
            try:
                op["require_field_char_cost_eq"] = max(0, min(10, int(raw.get("require_field_char_cost_eq") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("require_opp_char_cost_0_or_gte") is not None:
            try:
                op["require_opp_char_cost_0_or_gte"] = max(0, min(10, int(raw.get("require_opp_char_cost_0_or_gte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("require_field_char_cost_0_or_gte") is not None:
            try:
                op["require_field_char_cost_0_or_gte"] = max(0, min(10, int(raw.get("require_field_char_cost_0_or_gte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("per_own_trait"):
            op["per_own_trait"] = str(raw.get("per_own_trait"))[:40]
        if raw.get("then_trash_equal"):
            op["then_trash_equal"] = True
        if raw.get("equal_trashed"):
            op["equal_trashed"] = True
        if raw.get("until_hand_size") is not None:
            try:
                op["until_hand_size"] = max(0, min(10, int(raw.get("until_hand_size") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("require_event_activated_cost_gte") is not None:
            try:
                op["require_event_activated_cost_gte"] = max(
                    0, min(10, int(raw.get("require_event_activated_cost_gte") or 0))
                )
            except (TypeError, ValueError):
                pass
        if raw.get("require_hand_lte") is not None:
            try:
                op["require_hand_lte"] = max(0, min(20, int(raw.get("require_hand_lte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("require_rested_cards_gte") is not None:
            try:
                op["require_rested_cards_gte"] = max(0, min(20, int(raw.get("require_rested_cards_gte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("on_opp_ko"):
            op["on_opp_ko"] = True
        if raw.get("on_life_damage"):
            op["on_life_damage"] = True
        if raw.get("optional") is not None:
            op["optional"] = bool(raw.get("optional"))
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
        if raw.get("owner"):
            owner = str(raw.get("owner") or "self").strip().lower()
            if owner in {"self", "opponent"}:
                op["owner"] = owner
        if raw.get("require_don_field_gte") is not None:
            try:
                op["require_don_field_gte"] = max(0, min(20, int(raw.get("require_don_field_gte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("require_opp_don_field_gte") is not None:
            try:
                op["require_opp_don_field_gte"] = max(0, min(20, int(raw.get("require_opp_don_field_gte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("require_either_don_field_gte") is not None:
            try:
                op["require_either_don_field_gte"] = max(0, min(20, int(raw.get("require_either_don_field_gte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("require_either_don_field_lte") is not None:
            try:
                op["require_either_don_field_lte"] = max(0, min(20, int(raw.get("require_either_don_field_lte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("require_either_life_lte") is not None:
            try:
                op["require_either_life_lte"] = max(0, min(10, int(raw.get("require_either_life_lte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("require_either_life_gte") is not None:
            try:
                op["require_either_life_gte"] = max(0, min(10, int(raw.get("require_either_life_gte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("require_hand_lte") is not None:
            try:
                op["require_hand_lte"] = max(0, min(20, int(raw.get("require_hand_lte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("require_life_lte") is not None:
            try:
                op["require_life_lte"] = max(0, min(10, int(raw.get("require_life_lte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("require_life_gte") is not None:
            try:
                op["require_life_gte"] = max(0, min(10, int(raw.get("require_life_gte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("require_opp_char_power_gte") is not None:
            try:
                op["require_opp_char_power_gte"] = max(0, min(20000, int(raw.get("require_opp_char_power_gte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("require_don_field_lte") is not None:
            try:
                op["require_don_field_lte"] = max(0, min(20, int(raw.get("require_don_field_lte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("require_don_field_deficit_gte") is not None:
            try:
                op["require_don_field_deficit_gte"] = max(
                    0, min(10, int(raw.get("require_don_field_deficit_gte") or 0))
                )
            except (TypeError, ValueError):
                pass
        if raw.get("require_given_don_gte") is not None:
            try:
                op["require_given_don_gte"] = max(0, min(20, int(raw.get("require_given_don_gte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("if_played"):
            op["if_played"] = True
        if raw.get("on_life_leave"):
            op["on_life_leave"] = True
        if raw.get("if_returned"):
            op["if_returned"] = True
    if kind == "rest_opponent_character" and raw.get("include_leader"):
        op["include_leader"] = True
    if kind == "rest_opponent_character" and raw.get("include_don"):
        op["include_don"] = True
    if kind == "rest_opponent_character" and raw.get("include_stage"):
        op["include_stage"] = True
    if kind == "rest_opponent_character" and (raw.get("leader_only") or str(raw.get("target_kind") or "").strip().lower() in {"opponent_leader", "leader"}):
        op["leader_only"] = True
        op["include_leader"] = True
    if kind == "rest_opponent_character":
        for key, lo, hi in (
            ("cost_lte", 0, 10),
            ("base_cost_lte", 0, 10),
            ("cost_eq", 0, 10),
            ("don_attached_gte", 0, 10),
            ("base_power_lte", 0, 20000),
            ("power_lte", 0, 20000),
        ):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        if raw.get("cost_lte_opp_life"):
            op["cost_lte_opp_life"] = True
        if raw.get("cost_lte_total_life"):
            op["cost_lte_total_life"] = True
        if raw.get("require_blocker"):
            op["require_blocker"] = True
        if raw.get("require_opp_life_lte") is not None:
            try:
                op["require_opp_life_lte"] = max(0, min(10, int(raw.get("require_opp_life_lte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("optional") is not None:
            op["optional"] = bool(raw.get("optional"))
        if raw.get("all"):
            op["all"] = True
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "gain_don" and raw.get("as_rested"):
        op["as_rested"] = True
    if kind == "gain_don" and raw.get("optional") is not None:
        op["optional"] = bool(raw.get("optional"))
    if kind == "gain_don" and raw.get("at_end_of_turn"):
        op["at_end_of_turn"] = True
    if kind == "gain_don" and raw.get("require_given_don_gte") is not None:
        try:
            op["require_given_don_gte"] = max(0, min(20, int(raw.get("require_given_don_gte") or 0)))
        except (TypeError, ValueError):
            pass
    if kind == "gain_don" and raw.get("require_leader_name"):
        op["require_leader_name"] = str(raw.get("require_leader_name"))[:80]
    if kind == "gain_don" and raw.get("require_opp_char_base_power_gte") is not None:
        try:
            op["require_opp_char_base_power_gte"] = max(
                0, min(20000, int(raw.get("require_opp_char_base_power_gte") or 0))
            )
        except (TypeError, ValueError):
            pass
    if kind == "gain_don" and raw.get("require_opp_char_power_gte") is not None:
        try:
            op["require_opp_char_power_gte"] = max(
                0, min(20000, int(raw.get("require_opp_char_power_gte") or 0))
            )
        except (TypeError, ValueError):
            pass
    if kind == "gain_don" and raw.get("if_revealed_cost_lte") is not None:
        try:
            op["if_revealed_cost_lte"] = max(0, min(10, int(raw.get("if_revealed_cost_lte") or 0)))
        except (TypeError, ValueError):
            pass
    if kind == "draw" and raw.get("on_opp_ko"):
        op["on_opp_ko"] = True
    if kind in {"draw", "buff", "gain_don", "trash_hand"} and raw.get("if_revealed_trait_contains"):
        op["if_revealed_trait_contains"] = str(raw.get("if_revealed_trait_contains"))[:80]
    if kind in {"draw", "buff", "gain_don", "trash_hand"} and raw.get("if_revealed_trait_includes"):
        op["if_revealed_trait_includes"] = str(raw.get("if_revealed_trait_includes"))[:80]
    if kind in {"draw", "buff", "gain_don", "ko", "rest_opponent_character"} and raw.get(
        "if_declared_cost_match"
    ):
        op["if_declared_cost_match"] = True
    if kind == "gain_don" and raw.get("on_opp_ko"):
        op["on_opp_ko"] = True
    if kind == "gain_don" and raw.get("require_leader_trait"):
        op["require_leader_trait"] = str(raw.get("require_leader_trait"))[:80]
    if kind in {"buff", "buff_self"}:
        op["amount"] = max(-10000, min(10000, int(raw.get("amount") or 0)))
        if kind == "buff":
            if raw.get("target_iid"):
                op["target_iid"] = str(raw.get("target_iid"))[:40]
            if raw.get("target_kind"):
                tk = str(raw.get("target_kind"))
                if tk in TARGET_KINDS:
                    op["target_kind"] = tk
            # Debuffs without an explicit pool historically defaulted to own board —
            # prefer opponent Characters (paper almost always says 對手的角色卡).
            elif int(op.get("amount") or 0) < 0 and not raw.get("target_iid"):
                op["target_kind"] = "opponent_character"
            op["optional"] = bool(raw.get("optional", False))
            if raw.get("always_choose"):
                op["always_choose"] = True
            if raw.get("as_cost"):
                op["as_cost"] = True
            if raw.get("require_leader_active"):
                op["require_leader_active"] = True
            if raw.get("all"):
                op["all"] = True
            if raw.get("exclude_self"):
                op["exclude_self"] = True
            if raw.get("same_target"):
                op["same_target"] = True
            if raw.get("same_target_as_prior"):
                op["same_target_as_prior"] = True
            if raw.get("also_deny_blocker_when_attacks"):
                op["also_deny_blocker_when_attacks"] = True
            if raw.get("require_opp_life_lte") is not None:
                try:
                    op["require_opp_life_lte"] = max(0, min(10, int(raw.get("require_opp_life_lte") or 0)))
                except (TypeError, ValueError):
                    pass
            if raw.get("require_rested_cards_gte") is not None:
                try:
                    op["require_rested_cards_gte"] = max(
                        0, min(20, int(raw.get("require_rested_cards_gte") or 0))
                    )
                except (TypeError, ValueError):
                    pass
            if raw.get("if_life_lte") is not None:
                try:
                    op["if_life_lte"] = max(0, min(10, int(raw.get("if_life_lte") or 0)))
                except (TypeError, ValueError):
                    pass
            if raw.get("if_life_to_hand"):
                op["if_life_to_hand"] = True
            if raw.get("if_trash_gte") is not None:
                try:
                    op["if_trash_gte"] = max(0, min(60, int(raw.get("if_trash_gte") or 0)))
                except (TypeError, ValueError):
                    pass
            if raw.get("require_opp_char_power_gte") is not None:
                try:
                    op["require_opp_char_power_gte"] = max(
                        0, min(20000, int(raw.get("require_opp_char_power_gte") or 0))
                    )
                except (TypeError, ValueError):
                    pass
            if raw.get("count") is not None:
                try:
                    op["count"] = max(1, min(5, int(raw.get("count") or 1)))
                except (TypeError, ValueError):
                    pass
            for key, lo, hi in (("cost_lte", 0, 10), ("cost_eq", 0, 10), ("cost_gte", 0, 10)):
                if raw.get(key) is not None:
                    try:
                        op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                    except (TypeError, ValueError):
                        pass
            for key, lo, hi in (("power_lte", 0, 20000), ("power_gte", 0, 20000), ("base_power_lte", 0, 20000)):
                if raw.get(key) is not None:
                    try:
                        op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                    except (TypeError, ValueError):
                        pass
            if raw.get("name_contains"):
                op["name_contains"] = str(raw.get("name_contains"))[:60]
            if raw.get("include_leader"):
                op["include_leader"] = True
            if raw.get("include_stage"):
                op["include_stage"] = True
            if raw.get("include_leader_if_name"):
                op["include_leader_if_name"] = str(raw.get("include_leader_if_name"))[:80]
            if raw.get("trait_contains"):
                op["trait_contains"] = str(raw.get("trait_contains"))[:80]
            if raw.get("trait_includes"):
                op["trait_includes"] = str(raw.get("trait_includes"))[:40]
            trait_any = raw.get("trait_any")
            if isinstance(trait_any, list):
                op["trait_any"] = [str(t)[:40] for t in trait_any if str(t).strip()][:4]
            if raw.get("attribute"):
                op["attribute"] = str(raw.get("attribute"))[:40]
            if raw.get("color"):
                op["color"] = str(raw.get("color")).strip().lower()[:20]
            if raw.get("exclude_name"):
                op["exclude_name"] = str(raw.get("exclude_name"))[:60]
            if raw.get("require_leader_trait"):
                op["require_leader_trait"] = str(raw.get("require_leader_trait"))[:80]
            if raw.get("require_given_don_gte") is not None:
                try:
                    op["require_given_don_gte"] = max(0, min(20, int(raw.get("require_given_don_gte") or 0)))
                except (TypeError, ValueError):
                    pass
            if raw.get("require_opp_rested_chars_gte") is not None:
                try:
                    op["require_opp_rested_chars_gte"] = max(
                        0, min(20, int(raw.get("require_opp_rested_chars_gte") or 0))
                    )
                except (TypeError, ValueError):
                    pass
            if raw.get("no_base_effect"):
                op["no_base_effect"] = True
            for key, lo, hi in (("base_cost_lte", 0, 10), ("base_cost_gte", 0, 10)):
                if raw.get(key) is not None:
                    try:
                        op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                    except (TypeError, ValueError):
                        pass
            dur = str(raw.get("duration") or "").strip().lower()
            if dur in {"turn", "battle", "permanent", "until_opp_turn_end", "next_turn"}:
                op["duration"] = dur
            for key, lo, hi in (
                ("per_rested_don", 1, 10),
                ("per_don_attached", 1, 10),
                ("per_trash_cards", 1, 20),
                ("per_trash_events", 1, 20),
                ("per_own_chars", 1, 10),
                ("per_returned_chars", 1, 10),
            ):
                if raw.get(key) is not None:
                    try:
                        op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                    except (TypeError, ValueError):
                        pass
            if raw.get("per_distinct_own_char_names"):
                op["per_distinct_own_char_names"] = True
            if raw.get("per_own_trait"):
                op["per_own_trait"] = str(raw.get("per_own_trait"))[:40]
            if raw.get("per_choose"):
                op["per_choose"] = True
            if raw.get("summary"):
                op["summary"] = str(raw.get("summary"))[:160]
            if raw.get("card_id"):
                op["card_id"] = str(raw.get("card_id"))[:40]
            if raw.get("source_iid"):
                op["source_iid"] = str(raw.get("source_iid"))[:40]
        else:
            if raw.get("source_iid"):
                op["source_iid"] = str(raw.get("source_iid"))[:40]
            if raw.get("optional") is not None:
                op["optional"] = bool(raw.get("optional"))
            if raw.get("as_cost"):
                op["as_cost"] = True
            if raw.get("require_field_char_cost_eq") is not None:
                try:
                    op["require_field_char_cost_eq"] = max(0, min(10, int(raw.get("require_field_char_cost_eq") or 0)))
                except (TypeError, ValueError):
                    pass
            if raw.get("target_kind"):
                tk = str(raw.get("target_kind"))
                if tk in TARGET_KINDS or tk in {"leader", "self"}:
                    op["target_kind"] = tk
            for key, lo, hi in (
                ("per_rested_don", 1, 10),
                ("per_don_attached", 1, 10),
                ("per_trash_cards", 1, 20),
                ("per_trash_events", 1, 20),
                ("per_hand_cards", 1, 20),
                ("per_own_chars", 1, 10),
            ):
                if raw.get(key) is not None:
                    try:
                        op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                    except (TypeError, ValueError):
                        pass
            if raw.get("per_distinct_own_char_names"):
                op["per_distinct_own_char_names"] = True
            if raw.get("name_contains"):
                op["name_contains"] = str(raw.get("name_contains"))[:60]
            if raw.get("trait_contains"):
                op["trait_contains"] = str(raw.get("trait_contains"))[:40]
            if raw.get("vs_attribute"):
                op["vs_attribute"] = str(raw.get("vs_attribute"))[:40]
            if raw.get("per_revealed_cost"):
                op["per_revealed_cost"] = True
            dur = str(raw.get("duration") or "").strip().lower()
            if dur in {"turn", "battle", "permanent", "until_opp_turn_end", "next_turn"}:
                op["duration"] = dur
            if raw.get("if_revealed_power_gte") is not None:
                try:
                    op["if_revealed_power_gte"] = max(0, min(20000, int(raw.get("if_revealed_power_gte") or 0)))
                except (TypeError, ValueError):
                    pass
            if raw.get("summary"):
                op["summary"] = str(raw.get("summary"))[:160]
    if kind == "set_base_power_from_opponent_leader":
        if raw.get("source_iid"):
            op["source_iid"] = str(raw.get("source_iid"))[:40]
        if raw.get("require_don_attached_gte") is not None:
            try:
                op["require_don_attached_gte"] = max(0, min(10, int(raw.get("require_don_attached_gte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind in {"set_base_power_from_character", "set_base_power_from_attacker", "set_base_power", "set_power_equal_opponent_leader"}:
        if raw.get("source_iid"):
            op["source_iid"] = str(raw.get("source_iid"))[:40]
        if raw.get("target_iid"):
            op["target_iid"] = str(raw.get("target_iid"))[:40]
        tk = str(raw.get("target_kind") or "").strip()
        if tk in TARGET_KINDS or tk in {"self", "leader", "own_character", "own_characters", "own_leader_or_character"}:
            op["target_kind"] = tk
        if raw.get("name_contains"):
            op["name_contains"] = str(raw.get("name_contains"))[:60]
        if raw.get("all"):
            op["all"] = True
        op["optional"] = bool(raw.get("optional", True))
        if raw.get("require_don_attached_gte") is not None:
            try:
                op["require_don_attached_gte"] = max(0, min(10, int(raw.get("require_don_attached_gte") or 0)))
            except (TypeError, ValueError):
                pass
        if kind == "set_base_power" and raw.get("amount") is not None:
            try:
                op["amount"] = max(0, min(20000, int(raw.get("amount") or 0)))
            except (TypeError, ValueError):
                pass
        if kind == "set_base_power":
            if raw.get("all"):
                op["all"] = True
            if raw.get("trait_contains"):
                op["trait_contains"] = str(raw.get("trait_contains"))[:40]
            if raw.get("name_contains"):
                op["name_contains"] = str(raw.get("name_contains"))[:60]
            if raw.get("require_trigger"):
                op["require_trigger"] = True
            if raw.get("base_power_eq") is not None:
                try:
                    op["base_power_eq"] = max(0, min(20000, int(raw.get("base_power_eq") or 0)))
                except (TypeError, ValueError):
                    pass
            dur = str(raw.get("duration") or "").strip().lower()
            if dur in {"turn", "battle", "permanent", "until_opp_turn_end"}:
                op["duration"] = dur
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "swap_base_power":
        op["count"] = max(2, min(2, int(raw.get("count") or 2)))
        tk = str(raw.get("target_kind") or "own_character").strip()
        if tk in TARGET_KINDS or tk in {"own_character", "own_leader_or_character", "opponent_character", "any_character"}:
            op["target_kind"] = tk
        if raw.get("require_leader_and_character"):
            op["require_leader_and_character"] = True
        if raw.get("trait_contains"):
            op["trait_contains"] = str(raw.get("trait_contains"))[:40]
        trait_any = raw.get("trait_any")
        if isinstance(trait_any, list):
            op["trait_any"] = [str(t)[:40] for t in trait_any if str(t).strip()][:4]
        for key, lo, hi in (("base_power_lte", 0, 20000), ("base_power_gte", 0, 20000)):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        dur = str(raw.get("duration") or "turn").strip().lower()
        if dur in {"turn", "battle", "until_opp_turn_end"}:
            op["duration"] = dur
        op["optional"] = bool(raw.get("optional", False))
        if raw.get("include_leader"):
            op["include_leader"] = True
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "continuous_base_from_own_leader_printed":
        # Marker op for continuous evaluation; not executed by apply_ops.
        pass
    if kind in {"ko", "rest_character", "return_to_hand", "trash"}:
        if raw.get("target_iid"):
            op["target_iid"] = str(raw.get("target_iid"))[:40]
        tk = str(raw.get("target_kind") or "opponent_character")
        if tk in TARGET_KINDS or tk in {"self", "any_character", "all", "all_characters"}:
            op["target_kind"] = tk
        op["optional"] = bool(raw.get("optional"))
        if raw.get("as_cost"):
            op["as_cost"] = True
        if raw.get("exclude_self"):
            op["exclude_self"] = True
        if kind == "return_to_hand" and raw.get("cost_gte") is not None:
            try:
                op["cost_gte"] = max(0, min(10, int(raw.get("cost_gte"))))
            except (TypeError, ValueError):
                pass
        if kind in {"return_to_hand", "trash", "rest_character"}:
            if kind in {"rest_character", "return_to_hand"} and raw.get("count") is not None:
                try:
                    op["count"] = max(1, min(5, int(raw.get("count") or 1)))
                except (TypeError, ValueError):
                    pass
            for key, lo, hi in (("cost_lte", 0, 10), ("cost_eq", 0, 10), ("cost_gte", 0, 10)):
                if raw.get(key) is not None:
                    try:
                        op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                    except (TypeError, ValueError):
                        pass
            for key, lo, hi in (
                ("power_lte", 0, 20000),
                ("power_gte", 0, 20000),
                ("base_power_lte", 0, 20000),
                ("base_power_gte", 0, 20000),
                ("base_power_eq", 0, 20000),
            ):
                if raw.get(key) is not None:
                    try:
                        op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                    except (TypeError, ValueError):
                        pass
            if raw.get("trait_contains"):
                op["trait_contains"] = str(raw.get("trait_contains"))[:40]
            if raw.get("name_contains"):
                op["name_contains"] = str(raw.get("name_contains"))[:40]
            if raw.get("color"):
                op["color"] = str(raw.get("color")).strip().lower()[:20]
            if raw.get("require_trigger"):
                op["require_trigger"] = True
            ctype = str(raw.get("card_type") or "").strip().lower()
            if ctype in {"character", "event", "stage"}:
                op["card_type"] = ctype
            if kind == "return_to_hand":
                zone = str(raw.get("from_zone") or "").strip().lower()
                if zone in {"hand", "trash", "life", "field"}:
                    op["from_zone"] = zone
                chooser = str(raw.get("chooser") or "").strip().lower()
                if chooser in {"opponent", "self"}:
                    op["chooser"] = chooser
            if raw.get("summary"):
                op["summary"] = str(raw.get("summary"))[:160]
            if raw.get("card_id"):
                op["card_id"] = str(raw.get("card_id"))[:40]
            if raw.get("source_iid"):
                op["source_iid"] = str(raw.get("source_iid"))[:40]
            if kind == "rest_character" and raw.get("include_leader"):
                op["include_leader"] = True
            if kind == "rest_character" and raw.get("include_don"):
                op["include_don"] = True
            if kind == "rest_character" and raw.get("include_stage"):
                op["include_stage"] = True
            if kind == "rest_character" and raw.get("also_skip_untap"):
                op["also_skip_untap"] = True
            if kind == "rest_character" and raw.get("all"):
                op["all"] = True
            if kind == "trash" and raw.get("all"):
                op["all"] = True
        if kind == "ko":
            if raw.get("count") is not None:
                try:
                    op["count"] = max(1, min(3, int(raw.get("count") or 1)))
                except (TypeError, ValueError):
                    pass
            for key, lo, hi in (
                ("cost_lte", 0, 10),
                ("cost_eq", 0, 10),
                ("base_cost_lte", 0, 10),
                ("power_lte", 0, 20000),
                ("base_power_lte", 0, 20000),
                ("require_field_char_cost_gte", 0, 10),
                ("require_field_char_cost_eq", 0, 10),
                ("require_chars_trait_gte", 0, 5),
            ):
                if raw.get(key) is not None:
                    try:
                        op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                    except (TypeError, ValueError):
                        pass
            if raw.get("require_chars_trait"):
                op["require_chars_trait"] = str(raw.get("require_chars_trait"))[:80]
            if raw.get("trait_contains"):
                op["trait_contains"] = str(raw.get("trait_contains"))[:80]
            if raw.get("trait_includes"):
                op["trait_includes"] = str(raw.get("trait_includes"))[:80]
            if raw.get("as_cost"):
                op["as_cost"] = True
            if raw.get("exclude_self"):
                op["exclude_self"] = True
            if raw.get("all"):
                op["all"] = True
            if raw.get("rested_only"):
                op["rested_only"] = True
            if raw.get("cost_lte_opp_life"):
                op["cost_lte_opp_life"] = True
            if raw.get("cost_lte_total_life"):
                op["cost_lte_total_life"] = True
            if raw.get("always_choose"):
                op["always_choose"] = True
            if raw.get("require_life_lte") is not None:
                try:
                    op["require_life_lte"] = max(0, min(10, int(raw.get("require_life_lte") or 0)))
                except (TypeError, ValueError):
                    pass
            if raw.get("require_chars_deficit_gte") is not None:
                try:
                    op["require_chars_deficit_gte"] = max(0, min(5, int(raw.get("require_chars_deficit_gte") or 0)))
                except (TypeError, ValueError):
                    pass
            if raw.get("don_attached_gte") is not None:
                try:
                    op["don_attached_gte"] = max(0, min(10, int(raw.get("don_attached_gte") or 0)))
                except (TypeError, ValueError):
                    pass
            if raw.get("if_trash_hand"):
                op["if_trash_hand"] = True
            if raw.get("require_trash_hand_gte") is not None:
                try:
                    op["require_trash_hand_gte"] = max(
                        0, min(10, int(raw.get("require_trash_hand_gte") or 0))
                    )
                except (TypeError, ValueError):
                    pass
            if raw.get("total_power_lte") is not None:
                try:
                    op["total_power_lte"] = max(0, min(20000, int(raw.get("total_power_lte") or 0)))
                except (TypeError, ValueError):
                    pass
            if raw.get("total_cost_lte") is not None:
                try:
                    op["total_cost_lte"] = max(0, min(50, int(raw.get("total_cost_lte") or 0)))
                except (TypeError, ValueError):
                    pass
            if raw.get("require_own_char_power_gte") is not None:
                try:
                    op["require_own_char_power_gte"] = max(
                        0, min(20000, int(raw.get("require_own_char_power_gte") or 0))
                    )
                except (TypeError, ValueError):
                    pass
            if raw.get("require_chars_deficit_gte") is not None:
                try:
                    op["require_chars_deficit_gte"] = max(
                        0, min(10, int(raw.get("require_chars_deficit_gte") or 0))
                    )
                except (TypeError, ValueError):
                    pass
            if raw.get("same_target_as_prior"):
                op["same_target_as_prior"] = True
            if raw.get("summary"):
                op["summary"] = str(raw.get("summary"))[:160]
    if kind == "search_deck":
        op["name_contains"] = str(raw.get("name_contains") or "")[:160]
        op["trait_contains"] = str(raw.get("trait_contains") or "")[:80]
        trait_any = raw.get("trait_any")
        if isinstance(trait_any, list):
            op["trait_any"] = [str(x)[:40] for x in trait_any if str(x).strip()][:4]
        if raw.get("require_leader_name"):
            op["require_leader_name"] = str(raw.get("require_leader_name"))[:120]
        if raw.get("require_leader_trait"):
            op["require_leader_trait"] = str(raw.get("require_leader_trait"))[:80]
        if raw.get("require_rested_cards_gte") is not None:
            try:
                op["require_rested_cards_gte"] = max(
                    0, min(20, int(raw.get("require_rested_cards_gte") or 0))
                )
            except (TypeError, ValueError):
                pass
        op["top_n"] = max(1, min(8, int(raw.get("top_n") or 5)))
        op["max_add"] = max(1, min(3, int(raw.get("max_add") or 1)))
        # Default True: leftovers go to bottom in player-chosen order when ≥2.
        # trash_rest overrides: leftovers go to trash, not bottom.
        if raw.get("trash_rest"):
            op["trash_rest"] = True
            op["order_bottom"] = False
        else:
            op["order_bottom"] = bool(raw.get("order_bottom", True))
        if raw.get("to_top_or_bottom"):
            op["to_top_or_bottom"] = True
        excl = str(raw.get("exclude_name") or "").strip()
        if excl:
            op["exclude_name"] = excl[:160]
        if raw.get("cost_eq") is not None:
            try:
                op["cost_eq"] = max(0, min(10, int(raw.get("cost_eq"))))
            except (TypeError, ValueError):
                pass
        if raw.get("cost_lte") is not None:
            try:
                op["cost_lte"] = max(0, min(10, int(raw.get("cost_lte"))))
            except (TypeError, ValueError):
                pass
        if raw.get("cost_gte") is not None:
            try:
                op["cost_gte"] = max(0, min(10, int(raw.get("cost_gte"))))
            except (TypeError, ValueError):
                pass
        if raw.get("power_lte") is not None:
            try:
                op["power_lte"] = max(0, min(20000, int(raw.get("power_lte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("power_gte") is not None:
            try:
                op["power_gte"] = max(0, min(20000, int(raw.get("power_gte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("power_eq") is not None:
            try:
                op["power_eq"] = max(0, min(20000, int(raw.get("power_eq") or 0)))
            except (TypeError, ValueError):
                pass
        dest = str(raw.get("destination") or "hand").strip().lower()
        if dest in {"hand", "play", "life"}:
            op["destination"] = dest
        else:
            op["destination"] = "hand"
        face = str(raw.get("face") or "").strip().lower()
        if face in {"up", "down"}:
            op["face"] = face
        if dest == "play":
            ctype = str(raw.get("card_type") or "character").strip().lower()
            op["card_type"] = ctype if ctype in {"character", "event", "stage"} else "character"
        elif raw.get("card_type"):
            ctype = str(raw.get("card_type") or "").strip().lower()
            if ctype in {"character", "event", "stage", "any"}:
                op["card_type"] = ctype
        if raw.get("or_event"):
            op["or_event"] = True
        if raw.get("name_or_trait"):
            op["name_or_trait"] = True
        if raw.get("as_rested"):
            op["as_rested"] = True
        if raw.get("require_trigger"):
            op["require_trigger"] = True
        if raw.get("color"):
            op["color"] = str(raw.get("color")).strip().lower()[:20]
        if raw.get("attr_contains"):
            op["attr_contains"] = str(raw.get("attr_contains")).strip()[:40]
        elif raw.get("attribute"):
            op["attr_contains"] = str(raw.get("attribute")).strip()[:40]
        if raw.get("card_id"):
            op["card_id"] = str(raw.get("card_id"))[:40]
        if raw.get("source_iid"):
            op["source_iid"] = str(raw.get("source_iid"))[:40]
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
        if raw.get("reveal_adds") is True:
            op["reveal_adds"] = True
        elif raw.get("reveal_adds") is False:
            op["reveal_adds"] = False
    if kind == "look_deck":
        op["count"] = max(1, min(8, int(raw.get("count") or raw.get("top_n") or 1)))
        pos = str(raw.get("position") or "top_or_bottom").strip().lower()
        op["position"] = pos if pos in {"top", "bottom", "top_or_bottom"} else "top_or_bottom"
        op["optional"] = bool(raw.get("optional", False))
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "look_opp_deck":
        op["count"] = max(1, min(5, int(raw.get("count") or 1)))
        pos = str(raw.get("position") or "top").strip().lower()
        op["position"] = pos if pos in {"top", "bottom"} else "top"
        op["optional"] = bool(raw.get("optional", False))
        if raw.get("declare_cost"):
            op["declare_cost"] = True
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "play_from_hand":
        op["count"] = max(1, min(5, int(raw.get("count") or 1)))
        ctype = str(raw.get("card_type") or "character").strip().lower()
        if ctype not in {"character", "event", "stage", "character_or_stage"}:
            ctype = "character"
        op["card_type"] = ctype
        op["optional"] = bool(raw.get("optional", True))
        if raw.get("as_cost"):
            op["as_cost"] = True
        if raw.get("cost_lte") is not None:
            try:
                op["cost_lte"] = max(0, min(10, int(raw.get("cost_lte"))))
            except (TypeError, ValueError):
                pass
        if raw.get("cost_eq") is not None:
            try:
                op["cost_eq"] = max(0, min(10, int(raw.get("cost_eq"))))
            except (TypeError, ValueError):
                pass
        if raw.get("cost_gte") is not None:
            try:
                op["cost_gte"] = max(0, min(10, int(raw.get("cost_gte"))))
            except (TypeError, ValueError):
                pass
        if raw.get("power_lte") is not None:
            try:
                op["power_lte"] = max(0, min(20000, int(raw.get("power_lte"))))
            except (TypeError, ValueError):
                pass
        if raw.get("power_gte") is not None:
            try:
                op["power_gte"] = max(0, min(20000, int(raw.get("power_gte"))))
            except (TypeError, ValueError):
                pass
        if raw.get("power_eq") is not None:
            try:
                op["power_eq"] = max(0, min(20000, int(raw.get("power_eq"))))
            except (TypeError, ValueError):
                pass
        for key, lo, hi in (("base_power_lte", 0, 20000), ("base_power_gte", 0, 20000)):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        if raw.get("same_name_as_trashed"):
            op["same_name_as_trashed"] = True
        if raw.get("name_contains"):
            op["name_contains"] = str(raw.get("name_contains"))[:160]
        if raw.get("exclude_name"):
            op["exclude_name"] = str(raw.get("exclude_name"))[:60]
        if raw.get("trait_contains"):
            op["trait_contains"] = str(raw.get("trait_contains"))[:80]
        if raw.get("trait_includes"):
            op["trait_includes"] = str(raw.get("trait_includes"))[:40]
        trait_any = raw.get("trait_any")
        if isinstance(trait_any, list):
            op["trait_any"] = [str(t)[:40] for t in trait_any if str(t).strip()][:4]
        if raw.get("color"):
            op["color"] = str(raw.get("color"))[:12]
        if raw.get("as_rested"):
            op["as_rested"] = True
        if raw.get("different_color"):
            op["different_color"] = True
        if raw.get("different_names"):
            op["different_names"] = True
        if raw.get("total_cost_lte") is not None:
            try:
                op["total_cost_lte"] = max(0, min(50, int(raw.get("total_cost_lte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("cost_lte_opp_don_field"):
            op["cost_lte_opp_don_field"] = True
        if raw.get("cost_lte_own_don_field"):
            op["cost_lte_own_don_field"] = True
        if raw.get("attribute"):
            op["attribute"] = str(raw.get("attribute"))[:40]
        if raw.get("attr_contains"):
            op["attr_contains"] = str(raw.get("attr_contains"))[:40]
            if "attribute" not in op:
                op["attribute"] = op["attr_contains"]
        if raw.get("name_or_trait"):
            op["name_or_trait"] = True
        if raw.get("name_or_attribute"):
            op["name_or_attribute"] = True
        if raw.get("trait_or_attribute"):
            op["trait_or_attribute"] = True
        zone = str(raw.get("from_zone") or "hand").strip().lower()
        if zone in {"hand", "trash", "hand_or_trash", "deck", "life"}:
            op["from_zone"] = zone
        if raw.get("require_trigger"):
            op["require_trigger"] = True
        if raw.get("no_base_effect"):
            op["no_base_effect"] = True
        if raw.get("self_card"):
            op["self_card"] = True
        owner = str(raw.get("owner") or "").strip().lower()
        if owner in {"self", "opponent"}:
            op["owner"] = owner
        if raw.get("if_returned"):
            op["if_returned"] = True
        if raw.get("card_id"):
            op["card_id"] = str(raw.get("card_id"))[:40]
        if raw.get("source_iid"):
            op["source_iid"] = str(raw.get("source_iid"))[:40]
        if raw.get("require_life_lte") is not None:
            try:
                op["require_life_lte"] = max(0, min(10, int(raw.get("require_life_lte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("require_leader_trait"):
            op["require_leader_trait"] = str(raw.get("require_leader_trait"))[:80]
        if raw.get("require_opp_don_field_gte") is not None:
            try:
                op["require_opp_don_field_gte"] = max(0, min(20, int(raw.get("require_opp_don_field_gte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "attach_don":
        op["count"] = max(1, min(5, int(raw.get("count") or 1)))
        if raw.get("as_rested"):
            op["as_rested"] = True
        if raw.get("as_cost"):
            op["as_cost"] = True
        if raw.get("from_rested"):
            op["from_rested"] = True
        if raw.get("from_active"):
            op["from_active"] = True
        if raw.get("from_cost_area"):
            op["from_cost_area"] = True
        tk = str(raw.get("target_kind") or "self").strip()
        if tk in TARGET_KINDS or tk in {"self", "leader", "own_character", "own_leader_or_character", "opponent_character", "opponent_leader_or_character"}:
            op["target_kind"] = tk
        op["optional"] = bool(raw.get("optional", True))
        owner = str(raw.get("owner") or "").strip().lower()
        if owner in {"self", "opponent"}:
            op["owner"] = owner
        from_owner = str(raw.get("from_owner") or "").strip().lower()
        if from_owner in {"self", "opponent"}:
            op["from_owner"] = from_owner
        if raw.get("name_contains"):
            op["name_contains"] = str(raw.get("name_contains"))[:60]
        if raw.get("trait_contains"):
            op["trait_contains"] = str(raw.get("trait_contains"))[:80]
        if raw.get("target_iid"):
            op["target_iid"] = str(raw.get("target_iid"))[:40]
        if raw.get("source_iid"):
            op["source_iid"] = str(raw.get("source_iid"))[:40]
        if raw.get("base_power_eq") is not None:
            try:
                op["base_power_eq"] = max(0, min(20000, int(raw.get("base_power_eq") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("target_count") is not None:
            try:
                op["target_count"] = max(1, min(5, int(raw.get("target_count") or 1)))
            except (TypeError, ValueError):
                pass
        if raw.get("max_per_target") is not None:
            try:
                op["max_per_target"] = max(1, min(5, int(raw.get("max_per_target") or 1)))
            except (TypeError, ValueError):
                pass
        if raw.get("all"):
            op["all"] = True
        if raw.get("exclude_iids"):
            raw_ex = raw.get("exclude_iids")
            if isinstance(raw_ex, list):
                op["exclude_iids"] = [str(x)[:40] for x in raw_ex if str(x).strip()][:8]
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "set_character_active":
        op["count"] = max(1, min(5, int(raw.get("count") or 1)))
        tk = str(raw.get("target_kind") or "own_character").strip()
        if tk in TARGET_KINDS or tk in {"self", "leader", "own_leader_or_character"}:
            op["target_kind"] = tk
        if raw.get("target_iid"):
            op["target_iid"] = str(raw.get("target_iid"))[:40]
        if raw.get("source_iid"):
            op["source_iid"] = str(raw.get("source_iid"))[:40]
        op["optional"] = bool(raw.get("optional", True))
        if raw.get("all"):
            op["all"] = True
        if raw.get("color"):
            op["color"] = str(raw.get("color")).strip().lower()[:20]
        if raw.get("attribute"):
            op["attribute"] = str(raw.get("attribute"))[:40]
        for key, lo, hi in (("cost_lte", 0, 10), ("cost_eq", 0, 10), ("cost_gte", 0, 10)):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        if raw.get("name_contains"):
            op["name_contains"] = str(raw.get("name_contains"))[:60]
        if raw.get("exclude_name"):
            op["exclude_name"] = str(raw.get("exclude_name"))[:60]
        if raw.get("trait_contains"):
            op["trait_contains"] = str(raw.get("trait_contains"))[:80]
        if raw.get("name_contains"):
            op["name_contains"] = str(raw.get("name_contains"))[:60]
        if raw.get("include_leader"):
            op["include_leader"] = True
        if raw.get("include_stage"):
            op["include_stage"] = True
        if raw.get("include_don"):
            op["include_don"] = True
        if raw.get("at_end_of_turn"):
            op["at_end_of_turn"] = True
        if raw.get("rested_only"):
            op["rested_only"] = True
        for key, lo, hi in (("cost_lte", 0, 10), ("base_cost_lte", 0, 10), ("cost_eq", 0, 10), ("cost_gte", 0, 10), ("power_lte", 0, 20000), ("power_gte", 0, 20000), ("require_deck_lte", 0, 60), ("require_rested_own_chars_gte", 0, 10), ("require_life_gte", 0, 10)):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        if raw.get("require_leader_trait"):
            op["require_leader_trait"] = str(raw.get("require_leader_trait"))[:80]
        if raw.get("require_opp_don_field_gte") is not None:
            try:
                op["require_opp_don_field_gte"] = max(0, min(20, int(raw.get("require_opp_don_field_gte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "cannot_be_ko" or kind == "cannot_be_removed" or kind == "cannot_be_rested":
        tk = str(raw.get("target_kind") or "self").strip()
        if tk in TARGET_KINDS or tk in {"self", "own_character", "own_characters", "opponent_character", "opponent_characters"}:
            op["target_kind"] = tk
        if raw.get("target_iid"):
            op["target_iid"] = str(raw.get("target_iid"))[:40]
        if raw.get("source_iid"):
            op["source_iid"] = str(raw.get("source_iid"))[:40]
        if raw.get("all"):
            op["all"] = True
        trait_any = raw.get("trait_any")
        if isinstance(trait_any, list):
            op["trait_any"] = [str(t)[:40] for t in trait_any if str(t).strip()][:4]
        elif raw.get("trait_contains"):
            op["trait_any"] = [str(raw.get("trait_contains"))[:40]]
        if raw.get("color"):
            op["color"] = str(raw.get("color")).strip().lower()[:20]
        if raw.get("exclude_name"):
            op["exclude_name"] = str(raw.get("exclude_name"))[:60]
        if raw.get("attribute"):
            op["attribute"] = str(raw.get("attribute"))[:40]
        for key, lo, hi in (("cost_lte", 0, 10), ("cost_gte", 0, 10), ("cost_eq", 0, 10)):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        if raw.get("opp_effect_base_power_lte") is not None:
            try:
                op["opp_effect_base_power_lte"] = max(0, min(20000, int(raw.get("opp_effect_base_power_lte") or 0)))
            except (TypeError, ValueError):
                pass
        if kind == "cannot_be_removed":
            op["any_leave"] = True
        if raw.get("any_leave"):
            op["any_leave"] = True
        if raw.get("vs_leader_only") or raw.get("vs_leader"):
            op["vs_leader_only"] = True
        dur = str(raw.get("duration") or "").strip().lower()
        if dur in {"turn", "battle", "permanent", "until_opp_turn_end", "next_turn"}:
            op["duration"] = dur
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
        op["optional"] = bool(raw.get("optional", True))
    if kind == "grant_keyword":
        kw = str(raw.get("keyword") or "").strip().lower()
        if kw in {"blocker", "rush", "rush_character", "double_attack", "banish", "blockerless"}:
            op["keyword"] = kw
        else:
            return None
        tk = str(raw.get("target_kind") or "self").strip()
        if tk in TARGET_KINDS or tk in {"self", "leader", "own_character", "own_characters"}:
            op["target_kind"] = tk
        if raw.get("source_iid"):
            op["source_iid"] = str(raw.get("source_iid"))[:40]
        if raw.get("target_iid"):
            op["target_iid"] = str(raw.get("target_iid"))[:40]
        if raw.get("name_contains"):
            op["name_contains"] = str(raw.get("name_contains"))[:80]
        if raw.get("exclude_name"):
            op["exclude_name"] = str(raw.get("exclude_name"))[:60]
        if raw.get("trait_contains"):
            op["trait_contains"] = str(raw.get("trait_contains"))[:80]
        if raw.get("trait_includes"):
            op["trait_includes"] = str(raw.get("trait_includes"))[:80]
        trait_any = raw.get("trait_any")
        if isinstance(trait_any, list):
            op["trait_any"] = [str(t)[:40] for t in trait_any if str(t).strip()][:4]
        if raw.get("name_or_trait"):
            op["name_or_trait"] = True
        for key, lo, hi in (("cost_lte", 0, 10), ("cost_eq", 0, 10), ("power_gte", 0, 20000), ("power_lte", 0, 20000)):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        if raw.get("cost_gte") is not None:
            try:
                op["cost_gte"] = max(0, min(12, int(raw.get("cost_gte") or 0)))
            except (TypeError, ValueError):
                pass
        dur = str(raw.get("duration") or "turn").strip().lower()
        if dur in {"turn", "permanent", "battle", "until_opp_turn_end", "next_turn"}:
            op["duration"] = dur
        else:
            op["duration"] = "turn"
        if raw.get("optional") is not None:
            op["optional"] = bool(raw.get("optional"))
        if raw.get("count") is not None:
            try:
                op["count"] = max(1, min(5, int(raw.get("count") or 1)))
            except (TypeError, ValueError):
                op["count"] = 1
        if raw.get("require_no_on_play"):
            op["require_no_on_play"] = True
        if raw.get("require_no_when_attacking"):
            op["require_no_when_attacking"] = True
        if raw.get("require_no_effect"):
            op["require_no_effect"] = True
        if raw.get("require_leader_trait"):
            op["require_leader_trait"] = str(raw.get("require_leader_trait"))[:80]
        if raw.get("require_leader_attribute"):
            op["require_leader_attribute"] = str(raw.get("require_leader_attribute"))[:40]
        if raw.get("exclude_self"):
            op["exclude_self"] = True
        if raw.get("all"):
            op["all"] = True
        if raw.get("effect_played_only"):
            op["effect_played_only"] = True
        if raw.get("same_target_as_prior"):
            op["same_target_as_prior"] = True
        if raw.get("color"):
            op["color"] = str(raw.get("color")).strip().lower()[:20]
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "grant_attribute":
        attr = str(raw.get("attribute") or raw.get("attr_contains") or "").strip()
        if not attr:
            return None
        op["attribute"] = attr[:40]
        tk = str(raw.get("target_kind") or "self").strip()
        if tk in TARGET_KINDS or tk in {"self", "leader", "own_character", "own_characters"}:
            op["target_kind"] = tk
        if raw.get("source_iid"):
            op["source_iid"] = str(raw.get("source_iid"))[:40]
        if raw.get("target_iid"):
            op["target_iid"] = str(raw.get("target_iid"))[:40]
        if raw.get("name_contains"):
            op["name_contains"] = str(raw.get("name_contains"))[:60]
        if raw.get("trait_contains"):
            op["trait_contains"] = str(raw.get("trait_contains"))[:40]
        dur = str(raw.get("duration") or "turn").strip().lower()
        if dur in {"turn", "permanent", "battle", "until_opp_turn_end", "next_turn"}:
            op["duration"] = dur
        if raw.get("optional") is not None:
            op["optional"] = bool(raw.get("optional"))
        if raw.get("count") is not None:
            try:
                op["count"] = max(1, min(5, int(raw.get("count") or 1)))
            except (TypeError, ValueError):
                op["count"] = 1
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "deny_blocker":
        dur = str(raw.get("duration") or "battle").strip().lower()
        op["duration"] = dur if dur in {"battle", "turn"} else "battle"
        if raw.get("when_leader_attacks"):
            op["when_leader_attacks"] = True
        if raw.get("optional") is not None:
            op["optional"] = bool(raw.get("optional"))
        if raw.get("count") is not None:
            try:
                op["count"] = max(1, min(5, int(raw.get("count") or 1)))
            except (TypeError, ValueError):
                pass
        if raw.get("target_iid"):
            op["target_iid"] = str(raw.get("target_iid"))[:40]
        tk = str(raw.get("target_kind") or "").strip()
        if tk in TARGET_KINDS or tk in {"opponent_character", "own_character", "self"}:
            op["target_kind"] = tk
        for key, lo, hi in (("power_lte", 0, 20000), ("power_gte", 0, 20000)):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        for key, lo, hi in (("cost_lte", 0, 10), ("cost_eq", 0, 10), ("cost_gte", 0, 10)):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        for key, lo, hi in (("base_cost_lte", 0, 10), ("base_cost_gte", 0, 10)):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        if raw.get("require_life_lte") is not None:
            try:
                op["require_life_lte"] = max(0, min(10, int(raw.get("require_life_lte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "allow_attack_active":
        op["count"] = max(1, min(5, int(raw.get("count") or 1)))
        tk = str(raw.get("target_kind") or "own_character").strip()
        if tk in TARGET_KINDS or tk in {"self", "own_leader_or_character", "leader"}:
            op["target_kind"] = tk
        if raw.get("trait_contains"):
            op["trait_contains"] = str(raw.get("trait_contains"))[:40]
        trait_any = raw.get("trait_any")
        if isinstance(trait_any, list):
            op["trait_any"] = [str(t)[:40] for t in trait_any if str(t).strip()][:4]
        if raw.get("target_iid"):
            op["target_iid"] = str(raw.get("target_iid"))[:40]
        if raw.get("source_iid"):
            op["source_iid"] = str(raw.get("source_iid"))[:40]
        if raw.get("require_opp_chars_count_gte") is not None:
            try:
                op["require_opp_chars_count_gte"] = max(
                    0, min(10, int(raw.get("require_opp_chars_count_gte") or 0))
                )
            except (TypeError, ValueError):
                pass
        op["optional"] = bool(raw.get("optional", True))
        if raw.get("require_leader_trait"):
            op["require_leader_trait"] = str(raw.get("require_leader_trait"))[:80]
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "trash_hand":
        op["count"] = max(1, min(10, int(raw.get("count") or 1)))
        op["optional"] = bool(raw.get("optional", True))
        if raw.get("as_cost"):
            op["as_cost"] = True
        if raw.get("all"):
            op["all"] = True
            op["count"] = max(1, min(10, int(raw.get("count") or 10)))
        if raw.get("any_number"):
            op["any_number"] = True
            op["count"] = max(1, min(20, int(raw.get("count") or 20)))
        if raw.get("require_trigger"):
            op["require_trigger"] = True
        if raw.get("trait_contains"):
            op["trait_contains"] = str(raw.get("trait_contains"))[:40]
        if raw.get("name_contains"):
            op["name_contains"] = str(raw.get("name_contains"))[:60]
        ctype = str(raw.get("card_type") or "").strip().lower()
        if ctype in {"character", "event", "stage", "event_or_stage"}:
            op["card_type"] = ctype
        for key, lo, hi in (("power_lte", 0, 20000), ("power_eq", 0, 20000), ("power_gte", 0, 20000), ("cost_lte", 0, 10), ("cost_eq", 0, 10), ("cost_gte", 0, 10)):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        owner = str(raw.get("owner") or "self").strip().lower()
        if owner in {"self", "opponent"}:
            op["owner"] = owner
        if raw.get("then_trash_equal"):
            op["then_trash_equal"] = True
        if raw.get("source_iid"):
            op["source_iid"] = str(raw.get("source_iid"))[:40]
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
        if raw.get("require_rested_cards_gte") is not None:
            try:
                op["require_rested_cards_gte"] = max(0, min(20, int(raw.get("require_rested_cards_gte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("require_opp_chars_count_lte") is not None:
            try:
                op["require_opp_chars_count_lte"] = max(0, min(10, int(raw.get("require_opp_chars_count_lte") or 0)))
            except (TypeError, ValueError):
                pass
        for key, lo, hi in (("require_opp_hand_gte", 0, 20), ("require_opp_hand_lte", 0, 20), ("require_hand_gte", 0, 20), ("require_hand_lte", 0, 20)):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        chooser = str(raw.get("chooser") or "").strip().lower()
        if chooser in {"self", "opponent"}:
            op["chooser"] = chooser
    if kind == "replace_battle_ko":
        op["duration"] = "turn"
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "win_game":
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "arm_untap_on_char_battle":
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "arm_draw_on_event":
        try:
            op["cost_gte"] = max(0, min(10, int(raw.get("cost_gte") or raw.get("event_cost_gte") or 0)))
        except (TypeError, ValueError):
            op["cost_gte"] = 0
        try:
            op["count"] = max(1, min(5, int(raw.get("count") or raw.get("draw") or 1)))
        except (TypeError, ValueError):
            op["count"] = 1
        dur = str(raw.get("duration") or "turn").strip().lower()
        op["duration"] = dur if dur in {"turn", "until_opp_turn_end"} else "turn"
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "cannot_attack_char_base_cost_lte":
        try:
            op["count"] = max(0, min(10, int(raw.get("count") or raw.get("base_cost_lte") or 0)))
        except (TypeError, ValueError):
            op["count"] = 0
        dur = str(raw.get("duration") or "turn").strip().lower()
        if dur in {"turn", "until_opp_turn_end"}:
            op["duration"] = dur
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "rest_opponent_char_or_don":
        try:
            op["count"] = max(1, min(5, int(raw.get("count") or 1)))
        except (TypeError, ValueError):
            op["count"] = 1
        op["optional"] = bool(raw.get("optional", True))
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "play_characters_rested":
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "cannot_attack_leader":
        dur = str(raw.get("duration") or "turn").strip().lower()
        op["duration"] = dur if dur in {"turn", "until_opp_turn_end"} else "turn"
        if raw.get("on_play_turn") or raw.get("while_summoning_sick"):
            op["on_play_turn"] = True
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "replace_rest":
        # Continuous shield: rest another Character instead of this one being rested.
        tgt = str(raw.get("target") or "self").strip().lower()
        if tgt not in {"self"}:
            tgt = "self"
        op["target"] = tgt
        cost = str(raw.get("cost") or "rest_other_character").strip().lower()
        if cost not in {"rest_other_character", "rest_own", "rest_self"}:
            cost = "rest_other_character"
        op["cost"] = cost
        try:
            op["rest_count"] = max(1, min(5, int(raw.get("rest_count") or raw.get("count") or 1)))
        except (TypeError, ValueError):
            op["rest_count"] = 1
        if raw.get("rest_trait_contains"):
            op["rest_trait_contains"] = str(raw.get("rest_trait_contains"))[:40]
        op["optional"] = bool(raw.get("optional", True))
        if raw.get("once"):
            op["once"] = True
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "replace_leave":
        # Continuous shield: pay Life cost instead of leaving / being K.O.'d.
        trigger = str(raw.get("trigger") or "ko").strip().lower()
        if trigger in {"any_leave", "leave", "any"}:
            op["any_leave"] = True
            op["trigger"] = trigger
        elif trigger not in {"ko", "opp_remove"}:
            op["trigger"] = "ko"
        else:
            op["trigger"] = trigger
        tgt = str(raw.get("target") or "self").strip().lower()
        if tgt not in {"self", "own_filtered"}:
            tgt = "self"
        op["target"] = tgt
        cost = str(raw.get("cost") or "trash_life").strip().lower()
        if cost not in {
            "trash_life",
            "life_to_hand",
            "trash_hand",
            "flip_life",
            "trash_self",
            "ko_self",
            "rest_self",
            "rest_own",
            "rest_other_character",
            "return_don",
            "trash_to_bottom",
            "to_life",
            "rest_don",
            "return_self_to_hand",
            "return_other_to_bottom",
            "return_own_to_bottom",
            "self_power_minus",
        }:
            cost = "trash_life"
        op["cost"] = cost
        if cost == "return_don":
            try:
                op["don_count"] = max(1, min(5, int(raw.get("don_count") or raw.get("count") or 1)))
            except (TypeError, ValueError):
                op["don_count"] = 1
        if cost == "trash_hand":
            try:
                op["count"] = max(1, min(10, int(raw.get("count") or raw.get("trash_count") or 1)))
            except (TypeError, ValueError):
                op["count"] = 1
        if cost == "trash_to_bottom":
            try:
                op["trash_count"] = max(1, min(10, int(raw.get("trash_count") or raw.get("count") or 3)))
            except (TypeError, ValueError):
                op["trash_count"] = 3
        if cost == "self_power_minus":
            try:
                op["amount"] = max(-10000, min(0, int(raw.get("amount") or -2000)))
            except (TypeError, ValueError):
                op["amount"] = -2000
        if cost in {"rest_own", "rest_other_character", "rest_don"}:
            try:
                op["rest_count"] = max(1, min(5, int(raw.get("rest_count") or raw.get("count") or 1)))
            except (TypeError, ValueError):
                op["rest_count"] = 1
        if cost == "rest_other_character":
            rest_owner = str(raw.get("rest_owner") or "").strip().lower()
            if rest_owner in {"self", "opponent"}:
                op["rest_owner"] = rest_owner
            if raw.get("rest_trait_contains"):
                op["rest_trait_contains"] = str(raw.get("rest_trait_contains"))[:40]
        if cost == "self_power_minus":
            apply_to = str(raw.get("apply_to") or "").strip().lower()
            if apply_to in {"self", "leader", "source"}:
                op["apply_to"] = apply_to
        if cost == "flip_life":
            face = str(raw.get("face") or "up").strip().lower()
            op["face"] = "down" if face == "down" else "up"
        pos = str(raw.get("life_position") or "top").strip().lower()
        if pos in {"top", "bottom", "top_or_bottom"}:
            op["life_position"] = pos
        if raw.get("trait_contains"):
            op["trait_contains"] = str(raw.get("trait_contains"))[:40]
        if raw.get("rest_trait_contains"):
            op["rest_trait_contains"] = str(raw.get("rest_trait_contains"))[:40]
        if raw.get("name_contains"):
            op["name_contains"] = str(raw.get("name_contains"))[:80]
        if raw.get("rest_name_contains"):
            op["rest_name_contains"] = str(raw.get("rest_name_contains"))[:80]
        if raw.get("attr_contains"):
            op["attr_contains"] = str(raw.get("attr_contains"))[:20]
        if raw.get("exclude_name"):
            op["exclude_name"] = str(raw.get("exclude_name"))[:40]
        if raw.get("exclude_self"):
            op["exclude_self"] = True
        if raw.get("rested_only"):
            op["rested_only"] = True
        if raw.get("color"):
            op["color"] = str(raw.get("color")).strip().lower()[:20]
        if raw.get("base_power_gte") is not None:
            try:
                op["base_power_gte"] = max(0, min(20000, int(raw.get("base_power_gte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("base_power_lte") is not None:
            try:
                op["base_power_lte"] = max(0, min(20000, int(raw.get("base_power_lte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("base_power_eq") is not None:
            try:
                op["base_power_eq"] = max(0, min(20000, int(raw.get("base_power_eq") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("power_lte") is not None:
            try:
                op["power_lte"] = max(0, min(20000, int(raw.get("power_lte") or 0)))
            except (TypeError, ValueError):
                pass
        ctype = str(raw.get("card_type") or "").strip().lower()
        if ctype in {"character", "event", "stage"}:
            op["card_type"] = ctype
        # Prefer explicit hand_card_type for trash_hand cost (don't collide with victim card_type).
        if cost == "trash_hand":
            hand_ctype = str(raw.get("hand_card_type") or "").strip().lower()
            if not hand_ctype and ctype in {"event", "stage", "character", "event_or_stage"}:
                hand_ctype = ctype
                # Victim filters shouldn't steal event/stage hand cost type.
                if ctype in {"event", "stage", "event_or_stage"}:
                    op.pop("card_type", None)
            if hand_ctype in {"character", "event", "stage", "event_or_stage"}:
                op["hand_card_type"] = hand_ctype
            for key, lo, hi in (("hand_power_gte", 0, 20000), ("hand_power_lte", 0, 20000)):
                if raw.get(key) is not None:
                    try:
                        op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                    except (TypeError, ValueError):
                        pass
        if raw.get("base_cost_lte") is not None:
            try:
                op["base_cost_lte"] = max(0, min(10, int(raw.get("base_cost_lte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("base_cost_gte") is not None:
            try:
                op["base_cost_gte"] = max(0, min(10, int(raw.get("base_cost_gte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("then_draw") is not None:
            try:
                op["then_draw"] = max(0, min(5, int(raw.get("then_draw") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("hand_trait_contains"):
            op["hand_trait_contains"] = str(raw.get("hand_trait_contains"))[:40]
        if raw.get("once"):
            op["once"] = True
        if raw.get("any_leave"):
            op["any_leave"] = True
        op["optional"] = bool(raw.get("optional", True))
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "cannot_take_life":
        op["duration"] = "turn"
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "skip_untap":
        op["count"] = max(1, min(5, int(raw.get("count") or 1)))
        tk = str(raw.get("target_kind") or "opponent_character_rested").strip()
        if tk in TARGET_KINDS or tk.endswith("_rested") or tk in {"self", "own_character", "any_character", "all", "all_characters", "leader"}:
            op["target_kind"] = tk
        for key, lo, hi in (("cost_lte", 0, 10), ("cost_eq", 0, 10), ("power_lte", 0, 20000), ("base_power_lte", 0, 20000), ("don_attached_gte", 0, 10)):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        op["optional"] = bool(raw.get("optional", True))
        if raw.get("include_leader"):
            op["include_leader"] = True
        if raw.get("include_don"):
            op["include_don"] = True
        if raw.get("include_stage"):
            op["include_stage"] = True
        if raw.get("all"):
            op["all"] = True
        if raw.get("always_choose"):
            op["always_choose"] = True
        if raw.get("require_rested"):
            op["require_rested"] = True
        if raw.get("require_chars_trait"):
            op["require_chars_trait"] = str(raw.get("require_chars_trait"))[:40]
        if raw.get("require_chars_trait_gte") is not None:
            try:
                op["require_chars_trait_gte"] = max(0, min(5, int(raw.get("require_chars_trait_gte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "reorder_life":
        owner = str(raw.get("owner") or "self").strip().lower()
        if owner in {"self", "opponent", "self_or_opponent"}:
            op["owner"] = owner
        else:
            op["owner"] = "self"
        if raw.get("to_deck_top"):
            op["to_deck_top"] = True
        if raw.get("look_top"):
            op["look_top"] = True
        if raw.get("count") is not None:
            try:
                op["count"] = max(1, min(5, int(raw.get("count") or 1)))
            except (TypeError, ValueError):
                pass
        if raw.get("optional") is not None:
            op["optional"] = bool(raw.get("optional"))
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "trash_deck_top":
        op["count"] = max(1, min(10, int(raw.get("count") or 1)))
        op["optional"] = bool(raw.get("optional", False))
        if raw.get("as_cost"):
            op["as_cost"] = True
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "reduce_cost":
        try:
            op["amount"] = max(-20, min(20, int(raw.get("amount") or 0)))
        except (TypeError, ValueError):
            op["amount"] = -1
        op["count"] = max(1, min(5, int(raw.get("count") or 1)))
        tk = str(raw.get("target_kind") or "opponent_character").strip()
        if tk in TARGET_KINDS:
            op["target_kind"] = tk
        if raw.get("target_iid"):
            op["target_iid"] = str(raw.get("target_iid"))[:40]
        op["optional"] = bool(raw.get("optional", True))
        for key, lo, hi in (("cost_lte", 0, 10), ("cost_eq", 0, 10)):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        dur = str(raw.get("duration") or "turn").strip().lower()
        op["duration"] = dur if dur in {"turn", "battle", "until_opp_turn_end"} else "turn"
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "buff_all_own":
        try:
            op["amount"] = max(-10000, min(10000, int(raw.get("amount") or 0)))
        except (TypeError, ValueError):
            op["amount"] = 1000
        op["include_leader"] = bool(raw.get("include_leader", True))
        if raw.get("trait_contains"):
            op["trait_contains"] = str(raw.get("trait_contains"))[:40]
        if raw.get("trait_any") and isinstance(raw.get("trait_any"), list):
            op["trait_any"] = [str(x)[:40] for x in raw.get("trait_any") if str(x).strip()][:4]
        for key, lo, hi in (
            ("base_power_eq", 0, 20000),
            ("base_power_lte", 0, 20000),
            ("base_power_gte", 0, 20000),
        ):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        if raw.get("exclude_self"):
            op["exclude_self"] = True
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
        dur = str(raw.get("duration") or "").strip().lower()
        if dur in {"turn", "battle", "permanent", "until_opp_turn_end", "next_turn"}:
            op["duration"] = dur
    if kind in {"static_reduce_opp_cost", "hand_cost_reduce"}:
        try:
            op["amount"] = max(-20, min(20, int(raw.get("amount") or 0)))
        except (TypeError, ValueError):
            op["amount"] = -1
        if kind == "hand_cost_reduce":
            if raw.get("trait_contains"):
                op["trait_contains"] = str(raw.get("trait_contains"))[:40]
            if raw.get("name_contains"):
                op["name_contains"] = str(raw.get("name_contains"))[:80]
            if raw.get("cost_gte") is not None:
                try:
                    op["cost_gte"] = max(0, min(10, int(raw.get("cost_gte") or 0)))
                except (TypeError, ValueError):
                    pass
            if raw.get("next_only"):
                op["next_only"] = True
            if raw.get("once"):
                op["once"] = True
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
        if raw.get("trait_contains"):
            op["trait_contains"] = str(raw.get("trait_contains"))[:40]
        if raw.get("trait_any") and isinstance(raw.get("trait_any"), list):
            op["trait_any"] = [str(x)[:40] for x in raw.get("trait_any") if str(x).strip()][:4]
        for key, lo, hi in (("base_power_eq", 0, 20000), ("base_power_lte", 0, 20000), ("base_power_gte", 0, 20000)):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass

    if kind == "choose_target":
        tk = str(raw.get("target_kind") or "opponent_character")
        if tk not in TARGET_KINDS:
            tk = "opponent_character"
        op["target_kind"] = tk
        op["then_op"] = sanitize_op(raw.get("then_op")) if isinstance(raw.get("then_op"), dict) else None
        op["optional"] = bool(raw.get("optional", True))
        for key, lo, hi in (
            ("cost_lte", 0, 10),
            ("cost_eq", 0, 10),
            ("cost_gte", 0, 10),
            ("power_lte", 0, 20000),
            ("base_power_lte", 0, 20000),
        ):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "place_on_life":
        op["count"] = max(1, min(3, int(raw.get("count") or 1)))
        owner = str(raw.get("owner") or "opponent").strip().lower()
        if owner in {"controller", "card_owner", "owner"}:
            owner = "self"
        op["owner"] = owner if owner in {"self", "opponent"} else "opponent"
        pos = str(raw.get("position") or "top_or_bottom").strip().lower()
        op["position"] = pos if pos in {"top", "bottom", "top_or_bottom"} else "top_or_bottom"
        face = str(raw.get("face") or "up").strip().lower()
        op["face"] = face if face in {"up", "down"} else "up"
        default_tk = "own_character" if op.get("owner") == "self" else "opponent_character"
        tk = str(raw.get("target_kind") or default_tk)
        if tk in TARGET_KINDS or tk in {"own_character", "self", "opponent_character"}:
            op["target_kind"] = tk
        if raw.get("target_iid"):
            op["target_iid"] = str(raw.get("target_iid"))[:40]
        if raw.get("char_iid"):
            op["char_iid"] = str(raw.get("char_iid"))[:40]
        op["optional"] = bool(raw.get("optional", True))
        if raw.get("as_cost"):
            op["as_cost"] = True
        for key, lo, hi in (
            ("cost_lte", 0, 10),
            ("cost_eq", 0, 10),
            ("cost_gte", 0, 10),
            ("power_lte", 0, 20000),
            ("power_gte", 0, 20000),
            ("base_power_lte", 0, 20000),
            ("base_power_gte", 0, 20000),
        ):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        if raw.get("trait_contains"):
            op["trait_contains"] = str(raw.get("trait_contains"))[:80]
        if raw.get("exclude_name"):
            op["exclude_name"] = str(raw.get("exclude_name"))[:120]
        zone = str(raw.get("from_zone") or "").strip().lower()
        if zone in {"hand", "trash", "field"}:
            op["from_zone"] = zone
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "return_to_bottom":
        op["count"] = max(1, min(5, int(raw.get("count") or 1)))
        op["optional"] = bool(raw.get("optional", False))
        if raw.get("as_cost"):
            op["as_cost"] = True
        if raw.get("all"):
            op["all"] = True
        if raw.get("then_draw_equal"):
            op["then_draw_equal"] = True
        if raw.get("from_zone") == "hand":
            op["from_zone"] = "hand"
        if raw.get("exclude_self"):
            op["exclude_self"] = True
        if raw.get("at_end_of_battle"):
            op["at_end_of_battle"] = True
        if raw.get("at_end_of_turn"):
            op["at_end_of_turn"] = True
        if raw.get("effect_played_only"):
            op["effect_played_only"] = True
        if raw.get("target_iid"):
            op["target_iid"] = str(raw.get("target_iid"))[:40]
        tk = str(raw.get("target_kind") or "").strip()
        if tk in TARGET_KINDS or tk in {"self", "leader"}:
            op["target_kind"] = tk
        for key, lo, hi in (
            ("cost_lte", 0, 10),
            ("cost_eq", 0, 10),
            ("cost_gte", 0, 10),
            ("base_cost_lte", 0, 10),
            ("base_cost_gte", 0, 10),
            ("base_cost_eq", 0, 10),
            ("power_lte", 0, 20000),
            ("base_power_lte", 0, 20000),
            ("base_power_gte", 0, 20000),
        ):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
        if raw.get("card_id"):
            op["card_id"] = str(raw.get("card_id"))[:40]
        if raw.get("source_iid"):
            op["source_iid"] = str(raw.get("source_iid"))[:40]
    if kind == "negate_effects":
        op["count"] = max(1, min(20, int(raw.get("count") or 1)))
        op["optional"] = bool(raw.get("optional", True))
        dur = str(raw.get("duration") or "turn").strip().lower()
        op["duration"] = dur if dur in {"turn", "battle", "until_opp_turn_end"} else "turn"
        tk = str(raw.get("target_kind") or "opponent_leader_or_character").strip()
        if tk in TARGET_KINDS or tk in {
            "opponent_leader_or_character",
            "opponent_all",
            "self",
            "leader",
            "own_character",
            "own_characters",
        }:
            op["target_kind"] = tk
        else:
            op["target_kind"] = "opponent_leader_or_character"
        if raw.get("all"):
            op["all"] = True
        if raw.get("include_leader"):
            op["include_leader"] = True
        if raw.get("include_characters"):
            op["include_characters"] = True
        for key, lo, hi in (("cost_lte", 0, 10), ("cost_gte", 0, 10), ("cost_eq", 0, 10)):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        if raw.get("trait_contains"):
            op["trait_contains"] = str(raw.get("trait_contains"))[:40]
        if raw.get("exclude_trait"):
            op["exclude_trait"] = str(raw.get("exclude_trait"))[:40]
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
        if raw.get("source_iid"):
            op["source_iid"] = str(raw.get("source_iid"))[:40]
        if raw.get("target_iid"):
            op["target_iid"] = str(raw.get("target_iid"))[:40]
        if raw.get("same_target_as_prior"):
            op["same_target_as_prior"] = True
    if kind == "negate_on_play":
        side = str(raw.get("side") or "opponent").strip().lower()
        op["side"] = side if side in {"self", "opponent", "both"} else "opponent"
        dur = str(raw.get("duration") or "until_opp_turn_end").strip().lower()
        op["duration"] = dur if dur in {"turn", "until_opp_turn_end", "permanent"} else "until_opp_turn_end"
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "opponent_hand_to_bottom":
        op["count"] = max(1, min(5, int(raw.get("count") or 1)))
        op["optional"] = bool(raw.get("optional", False))
        for key, lo, hi in (("require_opp_hand_gte", 0, 20), ("require_opp_hand_lte", 0, 20)):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "trash_to_bottom":
        op["count"] = max(1, min(20, int(raw.get("count") or 1)))
        op["optional"] = bool(raw.get("optional", False))
        # Default self: "place N cards from your trash at the bottom of your deck".
        owner = str(raw.get("owner") or "self").strip().lower()
        op["owner"] = owner if owner in {"self", "opponent"} else "self"
        ct = str(raw.get("card_type") or "any").strip().lower()
        if ct in {"event", "character", "any"}:
            op["card_type"] = ct
        if raw.get("order_any"):
            op["order_any"] = True
        if raw.get("as_cost"):
            op["as_cost"] = True
        if raw.get("trait_contains"):
            op["trait_contains"] = str(raw.get("trait_contains"))[:40]
        if raw.get("trait_includes"):
            op["trait_includes"] = str(raw.get("trait_includes"))[:40]
        for key, lo, hi in (("cost_gte", 0, 10), ("cost_lte", 0, 10), ("cost_eq", 0, 10)):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        if raw.get("name_contains"):
            op["name_contains"] = str(raw.get("name_contains"))[:60]
        if raw.get("buff_self_per_n") is not None:
            try:
                op["buff_self_per_n"] = max(1, min(10, int(raw.get("buff_self_per_n") or 1)))
            except (TypeError, ValueError):
                pass
        if raw.get("buff_self_amount") is not None:
            try:
                op["buff_self_amount"] = max(0, min(10000, int(raw.get("buff_self_amount") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "cannot_attack":
        tk = str(raw.get("target_kind") or "self").strip()
        if tk in TARGET_KINDS or tk in {"self", "leader", "own_leader", "own_character", "own_characters"}:
            op["target_kind"] = tk
        if raw.get("all"):
            op["all"] = True
        for key, lo, hi in (("cost_lte", 0, 10), ("cost_eq", 0, 10), ("cost_gte", 0, 10)):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        cost_in = raw.get("cost_in")
        if isinstance(cost_in, list):
            vals = []
            for x in cost_in:
                try:
                    vals.append(max(0, min(10, int(x))))
                except (TypeError, ValueError):
                    pass
            if vals:
                op["cost_in"] = vals[:6]
        if raw.get("unless_field_char_base_power_gte") is not None:
            try:
                op["unless_field_char_base_power_gte"] = max(
                    0, min(20000, int(raw.get("unless_field_char_base_power_gte") or 0))
                )
            except (TypeError, ValueError):
                pass
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "taunt":
        tk = str(raw.get("target_kind") or "self").strip()
        if tk in TARGET_KINDS or tk in {"self"}:
            op["target_kind"] = tk
        if raw.get("while_rested"):
            op["while_rested"] = True
        if raw.get("name_contains"):
            op["name_contains"] = str(raw.get("name_contains"))[:60]
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "activate_timing":
        t = str(raw.get("timing") or "on_ko").strip().lower()
        if t in TIMINGS:
            op["timing"] = t
        else:
            op["timing"] = "on_ko"
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "add_from_trash":
        op["count"] = max(1, min(5, int(raw.get("count") or 1)))
        op["optional"] = bool(raw.get("optional", True))
        if raw.get("require_trigger"):
            op["require_trigger"] = True
        if raw.get("name_exclude"):
            op["name_exclude"] = str(raw.get("name_exclude"))[:80]
        if raw.get("exclude_name"):
            op["exclude_name"] = str(raw.get("exclude_name"))[:120]
            op["name_exclude"] = op["exclude_name"]
        if raw.get("name_contains"):
            op["name_contains"] = str(raw.get("name_contains"))[:60]
        if raw.get("trait_contains"):
            op["trait_contains"] = str(raw.get("trait_contains"))[:80]
        ctype = str(raw.get("card_type") or "").strip().lower()
        if ctype in {"character", "event", "stage", "any"}:
            op["card_type"] = ctype
        if raw.get("color"):
            op["color"] = str(raw.get("color")).strip().lower()[:20]
        if raw.get("cost_eq") is not None:
            try:
                op["cost_eq"] = max(0, min(10, int(raw.get("cost_eq"))))
            except (TypeError, ValueError):
                pass
        if raw.get("cost_lte") is not None:
            try:
                op["cost_lte"] = max(0, min(10, int(raw.get("cost_lte"))))
            except (TypeError, ValueError):
                pass
        if raw.get("cost_gte") is not None:
            try:
                op["cost_gte"] = max(0, min(10, int(raw.get("cost_gte"))))
            except (TypeError, ValueError):
                pass
        if raw.get("require_life_lte") is not None:
            try:
                op["require_life_lte"] = max(0, min(10, int(raw.get("require_life_lte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("self_card"):
            op["self_card"] = True
        if raw.get("require_trash_gte") is not None:
            try:
                op["require_trash_gte"] = max(0, min(60, int(raw.get("require_trash_gte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
        dest = str(raw.get("destination") or "hand").strip().lower()
        if dest in {"hand", "life"}:
            op["destination"] = dest
        face = str(raw.get("face") or "").strip().lower()
        if face in {"up", "down"}:
            op["face"] = face
        pos = str(raw.get("position") or "").strip().lower()
        if pos in {"top", "bottom"}:
            op["position"] = pos
    if kind == "cannot_play_from_hand":
        op["duration"] = "turn"
        ct = str(raw.get("card_type") or "any").strip().lower()
        if ct in {"any", "character", "event", "stage"}:
            op["card_type"] = ct
        for key, lo, hi in (
            ("base_cost_gte", 0, 10),
            ("base_cost_lte", 0, 10),
            # OP14-020 FAQ: 「之後無法登場」only if cost≥5 Character exists (either field).
            ("require_field_char_cost_gte", 0, 10),
        ):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "hand_to_deck":
        if raw.get("all"):
            op["all"] = True
            op["count"] = max(1, min(20, int(raw.get("count") or 20)))
        else:
            op["count"] = max(1, min(5, int(raw.get("count") or 1)))
        pos = str(raw.get("position") or "bottom").strip().lower()
        op["position"] = pos if pos in {"top", "bottom", "top_or_bottom"} else "bottom"
        op["optional"] = bool(raw.get("optional", False))
        if raw.get("as_cost"):
            op["as_cost"] = True
        if raw.get("include_self"):
            op["include_self"] = True
        if raw.get("shuffle"):
            op["shuffle"] = True
        if raw.get("then_draw_equal"):
            op["then_draw_equal"] = True
        if raw.get("then_draw") is not None:
            try:
                op["then_draw"] = max(0, min(10, int(raw.get("then_draw") or 0)))
            except (TypeError, ValueError):
                pass
        owner = str(raw.get("owner") or "self").strip().lower()
        if owner in {"self", "opponent"}:
            op["owner"] = owner
        if raw.get("if_revealed_trait_contains"):
            op["if_revealed_trait_contains"] = str(raw.get("if_revealed_trait_contains"))[:80]
        if raw.get("if_revealed_trait_includes"):
            op["if_revealed_trait_includes"] = str(raw.get("if_revealed_trait_includes"))[:80]
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "reveal_opp_hand":
        op["count"] = max(1, min(5, int(raw.get("count") or 1)))
        op["optional"] = bool(raw.get("optional", False))
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "reveal_hand":
        op["count"] = max(1, min(10, int(raw.get("count") or 1)))
        op["optional"] = bool(raw.get("optional", True))
        if raw.get("as_cost"):
            op["as_cost"] = True
        ctype = str(raw.get("card_type") or "").strip().lower()
        if ctype in {"character", "event", "stage"}:
            op["card_type"] = ctype
        if raw.get("trait_contains"):
            op["trait_contains"] = str(raw.get("trait_contains"))[:80]
        if raw.get("trait_includes"):
            op["trait_includes"] = str(raw.get("trait_includes"))[:80]
        trait_any = raw.get("trait_any")
        if isinstance(trait_any, list):
            op["trait_any"] = [str(t)[:40] for t in trait_any if str(t).strip()][:4]
        owner = str(raw.get("owner") or "self").strip().lower()
        if owner in {"self", "opponent"}:
            op["owner"] = owner
        for key, lo, hi in (("power_eq", 0, 20000), ("power_lte", 0, 20000), ("power_gte", 0, 20000), ("cost_lte", 0, 10), ("cost_eq", 0, 10)):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        if raw.get("require_trigger"):
            op["require_trigger"] = True
        if raw.get("then_to_deck_top"):
            op["then_to_deck_top"] = True
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "grant_cost":
        try:
            op["amount"] = max(-20, min(20, int(raw.get("amount") or 0)))
        except (TypeError, ValueError):
            op["amount"] = 1
        tk = str(raw.get("target_kind") or "own_character").strip()
        if tk in TARGET_KINDS or tk in {"self", "all_own"}:
            op["target_kind"] = tk
        if raw.get("name_contains"):
            op["name_contains"] = str(raw.get("name_contains"))[:60]
        if raw.get("exclude_name"):
            op["exclude_name"] = str(raw.get("exclude_name"))[:60]
        if raw.get("trait_contains"):
            op["trait_contains"] = str(raw.get("trait_contains"))[:80]
        if raw.get("trait_includes"):
            op["trait_includes"] = str(raw.get("trait_includes"))[:80]
        if raw.get("source_iid"):
            op["source_iid"] = str(raw.get("source_iid"))[:40]
        if raw.get("target_iid"):
            op["target_iid"] = str(raw.get("target_iid"))[:40]
        if raw.get("card_id"):
            op["card_id"] = str(raw.get("card_id"))[:40]
        if raw.get("color"):
            op["color"] = str(raw.get("color")).strip().lower()[:20]
        if raw.get("all"):
            op["all"] = True
        if raw.get("optional") is not None:
            op["optional"] = bool(raw.get("optional"))
        if raw.get("count") is not None:
            try:
                op["count"] = max(1, min(5, int(raw.get("count") or 1)))
            except (TypeError, ValueError):
                pass
        for key, lo, hi in (
            ("per_trash_cards", 1, 20),
            ("per_trash_events", 1, 20),
            ("cost_gte", 0, 10),
            ("cost_lte", 0, 10),
        ):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        dur = str(raw.get("duration") or "").strip().lower()
        if dur in {"turn", "battle", "permanent", "until_opp_turn_end"}:
            op["duration"] = dur
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "cannot_active_don_by_character":
        op["duration"] = "turn"
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "cannot_draw_by_effect":
        op["duration"] = "turn"
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "redirect_attack":
        tk = str(raw.get("target_kind") or "own_leader_or_character").strip()
        if tk in TARGET_KINDS or tk in {"own_leader_or_character", "leader", "self"}:
            op["target_kind"] = tk
        if raw.get("trait_contains"):
            op["trait_contains"] = str(raw.get("trait_contains"))[:40]
        if raw.get("name_contains"):
            op["name_contains"] = str(raw.get("name_contains"))[:60]
        if raw.get("include_leader"):
            op["include_leader"] = True
        if raw.get("base_power_gte") is not None:
            try:
                op["base_power_gte"] = max(0, min(20000, int(raw.get("base_power_gte") or 0)))
            except (TypeError, ValueError):
                pass
        op["optional"] = bool(raw.get("optional", False))
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "trash_hand_down_to":
        op["hand_size"] = max(0, min(10, int(raw.get("hand_size") or 5)))
        side = str(raw.get("side") or "both").strip().lower()
        op["side"] = side if side in {"self", "opponent", "both"} else "both"
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "life_to_hand":
        op["count"] = max(1, min(5, int(raw.get("count") or 1)))
        pos = str(raw.get("position") or "top").strip().lower()
        op["position"] = pos if pos in {"top", "bottom", "top_or_bottom"} else "top"
        op["optional"] = bool(raw.get("optional", True))
        if raw.get("as_cost"):
            op["as_cost"] = True
        if raw.get("if_played"):
            op["if_played"] = True
        owner = str(raw.get("owner") or "self").strip().lower()
        if owner in {"self", "opponent"}:
            op["owner"] = owner
        hand_owner = str(raw.get("hand_owner") or "").strip().lower()
        if hand_owner in {"life_owner", "controller"}:
            op["hand_owner"] = hand_owner
        elif owner == "opponent":
            # Default: stolen life goes to controller unless explicitly life_owner.
            op["hand_owner"] = "controller"
        if raw.get("require_opp_life_gte") is not None:
            try:
                op["require_opp_life_gte"] = max(0, min(10, int(raw.get("require_opp_life_gte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("require_opp_life_lte") is not None:
            try:
                op["require_opp_life_lte"] = max(0, min(10, int(raw.get("require_opp_life_lte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
        if raw.get("target_iid"):
            op["target_iid"] = str(raw.get("target_iid"))[:40]
    if kind in {"deny_attack", "deny_rest"}:
        op["count"] = max(1, min(5, int(raw.get("count") or 1)))
        op["optional"] = bool(raw.get("optional", True))
        tk = str(raw.get("target_kind") or "opponent_character").strip()
        if tk in TARGET_KINDS:
            op["target_kind"] = tk
        for key, lo, hi in (
            ("cost_lte", 0, 10),
            ("power_lte", 0, 20000),
            ("base_power_lte", 0, 20000),
            ("base_cost_lte", 0, 10),
        ):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        dur = str(raw.get("duration") or "until_opp_turn_end").strip().lower()
        op["duration"] = dur if dur in {"turn", "until_opp_turn_end", "battle"} else "until_opp_turn_end"
        if raw.get("active_only"):
            op["active_only"] = True
        if raw.get("all"):
            op["all"] = True
            op["optional"] = False
            op["count"] = max(op["count"], 5)
        if raw.get("include_leader"):
            op["include_leader"] = True
        if raw.get("rested_only"):
            op["rested_only"] = True
        if raw.get("exclude_name"):
            op["exclude_name"] = str(raw.get("exclude_name"))[:60]
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
        if raw.get("target_iid"):
            op["target_iid"] = str(raw.get("target_iid"))[:40]
        if raw.get("source_iid"):
            op["source_iid"] = str(raw.get("source_iid"))[:40]
        if raw.get("same_target_as_prior"):
            op["same_target_as_prior"] = True
        if raw.get("require_leader_trait"):
            op["require_leader_trait"] = str(raw.get("require_leader_trait"))[:80]
    if kind == "set_cost":
        try:
            op["amount"] = max(0, min(10, int(raw.get("amount") or 0)))
        except (TypeError, ValueError):
            op["amount"] = 0
        op["count"] = max(1, min(5, int(raw.get("count") or 1)))
        op["optional"] = bool(raw.get("optional", True))
        tk = str(raw.get("target_kind") or "opponent_character").strip()
        if tk in TARGET_KINDS:
            op["target_kind"] = tk
        if raw.get("require_no_effect"):
            op["require_no_effect"] = True
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
        if raw.get("target_iid"):
            op["target_iid"] = str(raw.get("target_iid"))[:40]
    if kind == "choose_one":
        chooser = str(raw.get("chooser") or "self").strip().lower()
        op["chooser"] = chooser if chooser in {"self", "opponent"} else "self"
        options_in = raw.get("options") if isinstance(raw.get("options"), list) else []
        options_out: list[dict[str, Any]] = []
        for i, opt in enumerate(options_in[:4]):
            if not isinstance(opt, dict):
                continue
            branch_ops = sanitize_ops_list(list(opt.get("ops") or []), max_ops=6)
            if not branch_ops:
                continue
            entry = {
                    "id": str(opt.get("id") or f"opt{i}")[:20],
                    "label": str(opt.get("label") or f"Option {i + 1}")[:120],
                    "ops": branch_ops,
                }
            for gk, gv in opt.items():
                if str(gk).startswith("require_") and gv is not None and gv is not False and gv != "":
                    if isinstance(gv, bool):
                        entry[gk] = True
                    elif isinstance(gv, (int, float)):
                        entry[gk] = gv
                    else:
                        entry[gk] = str(gv)[:120]
            options_out.append(entry)
        if len(options_out) < 2:
            return None
        op["options"] = options_out
        if raw.get("optional"):
            op["optional"] = True
        if raw.get("as_cost"):
            op["as_cost"] = True
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "attack_tax":
        op["trash_hand"] = max(1, min(5, int(raw.get("trash_hand") or 2)))
        op["all"] = bool(raw.get("all", True))
        dur = str(raw.get("duration") or "until_opp_turn_end").strip().lower()
        op["duration"] = dur if dur in {"turn", "until_opp_turn_end"} else "until_opp_turn_end"
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "trash_life":
        op["count"] = max(1, min(10, int(raw.get("count") or 1)))
        pos = str(raw.get("position") or "top").strip().lower()
        op["position"] = pos if pos in {"top", "bottom", "top_or_bottom", "all_face_up"} else "top"
        op["optional"] = bool(raw.get("optional", True))
        if raw.get("as_cost"):
            op["as_cost"] = True
        if raw.get("face_up"):
            op["face_up"] = True
        if raw.get("all") or pos == "all_face_up":
            op["all"] = True
            if pos == "all_face_up" or raw.get("face_up"):
                op["face_up"] = True
        owner = str(raw.get("owner") or "self").strip().lower()
        if owner in {"self", "opponent"}:
            op["owner"] = owner
        if raw.get("until_life_eq") is not None:
            try:
                op["until_life_eq"] = max(0, min(10, int(raw.get("until_life_eq") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("require_life_gte") is not None:
            try:
                op["require_life_gte"] = max(0, min(10, int(raw.get("require_life_gte") or 0)))
            except (TypeError, ValueError):
                pass
        if raw.get("require_leader_trait"):
            op["require_leader_trait"] = str(raw.get("require_leader_trait"))[:80]
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "hand_to_life":
        op["count"] = max(1, min(5, int(raw.get("count") or 1)))
        op["optional"] = bool(raw.get("optional", True))
        face = str(raw.get("face") or "").strip().lower()
        if face in {"up", "down"}:
            op["face"] = face
        pos = str(raw.get("position") or "").strip().lower()
        if pos in {"top", "bottom", "top_or_bottom"}:
            op["position"] = pos
        ctype = str(raw.get("card_type") or "").strip().lower()
        if ctype in {"character", "event", "stage"}:
            op["card_type"] = ctype
        if raw.get("require_trigger"):
            op["require_trigger"] = True
        if raw.get("name_contains"):
            op["name_contains"] = str(raw.get("name_contains"))[:60]
        if raw.get("trait_contains"):
            op["trait_contains"] = str(raw.get("trait_contains"))[:40]
        for key, lo, hi in (("cost_eq", 0, 10), ("cost_lte", 0, 10), ("cost_gte", 0, 10)):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        if raw.get("as_cost"):
            op["as_cost"] = True
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "flip_life":
        face = str(raw.get("face") or "down").strip().lower()
        op["face"] = face if face in {"up", "down"} else "down"
        pos = str(raw.get("position") or "top_or_bottom").strip().lower()
        op["position"] = pos if pos in {"top", "bottom", "top_or_bottom"} else "top_or_bottom"
        op["optional"] = bool(raw.get("optional", True))
        if raw.get("as_cost"):
            op["as_cost"] = True
        if raw.get("all"):
            op["all"] = True
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "look_life":
        op["count"] = max(1, min(5, int(raw.get("count") or 1)))
        owner = str(raw.get("owner") or "self").strip().lower()
        if owner in {"self", "opponent", "self_or_opponent"}:
            op["owner"] = owner
        else:
            op["owner"] = "self"
        pos = str(raw.get("position") or "top").strip().lower()
        op["position"] = pos if pos in {"top", "bottom", "top_or_bottom"} else "top"
        if raw.get("to_top_or_bottom"):
            op["to_top_or_bottom"] = True
        op["optional"] = bool(raw.get("optional", True))
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "reveal_life":
        op["count"] = max(1, min(5, int(raw.get("count") or 1)))
        pos = str(raw.get("position") or "top").strip().lower()
        op["position"] = pos if pos in {"top", "bottom", "top_or_bottom"} else "top"
        op["optional"] = bool(raw.get("optional", True))
        owner = str(raw.get("owner") or "self").strip().lower()
        if owner in {"self", "opponent"}:
            op["owner"] = owner
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "hand_counter":
        try:
            op["amount"] = max(-10000, min(10000, int(raw.get("amount") or 0)))
        except (TypeError, ValueError):
            op["amount"] = 2000
        for key, lo, hi in (("power_eq", 0, 20000), ("power_lte", 0, 20000), ("power_gte", 0, 20000)):
            if raw.get(key) is not None:
                try:
                    op[key] = max(lo, min(hi, int(raw.get(key) or 0)))
                except (TypeError, ValueError):
                    pass
        ctype = str(raw.get("card_type") or "character").strip().lower()
        if ctype in {"character", "event", "stage"}:
            op["card_type"] = ctype
        if raw.get("all"):
            op["all"] = True
        if raw.get("add"):
            op["add"] = True
        if raw.get("require_no_counter"):
            op["require_no_counter"] = True
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "rule_don_deck_size":
        try:
            op["count"] = max(1, min(20, int(raw.get("count") or 10)))
        except (TypeError, ValueError):
            op["count"] = 10
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "rule_deckout_end_of_turn":
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "rule_ban_events_cost_gte":
        try:
            op["cost_gte"] = max(0, min(10, int(raw.get("cost_gte") or 2)))
        except (TypeError, ValueError):
            op["cost_gte"] = 2
        if raw.get("summary"):
            op["summary"] = str(raw.get("summary"))[:160]
    if kind == "unsupported":
        op["reason"] = str(raw.get("reason") or "")[:120]
    if raw.get("if_trashed"):
        op["if_trashed"] = True
    if raw.get("at_end_of_turn"):
        op["at_end_of_turn"] = True
    if raw.get("require_own_name_all") is not None:
        raw_all = raw.get("require_own_name_all")
        if isinstance(raw_all, list):
            op["require_own_name_all"] = [str(x)[:80] for x in raw_all if str(x).strip()][:6]
        elif isinstance(raw_all, str) and raw_all.strip():
            op["require_own_name_all"] = [x.strip()[:80] for x in raw_all.split(";") if x.strip()][:6]
    if raw.get("require_chars_base_power_eq") is not None:
        try:
            op["require_chars_base_power_eq"] = max(
                0, min(20000, int(raw.get("require_chars_base_power_eq") or 0))
            )
        except (TypeError, ValueError):
            pass
    # Common op-level gates (「之後，若…」).
    if raw.get("require_leader_trait") and "require_leader_trait" not in op:
        op["require_leader_trait"] = str(raw.get("require_leader_trait"))[:80]
    if raw.get("require_leader_name") and "require_leader_name" not in op:
        op["require_leader_name"] = str(raw.get("require_leader_name"))[:120]
    if raw.get("require_played_this_turn") and "require_played_this_turn" not in op:
        op["require_played_this_turn"] = True
    if raw.get("require_rested_own_chars_gte") is not None and "require_rested_own_chars_gte" not in op:
        try:
            op["require_rested_own_chars_gte"] = max(
                0, min(10, int(raw.get("require_rested_own_chars_gte") or 0))
            )
        except (TypeError, ValueError):
            pass
    if raw.get("require_life_gte") is not None and "require_life_gte" not in op:
        try:
            op["require_life_gte"] = max(0, min(10, int(raw.get("require_life_gte") or 0)))
        except (TypeError, ValueError):
            pass
    if raw.get("require_life_lte") is not None and "require_life_lte" not in op:
        try:
            op["require_life_lte"] = max(0, min(10, int(raw.get("require_life_lte") or 0)))
        except (TypeError, ValueError):
            pass
    if raw.get("require_life_less_than_opponent") and "require_life_less_than_opponent" not in op:
        op["require_life_less_than_opponent"] = True
    if raw.get("require_leader_multicolor") and "require_leader_multicolor" not in op:
        op["require_leader_multicolor"] = True
    if raw.get("require_opp_don_field_gte") is not None and "require_opp_don_field_gte" not in op:
        try:
            op["require_opp_don_field_gte"] = max(0, min(20, int(raw.get("require_opp_don_field_gte") or 0)))
        except (TypeError, ValueError):
            pass
    if raw.get("require_don_field_lte") is not None and "require_don_field_lte" not in op:
        try:
            op["require_don_field_lte"] = max(0, min(20, int(raw.get("require_don_field_lte") or 0)))
        except (TypeError, ValueError):
            pass
    if raw.get("require_trash_gte") is not None and "require_trash_gte" not in op:
        try:
            op["require_trash_gte"] = max(0, min(60, int(raw.get("require_trash_gte") or 0)))
        except (TypeError, ValueError):
            pass
    if raw.get("require_own_char_cost_gte") is not None and "require_own_char_cost_gte" not in op:
        try:
            op["require_own_char_cost_gte"] = max(0, min(12, int(raw.get("require_own_char_cost_gte") or 0)))
        except (TypeError, ValueError):
            pass
    if raw.get("require_chars_trait") and "require_chars_trait" not in op:
        op["require_chars_trait"] = str(raw.get("require_chars_trait"))[:80]
    if raw.get("same_target_as_prior") and "same_target_as_prior" not in op:
        op["same_target_as_prior"] = True
    return op


def sanitize_ops_list(ops: list[Any], *, max_ops: int = 8) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in ops:
        op = sanitize_op(raw)
        if op:
            out.append(op)
        if len(out) >= max_ops:
            break
    return out


def normalize_card_entry(card_id: str, raw: dict[str, Any] | None) -> dict[str, Any]:
    abilities_in = []
    if isinstance(raw, dict):
        abilities_in = raw.get("abilities") if isinstance(raw.get("abilities"), list) else []
    abilities = []
    for a in abilities_in:
        na = normalize_ability(a if isinstance(a, dict) else None)
        if na:
            abilities.append(na)
    out: dict[str, Any] = {
        "card_id": card_id,
        "version": int((raw or {}).get("version") or 1) if isinstance(raw, dict) else 1,
        "abilities": abilities,
    }
    if isinstance(raw, dict) and raw.get("deck_ban_event_cost_gte") is not None:
        try:
            out["deck_ban_event_cost_gte"] = max(0, min(10, int(raw.get("deck_ban_event_cost_gte") or 0)))
        except (TypeError, ValueError):
            pass
    return out


def ability_is_runnable(ability: dict[str, Any]) -> bool:
    status = str(ability.get("status") or "")
    if status == "unsupported":
        return False
    ops = ability.get("ops") or []
    if not ops:
        return False
    if all(o.get("op") == "unsupported" for o in ops):
        return False
    return status in {"compiled", "verified", "needs_review"}
