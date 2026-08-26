"""Pay Life (or hand) to keep a Character from leaving / being K.O.'d."""

from __future__ import annotations

import copy
from typing import Any, Callable

from battle.effect_library import get_abilities
from battle.effects import _printed_power
from battle.state import CardInst, MatchState

CatalogFn = Callable[[str], dict[str, Any]]


def _trait_blob(info: dict[str, Any]) -> str:
    return " ".join(
        str(x or "") for x in (info.get("traits") or []) + (info.get("traits_en") or [])
    ).lower()


def _has_trait(info: dict[str, Any], trait: str) -> bool:
    needle = (trait or "").strip().lower()
    if not needle:
        return True
    aliases = {
        "sky island": ("sky island", "空島", "空岛"),
        "空島": ("sky island", "空島", "空岛"),
        "空岛": ("sky island", "空島", "空岛"),
        "straw hat crew": ("straw hat crew", "草帽一行人"),
        "草帽一行人": ("straw hat crew", "草帽一行人"),
        "odyssey": ("odyssey", "ODYSSEY"),
        "supernovas": ("supernovas", "超新星"),
        "超新星": ("supernovas", "超新星"),
        "film": ("film", "FILM"),
    }
    keys = aliases.get(needle, (trait,))
    blob = _trait_blob(info)
    return any(k.lower() in blob for k in keys)


def _printed_cost(info: dict[str, Any]) -> int:
    try:
        return max(0, int(str(info.get("cost") or "0").split()[0]))
    except (TypeError, ValueError):
        return 0


def _victim_base_power(victim: CardInst, info: dict[str, Any]) -> int:
    if victim.base_power_override is not None:
        return int(victim.base_power_override)
    return _printed_power(info)


def _victim_base_cost(victim: CardInst, info: dict[str, Any]) -> int:
    return _printed_cost(info) + int(getattr(victim, "cost_mod", 0) or 0)


def _name_parts(raw: str) -> list[str]:
    text = (raw or "").strip().lower()
    if not text:
        return []
    return [p.strip() for p in text.replace("|", "/").split("/") if p.strip()]


def _info_name_blob(info: dict[str, Any], card_id: str = "") -> str:
    parts = [
        str(info.get("name") or ""),
        str(info.get("name_en") or ""),
        str(info.get("name_cn") or ""),
        card_id,
    ]
    try:
        from battle.effects import _treated_as_names

        parts.extend(_treated_as_names(info))
    except Exception:
        pass
    return " ".join(p for p in parts if p).lower()


def _name_matches(info: dict[str, Any], card_id: str, parts: list[str]) -> bool:
    if not parts:
        return True
    blob = _info_name_blob(info, card_id)
    return any(p in blob for p in parts)


def _rest_one_own_card(
    owner,
    target_iid: str,
    *,
    catalog: CatalogFn | None = None,
    parts: list[str] | None = None,
    trait: str = "",
) -> bool:
    """Rest one of your cards by iid token: leader | don | character/stage iid."""
    tid = str(target_iid or "").strip()
    if tid == "leader" or tid.startswith("leader"):
        if getattr(owner, "leader_rested", False):
            return False
        if parts and catalog is not None:
            linfo = catalog(owner.leader_card_id) or {}
            if not _name_matches(linfo, owner.leader_card_id, parts):
                return False
        owner.leader_rested = True
        return True
    if tid == "don":
        if int(getattr(owner, "don_active", 0) or 0) <= 0:
            return False
        owner.don_active -= 1
        owner.don_rested = int(getattr(owner, "don_rested", 0) or 0) + 1
        return True
    inst = next((c for c in owner.characters if c.iid == tid), None)
    if inst is None:
        inst = next((s for s in (getattr(owner, "stages", None) or []) if s.iid == tid), None)
    if inst is None or getattr(inst, "rested", False):
        return False
    if catalog is not None and (parts or trait):
        info = catalog(inst.card_id) or {}
        if parts and not _name_matches(info, inst.card_id, parts):
            return False
        if trait and not _has_trait(info, trait):
            return False
    inst.rested = True
    return True


def _pay_replace_cost(
    owner,
    op: dict[str, Any],
    src_inst: CardInst | None = None,
    *,
    catalog: CatalogFn | None = None,
    foe=None,
    target_iid: str | None = None,
) -> bool:
    cost = str(op.get("cost") or "trash_life")
    pos = str(op.get("life_position") or "top")
    if cost == "trash_self":
        if src_inst is None:
            return False
        # Trash the shield Character to save the victim.
        chars = owner.characters
        for i, c in enumerate(chars):
            if c.iid == src_inst.iid:
                chars.pop(i)
                owner.trash.append(src_inst.card_id)
                return True
        return False
    if cost == "ko_self":
        if src_inst is None:
            return False
        chars = owner.characters
        for i, c in enumerate(chars):
            if c.iid == src_inst.iid:
                if src_inst.don_attached:
                    owner.don_rested = int(getattr(owner, "don_rested", 0) or 0) + int(src_inst.don_attached or 0)
                    src_inst.don_attached = 0
                chars.pop(i)
                owner.trash.append(src_inst.card_id)
                return True
        return False
    if cost == "rest_self":
        if src_inst is None or src_inst.rested:
            return False
        src_inst.rested = True
        return True
    if cost == "return_don":
        n = max(1, min(5, int(op.get("don_count") or op.get("count") or 1)))
        returned = 0
        # Prefer rested DON on field, then active.
        for _ in range(n):
            if getattr(owner, "don_rested", 0) > 0:
                owner.don_rested -= 1
                returned += 1
            elif getattr(owner, "don_active", 0) > 0:
                owner.don_active -= 1
                returned += 1
            else:
                break
        return returned >= n
    if cost == "rest_don":
        n = max(1, min(5, int(op.get("rest_count") or op.get("don_count") or op.get("count") or 1)))
        rested = 0
        for _ in range(n):
            if getattr(owner, "don_active", 0) > 0:
                owner.don_active -= 1
                owner.don_rested = int(getattr(owner, "don_rested", 0) or 0) + 1
                rested += 1
            else:
                break
        return rested >= n
    if cost == "trash_to_bottom":
        n = max(1, min(10, int(op.get("trash_count") or op.get("count") or 3)))
        if len(owner.trash) < n:
            return False
        moved = [owner.trash.pop() for _ in range(n)]
        owner.deck.extend(moved)
        return True
    if cost == "rest_own":
        # Rest N of your cards (Leader / Character / Stage / DON!!) — paper 「自己的卡片」.
        n = max(1, min(5, int(op.get("rest_count") or op.get("count") or 1)))
        parts = _name_parts(str(op.get("rest_name_contains") or ""))
        trait = str(op.get("rest_trait_contains") or "").strip()
        if target_iid:
            return _rest_one_own_card(owner, target_iid, catalog=catalog, parts=parts, trait=trait)
        rested = 0
        if parts or trait:
            # Named / trait-gated: may rest Leader or Characters matching filter.
            if catalog is not None and parts and not getattr(owner, "leader_rested", False):
                linfo = catalog(owner.leader_card_id) or {}
                if _name_matches(linfo, owner.leader_card_id, parts):
                    owner.leader_rested = True
                    rested += 1
            for c in owner.characters:
                if rested >= n:
                    break
                if c.rested:
                    continue
                info = (catalog(c.card_id) if catalog else {}) or {}
                if parts and not _name_matches(info, c.card_id, parts):
                    continue
                if trait and not _has_trait(info, trait):
                    continue
                c.rested = True
                rested += 1
            return rested >= n
        # Unfiltered 「自己的卡片」: Leader → Characters → Stages → DON!!.
        if not getattr(owner, "leader_rested", False) and rested < n:
            owner.leader_rested = True
            rested += 1
        for c in owner.characters:
            if rested >= n:
                break
            if not c.rested:
                c.rested = True
                rested += 1
        for s in list(getattr(owner, "stages", None) or []):
            if rested >= n:
                break
            if not getattr(s, "rested", False):
                s.rested = True
                rested += 1
        while rested < n and getattr(owner, "don_active", 0) > 0:
            owner.don_active -= 1
            owner.don_rested = int(getattr(owner, "don_rested", 0) or 0) + 1
            rested += 1
        return rested >= n
    if cost == "to_life":
        # Handled specially in try_replace_leave (moves victim to Life).
        return True
    if cost == "rest_other_character":
        if src_inst is None and str(op.get("target") or "") == "self":
            # Rest another Character while protecting self (src may be victim).
            pass
        n = max(1, min(5, int(op.get("rest_count") or op.get("count") or 1)))
        trait = str(op.get("rest_trait_contains") or "").strip()
        trait_opts = [t.strip() for t in trait.split("|") if t.strip()] if trait else []
        rest_owner_side = str(op.get("rest_owner") or "self").strip().lower()
        pool = foe.characters if rest_owner_side == "opponent" and foe is not None else owner.characters
        if target_iid:
            pick = next((c for c in pool if c.iid == target_iid), None)
            if pick is None or pick.rested:
                return False
            if src_inst is not None and pick.iid == src_inst.iid:
                return False
            if trait_opts:
                info = (catalog(pick.card_id) if catalog else {}) or {}
                if not any(_has_trait(info, t) for t in trait_opts):
                    return False
            pick.rested = True
            return True
        rested = 0
        for c in pool:
            if rested >= n:
                break
            if src_inst is not None and c.iid == src_inst.iid:
                continue
            if c.rested:
                continue
            if trait_opts:
                info = (catalog(c.card_id) if catalog else {}) or {}
                if not any(_has_trait(info, t) for t in trait_opts):
                    continue
            c.rested = True
            rested += 1
        return rested >= n
    if cost == "trash_hand":
        trait = str(op.get("hand_trait_contains") or "").strip()
        hand_ctype = str(op.get("hand_card_type") or "").strip().lower()
        hand_pow_gte = op.get("hand_power_gte")
        hand_pow_lte = op.get("hand_power_lte")
        need_filter = bool(trait or hand_ctype or hand_pow_gte is not None or hand_pow_lte is not None)
        need_n = max(1, min(10, int(op.get("count") or op.get("trash_count") or 1)))
        if len(owner.hand) < need_n:
            return False
        if str(target_iid or "").startswith("hand:"):
            parts_t = str(target_iid).split(":")
            try:
                idx = int(parts_t[1])
            except Exception:
                idx = -1
            if not (0 <= idx < len(owner.hand)):
                return False
            cid = owner.hand[idx]
            info = (catalog(cid) if catalog else {}) or {}
            if need_filter and catalog is not None:
                from battle.effects import card_type_of, _printed_power as _pp

                if trait and not _has_trait(info, trait):
                    return False
                if hand_ctype:
                    ctype = card_type_of(info)
                    if hand_ctype == "event_or_stage":
                        if ctype not in {"event", "stage"}:
                            return False
                    elif ctype != hand_ctype:
                        return False
                if hand_pow_gte is not None or hand_pow_lte is not None:
                    pow_v = _pp(info)
                    if hand_pow_gte is not None and pow_v < int(hand_pow_gte):
                        return False
                    if hand_pow_lte is not None and pow_v > int(hand_pow_lte):
                        return False
            owner.hand.pop(idx)
            owner.trash.append(cid)
            if need_n <= 1:
                return True
            cont = dict(op)
            cont["count"] = need_n - 1
            return _pay_replace_cost(owner, cont, src_inst, catalog=catalog, foe=foe, target_iid=None)
        if not need_filter:
            for _ in range(need_n):
                if not owner.hand:
                    return False
                owner.trash.append(owner.hand.pop(0))
            return True
        if catalog is None:
            return False
        from battle.effects import card_type_of, _printed_power

        trashed = 0
        for _ in range(need_n):
            picked = False
            for i, cid in enumerate(list(owner.hand)):
                info = catalog(cid) or {}
                if trait and not _has_trait(info, trait):
                    continue
                if hand_ctype:
                    ctype = card_type_of(info)
                    if hand_ctype == "event_or_stage":
                        if ctype not in {"event", "stage"}:
                            continue
                    elif ctype != hand_ctype:
                        continue
                if hand_pow_gte is not None or hand_pow_lte is not None:
                    pow_v = _printed_power(info)
                    if hand_pow_gte is not None and pow_v < int(hand_pow_gte):
                        continue
                    if hand_pow_lte is not None and pow_v > int(hand_pow_lte):
                        continue
                owner.hand.pop(i)
                owner.trash.append(cid)
                trashed += 1
                picked = True
                break
            if not picked:
                return False
        return trashed >= need_n
    if cost == "return_self_to_hand":
        if src_inst is None:
            return False
        chars = owner.characters
        for i, c in enumerate(chars):
            if c.iid == src_inst.iid:
                chars.pop(i)
                if c.don_attached:
                    owner.don_rested = int(getattr(owner, "don_rested", 0) or 0) + int(c.don_attached or 0)
                    c.don_attached = 0
                owner.hand.append(src_inst.card_id)
                return True
        return False
    if cost == "return_other_to_bottom":
        excl = str(op.get("exclude_name") or "").strip().lower()
        for i, c in enumerate(list(owner.characters)):
            if src_inst is not None and c.iid == src_inst.iid:
                continue
            info = (catalog(c.card_id) if catalog else {}) or {}
            names = _info_name_blob(info, c.card_id)
            if excl and excl in names:
                continue
            # Prefer non-victim characters; victim is kept by replace.
            owner.characters = [x for x in owner.characters if x.iid != c.iid]
            if c.don_attached:
                owner.don_rested = int(getattr(owner, "don_rested", 0) or 0) + int(c.don_attached or 0)
            owner.deck.append(c.card_id)
            return True
        return False
    if cost == "return_own_to_bottom":
        # Place any 1 of your Characters under deck (may be the victim itself — OP15-052 FAQ).
        excl = str(op.get("exclude_name") or "").strip().lower()
        pool = list(owner.characters)
        if target_iid:
            pool = [c for c in pool if c.iid == target_iid]
        for c in pool:
            info = (catalog(c.card_id) if catalog else {}) or {}
            names = _info_name_blob(info, c.card_id)
            if excl and excl in names:
                continue
            owner.characters = [x for x in owner.characters if x.iid != c.iid]
            if c.don_attached:
                owner.don_rested = int(getattr(owner, "don_rested", 0) or 0) + int(c.don_attached or 0)
                c.don_attached = 0
            owner.deck.append(c.card_id)
            return True
        return False
    if cost == "self_power_minus":
        amt = int(op.get("amount") or -2000)
        apply_to = str(op.get("apply_to") or "").strip().lower()
        # Leader shields (src_inst is None) default to Leader power; paper 「領航卡…-2000」uses apply_to=leader.
        if apply_to == "leader" or (not apply_to and src_inst is None):
            owner.leader_power_mod = int(getattr(owner, "leader_power_mod", 0) or 0) + amt
            return True
        if src_inst is None:
            return False
        src_inst.power_mod = int(getattr(src_inst, "power_mod", 0) or 0) + amt
        return True
    if cost == "flip_life":
        if not owner.life:
            return False
        # Face-up the top Life card (or ensure face list).
        if not owner.life_face or len(owner.life_face) != len(owner.life):
            owner.life_face = [False] * len(owner.life)
        face = str(op.get("face") or "up")
        idx = 0 if pos != "bottom" else len(owner.life) - 1
        owner.life_face[idx] = face != "down"
        return True
    if not owner.life:
        return False
    tid = str(target_iid or "")
    if tid == "life:bottom":
        pos = "bottom"
    elif tid == "life:top":
        pos = "top"
    if pos == "bottom":
        card = owner.life.pop()
        if owner.life_face:
            owner.life_face.pop()
    else:
        # top / top_or_bottom — default top when no interactive choice
        card = owner.life.pop(0)
        if owner.life_face:
            owner.life_face.pop(0)
    if cost == "life_to_hand":
        owner.hand.append(card)
    else:
        owner.trash.append(card)
    return True


def _replace_cost_payable(owner, op: dict[str, Any], src_inst: CardInst | None, catalog: CatalogFn, foe=None) -> bool:
    clone = copy.deepcopy(owner)
    foe_c = copy.deepcopy(foe) if foe is not None else None
    src_c = None
    if src_inst is not None:
        src_c = next((c for c in clone.characters if c.iid == src_inst.iid), None)
    return _pay_replace_cost(clone, op, src_c, catalog=catalog, foe=foe_c)


def _rest_own_choice_options(owner, catalog: CatalogFn, op: dict[str, Any]) -> list[str]:
    parts = _name_parts(str(op.get("rest_name_contains") or ""))
    trait = str(op.get("rest_trait_contains") or "").strip()
    out: list[str] = []
    if not getattr(owner, "leader_rested", False):
        if not parts or _name_matches(catalog(owner.leader_card_id) or {}, owner.leader_card_id, parts):
            out.append("leader")
    for c in owner.characters:
        if c.rested:
            continue
        info = catalog(c.card_id) or {}
        if parts and not _name_matches(info, c.card_id, parts):
            continue
        if trait and not _has_trait(info, trait):
            continue
        out.append(c.iid)
    for s in list(getattr(owner, "stages", None) or []):
        if getattr(s, "rested", False):
            continue
        out.append(s.iid)
    if int(getattr(owner, "don_active", 0) or 0) > 0 and not parts and not trait:
        out.append("don")
    return out


def _rest_other_choice_options(owner, foe, src_inst: CardInst | None, catalog: CatalogFn, op: dict[str, Any]) -> list[str]:
    trait = str(op.get("rest_trait_contains") or "").strip()
    trait_opts = [t.strip() for t in trait.split("|") if t.strip()] if trait else []
    rest_owner_side = str(op.get("rest_owner") or "self").strip().lower()
    pool = foe.characters if rest_owner_side == "opponent" and foe is not None else owner.characters
    out: list[str] = []
    for c in pool:
        if src_inst is not None and c.iid == src_inst.iid:
            continue
        if c.rested:
            continue
        if trait_opts:
            info = catalog(c.card_id) or {}
            if not any(_has_trait(info, t) for t in trait_opts):
                continue
        out.append(c.iid)
    return out


def _trash_hand_choice_options(owner, catalog: CatalogFn, op: dict[str, Any]) -> list[str]:
    trait = str(op.get("hand_trait_contains") or "").strip()
    hand_ctype = str(op.get("hand_card_type") or "").strip().lower()
    hand_pow_gte = op.get("hand_power_gte")
    hand_pow_lte = op.get("hand_power_lte")
    need_filter = bool(trait or hand_ctype or hand_pow_gte is not None or hand_pow_lte is not None)
    from battle.effects import card_type_of, _printed_power as _pp

    out: list[str] = []
    for i, cid in enumerate(owner.hand):
        info = catalog(cid) or {}
        if need_filter:
            if trait and not _has_trait(info, trait):
                continue
            if hand_ctype:
                ctype = card_type_of(info)
                if hand_ctype == "event_or_stage":
                    if ctype not in {"event", "stage"}:
                        continue
                elif ctype != hand_ctype:
                    continue
            if hand_pow_gte is not None or hand_pow_lte is not None:
                pow_v = _pp(info)
                if hand_pow_gte is not None and pow_v < int(hand_pow_gte):
                    continue
                if hand_pow_lte is not None and pow_v > int(hand_pow_lte):
                    continue
        out.append(f"hand:{i}:{cid}")
    return out


def stash_replace_resume(
    state: MatchState,
    *,
    leave_kind: str,
    apply_seat: int,
    extra_ops: list[dict[str, Any]] | None = None,
    queue: list[dict[str, Any]] | None = None,
) -> bool:
    pr = getattr(state, "pending_replace", None)
    if pr is None:
        return False
    pr.leave_kind = leave_kind
    pr.apply_seat = apply_seat
    pr.remaining_ops = list(extra_ops or []) + list(queue or [])
    return True


def _begin_optional_replace(
    state: MatchState,
    owner_seat: int,
    victim: CardInst,
    src_inst: CardInst | None,
    source_iid: str,
    card_id: str,
    op: dict[str, Any],
    once: bool,
    catalog: CatalogFn,
    *,
    kind: str = "leave",
) -> bool:
    from battle.state import PendingChoice, PendingEffect, PendingReplace, new_iid

    owner = state.player(owner_seat)
    foe = state.player(state.other(owner_seat))
    cost = str(op.get("cost") or "")
    state.pending_replace = PendingReplace(
        owner_seat=owner_seat,
        victim_iid=victim.iid,
        victim_card_id=victim.card_id,
        source_iid=source_iid,
        card_id=card_id,
        op=dict(op),
        once=once,
        summary=str(op.get("summary") or "replace_leave"),
        kind=kind,
        by_opponent=True,
        by_ko=True,
    )
    options: list[str] | None = None
    target_kind = "own_character"
    if cost == "rest_own":
        options = _rest_own_choice_options(owner, catalog, op)
    elif cost == "rest_other_character":
        options = _rest_other_choice_options(owner, foe, src_inst, catalog, op)
    elif cost == "rest_self" and src_inst is not None and not src_inst.rested:
        options = [src_inst.iid]
    elif cost == "trash_hand":
        options = _trash_hand_choice_options(owner, catalog, op)
        target_kind = "hand_card"
    elif cost == "return_own_to_bottom":
        excl = str(op.get("exclude_name") or "").strip().lower()
        options = []
        for c in owner.characters:
            if excl:
                info = catalog(c.card_id) or {}
                names = _info_name_blob(info, c.card_id)
                if excl in names:
                    continue
            options.append(c.iid)
        target_kind = "own_character"
    elif cost in {"trash_life", "life_to_hand"} and str(op.get("life_position") or "") == "top_or_bottom":
        options = ["life:top", "life:bottom"]
        target_kind = "life_position"
    if options is not None:
        if not options:
            state.pending_replace = None
            return False
        state.pending_choice = PendingChoice(
            seat=owner_seat,
            card_id=card_id,
            source_iid=source_iid,
            target_kind=target_kind,
            options=options,
            remaining_ops=[],
            optional=True,
            summary=str(op.get("summary") or "Choose a replacement cost"),
            purpose="replace_leave",
            controller_seat=owner_seat,
        )
        return True
    state.pending_effect = PendingEffect(
        effect_id=new_iid("rl"),
        seat=owner_seat,
        card_id=card_id,
        source_iid=source_iid,
        summary=str(op.get("summary") or "replace_leave"),
        ops=[{"op": "commit_replace_leave"}],
        uncertain=True,
        once=False,
    )
    return True


def finish_optional_replace(
    state: MatchState,
    catalog: CatalogFn,
    *,
    accept: bool,
    target_iid: str | None = None,
) -> list[dict[str, Any]]:
    """Complete a paused optional replace (accept pays cost; decline resumes the leave/rest)."""
    pr = getattr(state, "pending_replace", None)
    state.pending_replace = None
    if state.pending_effect and (not state.pending_effect.ops or state.pending_effect.ops[0].get("op") == "commit_replace_leave"):
        state.pending_effect = None
    logs: list[dict[str, Any]] = []
    if not pr:
        return logs
    owner = state.player(pr.owner_seat)
    victim = next((c for c in owner.characters if c.iid == pr.victim_iid), None)
    src = None
    if pr.source_iid and pr.source_iid != "leader":
        src = next((c for c in owner.characters if c.iid == pr.source_iid), None)
    paid = False
    if accept and victim is not None:
        foe = state.player(state.other(pr.owner_seat))
        paid = _pay_replace_cost(owner, pr.op, src, catalog=catalog, foe=foe, target_iid=target_iid)
        if paid:
            if pr.once:
                if src is not None:
                    src.once_used = True
                else:
                    owner.leader_once_used = True
            if str(pr.op.get("cost") or "") == "to_life" and victim is not None:
                if victim.don_attached:
                    owner.don_rested = int(getattr(owner, "don_rested", 0) or 0) + int(victim.don_attached or 0)
                    victim.don_attached = 0
                owner.characters = [c for c in owner.characters if c.iid != victim.iid]
                if not owner.life_face or len(owner.life_face) != len(owner.life):
                    owner.life_face = [False] * len(owner.life)
                owner.life.insert(0, victim.card_id)
                owner.life_face.insert(0, False)
            if str(pr.op.get("cost") or "") == "ko_self" and src is not None:
                try:
                    from battle.effects import _victim_on_ko_ops, apply_ops

                    ko_ops = _victim_on_ko_ops(state, pr.owner_seat, src.card_id, src.iid, catalog)
                    if ko_ops:
                        apply_ops(state, pr.owner_seat, ko_ops, catalog)
                except Exception:
                    pass
            if str(pr.op.get("cost") or "") in {"rest_own", "rest_self", "rest_other_character", "rest_don"}:
                try:
                    from battle.engine import _fire_self_rested

                    if target_iid and target_iid not in {"leader", "don"} and not str(target_iid).startswith("leader"):
                        _fire_self_rested(state, pr.owner_seat, str(target_iid), catalog)
                    elif str(pr.op.get("cost") or "") == "rest_self" and src is not None:
                        _fire_self_rested(state, pr.owner_seat, src.iid, catalog)
                except Exception:
                    pass
            if pr.op.get("then_draw"):
                n = max(1, min(3, int(pr.op.get("then_draw") or 1)))
                for _ in range(n):
                    if owner.deck:
                        owner.hand.append(owner.deck.pop(0))
            logs.append(
                {
                    "key": "play.log.effect_applied",
                    "summary": str(pr.op.get("summary") or pr.summary or "replace_leave"),
                    "id": pr.victim_card_id,
                }
            )
    if not paid:
        if pr.kind == "rest":
            if victim is not None and not victim.rested:
                victim.rested = True
                logs.append({"key": "play.log.rests", "id": victim.card_id})
                try:
                    from battle.engine import _fire_self_rested

                    _fire_self_rested(state, pr.owner_seat, victim.iid, catalog)
                except Exception:
                    pass
        elif victim is not None:
            logs.extend(_force_character_leave(state, pr, victim, catalog))
        else:
            logs.append({"key": "play.log.effect_skipped"})
    remaining = list(pr.remaining_ops or [])
    if remaining:
        from battle.effects import apply_ops

        logs.extend(apply_ops(state, int(pr.apply_seat), remaining, catalog))
    if str(pr.leave_kind or "") == "battle_ko":
        try:
            from battle.engine import _clear_battle_deny_blocker
            from battle.rules.checkpoints import rule_process

            _clear_battle_deny_blocker(state)
            state.attack = None
            if state.status == "playing":
                state.phase = "main"
            rule_process(state)
        except Exception:
            pass
    return logs


def _force_character_leave(
    state: MatchState,
    pr: Any,
    victim: CardInst,
    catalog: CatalogFn,
) -> list[dict[str, Any]]:
    logs: list[dict[str, Any]] = []
    owner = state.player(pr.owner_seat)
    leave_kind = str(pr.leave_kind or "ko")
    if leave_kind == "battle_ko":
        from battle.engine import apply_battle_character_ko

        apply_battle_character_ko(state, pr.owner_seat, victim, catalog)
        return logs
    if victim.don_attached:
        owner.don_rested = int(getattr(owner, "don_rested", 0) or 0) + int(victim.don_attached or 0)
        victim.don_attached = 0
    owner.characters = [c for c in owner.characters if c.iid != victim.iid]
    if leave_kind in {"ko", "trash"}:
        owner.trash.append(victim.card_id)
        logs.append({"key": "play.log.ko" if leave_kind == "ko" else "play.log.trashes", "id": victim.card_id})
        if leave_kind == "ko":
            try:
                from battle.effects import _victim_on_ko_ops, apply_ops
                from battle.engine import fire_on_opp_ko, fire_own_trait_leave_or_ko

                fire_own_trait_leave_or_ko(
                    state,
                    pr.owner_seat,
                    victim.card_id,
                    catalog,
                    by_opponent_effect=bool(pr.by_opponent),
                    by_ko=True,
                )
                fire_on_opp_ko(state, pr.owner_seat, catalog)
                ko_ops = _victim_on_ko_ops(state, pr.owner_seat, victim.card_id, victim.iid, catalog)
                if ko_ops:
                    apply_ops(state, pr.owner_seat, ko_ops, catalog)
            except Exception:
                pass
    elif leave_kind == "return_hand":
        owner.hand.append(victim.card_id)
        logs.append({"key": "play.log.return_hand", "id": victim.card_id})
        try:
            from battle.engine import fire_own_trait_leave_or_ko

            fire_own_trait_leave_or_ko(
                state,
                pr.owner_seat,
                victim.card_id,
                catalog,
                by_opponent_effect=bool(pr.by_opponent),
                by_ko=False,
            )
        except Exception:
            pass
    elif leave_kind == "bottom":
        owner.deck.append(victim.card_id)
        logs.append({"key": "play.log.return_bottom_char", "id": victim.card_id, "name": owner.username})
        try:
            from battle.engine import fire_own_trait_leave_or_ko

            fire_own_trait_leave_or_ko(
                state,
                pr.owner_seat,
                victim.card_id,
                catalog,
                by_opponent_effect=bool(pr.by_opponent),
                by_ko=False,
            )
        except Exception:
            pass
    else:
        owner.trash.append(victim.card_id)
        logs.append({"key": "play.log.ko", "id": victim.card_id})
    return logs


def confirm_replace_if_pending(
    state: MatchState,
    catalog: CatalogFn,
    *,
    accept: bool = True,
    target_iid: str | None = None,
) -> bool:
    """Tests / helpers: resolve a paused optional replace using the first legal pick."""
    if getattr(state, "pending_replace", None) is None:
        return False
    if state.pending_choice:
        if accept and target_iid is None:
            target_iid = state.pending_choice.options[0] if state.pending_choice.options else None
        state.pending_choice = None
    finish_optional_replace(state, catalog, accept=accept, target_iid=target_iid)
    return True


def try_replace_leave(
    state: MatchState,
    owner_seat: int,
    victim: CardInst,
    *,
    by_opponent: bool,
    catalog: CatalogFn,
    by_ko: bool = True,
) -> bool:
    """
    If a replace_leave shield applies and its cost can be paid, pay cost and keep victim.
    Returns True when the leave/KO is cancelled.
    """
    owner = state.player(owner_seat)
    foe = state.player(state.other(owner_seat))
    sources: list[tuple[str, str, CardInst | None]] = [
        (c.card_id, c.iid, c) for c in owner.characters
    ]
    sources.append((owner.leader_card_id, "leader", None))

    def _mark_once(src: CardInst | None, once: bool) -> None:
        if not once:
            return
        if src is not None:
            src.once_used = True
        else:
            owner.leader_once_used = True

    def _once_blocked(src: CardInst | None, once: bool) -> bool:
        if not once:
            return False
        if src is not None:
            return bool(src.once_used)
        return bool(getattr(owner, "leader_once_used", False))

    for card_id, source_iid, src_inst in sources:
        for ab in get_abilities(card_id):
            for op in ab.get("ops") or []:
                if op.get("op") != "replace_leave":
                    continue
                once = bool(op.get("once") or ab.get("once"))
                try:
                    from battle.engine import _ability_board_conditions_ok

                    don = int(src_inst.don_attached or 0) if src_inst is not None else int(owner.leader_don or 0)
                    if not _ability_board_conditions_ok(
                        state,
                        owner_seat,
                        ab,
                        catalog,
                        don_attached=don,
                        source_iid=source_iid,
                    ):
                        continue
                except Exception:
                    pass
                trigger = str(op.get("trigger") or "ko").strip().lower()
                any_leave = bool(op.get("any_leave")) or trigger in {"leave", "any", "any_leave"}
                if any_leave:
                    pass
                elif trigger == "ko":
                    if not by_ko:
                        continue
                elif trigger == "opp_remove":
                    if not by_opponent:
                        continue
                else:
                    if not by_ko:
                        continue
                tgt = str(op.get("target") or "self")
                if tgt == "self":
                    if source_iid != victim.iid:
                        continue
                elif tgt == "own_filtered":
                    # Cannot save the shield Character with itself when exclude_self.
                    if op.get("exclude_self") and source_iid == victim.iid:
                        continue
                    if op.get("rested_only") and not bool(getattr(victim, "rested", False)):
                        continue
                    vinfo = catalog(victim.card_id) or {}
                    if op.get("trait_contains"):
                        raw_t = str(op["trait_contains"])
                        opts = [t.strip() for t in raw_t.split("|") if t.strip()] or [raw_t]
                        if not any(_has_trait(vinfo, t) for t in opts):
                            continue
                    if op.get("exclude_name"):
                        excl = str(op["exclude_name"]).strip().lower()
                        names = " ".join(
                            str(x or "")
                            for x in (vinfo.get("name"), vinfo.get("name_en"), victim.card_id)
                        ).lower()
                        if excl and excl in names:
                            continue
                    if op.get("name_contains"):
                        parts = _name_parts(str(op.get("name_contains") or ""))
                        if parts and not _name_matches(vinfo, victim.card_id, parts):
                            continue
                    if op.get("color"):
                        want = str(op["color"]).strip().lower()
                        colors = " ".join(
                            str(x or "")
                            for x in (vinfo.get("colors") or [])
                            + (vinfo.get("color") or [])
                            + ([vinfo.get("color")] if isinstance(vinfo.get("color"), str) else [])
                        ).lower()
                        # Also check Chinese aliases lightly via color field strings.
                        aliases = {
                            "green": ("green", "綠", "绿"),
                            "red": ("red", "紅", "红"),
                            "blue": ("blue", "藍", "蓝"),
                            "yellow": ("yellow", "黃", "黄"),
                            "black": ("black", "黑"),
                            "purple": ("purple", "紫"),
                        }
                        keys = aliases.get(want, (want,))
                        if not any(k.lower() in colors for k in keys):
                            continue
                    if op.get("base_power_gte") is not None:
                        if _victim_base_power(victim, vinfo) < int(op["base_power_gte"]):
                            continue
                    if op.get("base_power_lte") is not None:
                        if _victim_base_power(victim, vinfo) > int(op["base_power_lte"]):
                            continue
                    if op.get("base_power_eq") is not None:
                        if _victim_base_power(victim, vinfo) != int(op["base_power_eq"]):
                            continue
                    if op.get("base_cost_lte") is not None:
                        if _victim_base_cost(victim, vinfo) > int(op["base_cost_lte"]):
                            continue
                    if op.get("base_cost_gte") is not None:
                        if _victim_base_cost(victim, vinfo) < int(op["base_cost_gte"]):
                            continue
                    if op.get("attr_contains"):
                        attrs = " ".join(
                            str(x or "")
                            for x in (vinfo.get("attributes") or []) + (vinfo.get("attributes_en") or [])
                        ).lower()
                        needle = str(op["attr_contains"]).strip().lower()
                        aliases = {
                            "slash": ("slash", "斬", "斩"),
                            "斬": ("slash", "斬", "斩"),
                            "斩": ("slash", "斬", "斩"),
                            "strike": ("strike", "打"),
                            "打": ("strike", "打"),
                            "ranged": ("ranged", "射"),
                            "射": ("ranged", "射"),
                            "special": ("special", "特"),
                            "特": ("special", "特"),
                            "wisdom": ("wisdom", "知"),
                            "知": ("wisdom", "知"),
                        }
                        keys = aliases.get(needle, (needle,))
                        if not any(k in attrs for k in keys):
                            continue
                else:
                    continue
                if _once_blocked(src_inst, once):
                    continue
                cost = str(op.get("cost") or "trash_life")
                if bool(op.get("optional", True)):
                    if cost != "to_life" and not _replace_cost_payable(owner, op, src_inst, catalog, foe):
                        continue
                    if _begin_optional_replace(
                        state,
                        owner_seat,
                        victim,
                        src_inst,
                        source_iid,
                        card_id,
                        op,
                        once,
                        catalog,
                        kind="leave",
                    ):
                        return True
                    continue
                if cost == "to_life":
                    # Move victim onto Life face-down instead of the original leave.
                    if victim.don_attached:
                        owner.don_rested = int(getattr(owner, "don_rested", 0) or 0) + int(victim.don_attached or 0)
                        victim.don_attached = 0
                    owner.characters = [c for c in owner.characters if c.iid != victim.iid]
                    if not owner.life_face or len(owner.life_face) != len(owner.life):
                        owner.life_face = [False] * len(owner.life)
                    owner.life.insert(0, victim.card_id)
                    owner.life_face.insert(0, False)
                    _mark_once(src_inst, once)
                    state.add_log(
                        "play.log.effect_applied",
                        summary=str(op.get("summary") or "replace_leave_to_life"),
                        id=victim.card_id,
                    )
                    return True
                if not _pay_replace_cost(owner, op, src_inst, catalog=catalog, foe=foe):
                    continue
                _mark_once(src_inst, once)
                if str(op.get("cost") or "") == "ko_self" and src_inst is not None:
                    try:
                        from battle.effects import _victim_on_ko_ops, apply_ops

                        ko_ops = _victim_on_ko_ops(
                            state, owner_seat, src_inst.card_id, src_inst.iid, catalog
                        )
                        if ko_ops:
                            apply_ops(state, owner_seat, ko_ops, catalog)
                    except Exception:
                        pass
                # Optional then draw after paying trash_self (ST30-009).
                if op.get("then_draw"):
                    n = max(1, min(3, int(op.get("then_draw") or 1)))
                    for _ in range(n):
                        if owner.deck:
                            owner.hand.append(owner.deck.pop(0))
                state.add_log(
                    "play.log.effect_applied",
                    summary=str(op.get("summary") or "replace_leave"),
                    id=victim.card_id,
                )
                return True
    return False


def try_replace_rest(
    state: MatchState,
    owner_seat: int,
    victim: CardInst,
    *,
    by_opponent_character_effect: bool,
    catalog: CatalogFn,
) -> bool:
    """
    If a replace_rest shield applies (would be rested by opponent Character effect),
    pay its cost and keep the victim active. Returns True when the rest is cancelled.
    """
    if not by_opponent_character_effect or victim is None:
        return False
    if bool(getattr(victim, "rested", False)):
        return False
    owner = state.player(owner_seat)
    foe = state.player(state.other(owner_seat))
    sources: list[tuple[str, str, CardInst | None]] = [
        (c.card_id, c.iid, c) for c in owner.characters
    ]

    def _mark_once(src: CardInst | None, once: bool) -> None:
        if once and src is not None:
            src.once_used = True

    def _once_blocked(src: CardInst | None, once: bool) -> bool:
        if not once or src is None:
            return False
        return bool(src.once_used)

    for card_id, source_iid, src_inst in sources:
        for ab in get_abilities(card_id):
            for op in ab.get("ops") or []:
                if op.get("op") != "replace_rest":
                    continue
                once = bool(op.get("once") or ab.get("once"))
                try:
                    from battle.engine import _ability_board_conditions_ok

                    don = int(src_inst.don_attached or 0) if src_inst is not None else 0
                    if not _ability_board_conditions_ok(
                        state,
                        owner_seat,
                        ab,
                        catalog,
                        don_attached=don,
                        source_iid=source_iid,
                    ):
                        continue
                except Exception:
                    pass
                # Paper: 【對方回合中】— only during opponent's turn when timing says so.
                timing = str(ab.get("timing") or "")
                if timing == "opponent_turn" and state.turn_seat == owner_seat:
                    continue
                if timing == "your_turn" and state.turn_seat != owner_seat:
                    continue
                tgt = str(op.get("target") or "self")
                if tgt == "self":
                    if source_iid != victim.iid:
                        continue
                else:
                    continue
                if _once_blocked(src_inst, once):
                    continue
                pay = dict(op)
                pay.setdefault("cost", "rest_other_character")
                if bool(op.get("optional", True)):
                    if not _replace_cost_payable(owner, pay, src_inst or victim, catalog, foe):
                        continue
                    if _begin_optional_replace(
                        state,
                        owner_seat,
                        victim,
                        src_inst or victim,
                        source_iid,
                        card_id,
                        pay,
                        once,
                        catalog,
                        kind="rest",
                    ):
                        return True
                    continue
                if not _pay_replace_cost(owner, pay, src_inst or victim, catalog=catalog, foe=foe):
                    continue
                _mark_once(src_inst, once)
                state.add_log(
                    "play.log.effect_applied",
                    summary=str(op.get("summary") or "replace_rest"),
                    id=victim.card_id,
                )
                return True
    return False
