from __future__ import annotations

import json
import re
from typing import Any, Callable

from battle.choice_purpose import pending_choice_purpose
from battle.engine import apply_action, inst_power, legal_actions, printed_cost
from battle.state import CardInst, MatchState, PendingChoice, PlayerState

CatalogFn = Callable[[str], dict[str, Any]]


def _card_type(info: dict[str, Any]) -> str:
    raw = str(info.get("card_type") or info.get("type") or "").strip().lower()
    if "leader" in raw:
        return "leader"
    if "event" in raw:
        return "event"
    if "stage" in raw:
        return "stage"
    return "character"


def _name_blob(info: dict[str, Any], cid: str = "") -> str:
    parts = [
        cid,
        str(info.get("name") or ""),
        str(info.get("name_en") or ""),
        str(info.get("name_cn") or ""),
    ]
    return " ".join(parts).lower()


def _name_hits(info: dict[str, Any], needle: str, cid: str = "") -> bool:
    blob = _name_blob(info, cid)
    opts = [p.strip().lower() for p in str(needle or "").replace("|", "/").split("/") if p.strip()]
    return any(opt in blob for opt in opts) if opts else True


def _find_inst(player: PlayerState, iid: str) -> CardInst | None:
    if iid == "leader":
        return None
    for ch in player.characters:
        if ch.iid == iid:
            return ch
    for st in player.stages:
        if st.iid == iid:
            return st
    return None


def _inst_cost(catalog: CatalogFn, card_id: str) -> int:
    try:
        return printed_cost(catalog(card_id))
    except Exception:
        return 0


def _inst_printed_power(catalog: CatalogFn, card_id: str) -> int:
    info = catalog(card_id) or {}
    try:
        return int(info.get("power") or info.get("power_en") or 0)
    except (TypeError, ValueError):
        return 0


def _has_when_attacking(card_id: str) -> bool:
    try:
        from battle.effect_library import get_abilities

        return bool(get_abilities(card_id, "when_attacking"))
    except Exception:
        return False


def _hand_matches_op(
    info: dict[str, Any],
    op: dict[str, Any],
    cid: str = "",
    *,
    opp_don: int | None = None,
) -> bool:
    want_type = str(op.get("card_type") or "").strip().lower()
    if want_type:
        ctype = _card_type(info)
        if want_type == "event_or_stage" and ctype not in {"event", "stage"}:
            return False
        if want_type not in {"event_or_stage", "any", ""} and ctype != want_type:
            return False
    name = str(op.get("name_contains") or "").strip()
    if name and not _name_hits(info, name, cid):
        return False
    try:
        cost = printed_cost(info)
    except Exception:
        cost = 0
    if op.get("cost_lte") is not None and cost > int(op["cost_lte"]):
        return False
    if op.get("cost_gte") is not None and cost < int(op["cost_gte"]):
        return False
    if op.get("cost_eq") is not None and cost != int(op["cost_eq"]):
        return False
    if op.get("cost_lte_opp_don_field") and opp_don is not None and cost > int(opp_don):
        return False
    return True


def _count_hand_matches(state: MatchState, seat: int, op: dict[str, Any], catalog: CatalogFn) -> int:
    player = state.player(seat)
    foe = state.player(state.other(seat))
    n = 0
    for cid in player.hand:
        if _hand_matches_op(catalog(cid), op, cid, opp_don=foe.don_total):
            n += 1
    return n


def _followup_ops(pending: PendingChoice) -> list[dict[str, Any]]:
    ops = list(pending.remaining_ops or [])
    if pending.then_op and isinstance(pending.then_op, dict):
        rest = ops[1:] if ops and ops[0].get("op") == pending.then_op.get("op") else ops
        return [pending.then_op, *rest]
    if ops:
        first = ops[0]
        if first.get("as_cost") or first.get("op") in {"trash", "rest_character", "flip_life", "return_don"}:
            return ops[1:]
        return ops
    return []


def _followup_worth(state: MatchState, seat: int, ops: list[dict[str, Any]], catalog: CatalogFn) -> float:
    """Rough value of remaining effect ops (after an optional cost)."""
    if not ops:
        return 0.0
    player = state.player(seat)
    foe = state.player(state.other(seat))
    score = 0.0
    for op in ops:
        kind = str(op.get("op") or "")
        if kind in {"draw", "search_deck", "gain_don", "active_don", "look_deck"}:
            score += 12 + 3 * max(1, int(op.get("count") or op.get("max_add") or 1))
        elif kind in {"ko", "trash"} and "opponent" in str(op.get("target_kind") or ""):
            score += 18 if foe.characters else 0
        elif kind == "buff":
            amt = int(op.get("amount") or 0)
            if amt < 0:
                n = 0
                for ch in foe.characters:
                    info = catalog(ch.card_id)
                    try:
                        cost = printed_cost(info)
                    except Exception:
                        cost = 0
                    if op.get("cost_eq") is not None and cost != int(op["cost_eq"]):
                        continue
                    if op.get("cost_lte") is not None and cost > int(op["cost_lte"]):
                        continue
                    n += 1
                score += 12 * n
            else:
                score += 8
        elif kind == "play_from_hand":
            n = _count_hand_matches(state, seat, op, catalog)
            score += 22 * n
        elif kind == "play_from_trash":
            score += 10 if player.trash else 0
        elif kind in {"grant_keyword", "set_character_active", "rest_character", "rest_opponent_character"}:
            score += 10
        elif kind == "look_opp_deck":
            score += 4
        elif kind in {"choose_one", "choose_effect"}:
            score += 8
        else:
            score += 3
    return score


def _note_skipped_activate(state: MatchState, pending: PendingChoice | None) -> None:
    if pending is None:
        return
    first = (pending.remaining_ops or [None])[0]
    then = pending.then_op
    as_cost = bool(isinstance(first, dict) and first.get("as_cost")) or bool(
        isinstance(then, dict) and then.get("as_cost")
    )
    purpose = pending_choice_purpose(pending)
    self_cost = purpose in {"trash", "rest"} and str(pending.target_kind or "").startswith("own")
    if not as_cost and not self_cost:
        return
    src = str(pending.mark_once_source_iid or pending.source_iid or "")
    if not src:
        return
    controller = pending.controller_seat if pending.controller_seat is not None else pending.seat
    player = state.player(int(controller))
    iids = getattr(player, "skipped_activate_iids", None)
    if iids is None:
        player.skipped_activate_iids = []
        iids = player.skipped_activate_iids
    if src not in iids:
        iids.append(src)


def _activate_spec_value(
    state: MatchState,
    seat: int,
    source_iid: str,
    catalog: CatalogFn,
) -> float:
    from battle.effect_library import resolve_activate_spec

    player = state.player(seat)
    skipped = set(getattr(player, "skipped_activate_iids", None) or [])
    if source_iid in skipped:
        return -400.0
    if source_iid == "leader":
        cid = player.leader_card_id
        once_used = player.leader_once_used
    else:
        inst = _find_inst(player, source_iid)
        if inst is None:
            return -50.0
        cid = inst.card_id
        once_used = bool(inst.once_used)
    spec = resolve_activate_spec(cid, catalog(cid)) or {}
    if spec.get("once") and once_used:
        return -400.0
    ops = list(spec.get("ops") or [])
    if not ops:
        return -50.0
    costs = [o for o in ops if o.get("as_cost")]
    payoff = [o for o in ops if not o.get("as_cost")]
    worth = _followup_worth(state, seat, payoff or ops, catalog)
    # Self-trash / rest-self with nothing to do afterwards is a trap.
    self_pay = any(
        o.get("op") in {"trash", "ko"} and str(o.get("target_kind") or "") in {"self", "source", "own_character"}
        for o in costs
        or ops[:1]
    )
    if self_pay and worth < 8:
        return -80.0
    if worth <= 0:
        return -20.0
    return 28.0 + min(40.0, worth)


def _score_choice(
    state: MatchState,
    seat: int,
    action: dict[str, Any],
    catalog: CatalogFn,
) -> float:
    pending = state.pending_choice
    if pending is None:
        return 0.0
    if action.get("type") == "skip_choice":
        worth = _followup_worth(state, seat, _followup_ops(pending), catalog)
        purpose = pending_choice_purpose(pending)
        first = (pending.remaining_ops or [None])[0]
        as_cost = bool(isinstance(first, dict) and first.get("as_cost"))
        # Paying a steep self-cost for a weak follow-up is worse than skipping.
        if as_cost and worth < 8:
            return 40.0
        if purpose in {"trash", "ko"} and str(pending.target_kind or "").startswith("own") and worth < 8:
            return 35.0
        if pending.optional and worth < 4:
            return 8.0
        return -6.0

    tid = str(action.get("target_iid") or "")
    purpose = pending_choice_purpose(pending)
    tk = str(pending.target_kind or "")
    player = state.player(seat)
    foe = state.player(state.other(seat))

    if tk == "effect_option" or tid.startswith("opt:"):
        label = str((pending.option_labels or {}).get(tid) or "").lower()
        if any(x in label for x in ("draw", "抽", "don", "咚", "ko", "擊破", "击破")):
            return 24.0
        return 10.0 - (int(tid.split(":")[-1]) if tid.split(":")[-1].isdigit() else 0)

    if tk == "life_position" or tid in {"life:top", "life:bottom"}:
        # Pudding-style flip / reorder: paying the cost is usually correct.
        worth = _followup_worth(state, seat, _followup_ops(pending), catalog)
        return 18.0 if worth >= 4 else 6.0

    if tid in {"deck:top", "deck:bottom"}:
        return 12.0 if tid == "deck:bottom" else 4.0

    if tid.startswith("hand:") or tid.startswith("trash:"):
        cid = tid.split(":")[-1]
        info = catalog(cid)
        cost = _inst_cost(catalog, cid)
        ctype = _card_type(info)
        if purpose == "play":
            return 20.0 + cost * 3 + (6 if ctype == "character" else 0)
        if purpose in {"trash", "bottom"}:
            # Discard the least useful card.
            return 8.0 - cost * 0.6 - (4 if ctype == "character" else 0)
        if purpose == "life":
            return 10.0 + cost
        return cost

    own = _find_inst(player, tid)
    enemy = _find_inst(foe, tid)
    if tid == "leader":
        if purpose in {"buff", "grant_keyword", "attach_don", "set_active"}:
            return 16.0
        if purpose in {"ko", "trash", "rest", "return_hand", "bottom"}:
            return -30.0
        return 4.0

    def _char_value(inst: CardInst, *, enemy_side: bool) -> float:
        cost = _inst_cost(catalog, inst.card_id)
        try:
            pwr = inst_power(state, foe.seat if enemy_side else player.seat, inst.iid, catalog)
        except Exception:
            pwr = _inst_printed_power(catalog, inst.card_id)
        kw = " ".join(inst.keywords or []).lower()
        blocker = 8.0 if "blocker" in kw else 0.0
        return cost * 3.0 + pwr / 1000.0 + blocker

    if enemy is not None:
        val = _char_value(enemy, enemy_side=True)
        if purpose in {"ko", "trash", "return_hand", "bottom", "rest"}:
            return 20.0 + val
        if purpose == "buff":
            # Negative power buffs land here too.
            amt = 0
            then = pending.then_op or ((pending.remaining_ops or [None])[0])
            if isinstance(then, dict):
                amt = int(then.get("amount") or 0)
            return (18.0 + val) if amt < 0 else -10.0
        return val

    if own is not None:
        val = _char_value(own, enemy_side=False)
        worth = _followup_worth(state, seat, _followup_ops(pending), catalog)
        if purpose in {"ko", "trash", "bottom", "return_hand"}:
            # Pay self-cost only when the follow-up is real; otherwise pick the cheapest body.
            if worth >= 12:
                return 14.0 - val
            return 4.0 - val
        if purpose in {"buff", "grant_keyword", "attach_don"}:
            # Prefer the attacker we'll swing with.
            bonus = 6.0 if not own.rested else 0.0
            if own.iid == (state.attack.attacker_iid if state.attack else ""):
                bonus += 10.0
            return 12.0 + val + bonus
        if purpose == "set_active":
            return 16.0 + val if own.rested else -8.0
        if purpose == "rest":
            return 6.0 - val
        if purpose == "replace":
            return 10.0 - val
        return 2.0 - val * 0.2

    if tid.startswith("don:"):
        order = {"don:active": 30.0, "don:rested": 18.0, "don:leader": 8.0}
        return order.get(tid, 4.0)

    return 1.0


def _score_search(state: MatchState, action: dict[str, Any], catalog: CatalogFn) -> float:
    pending = state.pending_search
    if pending is None:
        return 0.0
    kind = action.get("type")
    if kind == "skip_search":
        selected = list(getattr(pending, "selected", None) or [])
        return 12.0 if selected or int(pending.max_add or 0) <= 0 else -4.0
    if kind == "confirm_search":
        return 30.0 if list(getattr(pending, "selected", None) or []) else -8.0
    if kind == "select_search":
        idx = int(action.get("index", -1))
        selected = {int(x) for x in (getattr(pending, "selected", None) or [])}
        if idx in selected:
            return -20.0
        cid = str(action.get("card_id") or "")
        if not cid and 0 <= idx < len(pending.revealed or []):
            cid = pending.revealed[idx]
        info = catalog(cid)
        cost = _inst_cost(catalog, cid)
        ctype = _card_type(info)
        dest = str(getattr(pending, "destination", None) or "hand")
        bonus = 8.0 if ctype == "character" else 3.0 if ctype == "event" else 2.0
        if dest == "play":
            return 20.0 + cost * 4 + bonus
        return 14.0 + cost * 2.5 + bonus
    if kind == "order_search_bottom":
        idx = int(action.get("index", 0) or 0)
        return 10.0 - idx * 0.1
    if kind == "undo_search_order":
        return -15.0
    if kind == "select_choice":
        tid = str(action.get("target_iid") or "")
        return 16.0 if tid == "deck:bottom" else 6.0 if tid == "deck:top" else 0.0
    return 0.0


def _counter_amounts(actions: list[dict[str, Any]]) -> dict[int, int]:
    """Best Counter value per hand index among legal counter actions."""
    pool: dict[int, int] = {}
    for a in actions:
        if a.get("type") != "counter":
            continue
        try:
            idx = int(a.get("hand_index", -1))
        except (TypeError, ValueError):
            continue
        amt = int(a.get("counter") or 0)
        if amt > 0:
            pool[idx] = max(pool.get(idx, 0), amt)
    return pool


def pick_ai_action(state: MatchState, seat: int, catalog: CatalogFn) -> dict[str, Any] | None:
    actions = [a for a in legal_actions(state, seat, catalog) if a.get("type") != "concede"]
    if not actions:
        return None
    if state.pending_choice:
        picks = [a for a in actions if a.get("type") in {"select_choice", "skip_choice"}]
        if picks:
            return max(picks, key=lambda a: _score_choice(state, seat, a, catalog))
        return None
    if state.pending_search:
        search_kinds = {
            "select_search",
            "confirm_search",
            "skip_search",
            "order_search_bottom",
            "undo_search_order",
            "select_choice",
        }
        picks = [a for a in actions if a.get("type") in search_kinds]
        if picks:
            return max(picks, key=lambda a: _score_search(state, a, catalog))
        return None
    if state.pending_effect:
        return {"type": "confirm_effect", "accept": True}

    player = state.player(seat)
    foe = state.player(state.other(seat))
    can_play = any(a.get("type") == "play_card" for a in actions)
    can_attack = any(a.get("type") == "attack" for a in actions)

    def score(action: dict[str, Any]) -> float:
        kind = action.get("type")
        if kind == "concede":
            return -1000.0
        if kind == "mulligan":
            costs = [printed_cost(catalog(cid)) for cid in player.hand]
            avg = sum(costs) / max(1, len(costs))
            low = sum(1 for c in costs if c <= 2)
            chars = sum(1 for cid in player.hand if _card_type(catalog(cid)) == "character")
            keep = (avg <= 3.4 and chars >= 2) or low >= 2
            if action.get("redraw"):
                return 20.0 if not keep else -5.0
            return 20.0 if keep else -5.0
        if kind == "trigger":
            ops = (state.pending_trigger.ops if state.pending_trigger else None) or []
            if action.get("accept"):
                return 40.0 if ops else 5.0
            return 10.0 if not ops else -5.0
        if kind == "activate_main":
            return _activate_spec_value(state, seat, str(action.get("source_iid") or ""), catalog)
        if kind == "play_card":
            ctype = action.get("card_type")
            cost = float(action.get("cost") or 0)
            bonus = 14.0 if ctype == "character" else 5.0 if ctype == "stage" else 4.0
            if ctype == "character":
                try:
                    from battle.effects import has_blocker

                    cid = str(action.get("card_id") or "")
                    if cid and has_blocker(catalog(cid)):
                        bonus += 5.0
                except Exception:
                    pass
            replace = action.get("replace_iid")
            if replace:
                bonus -= 4.0
                try:
                    bonus -= inst_power(state, seat, str(replace), catalog) / 4000.0
                except Exception:
                    pass
            # Late game: dump high cost; early: prefer curve pieces we can actually swing with.
            curve = 2.0 if player.turns_completed <= 1 and cost <= 2 else 0.0
            return 120.0 + cost * 4.0 + bonus + curve
        if kind == "attach_don":
            if can_play:
                return 8.0
            tgt = str(action.get("target_iid") or "leader")
            try:
                pwr = inst_power(state, seat, tgt, catalog)
            except Exception:
                pwr = 0
            try:
                lead = inst_power(state, foe.seat, "leader", catalog)
            except Exception:
                lead = 5000
            gap = lead - pwr
            if 0 < gap <= 1000:
                return 80.0
            for ch in foe.characters:
                if not ch.rested:
                    continue
                try:
                    def_p = inst_power(state, foe.seat, ch.iid, catalog)
                except Exception:
                    continue
                need = def_p - pwr
                if 0 < need <= 1000:
                    return 74.0 + _inst_cost(catalog, ch.card_id) * 0.4
            if tgt == "leader":
                return 58.0 if can_attack else 40.0
            inst = _find_inst(player, tgt)
            if inst is not None and not inst.rested:
                return 64.0
            return 50.0
        if kind == "remove_don":
            return -80.0
        if kind == "attack":
            atk = inst_power(state, seat, str(action["attacker_iid"]), catalog)
            tgt = str(action["target_iid"])
            atk_iid = str(action["attacker_iid"])
            found = _find_inst(player, atk_iid)
            atk_cid = player.leader_card_id if atk_iid == "leader" else (found.card_id if found else "")
            trigger = _has_when_attacking(atk_cid) if atk_cid else False
            if tgt == "leader":
                def_p = inst_power(state, foe.seat, "leader", catalog)
                wins = atk >= def_p
                lethal = wins and foe.life_count <= 1
                low = wins and foe.life_count <= 2
                if lethal:
                    return 95.0 + atk / 400.0
                if wins:
                    return 62.0 + (22.0 if low else 0.0) + atk / 400.0
                return (42.0 if trigger else 6.0) + atk / 800.0
            def_p = inst_power(state, foe.seat, tgt, catalog)
            wins = atk >= def_p
            inst = _find_inst(foe, tgt)
            cost = _inst_cost(catalog, inst.card_id) if inst else 0
            kw = " ".join(inst.keywords or []).lower() if inst else ""
            blocker = 10.0 if inst and "blocker" in kw else 0.0
            if wins:
                return 54.0 + cost * 3.0 + blocker + atk / 500.0
            return -18.0
        if kind == "block":
            blocker = action.get("blocker_iid")
            if not state.attack:
                return 0.0
            atk_p = inst_power(state, state.attack.attacker_seat, state.attack.attacker_iid, catalog)
            targeting_leader = state.attack.target_iid == "leader"
            lead_p = inst_power(state, seat, "leader", catalog)
            takes_life = targeting_leader and atk_p >= lead_p
            attacker_char = state.attack.attacker_iid != "leader"
            life = player.life_count
            if blocker is None:
                if takes_life and life <= 1:
                    return -30.0
                if takes_life and life <= 2:
                    return -8.0
                if takes_life and life <= 3:
                    return 1.0
                if not targeting_leader:
                    tgt_inst = _find_inst(player, str(state.attack.target_iid))
                    if tgt_inst is not None:
                        try:
                            tgt_p = inst_power(state, seat, tgt_inst.iid, catalog)
                        except Exception:
                            tgt_p = 0
                        tgt_cost = _inst_cost(catalog, tgt_inst.card_id)
                        if atk_p >= tgt_p and tgt_cost >= 5:
                            return -2.0
                    return 10.0
                return 9.0
            blk_p = inst_power(state, seat, str(blocker), catalog)
            inst = _find_inst(player, str(blocker))
            body = _inst_cost(catalog, inst.card_id) if inst else 4
            survives = blk_p > atk_p
            ko_attacker = attacker_char and blk_p > atk_p
            if ko_attacker:
                return 46.0 - body * 1.2 + (10.0 if takes_life else 6.0) + (8.0 if life <= 3 else 0.0)
            if takes_life:
                if life <= 1:
                    return 52.0 - body * 2.0
                if life <= 2:
                    return 34.0 - body * 1.4 + (6.0 if survives else -8.0)
                if life <= 3:
                    return 22.0 - body + (8.0 if survives else -8.0)
                if survives:
                    return 14.0 - body * 0.4
                if body <= 2:
                    return 12.0
                return 3.0 - body
            tgt_inst = _find_inst(player, str(state.attack.target_iid))
            if tgt_inst is not None:
                try:
                    tgt_p = inst_power(state, seat, tgt_inst.iid, catalog)
                except Exception:
                    tgt_p = 0
                tgt_cost = _inst_cost(catalog, tgt_inst.card_id)
                if atk_p >= tgt_p:
                    if survives:
                        return 24.0 + tgt_cost * 2.0 - body
                    if tgt_cost >= 6 and body <= 3:
                        return 14.0
                    return -6.0
            return -12.0
        if kind == "counter":
            if not state.attack:
                return -10.0
            atk_p = inst_power(state, state.attack.attacker_seat, state.attack.attacker_iid, catalog)
            tgt = state.attack.blocker_iid or state.attack.target_iid
            buff_tgt = str(action.get("buff_target") or tgt)
            defended = "leader" if tgt == "leader" else tgt
            base_def = inst_power(state, seat, defended, catalog)
            bonus = int(action.get("counter") or 0) if buff_tgt == defended else 0
            if bonus <= 0:
                return 4.0 if defended == "leader" else 1.0
            gap = atk_p - base_def
            if gap <= 0:
                return -18.0
            if bonus >= gap:
                return 42.0 if defended == "leader" else 34.0
            pool = _counter_amounts(actions)
            try:
                this_idx = int(action.get("hand_index", -1))
            except (TypeError, ValueError):
                this_idx = -1
            rest = sum(v for i, v in pool.items() if i != this_idx)
            remaining = gap - bonus
            if rest >= remaining:
                return 30.0 if defended == "leader" else 22.0
            if defended == "leader" and player.life_count <= 2 and bonus >= 2000:
                return 18.0
            return -12.0
        if kind == "pass_counter":
            return 5.0
        if kind == "end_turn":
            if can_play and player.don_active >= 1:
                return -30.0
            if can_attack:
                return -12.0
            return 2.0
        return 0.0

    ranked = sorted(actions, key=score, reverse=True)
    return ranked[0]


def pick_ai_action_smart(
    state: MatchState,
    seat: int,
    catalog: CatalogFn,
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
    catalog: CatalogFn,
    ask_llm: Callable[[str], str] | None = None,
) -> bool:
    """
    Apply at most one AI action (plus a single fallback if the pick fails).
    Returns True if the match advanced due to AI.
    """
    if state.status != "playing":
        return False
    from battle.engine import _finish_cleared_interactive, _pending_interactive, _resume_end_phase_if_needed

    # Recover orphaned trigger phase left after nested Trigger choices (engine bug legacy).
    if (
        state.phase == "trigger"
        and state.pending_trigger is None
        and not state.pending_choice
        and not state.pending_search
        and not state.pending_effect
        and getattr(state, "pending_replace", None) is None
    ):
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
    # End phase paused with no prompt — resume 6-6 pipeline.
    if state.phase == "end" and not _pending_interactive(state):
        before = (state.phase, state.turn_seat, state.turn_number, state.end_phase_step)
        _resume_end_phase_if_needed(state, catalog)
        after = (state.phase, state.turn_seat, state.turn_number, state.end_phase_step)
        return after != before
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
    if action.get("type") == "skip_choice":
        _note_skipped_activate(state, state.pending_choice)
    if action.get("type") == "activate_main":
        # Treat Activate: Main as once-per-source this turn so optional costs cannot loop.
        src = str(action.get("source_iid") or "")
        if src:
            actor = state.player(seat)
            iids = getattr(actor, "skipped_activate_iids", None)
            if iids is None:
                actor.skipped_activate_iids = []
                iids = actor.skipped_activate_iids
            if src not in iids:
                iids.append(src)
    result = apply_action(state, seat, action, catalog, ask_llm=ask_llm)
    if result.get("ok"):
        return True
    if state.phase == "block":
        fb = apply_action(state, seat, {"type": "block", "blocker_iid": None}, catalog, ask_llm=ask_llm)
        return bool(fb.get("ok"))
    if state.phase == "counter":
        fb = apply_action(state, seat, {"type": "pass_counter"}, catalog, ask_llm=ask_llm)
        return bool(fb.get("ok"))
    if state.phase == "mulligan":
        fb = apply_action(state, seat, {"type": "mulligan", "redraw": False}, catalog, ask_llm=ask_llm)
        return bool(fb.get("ok"))
    if state.phase == "trigger":
        fb = apply_action(state, seat, {"type": "trigger", "accept": True}, catalog, ask_llm=ask_llm)
        return bool(fb.get("ok"))
    if state.pending_search:
        if state.pending_search.phase == "choose_dest":
            fb = apply_action(
                state, seat, {"type": "select_choice", "target_iid": "deck:bottom"}, catalog, ask_llm=ask_llm
            )
            return bool(fb.get("ok"))
        if state.pending_search.phase == "order" and state.pending_search.revealed:
            fb = apply_action(
                state,
                seat,
                {"type": "order_search_bottom", "index": 0},
                catalog,
                ask_llm=ask_llm,
            )
            return bool(fb.get("ok"))
        fb = apply_action(state, seat, {"type": "skip_search"}, catalog, ask_llm=ask_llm)
        return bool(fb.get("ok"))
    if state.pending_choice:
        opts = list(state.pending_choice.options or [])
        for tid in opts:
            retry = apply_action(
                state, seat, {"type": "select_choice", "target_iid": tid}, catalog, ask_llm=ask_llm
            )
            if retry.get("ok"):
                return True
        if state.pending_choice and state.pending_choice.optional:
            _note_skipped_activate(state, state.pending_choice)
            fb = apply_action(state, seat, {"type": "skip_choice"}, catalog, ask_llm=ask_llm)
            return bool(fb.get("ok"))
        return False
    if state.phase == "main":
        fb = apply_action(state, seat, {"type": "end_turn"}, catalog, ask_llm=ask_llm)
        return bool(fb.get("ok"))
    return False


def run_ai_until_human(
    state: MatchState,
    catalog: CatalogFn,
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
