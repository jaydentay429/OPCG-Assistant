from __future__ import annotations

import json
import re
from typing import Any, Callable

from battle.engine import apply_action, inst_power, legal_actions, printed_cost
from battle.state import MatchState


def pick_ai_action(state: MatchState, seat: int, catalog: Callable[[str], dict[str, Any]]) -> dict[str, Any] | None:
    actions = [a for a in legal_actions(state, seat, catalog) if a.get("type") != "concede"]
    if not actions:
        return None
    if state.pending_choice:
        picks = [a for a in actions if a.get("type") == "select_choice"]
        if picks and state.pending_choice.target_kind == "return_don":
            # Prefer cost-area DON, then leader, then characters (keep attached for power).
            order = ("don:active", "don:rested", "don:leader")
            ranked = sorted(
                picks,
                key=lambda a: (
                    order.index(str(a.get("target_iid")))
                    if str(a.get("target_iid")) in order
                    else 10
                ),
            )
            return ranked[0]
        if picks:
            return picks[0]
        if state.pending_choice.optional and any(a.get("type") == "skip_choice" for a in actions):
            return {"type": "skip_choice"}
        return None
    if state.pending_search:
        if state.pending_search.phase == "order":
            order_picks = [a for a in actions if a.get("type") == "order_search_bottom"]
            if order_picks:
                return order_picks[0]
            return {"type": "undo_search_order"} if any(a.get("type") == "undo_search_order" for a in actions) else None
        picks = [a for a in actions if a.get("type") == "select_search"]
        if picks:
            selected = {
                int(x)
                for x in (getattr(state.pending_search, "selected", None) or [])
            }
            max_add = max(1, int(getattr(state.pending_search, "max_add", 1) or 1))
            open_picks = [a for a in picks if int(a.get("index", -1)) not in selected]
            if open_picks and len(selected) < max_add:
                return open_picks[0]
            if any(a.get("type") == "confirm_search" for a in actions):
                return {"type": "confirm_search"}
            return picks[0]
        if any(a.get("type") == "confirm_search" for a in actions):
            return {"type": "confirm_search"}
        return {"type": "skip_search"}
    if state.pending_effect:
        # Prefer skip when uncertain ops look unsafe; otherwise accept library confirms.
        return {"type": "confirm_effect", "accept": True}

    player = state.player(seat)
    can_play = any(a.get("type") == "play_card" for a in actions)

    def score(action: dict[str, Any]) -> float:
        kind = action.get("type")
        foe = state.player(state.other(seat))
        if kind == "concede":
            return -1000
        if kind == "mulligan":
            # Keep hands with low average cost / some 1-drops; else redraw
            costs = []
            for cid in player.hand:
                costs.append(printed_cost(catalog(cid)))
            avg = sum(costs) / max(1, len(costs))
            low = sum(1 for c in costs if c <= 2)
            keep = avg <= 3.2 or low >= 2
            if action.get("redraw"):
                return 20 if not keep else -5
            return 20 if keep else -5
        if kind == "trigger":
            # Prefer activating when ops exist
            ops = (state.pending_trigger.ops if state.pending_trigger else None) or []
            if action.get("accept"):
                return 40 if ops else 5
            return 10 if not ops else -5
        if kind == "activate_main":
            return 70
        if kind == "play_card":
            ctype = action.get("card_type")
            cost = float(action.get("cost") or 0)
            bonus = 12 if ctype == "character" else 4 if ctype == "stage" else 3
            replace = action.get("replace_iid")
            if replace:
                bonus -= 3
                try:
                    bonus -= inst_power(state, seat, str(replace), catalog) / 5000.0
                except Exception:
                    pass
            return 120 + cost * 4 + bonus
        if kind == "attach_don":
            if can_play:
                return 8
            if action.get("target_iid") == "leader":
                return 55
            return 62
        if kind == "remove_don":
            return -80
        if kind == "attack":
            atk = inst_power(state, seat, str(action["attacker_iid"]), catalog)
            tgt = str(action["target_iid"])
            if tgt == "leader":
                return 45 + atk / 200.0 + (25 if foe.life_count <= 2 else 0)
            def_p = inst_power(state, foe.seat, tgt, catalog)
            return 32 + (14 if atk >= def_p else -10) + atk / 400.0
        if kind == "block":
            blocker = action.get("blocker_iid")
            if not state.attack:
                return 0
            atk_p = inst_power(state, state.attack.attacker_seat, state.attack.attacker_iid, catalog)
            targeting_leader = state.attack.target_iid == "leader"
            if blocker is None:
                return -8 if targeting_leader and player.life_count <= 2 else 6
            blk_p = inst_power(state, seat, str(blocker), catalog)
            lethal = targeting_leader and player.life_count <= 1
            return (40 if lethal else 12) + (8 if blk_p >= atk_p else -6)
        if kind == "counter":
            if not state.attack:
                return -10
            atk_p = inst_power(state, state.attack.attacker_seat, state.attack.attacker_iid, catalog)
            tgt = state.attack.blocker_iid or state.attack.target_iid
            buff_tgt = str(action.get("buff_target") or tgt)
            base_def = inst_power(state, seat, "leader" if tgt == "leader" else tgt, catalog)
            # Only count buff if it lands on the defended card
            bonus = int(action.get("counter") or 0) if buff_tgt == ("leader" if tgt == "leader" else tgt) else 0
            projected = base_def + bonus
            if base_def < atk_p <= projected:
                return 36 if tgt == "leader" else 30
            return -8
        if kind == "pass_counter":
            return 5
        if kind == "end_turn":
            return -30 if can_play and player.don_active >= 1 else 2
        return 0

    ranked = sorted(actions, key=score, reverse=True)
    return ranked[0]


def pick_ai_action_smart(
    state: MatchState,
    seat: int,
    catalog: Callable[[str], dict[str, Any]],
    ask_llm: Callable[[str], str] | None = None,
) -> dict[str, Any] | None:
    heuristic = pick_ai_action(state, seat, catalog)
    actions = legal_actions(state, seat, catalog)
    if not ask_llm or not actions or state.pending_effect or state.phase in {"mulligan", "trigger"}:
        return heuristic
    player = state.player(seat)
    foe = state.player(state.other(seat))
    complex_choice = (
        (player.life_count <= 2 or foe.life_count <= 2)
        and state.phase in {"main", "block", "counter"}
        and len(actions) >= 6
    )
    if not complex_choice:
        return heuristic
    prompt = (
        "Pick exactly one legal OPTCG action. Return ONLY JSON like "
        '{"type":"attack","attacker_iid":"leader","target_iid":"leader"} '
        "copied from the legal list.\n"
        f"My seat: {seat} life={player.life_count} don={player.don_active}\n"
        f"Foe life={foe.life_count}\n"
        f"Phase: {state.phase}\n"
        f"Legal actions:\n{json.dumps(actions[:40], ensure_ascii=False)}\n"
    )
    try:
        raw = ask_llm(prompt).strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.S)
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("type"):
            for item in actions:
                if all(item.get(k) == data.get(k) for k in item.keys() if k in data or k == "type"):
                    if item.get("type") == data.get("type"):
                        return item
    except Exception:
        return heuristic
    return heuristic


def ai_must_act(state: MatchState) -> bool:
    """True when the seat that must act is an AI player."""
    if state.status != "playing":
        return False
    seat = _acting_seat(state)
    if seat is None:
        return False
    return bool(state.player(seat).is_ai)


def step_ai_once(
    state: MatchState,
    catalog: Callable[[str], dict[str, Any]],
    ask_llm: Callable[[str], str] | None = None,
) -> bool:
    """
    Apply at most one AI action (plus a single fallback if the pick fails).
    Returns True if the match advanced due to AI.
    """
    if state.status != "playing":
        return False
    # Recover orphaned trigger phase left after nested Trigger choices (engine bug legacy).
    if (
        state.phase == "trigger"
        and state.pending_trigger is None
        and not state.pending_choice
        and not state.pending_search
        and not state.pending_effect
        and getattr(state, "pending_replace", None) is None
    ):
        from battle.engine import _finish_cleared_interactive

        before = (state.phase, state.turn_number, bool(state.attack), getattr(state, "trigger_resume", None))
        _finish_cleared_interactive(state, catalog)
        after = (state.phase, state.turn_number, bool(state.attack), getattr(state, "trigger_resume", None))
        if after != before or state.phase != "trigger":
            return True
    # Attack declared but Block/Counter never entered (watchers settled with no acting seat).
    if (
        state.attack
        and not state.attack.combat_entered
        and not state.pending_choice
        and not state.pending_search
        and not state.pending_effect
        and not state.pending_trigger
        and getattr(state, "pending_replace", None) is None
    ):
        from battle.engine import _finish_cleared_interactive

        before = (
            state.phase,
            bool(state.attack.combat_entered) if state.attack else None,
            getattr(state.attack, "opp_attack_watchers_done", None) if state.attack else None,
        )
        _finish_cleared_interactive(state, catalog)
        after = (
            state.phase,
            bool(state.attack.combat_entered) if state.attack else None,
            getattr(state.attack, "opp_attack_watchers_done", None) if state.attack else None,
        )
        if after != before:
            return True
    if not ai_must_act(state):
        return False
    seat = _acting_seat(state)
    if seat is None:
        return False
    action = pick_ai_action_smart(state, seat, catalog, ask_llm=ask_llm)
    if not action:
        # Only concede left (filtered out) or empty — try safe progress actions.
        actions = [a for a in legal_actions(state, seat, catalog) if a.get("type") != "concede"]
        if not actions:
            if state.phase == "main" and state.attack is None:
                action = {"type": "end_turn"}
            elif state.phase == "block":
                action = {"type": "block", "blocker_iid": None}
            elif state.phase == "counter":
                action = {"type": "pass_counter"}
            else:
                return False
        else:
            return False
    result = apply_action(state, seat, action, catalog, ask_llm=ask_llm)
    if result.get("ok"):
        return True
    if state.phase == "block":
        apply_action(state, seat, {"type": "block", "blocker_iid": None}, catalog, ask_llm=ask_llm)
    elif state.phase == "counter":
        apply_action(state, seat, {"type": "pass_counter"}, catalog, ask_llm=ask_llm)
    elif state.phase == "mulligan":
        apply_action(state, seat, {"type": "mulligan", "redraw": False}, catalog, ask_llm=ask_llm)
    elif state.phase == "trigger":
        apply_action(state, seat, {"type": "trigger", "accept": True}, catalog, ask_llm=ask_llm)
    elif state.pending_search:
        if state.pending_search.phase == "order" and state.pending_search.revealed:
            apply_action(
                state,
                seat,
                {"type": "order_search_bottom", "index": 0},
                catalog,
                ask_llm=ask_llm,
            )
        else:
            apply_action(state, seat, {"type": "skip_search"}, catalog, ask_llm=ask_llm)
    elif state.pending_choice:
        opts = list(state.pending_choice.options or [])
        resolved = False
        for tid in opts:
            retry = apply_action(
                state, seat, {"type": "select_choice", "target_iid": tid}, catalog, ask_llm=ask_llm
            )
            if retry.get("ok"):
                resolved = True
                break
        if not resolved and state.pending_choice and state.pending_choice.optional:
            apply_action(state, seat, {"type": "skip_choice"}, catalog, ask_llm=ask_llm)
        elif not resolved:
            return False
    elif state.phase == "main":
        apply_action(state, seat, {"type": "end_turn"}, catalog, ask_llm=ask_llm)
    else:
        return False
    return True


def run_ai_until_human(
    state: MatchState,
    catalog: Callable[[str], dict[str, Any]],
    ask_llm: Callable[[str], str] | None = None,
    max_steps: int = 40,
) -> None:
    steps = 0
    while state.status == "playing" and steps < max_steps:
        if not step_ai_once(state, catalog, ask_llm=ask_llm):
            return
        steps += 1


def _acting_seat(state: MatchState) -> int | None:
    if state.pending_choice:
        return state.pending_choice.seat
    if state.pending_search:
        return state.pending_search.seat
    if state.pending_effect:
        # Only the effect controller may accept/decline (_confirm_effect).
        # Do NOT iterate all non-AI seats — in hotseat both seats are human and
        # that wrongly keeps the viewer on seat 0 while the defender must confirm
        # (e.g. 【对方攻击时】 after an attack → UI looks frozen until view flips).
        return int(state.pending_effect.seat)
    if state.phase == "mulligan" and state.mulligan_seat is not None:
        return state.mulligan_seat
    if state.phase == "trigger" and state.pending_trigger:
        return state.pending_trigger.seat
    if state.phase in {"block", "counter"} and state.attack:
        return state.other(state.attack.attacker_seat)
    # Attack declared but Block/Counter not entered yet (When Attacking still resolving).
    if state.attack and not state.attack.combat_entered and state.phase == "main":
        return int(state.attack.attacker_seat)
    if state.phase == "main":
        return state.turn_seat
    return None
