from __future__ import annotations

import json
import re
from typing import Any, Callable

from battle.choice_purpose import pending_choice_purpose
from battle.engine import apply_action, inst_power, legal_actions, printed_cost, printed_counter
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


def _live_char_cost(state: MatchState, owner_seat: int, inst: CardInst, catalog: CatalogFn) -> int:
    try:
        from battle.engine import effective_character_cost

        return int(effective_character_cost(state, owner_seat, inst, catalog))
    except Exception:
        return _inst_cost(catalog, inst.card_id)


def _field_has_char_cost_gte(state: MatchState, seat: int, need: int, catalog: CatalogFn) -> bool:
    player = state.player(seat)
    foe = state.player(state.other(seat))
    for owner, chars in ((seat, player.characters), (foe.seat, foe.characters)):
        for ch in chars:
            if _live_char_cost(state, owner, ch, catalog) >= need:
                return True
    return False


def _opp_char_matches_op(
    state: MatchState,
    seat: int,
    ch: CardInst,
    op: dict[str, Any],
    catalog: CatalogFn,
) -> bool:
    if op.get("rested_only") and not ch.rested:
        return False
    cost = _live_char_cost(state, state.other(seat), ch, catalog)
    printed = _inst_cost(catalog, ch.card_id)
    if op.get("cost_lte") is not None and cost > int(op["cost_lte"]):
        return False
    if op.get("base_cost_lte") is not None and printed > int(op["base_cost_lte"]):
        return False
    if op.get("cost_gte") is not None and cost < int(op["cost_gte"]):
        return False
    if op.get("cost_eq") is not None and cost != int(op["cost_eq"]):
        return False
    try:
        pwr = inst_power(state, state.other(seat), ch.iid, catalog)
    except Exception:
        pwr = _inst_printed_power(catalog, ch.card_id)
    base_p = _inst_printed_power(catalog, ch.card_id)
    if op.get("power_lte") is not None and pwr > int(op["power_lte"]):
        return False
    if op.get("power_gte") is not None and pwr < int(op["power_gte"]):
        return False
    if op.get("base_power_lte") is not None and base_p > int(op["base_power_lte"]):
        return False
    if op.get("base_power_gte") is not None and base_p < int(op["base_power_gte"]):
        return False
    return True


def _opp_removal_hits(
    state: MatchState,
    seat: int,
    op: dict[str, Any],
    catalog: CatalogFn,
) -> list[CardInst]:
    foe = state.player(state.other(seat))
    hits = [ch for ch in foe.characters if _opp_char_matches_op(state, seat, ch, op, catalog)]
    cap = op.get("total_cost_lte")
    if cap is None:
        return hits
    cap_n = int(cap)
    ordered = sorted(hits, key=lambda c: _live_char_cost(state, foe.seat, c, catalog))
    picked: list[CardInst] = []
    acc = 0
    for ch in ordered:
        c = _live_char_cost(state, foe.seat, ch, catalog)
        if acc + c <= cap_n:
            picked.append(ch)
            acc += c
    return picked


def _has_when_attacking(card_id: str) -> bool:
    try:
        from battle.effect_library import get_abilities

        return bool(get_abilities(card_id, "when_attacking"))
    except Exception:
        return False


def _attacker_has_banish(
    state: MatchState,
    seat: int,
    attacker_iid: str,
    inst: CardInst | None,
    catalog: CatalogFn,
) -> bool:
    try:
        from battle.effects import has_banish

        player = state.player(seat)
        if attacker_iid == "leader":
            return bool(has_banish(catalog(player.leader_card_id), None))
        if inst is None:
            return False
        return bool(has_banish(catalog(inst.card_id), inst))
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


def _leader_printed_life(player: PlayerState, catalog: CatalogFn) -> int:
    try:
        v = (catalog(player.leader_card_id) or {}).get("life")
        return int(v) if v is not None else 5
    except (TypeError, ValueError):
        return 5


def _wants_life_card(player: PlayerState, catalog: CatalogFn) -> bool:
    """5-life Leaders at 4–5 life usually take the hit for the extra card."""
    if int(player.life_count) <= 3:
        return False
    return _leader_printed_life(player, catalog) >= 5


def _leader_has_don_return_trigger(state: MatchState, seat: int) -> bool:
    try:
        from battle.effect_library import get_abilities

        return bool(get_abilities(state.player(seat).leader_card_id, "on_don_returned"))
    except Exception:
        return False


def _leader_don_return_ready(state: MatchState, seat: int) -> bool:
    """True if Yonko Luffy (etc.) can still fire this turn from returning ≥2 DON."""
    if state.turn_seat != seat:
        return False
    if not _leader_has_don_return_trigger(state, seat):
        return False
    player = state.player(seat)
    if player.leader_once_used:
        return False
    already = int(getattr(player, "_last_return_don_count", 0) or 0)
    if already >= 2:
        return False
    return int(player.don_total or 0) >= 2


def _ops_return_don_count(ops: list[dict[str, Any]] | None) -> int:
    n = 0
    for op in ops or []:
        if str(op.get("op") or "") == "return_don":
            n = max(n, int(op.get("count") or 1))
    return n


def _don_return_leader_play_bonus(state: MatchState, seat: int, ops: list[dict[str, Any]] | None) -> float:
    """Luffy's +1 active / +1 rested is the reason to play a DON−2 even if KO fizzles."""
    if _ops_return_don_count(ops) < 2 or not _leader_don_return_ready(state, seat):
        return 0.0
    return 36.0


def _return_don_leader_bonus(state: MatchState, seat: int) -> float:
    if not _leader_has_don_return_trigger(state, seat):
        return 0.0
    already = int(getattr(state.player(seat), "_last_return_don_count", 0) or 0)
    return 22.0 if already < 2 else 0.0


def _leader_wants_base_cost(state: MatchState, seat: int) -> int | None:
    """Leader aura that needs an own Character of printed cost ≥ N (e.g. Sabo 8)."""
    try:
        from battle.effect_library import get_abilities

        best: int | None = None
        for ability in get_abilities(state.player(seat).leader_card_id):
            n = ability.get("require_chars_base_cost_gte")
            if n is None:
                continue
            v = int(n)
            best = v if best is None else min(best, v)
        return best
    except Exception:
        return None


def _leader_aura_don_needed(state: MatchState, seat: int, catalog: CatalogFn) -> int:
    """How many more DON the Leader still needs for a printed DON×N aura."""
    player = state.player(seat)
    attached = int(player.leader_don or 0)
    best = 0
    try:
        from battle.effect_library import get_abilities

        for ability in get_abilities(player.leader_card_id):
            n = ability.get("require_don_attached_gte")
            if n is None:
                continue
            n = int(n)
            want = ability.get("require_chars_base_cost_gte")
            if want is not None:
                want_n = int(want)
                if not any(_inst_cost(catalog, ch.card_id) >= want_n for ch in player.characters):
                    continue
            if ability.get("on_own_trait_ko") and not player.characters:
                continue
            ops = list(ability.get("ops") or [])
            kinds = {str(o.get("op") or "") for o in ops}
            field_only = bool(ops) and kinds <= {"grant_cost", "buff", "buff_all_own"} and not any(
                o.get("include_leader") or str(o.get("target_kind") or "") == "leader" for o in ops
            )
            if field_only and not player.characters:
                continue
            best = max(best, n)
    except Exception:
        return 0
    return max(0, best - attached)


def _leader_aura_pumps_combat(state: MatchState, seat: int, catalog: CatalogFn) -> bool:
    """True if the printed DON×N aura actually changes power (Sabo), not just cost (Luffy)."""
    if _leader_aura_don_needed(state, seat, catalog) <= 0:
        return False
    player = state.player(seat)
    try:
        from battle.effect_library import get_abilities

        for ability in get_abilities(player.leader_card_id):
            if ability.get("require_don_attached_gte") is None:
                continue
            for op in ability.get("ops") or []:
                kind = str(op.get("op") or "")
                if kind in {"buff", "buff_all_own"} and int(op.get("amount") or 0) > 0:
                    return True
    except Exception:
        return False
    return False


def _followup_worth(state: MatchState, seat: int, ops: list[dict[str, Any]], catalog: CatalogFn) -> float:
    """Rough value of remaining effect ops (after an optional cost)."""
    if not ops:
        return 0.0
    player = state.player(seat)
    foe = state.player(state.other(seat))
    score = 0.0
    for op in ops:
        if op.get("require_field_char_cost_gte") is not None:
            if not _field_has_char_cost_gte(state, seat, int(op["require_field_char_cost_gte"]), catalog):
                continue
        if op.get("require_opp_hand_gte") is not None and len(foe.hand) < int(op["require_opp_hand_gte"]):
            continue
        kind = str(op.get("op") or "")
        if kind in {"draw", "search_deck", "gain_don", "active_don", "look_deck"}:
            n = max(1, int(op.get("count") or op.get("max_add") or 1))
            score += 12 + 3 * n
            if kind in {"gain_don", "active_don"} and n >= 3:
                score += 10
        elif kind == "attach_don":
            score += 6 + 3 * max(1, int(op.get("count") or 1))
        elif kind == "cannot_play_from_hand":
            continue
        elif kind == "buff_all_own":
            score += 10
        elif kind == "skip_untap":
            score += 12 if any(c.rested for c in foe.characters) else 0
        elif kind == "return_don":
            n = max(1, int(op.get("count") or 1))
            if n >= 2 and _leader_has_don_return_trigger(state, seat):
                score += 16 + _return_don_leader_bonus(state, seat)
            else:
                score += 4
        elif kind in {"ko", "trash"} and "opponent" in str(op.get("target_kind") or ""):
            hits = _opp_removal_hits(state, seat, op, catalog)
            score += 14 + 4 * min(3, len(hits)) if hits else 0
        elif kind in {"return_hand", "return_to_bottom", "return_to_deck", "bottom"}:
            tk = str(op.get("target_kind") or "")
            if "opponent" in tk:
                hits = _opp_removal_hits(state, seat, op, catalog)
                score += 14 + 3 * min(3, len(hits)) if hits else 0
            elif op.get("all") and "own" in tk:
                score -= 18
            else:
                score += 3
        elif kind == "extra_turn":
            score += 48
        elif kind == "set_base_power":
            score += 12
        elif kind == "buff":
            amt = int(op.get("amount") or 0)
            if amt < 0:
                n = len(_opp_removal_hits(state, seat, op, catalog))
                score += 12 * n
            else:
                score += 8
        elif kind == "play_from_hand":
            n = _count_hand_matches(state, seat, op, catalog)
            score += 22 * n
        elif kind == "play_from_trash":
            score += 10 if player.trash else 0
        elif kind in {"grant_keyword", "set_character_active", "rest_character"}:
            score += 10
        elif kind == "rest_opponent_character":
            score += 10 if foe.characters else 0
        elif kind == "look_opp_deck":
            score += 4
        elif kind in {"choose_one", "choose_effect"}:
            score += 8
        else:
            score += 3
    return score


def _counter_event_power(state: MatchState, seat: int, card_id: str, catalog: CatalogFn) -> int:
    """Battle power from a Counter Event's buff ops (e.g. OP09-078 +4000)."""
    if not card_id:
        return 0
    try:
        from battle.effect_library import get_abilities
        from battle.engine import _info_has_trait
    except Exception:
        return 0
    lead = catalog(state.player(seat).leader_card_id) or {}
    total = 0
    try:
        for timing in ("counter_event", "counter"):
            for ability in get_abilities(card_id, timing):
                req = str(ability.get("require_leader_trait") or "")
                if req and not _info_has_trait(lead, req):
                    continue
                for op in ability.get("ops") or []:
                    if str(op.get("op") or "") not in {"buff", "buff_self"}:
                        continue
                    if op.get("as_cost"):
                        continue
                    amt = int(op.get("amount") or 0)
                    if amt <= 0:
                        continue
                    oreq = str(op.get("require_leader_trait") or "")
                    if oreq and not _info_has_trait(lead, oreq):
                        continue
                    total += amt
    except Exception:
        return 0
    return total


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
    worth = _followup_worth(state, seat, payoff or ops, catalog) + _don_return_leader_play_bonus(
        state, seat, ops
    )
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
    # Once-per-turn ramp / extra turn must beat playing a curve piece (play ≈ 120–160).
    wants_body = _activate_wants_body_first(state, seat, spec, catalog)
    if spec.get("once") and worth >= 16:
        # Don't jump a once-lock (Mihawk) or Enel attach-4 ahead of a better body.
        if not _activate_locks_character_plays(state, seat, source_iid, catalog) and not wants_body:
            return 158.0 + min(28.0, worth)
    if wants_body:
        return 45.0
    # Search / ramp / Rush-grant must beat dumping a 0–2 cost body (play ≈ 120+).
    return 90.0 + min(45.0, worth)


def _activate_wants_body_first(
    state: MatchState,
    seat: int,
    spec: dict[str, Any],
    catalog: CatalogFn,
) -> bool:
    """True if this Activate attaches DON to a Character and a stronger playable body is in hand.

    Enel (OP15-058) attach-4 is wasted on a 4k if the 8-drop is still in hand.
    """
    attach_n = 0
    for op in spec.get("ops") or []:
        if str(op.get("op") or "") != "attach_don":
            continue
        tk = str(op.get("target_kind") or "").lower()
        if "character" in tk and "opponent" not in tk:
            attach_n = max(attach_n, int(op.get("count") or 1))
    if attach_n < 2:
        return False
    player = state.player(seat)
    field_best = 0
    for ch in player.characters:
        field_best = max(field_best, _inst_printed_power(catalog, ch.card_id))
    don = int(player.don_active or 0)
    hand_best = 0
    for cid in player.hand or []:
        info = catalog(cid) or {}
        if _card_type(info) != "character":
            continue
        if _inst_cost(catalog, cid) > don:
            continue
        hand_best = max(hand_best, _inst_printed_power(catalog, cid))
    return hand_best > field_best


def _activate_locks_character_plays(
    state: MatchState,
    seat: int,
    source_iid: str,
    catalog: CatalogFn,
) -> bool:
    """True if this Activate: Main will forbid playing Characters afterwards."""
    from battle.effect_library import resolve_activate_spec

    player = state.player(seat)
    if source_iid == "leader":
        cid = player.leader_card_id
    else:
        inst = _find_inst(player, source_iid)
        if inst is None:
            return False
        cid = inst.card_id
    spec = resolve_activate_spec(cid, catalog(cid)) or {}
    for op in spec.get("ops") or []:
        if str(op.get("op") or "") != "cannot_play_from_hand":
            continue
        ctype = str(op.get("card_type") or "character").strip().lower()
        if ctype not in {"", "character", "any"}:
            continue
        if op.get("require_field_char_cost_gte") is not None:
            if not _field_has_char_cost_gte(state, seat, int(op["require_field_char_cost_gte"]), catalog):
                continue
        return True
    return False


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
        already = int(getattr(state.player(seat), "_last_return_don_count", 0) or 0)
        if isinstance(first, dict) and first.get("op") == "return_don":
            worth += _return_don_leader_bonus(state, seat)
        elif purpose == "return_don" or str(pending.target_kind or "") == "return_don":
            worth += _return_don_leader_bonus(state, seat)
        # Yonko Luffy: must actually return 2 DON, even if the card's own follow-up fizzled.
        if (
            _leader_don_return_ready(state, seat)
            and already < 2
            and (purpose == "return_don" or str(pending.target_kind or "") == "return_don" or (isinstance(first, dict) and first.get("op") == "return_don"))
        ):
            return -25.0
        if as_cost and isinstance(first, dict) and first.get("op") == "flip_life":
            if state.player(seat).life_count <= 2:
                return 45.0
        if as_cost and purpose == "trash":
            opts = [str(x) for x in (pending.options or [])]
            if opts and state.player(seat).life_count <= 2:
                try:
                    if all(printed_counter(catalog(tid.split(":")[-1])) >= 2000 for tid in opts):
                        return 36.0
                except Exception:
                    pass
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
        # Pudding-style flip: skip when the last Life cards would be exposed.
        if player.life_count <= 2:
            return 2.0
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
            # Discard the least useful card; keep 2k Counters when possible.
            ctr = printed_counter(info)
            return 8.0 - cost * 0.6 - (4 if ctype == "character" else 0) - (
                12.0 if ctr >= 2000 else 4.0 if ctr >= 1000 else 0.0
            )
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
        blocker = 0.0
        owner = foe.seat if enemy_side else player.seat
        if _is_own_blocker(state, owner, inst, catalog):
            # Active enemy Blockers still prevent swings; rested ones already committed.
            blocker = 12.0 if enemy_side and not inst.rested else 8.0
        # Live power beats printed cost (8c 0p is worse to KO than a 5c 8k).
        return cost * 1.6 + pwr / 450.0 + blocker

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
            # Prefer the attacker we'll swing with; Rush wants summoning-sick bodies.
            bonus = 6.0 if not own.rested else 0.0
            if own.iid == (state.attack.attacker_iid if state.attack else ""):
                bonus += 10.0
            then = pending.then_op or ((pending.remaining_ops or [None])[0])
            kw = str(then.get("keyword") or "").lower() if isinstance(then, dict) else ""
            if purpose == "grant_keyword" and "rush" in kw:
                try:
                    from battle.effects import has_rush

                    if has_rush(catalog(own.card_id), own):
                        return -20.0
                except Exception:
                    pass
                if own.summoning_sick:
                    bonus += 18.0
            if purpose == "attach_don":
                n_don = 1
                ops_src = list(pending.remaining_ops or [])
                if isinstance(pending.then_op, dict):
                    ops_src.append(pending.then_op)
                for op in ops_src:
                    if isinstance(op, dict) and op.get("op") == "attach_don":
                        n_don = max(1, int(op.get("count") or 1))
                        break
                try:
                    pwr = inst_power(state, seat, own.iid, catalog)
                    lead = inst_power(state, foe.seat, "leader", catalog)
                    extra = n_don * 1000
                    can_swing = (not own.rested) and (not own.summoning_sick)
                    if n_don >= 3:
                        # Enel-style: park a stack on the biggest body, even if sick.
                        bonus += pwr / 250.0 + n_don * 4.0
                        if not own.rested:
                            bonus += 6.0
                    elif can_swing and pwr < lead <= pwr + extra:
                        bonus += 20.0
                    elif can_swing and pwr + extra >= lead:
                        bonus += 8.0
                except Exception:
                    pass
            return 12.0 + val + bonus
        if purpose == "set_active":
            return 16.0 + val if own.rested else -8.0
        if purpose == "rest":
            return 6.0 - val
        if purpose == "replace":
            return 10.0 - val
        return 2.0 - val * 0.2

    if tid.startswith("don:"):
        if purpose == "rest":
            # Rest a rested DON as cost; keep Active DON for plays / combat attach.
            if tid == "don:rested":
                return 28.0
            if tid == "don:leader":
                return 12.0
            if tid == "don:active":
                return -8.0 if player.don_active <= 3 else 6.0
        if purpose == "return_don" or tk == "return_don":
            # Keep Active DON for further plays; Luffy refunds after returning rested.
            if tid == "don:rested":
                return 32.0
            if tid.startswith("don:char:"):
                return 22.0
            if tid == "don:leader":
                return 8.0 if _leader_aura_don_needed(state, seat, catalog) > 0 else 18.0
            if tid == "don:active":
                return 6.0
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
        bonus = 8.0 if ctype == "character" else 5.0 if ctype == "event" else 2.0
        ctr = printed_counter(info)
        bonus += 10.0 if ctr >= 2000 else 4.0 if ctr >= 1000 else 0.0
        if dest == "play":
            return 20.0 + cost * 4 + bonus
        player = state.player(pending.seat)
        don = max(int(player.don_given or 0), int(player.don_active or 0), 1)
        curve = 8.0 if cost <= don + 2 else 0.0
        if cost > don + 1:
            bonus -= 18.0
        if cost > don + 3:
            bonus -= 10.0
        bonus += min(16.0, _on_play_worth(state, pending.seat, cid, catalog))
        want = _leader_wants_base_cost(state, pending.seat)
        if want is not None and cost >= want:
            bonus += 12.0
        return 14.0 + cost * 2.0 + bonus + curve
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


def _defender_need(atk: int, defense: int) -> int:
    """Minimum extra defense to not lose. Attacker wins ties (atk >= def)."""
    return max(0, int(atk) - int(defense) + 1)


def _active_attacker_iids(player: PlayerState) -> list[str]:
    out: list[str] = []
    if not player.leader_rested:
        out.append("leader")
    for ch in player.characters:
        if not ch.rested and not ch.summoning_sick:
            out.append(ch.iid)
    return out


def _later_connecting_powers(
    state: MatchState,
    defender_seat: int,
    catalog: CatalogFn,
) -> list[int]:
    """Powers of other ready attackers that can still take Life after this swing."""
    atk = state.attack
    if atk is None:
        return []
    foe = state.player(atk.attacker_seat)
    try:
        lead = inst_power(state, defender_seat, "leader", catalog)
    except Exception:
        lead = 5000
    out: list[int] = []
    for iid in _active_attacker_iids(foe):
        if iid == atk.attacker_iid:
            continue
        try:
            pwr = inst_power(state, foe.seat, iid, catalog)
        except Exception:
            continue
        if pwr >= lead:
            out.append(int(pwr))
    return out


def _ready_life_hits(state: MatchState, seat: int, catalog: CatalogFn) -> int:
    """How many ready attackers currently take Life if they swing at Leader."""
    foe = state.player(state.other(seat))
    try:
        lead = inst_power(state, foe.seat, "leader", catalog)
    except Exception:
        lead = 5000
    n = 0
    for iid in _active_attacker_iids(state.player(seat)):
        try:
            pwr = inst_power(state, seat, iid, catalog)
        except Exception:
            continue
        if pwr >= lead:
            n += 1
    return n


def _expected_opp_counter(foe: PlayerState, *, conservative: bool = False) -> int:
    """Rough Counter the opponent can still play from hand (1000-step).

    Attach math uses the default (beat a 1k). Attack 'reliable' uses conservative
    when the hand is large enough that a 2k is likely.
    """
    n = len(foe.hand or [])
    if n <= 0:
        return 0
    if conservative and n >= 4:
        return 2000
    if n >= 6:
        return 2000
    return 1000


def _attach_closes_any(state: MatchState, seat: int, catalog: CatalogFn, extra: int = 1000) -> bool:
    """True if +extra power newly connects (raw or after expected Counter)."""
    player = state.player(seat)
    foe = state.player(state.other(seat))
    if int(player.don_active or 0) < 1:
        return False
    expect = _expected_opp_counter(foe)
    foes: list[str] = ["leader"]
    for ch in foe.characters:
        if ch.rested:
            foes.append(ch.iid)
    for atk_iid in _active_attacker_iids(player):
        try:
            pwr = inst_power(state, seat, atk_iid, catalog)
        except Exception:
            continue
        for tgt in foes:
            try:
                def_p = inst_power(state, foe.seat, tgt, catalog)
            except Exception:
                continue
            # 4k vs 5k (Sabo at 4+ life) must still pump even if they might have a 1k.
            if pwr < def_p <= pwr + extra:
                return True
            if pwr < def_p + expect <= pwr + extra:
                return True
    return False


def _feeds_blocker(
    state: MatchState,
    seat: int,
    atk_iid: str,
    atk_pwr: int,
    catalog: CatalogFn,
) -> bool:
    """True if swinging this Character at Leader likely dies to an active Blocker."""
    if atk_iid == "leader":
        return False
    try:
        from battle.effects import has_blocker, has_blockerless
        from battle.engine import _blocker_denied
    except Exception:
        return False
    found = _find_inst(state.player(seat), atk_iid)
    if found is None:
        return False
    info = catalog(found.card_id)
    if has_blockerless(info, found):
        return False
    foe = state.player(state.other(seat))
    for ch in foe.characters:
        if ch.rested:
            continue
        binfo = catalog(ch.card_id)
        if not has_blocker(binfo, ch, state=state, owner_seat=foe.seat, catalog=catalog):
            continue
        try:
            from battle.engine import _character_denied_rest

            if _character_denied_rest(foe, ch.iid):
                continue
            if _blocker_denied(state, seat, ch, catalog):
                continue
        except Exception:
            pass
        try:
            bp = inst_power(state, foe.seat, ch.iid, catalog)
        except Exception:
            continue
        if bp > atk_pwr:
            return True
    return False


def _is_own_blocker(
    state: MatchState,
    seat: int,
    inst: CardInst,
    catalog: CatalogFn,
) -> bool:
    try:
        from battle.effects import has_blocker

        return has_blocker(catalog(inst.card_id), inst, state=state, owner_seat=seat, catalog=catalog)
    except Exception:
        return "blocker" in " ".join(inst.keywords or []).lower()


def _ready_blocker_iids(state: MatchState, seat: int, catalog: CatalogFn) -> list[str]:
    from battle.engine import _character_denied_rest

    player = state.player(seat)
    return [
        ch.iid
        for ch in player.characters
        if (not ch.rested)
        and _is_own_blocker(state, seat, ch, catalog)
        and not _character_denied_rest(player, ch.iid)
    ]


def _ko_threat_bonus(
    state: MatchState,
    seat: int,
    inst: CardInst,
    def_p: int,
    catalog: CatalogFn,
) -> float:
    """Extra value for removing a body that will take our Life next turn."""
    try:
        our_lead = inst_power(state, seat, "leader", catalog)
    except Exception:
        our_lead = 5000
    cost = _inst_cost(catalog, inst.card_id)
    blk = 8.0 if _is_own_blocker(state, state.other(seat), inst, catalog) else 0.0
    # Strictly over our Leader: they connect even through a 0 Counter.
    if def_p > our_lead:
        return 22.0 + cost * 1.5 + blk
    if blk:
        return 10.0 + cost
    return 0.0


def _on_play_worth(state: MatchState, seat: int, card_id: str, catalog: CatalogFn) -> float:
    try:
        from battle.effect_library import get_abilities

        ops: list[dict[str, Any]] = []
        for ability in get_abilities(card_id, "on_play"):
            gte = ability.get("require_field_char_cost_gte")
            if gte is not None and not _field_has_char_cost_gte(state, seat, int(gte), catalog):
                continue
            ops.extend(ability.get("ops") or [])
        if not ops:
            for ability in get_abilities(card_id, "activate_main"):
                ops.extend(ability.get("ops") or [])
        payoff = [o for o in ops if not o.get("as_cost")]
        return _followup_worth(state, seat, payoff or ops, catalog) + _don_return_leader_play_bonus(
            state, seat, ops
        )
    except Exception:
        return 0.0


def _when_attacking_worth(state: MatchState, seat: int, card_id: str, catalog: CatalogFn) -> float:
    try:
        from battle.effect_library import get_abilities

        ops: list[dict[str, Any]] = []
        for ability in get_abilities(card_id, "when_attacking"):
            ops.extend(ability.get("ops") or [])
        payoff = [o for o in ops if not o.get("as_cost")]
        return _followup_worth(state, seat, payoff or ops, catalog) + _don_return_leader_play_bonus(
            state, seat, ops
        )
    except Exception:
        return 0.0


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
    aura_need = _leader_aura_don_needed(state, seat, catalog)
    can_close = _ready_life_hits(state, seat, catalog) >= max(1, int(foe.life_count or 0))
    best_unlocked_activate = max(
        (
            _activate_spec_value(state, seat, str(a.get("source_iid") or ""), catalog)
            for a in actions
            if a.get("type") == "activate_main"
            and not _activate_locks_character_plays(
                state, seat, str(a.get("source_iid") or ""), catalog
            )
        ),
        default=-999.0,
    )

    def score(action: dict[str, Any]) -> float:
        kind = action.get("type")
        if kind == "concede":
            return -1000.0
        if kind == "mulligan":
            costs = [printed_cost(catalog(cid)) for cid in player.hand]
            avg = sum(costs) / max(1, len(costs))
            low = sum(1 for c in costs if c <= 2)
            chars = sum(1 for cid in player.hand if _card_type(catalog(cid)) == "character")
            twok = sum(1 for cid in player.hand if printed_counter(catalog(cid)) >= 2000)
            keep = (avg <= 3.4 and chars >= 2) or low >= 2 or (twok >= 1 and low >= 1) or (
                twok >= 1 and avg <= 4.2
            ) or (_leader_printed_life(player, catalog) <= 4 and twok >= 1)
            want = _leader_wants_base_cost(state, seat)
            if (
                want is not None
                and any(c >= want for c in costs)
                and (low >= 1 or twok >= 1)
            ):
                keep = True
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
            cid = str(action.get("card_id") or "")
            bonus = 14.0 if ctype == "character" else 8.0 if ctype == "stage" else 4.0
            info = catalog(cid) if cid else {}
            if ctype == "character":
                rush = False
                blocker = False
                try:
                    from battle.effects import has_blocker, has_rush

                    blocker = bool(cid and has_blocker(info))
                    rush = bool(cid and has_rush(info))
                    if blocker:
                        bonus += 5.0
                    if rush:
                        bonus += 16.0
                    # Keep cheap Counter cards in hand unless this is the only curve piece.
                    ctr = printed_counter(info)
                    if (
                        cost <= 2
                        and ctr >= 1000
                        and not rush
                        and not blocker
                        and (player.characters or player.turns_completed >= 1)
                    ):
                        # 2k is a Counter, not a body. Base play ≈ 120, so this must
                        # lose to attacking and to ending the turn.
                        bonus -= 180.0 if ctr >= 2000 else 55.0
                except Exception:
                    pass
                bonus += min(28.0, _on_play_worth(state, seat, cid, catalog))
                if cid and _has_when_attacking(cid):
                    bonus += 6.0
                want = _leader_wants_base_cost(state, seat)
                if want is not None and cost >= want:
                    bonus += 12.0
                leftover = int(player.don_active) - int(cost)
                closes_now = _attach_closes_any(state, seat, catalog)
                # Don't dump summoning-sick bodies if that DON would KO / connect.
                if leftover < 2 and int(cost) > 0 and closes_now and not rush:
                    field_best = max(
                        (_inst_printed_power(catalog, ch.card_id) for ch in player.characters),
                        default=0,
                    )
                    new_p = _inst_printed_power(catalog, cid) if cid else 0
                    from battle.effect_library import resolve_activate_spec as _ras

                    lspec = _ras(player.leader_card_id, catalog(player.leader_card_id)) or {}
                    keep_curve = (want is not None and cost >= want) or (
                        leftover == 0
                        and cost >= 4
                        and new_p > field_best
                        and _activate_wants_body_first(state, seat, lspec, catalog)
                    )
                    if not keep_curve:
                        if cost <= 2:
                            bonus -= 110.0
                        else:
                            bonus -= 78.0 if leftover == 1 else 80.0
                # Ramp / search Activate: Main before spending the last DON on a 1-drop.
                if cost <= 2 and best_unlocked_activate >= 24.0:
                    bonus -= 55.0
                # Keep the last DON(s) that turn on a Leader DON×N aura.
                if cost <= 2 and aura_need > 0 and leftover < aura_need:
                    bonus -= 70.0
            elif ctype == "event":
                worth = _on_play_worth(state, seat, cid, catalog)
                # Don't spend DON on an Event that currently does nothing.
                if worth < 8:
                    return -40.0 + cost * 0.2
                bonus += min(40.0, worth)
            replace = action.get("replace_iid")
            if replace:
                rinst = _find_inst(player, str(replace))
                if rinst is not None:
                    try:
                        rp = inst_power(state, seat, rinst.iid, catalog)
                    except Exception:
                        rp = _inst_printed_power(catalog, rinst.card_id)
                    old_c = _inst_cost(catalog, rinst.card_id)
                    new_p = _inst_printed_power(catalog, cid) if cid else 0
                    bonus -= 12.0 + old_c * 6.0 + rp / 1000.0
                    # 5-wide: don't bin a bigger attacker for a weaker summoning-sick body.
                    if cost + 1 < old_c and new_p <= rp:
                        bonus -= 90.0
                    elif new_p + 1000 < rp and cost <= old_c:
                        bonus -= 70.0
                else:
                    bonus -= 12.0
            # Late game: dump high cost; early: prefer curve pieces we can actually swing with.
            curve = 2.0 if player.turns_completed <= 1 and cost <= 2 else 0.0
            return 120.0 + cost * 4.0 + bonus + curve
        if kind == "attach_don":
            tgt = str(action.get("target_iid") or "leader")
            try:
                pwr = inst_power(state, seat, tgt, catalog)
            except Exception:
                pwr = 0
            try:
                lead = inst_power(state, foe.seat, "leader", catalog)
            except Exception:
                lead = 5000
            expect = _expected_opp_counter(foe)
            need_lead = (lead + expect) - pwr
            need_raw = lead - pwr
            closes = 0 < need_lead <= 1000 or 0 < need_raw <= 1000
            ko_bonus = 0.0
            for ch in foe.characters:
                if not ch.rested:
                    continue
                try:
                    def_p = inst_power(state, foe.seat, ch.iid, catalog)
                except Exception:
                    continue
                need = (def_p + expect) - pwr
                need_ko_raw = def_p - pwr
                if 0 < need <= 1000 or 0 < need_ko_raw <= 1000:
                    closes = True
                    ko_bonus = max(ko_bonus, 92.0 + _inst_cost(catalog, ch.card_id) * 2.0)
            inst = _find_inst(player, tgt)
            aura_attach = tgt == "leader" and aura_need > 0
            if inst is not None and inst.rested and not closes and not aura_attach:
                return 8.0 if can_play else 18.0
            if inst is not None and inst.summoning_sick and not closes and not aura_attach:
                return 6.0 if can_play else 14.0
            if can_play and not closes and not aura_attach:
                return 8.0 if can_attack else 1.0
            if 0 < need_raw <= 1000:
                return 88.0
            if 0 < need_lead <= 1000:
                return 86.0
            # 6k still loses to a likely 2k; a second DON makes 7k.
            likely_2k = len(foe.hand or []) >= 4
            need_vs_2k = (lead + 2000) - pwr
            if likely_2k and int(player.don_active or 0) >= 1 and 0 < need_vs_2k <= 1000:
                return 87.0
            ko_2k = 0.0
            if likely_2k:
                for ch in foe.characters:
                    if not ch.rested:
                        continue
                    try:
                        def_p = inst_power(state, foe.seat, ch.iid, catalog)
                    except Exception:
                        continue
                    need2 = (def_p + 2000) - pwr
                    if 0 < need2 <= 1000:
                        ko_2k = max(ko_2k, 90.0 + _inst_cost(catalog, ch.card_id) * 2.0)
            if ko_2k:
                return ko_2k
            if ko_bonus:
                return ko_bonus
            if aura_attach:
                # Power auras (Sabo) attach before the swing. Cost-only (Luffy) must not
                # beat pumping a body that actually takes Life this turn.
                if _leader_aura_pumps_combat(state, seat, catalog):
                    return 90.0 if can_attack else 78.0
                return 81.0 if can_attack else 76.0
            # Leftover DON stay in the cost area for next turn unless this attach actually connects.
            return 12.0 if can_attack else 1.0
        if kind == "remove_don":
            return -80.0
        if kind == "attack":
            atk = inst_power(state, seat, str(action["attacker_iid"]), catalog)
            tgt = str(action["target_iid"])
            atk_iid = str(action["attacker_iid"])
            found = _find_inst(player, atk_iid)
            atk_cid = player.leader_card_id if atk_iid == "leader" else (found.card_id if found else "")
            trigger = _has_when_attacking(atk_cid) if atk_cid else False
            wa_bonus = 0.0
            if trigger and atk_cid:
                wa_bonus = 8.0 + min(12.0, max(0.0, _when_attacking_worth(state, seat, atk_cid, catalog)))
            double_atk = False
            banish = _attacker_has_banish(state, seat, atk_iid, found, catalog)
            if atk_cid:
                try:
                    from battle.effects import has_double_attack

                    double_atk = bool(has_double_attack(catalog(atk_cid), found))
                except Exception:
                    double_atk = False
            last_blocker = (
                found is not None
                and _is_own_blocker(state, seat, found, catalog)
                and _ready_blocker_iids(state, seat, catalog) == [atk_iid]
            )
            if tgt == "leader":
                def_p = inst_power(state, foe.seat, "leader", catalog)
                wins = atk >= def_p
                expect = _expected_opp_counter(foe, conservative=True)
                reliable = atk >= def_p + expect
                lethal = wins and foe.life_count <= 1
                low = wins and foe.life_count <= 2
                if (
                    atk_iid != "leader"
                    and not lethal
                    and _feeds_blocker(state, seat, atk_iid, atk, catalog)
                ):
                    return -32.0
                if (
                    last_blocker
                    and not lethal
                    and foe.life_count > 2
                ):
                    return -18.0
                if lethal:
                    return 95.0 + atk / 400.0
                if reliable:
                    race = 62.0 + (22.0 if low else 0.0) + atk / 400.0
                    race += wa_bonus
                    if double_atk:
                        race += 12.0
                    if banish:
                        race += 20.0
                    if player.life_count > foe.life_count and foe.characters:
                        race -= 10.0
                    if player.life_count < foe.life_count:
                        race += 10.0
                    if can_close:
                        race += 16.0
                    return race
                if wins:
                    # 5k vs 5k takes life only if they have no 1k Counter — attach first if we can.
                    face = 48.0 + atk / 400.0 + (8.0 if double_atk else 0.0)
                    if banish:
                        face += 20.0
                    return face
                # Resting a body that cannot take life is only worth [When Attacking] value.
                return 42.0 + atk / 800.0 + wa_bonus if trigger else -25.0
            def_p = inst_power(state, foe.seat, tgt, catalog)
            wins = atk >= def_p
            inst = _find_inst(foe, tgt)
            cost = _inst_cost(catalog, inst.card_id) if inst else 0
            blocker = 10.0 if inst and _is_own_blocker(state, foe.seat, inst, catalog) else 0.0
            expect = _expected_opp_counter(foe, conservative=True)
            reliable = atk >= def_p + expect
            threat = _ko_threat_bonus(state, seat, inst, def_p, catalog) if inst else 0.0
            if last_blocker and foe.life_count > 2 and not (reliable and (cost >= 6 or blocker or threat >= 22)):
                return -18.0
            if reliable:
                val = 54.0 + cost * 3.0 + blocker + threat + atk / 500.0
                val += wa_bonus * 0.75
                if double_atk:
                    val += 10.0
                if banish and threat < 22:
                    val -= 16.0
                if player.life_count < foe.life_count and threat < 22:
                    val -= 8.0
                if can_close and threat < 22:
                    val -= 22.0
                return val
            if wins:
                return 40.0 + cost * 2.0 + blocker + threat * 0.5
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
            pass_life = life
            if _leader_printed_life(player, catalog) <= 4:
                pass_life = min(life, 3)
            later = _later_connecting_powers(state, seat, catalog)
            later_max = max(later) if later else 0
            hold_for_bigger = bool(takes_life and later_max > atk_p and life > 1)
            if blocker is None:
                if hold_for_bigger:
                    return 24.0
                if takes_life and pass_life <= 1:
                    return -30.0
                if takes_life and pass_life <= 2:
                    return -8.0
                if takes_life and pass_life <= 3:
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
            if hold_for_bigger and len(_ready_blocker_iids(state, seat, catalog)) <= 1:
                return 2.0 - body
            if ko_attacker:
                return 46.0 - body * 1.2 + (10.0 if takes_life else 6.0) + (8.0 if life <= 3 else 0.0)
            if takes_life:
                if pass_life <= 1:
                    return 52.0 - body * 2.0
                if pass_life <= 2:
                    return 34.0 - body * 1.4 + (6.0 if survives else -8.0)
                if pass_life <= 3:
                    return 22.0 - body + (8.0 if survives else -8.0)
                if survives:
                    return 14.0 - body * 0.4
                # High life: take the Life card instead of chumping.
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
            later = _later_connecting_powers(state, seat, catalog)
            later_max = max(later) if later else 0
            hold_counter = bool(
                defended == "leader" and later_max > atk_p and player.life_count > 1
            )
            base_def = inst_power(state, seat, defended, catalog)
            printed = int(action.get("counter") or 0) if buff_tgt == defended else 0
            cid = str(action.get("card_id") or "")
            effect_p = 0 if printed > 0 else _counter_event_power(state, seat, cid, catalog)
            bonus = printed + effect_p
            if bonus <= 0:
                extra = 0.0
                if cid:
                    try:
                        from battle.effect_library import get_abilities

                        for timing in ("counter_event", "counter"):
                            for ability in get_abilities(cid, timing):
                                extra += _followup_worth(state, seat, ability.get("ops") or [], catalog)
                    except Exception:
                        extra = 0.0
                if extra >= 12:
                    return 16.0 if defended == "leader" else 8.0
                return 4.0 if defended == "leader" else 1.0
            need = _defender_need(atk_p, base_def)
            if need <= 0:
                return -18.0
            if bonus >= need:
                # Prefer the smallest Counter that actually saves (ties still take life).
                if hold_counter:
                    return 3.0 - bonus / 400.0
                if defended == "leader":
                    if _wants_life_card(player, catalog):
                        return 4.0 - bonus / 400.0
                    return 42.0 - bonus / 400.0
                inst = _find_inst(player, defended)
                body = _inst_cost(catalog, inst.card_id) if inst else 4
                want = _leader_wants_base_cost(state, seat)
                if want is not None and inst is not None and body >= want:
                    return 38.0 - bonus / 400.0
                blocker = bool(inst and _is_own_blocker(state, seat, inst, catalog))
                if body <= 2 and not blocker:
                    return 8.0 - bonus / 400.0
                return 34.0 - bonus / 400.0
            pool = _counter_amounts(actions)
            try:
                this_idx = int(action.get("hand_index", -1))
            except (TypeError, ValueError):
                this_idx = -1
            rest = sum(v for i, v in pool.items() if i != this_idx)
            remaining = need - bonus
            if rest >= remaining:
                if hold_counter or (defended == "leader" and _wants_life_card(player, catalog)):
                    return 3.0 - bonus / 400.0
                return (30.0 if defended == "leader" else 22.0) - bonus / 400.0
            if hold_counter:
                return 3.0 - bonus / 400.0
            if defended == "leader" and player.life_count <= 2 and bonus >= 2000:
                return 18.0
            return -12.0
        if kind == "pass_counter":
            return 5.0
        if kind == "end_turn":
            # Real plays/activates/connect-attaches score ~80–180. Do not force
            # dumping 2k Counters or blank Events just because DON remains.
            if can_attack:
                return -12.0
            return 3.0
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
