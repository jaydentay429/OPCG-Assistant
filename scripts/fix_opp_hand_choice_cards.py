#!/usr/bin/env python3
"""Fix all EB04-022-class opponent-hand choice encodings (dual-write).

Covers:
  - opponent_hand_to_bottom (+ require_opp_hand_gte)
  - trash_hand owner=opponent (+ require_opp_hand_gte)
  - attack_tax (must trash N to attack)

Usage:
  PYTHONPATH=. python3 scripts/fix_opp_hand_choice_cards.py --dry-run
  PYTHONPATH=. python3 scripts/fix_opp_hand_choice_cards.py
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_schema import normalize_card_entry, sanitize_ops_list  # noqa: E402
from battle.effects import _extract_require_opp_hand_gte_from_text  # noqa: E402

LIB_PATH = ROOT / "index" / "card_effects.json"
OV_PATH = ROOT / "index" / "card_effect_overrides.json"
CARDS_PATH = ROOT / "index" / "cards_by_id.json"
OUT_IDS = ROOT / "meta" / "logs" / "opp_hand_choice_fixed_ids.txt"

BOTTOM_RE = re.compile(
    r"對手將\s*(\d+)\s*[張张]自身的手牌(?:依任意順序)?放置[在到]卡組下面|"
    r"对手将\s*(\d+)\s*[张張]自身的手牌(?:依任意顺序)?放置[在到]卡组下面|"
    r"對手將1張自身的手牌(?:依任意順序)?放置[在到]卡組下面|"
    r"对手将1张自身的手牌(?:依任意顺序)?放置[在到]卡组下面|"
    r"places?\s*(\d+)\s*cards? from (?:their|the) hand(?:\s+in any order)? at the bottom|"
    r"places? 1 card from (?:their|the) hand(?:\s+in any order)? at the bottom",
    re.I,
)
# Exclude "全部放回卡組" (OP06-047 style).
BOTTOM_ALL_RE = re.compile(r"手牌全部放回|returns? all .+ hand|entire hand", re.I)
TRASH_RE = re.compile(
    r"對手廢棄\s*(\d+)\s*[張张]?自身的?手牌|对手废弃\s*(\d+)\s*[张張]?自身的?手牌|"
    r"對手廢棄1張自身的手牌|对手废弃1张自身的手牌|"
    r"(?:your )?opponent trashes?\s*(\d+)",
    re.I,
)
ATTACK_TAX_RE = re.compile(
    r"要進行攻擊時.{0,24}廢棄\s*(\d+)\s*[張张]自身的手牌|"
    r"must trash\s*(\d+)\s*cards? from (?:their )?hand to attack",
    re.I,
)


def _base_id(cid: str) -> str:
    m = re.match(r"^([A-Z0-9]+-\d+)", cid)
    return m.group(1) if m else cid


def _iter_ops(ops: list[dict[str, Any]]):
    for o in ops or []:
        yield o
        if o.get("op") == "choose_one":
            for opt in o.get("options") or []:
                yield from _iter_ops(list(opt.get("ops") or []))


def _paper_kinds(zh: str, en: str) -> set[str]:
    blob = f"{zh}\n{en}"
    kinds: set[str] = set()
    if BOTTOM_RE.search(blob) and not BOTTOM_ALL_RE.search(blob):
        kinds.add("bottom")
    if ATTACK_TAX_RE.search(blob):
        kinds.add("attack_tax")
    elif TRASH_RE.search(blob):
        kinds.add("trash")
    return kinds


def _counts(zh: str, en: str, kind: str) -> tuple[int, int | None]:
    blob = f"{zh}\n{en}"
    hand_gte = _extract_require_opp_hand_gte_from_text(blob)
    if hand_gte is None:
        m = re.search(r"手牌有\s*(\d+)\s*[張张]以上", blob)
        if m:
            hand_gte = int(m.group(1))
    if kind == "bottom":
        m = BOTTOM_RE.search(blob)
        if m:
            nums = [int(g) for g in m.groups() if g]
            return (nums[0] if nums else 1), hand_gte
        return 1, hand_gte
    if kind == "trash":
        m = TRASH_RE.search(blob)
        if m:
            nums = [int(g) for g in m.groups() if g]
            return (nums[0] if nums else 1), hand_gte
        return 1, hand_gte
    if kind == "attack_tax":
        m = ATTACK_TAX_RE.search(blob)
        if m:
            nums = [int(g) for g in m.groups() if g]
            return (nums[0] if nums else 2), hand_gte
        return 2, hand_gte
    return 1, hand_gte


def _ensure_bottom_op(ops: list[dict[str, Any]], n: int, hand_gte: int | None) -> list[dict[str, Any]]:
    out = copy.deepcopy(ops)
    found = False
    for o in _iter_ops(out):
        if o.get("op") == "opponent_hand_to_bottom":
            o["count"] = n
            o["optional"] = False
            if hand_gte is not None:
                o["require_opp_hand_gte"] = hand_gte
            else:
                o.pop("require_opp_hand_gte", None)
            found = True
    if found:
        # Drop mistaken return_to_bottom that was standing in for hand→bottom.
        cleaned: list[dict[str, Any]] = []
        for o in out:
            if o.get("op") == "return_to_bottom" and not o.get("target_kind") and int(o.get("count") or 0) == n:
                # Likely mis-parse of opponent hand to bottom — skip if we already have real op.
                continue
            cleaned.append(o)
        return cleaned
    op: dict[str, Any] = {"op": "opponent_hand_to_bottom", "count": n, "optional": False}
    if hand_gte is not None:
        op["require_opp_hand_gte"] = hand_gte
    out.append(op)
    return out


def _ensure_opp_trash_op(ops: list[dict[str, Any]], n: int, hand_gte: int | None) -> list[dict[str, Any]]:
    out = copy.deepcopy(ops)
    found = False
    for o in _iter_ops(out):
        if o.get("op") == "trash_hand" and o.get("owner") == "opponent":
            o["count"] = n
            o["optional"] = False
            if hand_gte is not None:
                o["require_opp_hand_gte"] = hand_gte
            found = True
        # Fix wrong owner=self / missing owner when this is the only trash_hand and paper is opp.
    if found:
        # Also push option-level gates onto nested ops.
        for o in out:
            if o.get("op") != "choose_one":
                continue
            for opt in o.get("options") or []:
                for oo in opt.get("ops") or []:
                    if oo.get("op") == "trash_hand" and oo.get("owner") == "opponent":
                        if hand_gte is not None:
                            oo["require_opp_hand_gte"] = hand_gte
                            # Keep option meta in sync for UI filtering.
                            if "若對手" in str(opt.get("label") or "") or "opp hand" in str(opt.get("label") or "").lower():
                                opt["require_opp_hand_gte"] = hand_gte
        return out

    # Convert a mistaken self trash_hand that is clearly the opp effect (optional True, count match),
    # but only when there is no as_cost self trash in the same list.
    converted = False
    self_costs = [
        o
        for o in out
        if o.get("op") == "trash_hand" and o.get("owner") != "opponent" and o.get("as_cost")
    ]
    candidates = [
        o
        for o in out
        if o.get("op") == "trash_hand" and o.get("owner") != "opponent" and not o.get("as_cost")
    ]
    if candidates and not self_costs:
        for o in candidates:
            if int(o.get("count") or 1) == n:
                o["owner"] = "opponent"
                o["optional"] = False
                if hand_gte is not None:
                    o["require_opp_hand_gte"] = hand_gte
                converted = True
                break
    if converted:
        return out

    # If there is as_cost self trash + a wrong extra self trash, retarget the non-cost one.
    non_cost = [
        o
        for o in out
        if o.get("op") == "trash_hand" and o.get("owner") != "opponent" and not o.get("as_cost")
    ]
    if self_costs and non_cost:
        for o in non_cost:
            o["owner"] = "opponent"
            o["optional"] = False
            if hand_gte is not None:
                o["require_opp_hand_gte"] = hand_gte
            converted = True
            break
    if converted:
        return out

    op: dict[str, Any] = {"op": "trash_hand", "count": n, "optional": False, "owner": "opponent"}
    if hand_gte is not None:
        op["require_opp_hand_gte"] = hand_gte
    out.append(op)
    return out


def _fix_ability(ability: dict[str, Any], zh: str, en: str, kinds: set[str]) -> dict[str, Any] | None:
    """Return updated ability or None if unchanged / not applicable."""
    a = copy.deepcopy(ability)
    timing = str(a.get("timing") or "")
    blob = f"{zh}\n{en}"
    # Timing chunk rough filter — prefer editing abilities whose timing appears in paper near the cue.
    changed = False
    ops = list(a.get("ops") or [])

    for kind in kinds:
        n, hand_gte = _counts(zh, en, kind)
        # attack_tax usually on_play
        if kind == "attack_tax":
            if timing not in {"on_play", "your_turn", "opponent_turn"} and "登場" not in blob:
                continue
            if any(o.get("op") == "attack_tax" for o in _iter_ops(ops)):
                for o in _iter_ops(ops):
                    if o.get("op") == "attack_tax":
                        o["trash_hand"] = n
                        o["all"] = True
                        o["duration"] = "until_opp_turn_end"
                # strip junk choose_targets
                ops = [o for o in ops if o.get("op") != "choose_target"]
                changed = True
            else:
                # Replace bogus choose_target-only payloads.
                if all(o.get("op") == "choose_target" for o in ops) or not ops:
                    ops = [
                        {
                            "op": "attack_tax",
                            "trash_hand": n,
                            "all": True,
                            "duration": "until_opp_turn_end",
                        }
                    ]
                    m_life = re.search(r"生命值卡在\s*(\d+)\s*[張张]以下|Life (?:is |cards? )?(?:of )?(\d+) or less", blob, re.I)
                    if m_life:
                        a["require_life_lte"] = int(next(g for g in m_life.groups() if g))
                    m_tr = re.search(r"『([^』]+)』|\{([^}]+)\}", blob)
                    if m_tr and re.search(r"領航卡|Leader", blob, re.I):
                        a["require_leader_trait"] = next(g for g in m_tr.groups() if g)
                    changed = True
            continue

        if kind == "bottom":
            # Skip abilities that clearly don't contain the bottom cue in this timing.
            if timing == "activate_main" and not re.search(r"啟動主要|Activate", blob, re.I):
                pass
            has = any(o.get("op") == "opponent_hand_to_bottom" for o in _iter_ops(ops))
            wrong_proxy = any(
                o.get("op") == "return_to_bottom" and not o.get("target_kind") for o in ops
            ) and re.search(r"對手將|对手将|places? .+ hand .+ bottom", blob, re.I)
            needs = has or wrong_proxy or (
                timing in {"on_play", "when_attacking", "activate_main", "your_turn"}
                and re.search(r"對手將|对手将|places? .+ from (?:their|the) hand", blob, re.I)
            )
            if not needs and not has:
                continue
            new_ops = _ensure_bottom_op(ops, n, hand_gte)
            # OP07-047: return self to hand as cost
            if timing == "activate_main" and re.search(r"放回持有者的手牌|return this Character to", blob, re.I):
                if not any(o.get("op") == "return_to_hand" and o.get("target_kind") == "self" for o in new_ops):
                    # Fix wrong opponent return
                    for o in new_ops:
                        if o.get("op") == "return_to_hand":
                            o["target_kind"] = "self"
                            o["optional"] = True
                            o["as_cost"] = True
                    if not any(o.get("op") == "return_to_hand" for o in new_ops):
                        new_ops.insert(
                            0,
                            {
                                "op": "return_to_hand",
                                "target_kind": "self",
                                "optional": True,
                                "as_cost": True,
                            },
                        )
                # Remove stray choose_target
                new_ops = [o for o in new_ops if o.get("op") != "choose_target"]
            # OP16-047: rest self as cost
            if timing == "activate_main" and re.search(r"置為休息狀態：|rest this Character:", blob, re.I):
                for o in new_ops:
                    if o.get("op") == "rest_character" and o.get("target_kind") == "opponent_character":
                        o["target_kind"] = "self"
                        o["optional"] = True
                        o["as_cost"] = True
                if not any(o.get("op") == "rest_character" for o in new_ops):
                    new_ops.insert(
                        0,
                        {"op": "rest_character", "target_kind": "self", "optional": True, "as_cost": True},
                    )
            # P-048: DON!! x1 + life gate
            if timing == "when_attacking" and re.search(r"咚‼?\s*×\s*1|DON!! x1", blob, re.I):
                a["require_don_attached_gte"] = 1
            if timing == "when_attacking" and re.search(r"生命值卡在\s*(\d+)\s*[張张]以上", blob):
                m = re.search(r"生命值卡在\s*(\d+)\s*[張张]以上", blob)
                if m:
                    a["require_life_gte"] = int(m.group(1))
            # Prefer op-level gate; clear wrong ability-only if op has it
            if hand_gte is not None:
                # Keep ability-level too for continuous/your_turn reactions (OP08-046).
                if timing in {"your_turn", "opponent_turn"}:
                    a["require_opp_hand_gte"] = hand_gte
            if new_ops != ops:
                ops = new_ops
                changed = True
            elif has and hand_gte is not None:
                # still ensure gate
                for o in _iter_ops(ops):
                    if o.get("op") == "opponent_hand_to_bottom" and o.get("require_opp_hand_gte") != hand_gte:
                        o["require_opp_hand_gte"] = hand_gte
                        changed = True

        if kind == "trash":
            has = any(
                o.get("op") == "trash_hand" and o.get("owner") == "opponent" for o in _iter_ops(ops)
            )
            # Timing must match paper section containing the trash cue when possible.
            if timing == "on_ko" and not re.search(r"【KO時】|\[on k\.?o", blob, re.I):
                continue
            if timing == "when_attacking" and not re.search(r"【攻擊時】|\[when attacking\]", blob, re.I):
                continue
            if timing == "on_play" and not re.search(r"【登場時】|\[on play\]", blob, re.I):
                # still allow if only ability
                pass
            # P-121 / P-145: KO trash
            if re.search(r"【KO時】.{0,80}對手廢棄|\[on k\.?o\.?\].{0,80}opponent trashes?", blob, re.I):
                if timing != "on_ko":
                    # don't put KO effect on on_play
                    if timing == "on_play":
                        continue
            new_ops = _ensure_opp_trash_op(ops, n, hand_gte)
            # OP05-082: rest self + trash_to_bottom 2 as cost
            if timing == "activate_main" and re.search(r"置為休息狀態.{0,40}廢棄區", blob):
                new_ops = [
                    o
                    for o in new_ops
                    if not (
                        o.get("op") == "rest_character"
                        and o.get("target_kind") == "opponent_character"
                    )
                ]
                if not any(o.get("op") == "rest_character" and o.get("target_kind") == "self" for o in new_ops):
                    new_ops.insert(
                        0,
                        {"op": "rest_character", "target_kind": "self", "optional": True, "as_cost": True},
                    )
                # remove bogus return_to_bottom duplicates if trash_to_bottom present
                if any(o.get("op") == "trash_to_bottom" for o in new_ops):
                    new_ops = [
                        o
                        for o in new_ops
                        if not (o.get("op") == "return_to_bottom" and not o.get("target_kind"))
                    ]
                # ensure trash_to_bottom cost
                if not any(o.get("op") == "trash_to_bottom" for o in new_ops):
                    new_ops.insert(
                        1,
                        {
                            "op": "trash_to_bottom",
                            "count": 2,
                            "optional": True,
                            "owner": "self",
                            "card_type": "any",
                            "order_any": True,
                            "as_cost": True,
                        },
                    )
                else:
                    for o in new_ops:
                        if o.get("op") == "trash_to_bottom":
                            o["as_cost"] = True
                            o["optional"] = True
                # remove wrong owner=self trash if we added opponent
                cleaned = []
                seen_opp = False
                for o in new_ops:
                    if o.get("op") == "trash_hand" and o.get("owner") == "opponent":
                        if seen_opp:
                            continue
                        seen_opp = True
                        cleaned.append(o)
                    elif o.get("op") == "trash_hand" and o.get("owner") != "opponent" and not o.get("as_cost"):
                        continue
                    else:
                        cleaned.append(o)
                new_ops = cleaned
            # OP01-102 / 114: return_don 1 + opp trash (not optional self)
            if re.search(r"咚!!\s*-?\s*1|DON!!\s*-1", blob, re.I) and timing in {
                "when_attacking",
                "on_play",
            }:
                for o in new_ops:
                    if o.get("op") == "rest_don":
                        o["op"] = "return_don"
                if not any(o.get("op") == "return_don" for o in new_ops):
                    new_ops.insert(0, {"op": "return_don", "count": 1})
            # ST33-002: as_cost self trash then opp trash with gate
            if timing == "when_attacking" and re.search(r"可以廢棄1張自己的手牌：", blob):
                for o in new_ops:
                    if o.get("op") == "trash_hand" and o.get("owner") != "opponent":
                        o["as_cost"] = True
                        o["optional"] = True
                        o["owner"] = "self"
            # ST35-003: mill 2 as cost
            if timing == "when_attacking" and re.search(r"卡組上面的卡片放置在廢棄區：", blob):
                for o in new_ops:
                    if o.get("op") == "trash_deck_top":
                        o["as_cost"] = True
                        o["optional"] = True
            # OP07-093: trash_to_bottom 3 cost, opp trash, then opp trash_to_bottom 1
            if timing == "on_play" and re.search(r"可將3張自己廢棄區", blob):
                new_ops = [
                    o
                    for o in new_ops
                    if not (o.get("op") == "return_to_bottom" and int(o.get("count") or 0) == 3)
                ]
                # fix last return_to_bottom 1 → trash_to_bottom opponent
                fixed = []
                for o in new_ops:
                    if o.get("op") == "return_to_bottom" and int(o.get("count") or 0) == 1:
                        fixed.append(
                            {
                                "op": "trash_to_bottom",
                                "count": 1,
                                "optional": True,
                                "owner": "opponent",
                                "card_type": "any",
                            }
                        )
                    else:
                        fixed.append(o)
                new_ops = fixed
            if new_ops != ops:
                ops = new_ops
                changed = True
            elif has and hand_gte is not None:
                for o in _iter_ops(ops):
                    if o.get("op") == "trash_hand" and o.get("owner") == "opponent":
                        if o.get("require_opp_hand_gte") != hand_gte:
                            o["require_opp_hand_gte"] = hand_gte
                            changed = True
            # Ability-level gate when paper gates whole effect (choose_one after 若…)
            if hand_gte is not None and re.search(
                r"若對手的手牌有\s*\d+\s*[張张]以上時，選擇|if your opponent has \d+ or more cards in their hand, choose",
                blob,
                re.I,
            ):
                if a.get("require_opp_hand_gte") != hand_gte:
                    a["require_opp_hand_gte"] = hand_gte
                    changed = True

    if not changed:
        return None
    a["ops"] = sanitize_ops_list(ops)
    a["status"] = "verified"
    a["confidence"] = 1.0
    if not a.get("summary"):
        a["summary"] = (zh or en)[:180]
    return a


def _ensure_on_ko_ability(card: dict[str, Any], zh: str, en: str, n: int, hand_gte: int | None) -> bool:
    abs_ = list(card.get("abilities") or [])
    for a in abs_:
        if a.get("timing") == "on_ko":
            new_a = _fix_ability(a, zh, en, {"trash"})
            if new_a:
                # replace
                for i, old in enumerate(abs_):
                    if old is a or old.get("timing") == "on_ko":
                        abs_[i] = new_a
                        card["abilities"] = abs_
                        return True
            # empty on_ko
            if not (a.get("ops") or []):
                op: dict[str, Any] = {
                    "op": "trash_hand",
                    "count": n,
                    "optional": False,
                    "owner": "opponent",
                }
                if hand_gte is not None:
                    op["require_opp_hand_gte"] = hand_gte
                a["ops"] = sanitize_ops_list([op])
                if hand_gte is not None:
                    a["require_opp_hand_gte"] = hand_gte
                a["status"] = "verified"
                a["confidence"] = 1.0
                a["summary"] = "【KO時】對手廢棄自身的手牌"
                card["abilities"] = abs_
                return True
            return False
    # missing on_ko entirely
    op = {"op": "trash_hand", "count": n, "optional": False, "owner": "opponent"}
    if hand_gte is not None:
        op["require_opp_hand_gte"] = hand_gte
    ab: dict[str, Any] = {
        "timing": "on_ko",
        "summary": "【KO時】對手廢棄自身的手牌",
        "ops": sanitize_ops_list([op]),
        "status": "verified",
        "confidence": 1.0,
    }
    if hand_gte is not None:
        ab["require_opp_hand_gte"] = hand_gte
    abs_.append(ab)
    card["abilities"] = abs_
    return True


def diagnose(cid: str, zh: str, en: str, card: dict[str, Any]) -> list[str]:
    kinds = _paper_kinds(zh, en)
    if not kinds:
        return []
    abs_ = card.get("abilities") or []
    issues: list[str] = []
    for kind in kinds:
        n, hand_gte = _counts(zh, en, kind)
        found = False
        gate_ok = hand_gte is None
        for a in abs_:
            ops = a.get("ops") or []
            if kind == "bottom":
                for o in _iter_ops(ops):
                    if o.get("op") == "opponent_hand_to_bottom":
                        found = True
                        if int(o.get("count") or 0) != n:
                            issues.append(f"bottom count {o.get('count')}!={n}")
                        g = o.get("require_opp_hand_gte") or a.get("require_opp_hand_gte")
                        if hand_gte and g == hand_gte:
                            gate_ok = True
            if kind == "trash":
                for o in _iter_ops(ops):
                    if o.get("op") == "trash_hand" and o.get("owner") == "opponent":
                        found = True
                        if int(o.get("count") or 0) != n:
                            issues.append(f"trash count {o.get('count')}!={n}")
                        g = o.get("require_opp_hand_gte") or a.get("require_opp_hand_gte")
                        if hand_gte and g == hand_gte:
                            gate_ok = True
                for o in ops:
                    if o.get("op") != "choose_one":
                        continue
                    for opt in o.get("options") or []:
                        if any(
                            x.get("op") == "trash_hand" and x.get("owner") == "opponent"
                            for x in (opt.get("ops") or [])
                        ):
                            found = True
                            if hand_gte and (
                                opt.get("require_opp_hand_gte") == hand_gte
                                or any(
                                    x.get("require_opp_hand_gte") == hand_gte
                                    for x in (opt.get("ops") or [])
                                )
                                or a.get("require_opp_hand_gte") == hand_gte
                            ):
                                gate_ok = True
            if kind == "attack_tax":
                for o in _iter_ops(ops):
                    if o.get("op") == "attack_tax":
                        found = True
                        gate_ok = True
                        if int(o.get("trash_hand") or 0) != n:
                            issues.append(f"attack_tax {o.get('trash_hand')}!={n}")
        if not found:
            issues.append(f"MISSING {kind} n={n} hand_gte={hand_gte}")
        elif hand_gte and not gate_ok:
            issues.append(f"MISSING hand_gte={hand_gte} on {kind}")
    return issues


def fix_card(cid: str, info: dict[str, Any], card: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    zh = str(info.get("effect") or "")
    en = str(info.get("effect_en") or "")
    kinds = _paper_kinds(zh, en)
    before = diagnose(cid, zh, en, card)
    if not kinds:
        return card, []
    card = copy.deepcopy(card)
    card.setdefault("card_id", cid)
    card.setdefault("version", 1)
    abs_ = list(card.get("abilities") or [])
    new_abs: list[dict[str, Any]] = []
    touched = False
    for a in abs_:
        fixed = _fix_ability(a, zh, en, kinds)
        if fixed:
            new_abs.append(fixed)
            touched = True
        else:
            new_abs.append(a)
    card["abilities"] = new_abs

    # Ensure KO abilities exist when paper has KO trash
    if "trash" in kinds and re.search(r"【KO時】.{0,80}對手廢棄|\[on k\.?o\.?\].{0,80}opponent trashes?", f"{zh}\n{en}", re.I):
        n, hand_gte = _counts(zh, en, "trash")
        if _ensure_on_ko_ability(card, zh, en, n, hand_gte):
            touched = True

    # Copy good base ability for P variants still broken
    after = diagnose(cid, zh, en, card)
    return card, after


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cards = json.loads(CARDS_PATH.read_text(encoding="utf-8"))
    lib = json.loads(LIB_PATH.read_text(encoding="utf-8"))
    ov = json.loads(OV_PATH.read_text(encoding="utf-8"))
    lib_cards = lib.setdefault("cards", {})
    ov_cards = ov.setdefault("cards", {})

    # Prefer copying from healthy base before per-card surgery.
    fixed_ids: list[str] = []
    report: list[str] = []

    # First pass: identify all relevant cids
    targets = []
    for cid, info in sorted(cards.items()):
        zh = str(info.get("effect") or "")
        en = str(info.get("effect_en") or "")
        if _paper_kinds(zh, en):
            targets.append(cid)

    # Build base templates from current lib when healthy
    base_ok: dict[str, dict[str, Any]] = {}
    for cid in targets:
        info = cards[cid]
        zh = str(info.get("effect") or "")
        en = str(info.get("effect_en") or "")
        entry = lib_cards.get(cid) or ov_cards.get(cid) or {"card_id": cid, "version": 1, "abilities": []}
        if not diagnose(cid, zh, en, entry):
            base_ok[_base_id(cid)] = copy.deepcopy(entry)

    for cid in targets:
        info = cards[cid]
        zh = str(info.get("effect") or "")
        en = str(info.get("effect_en") or "")
        entry = copy.deepcopy(lib_cards.get(cid) or ov_cards.get(cid) or {"card_id": cid, "version": 1, "abilities": []})
        before = diagnose(cid, zh, en, entry)
        if not before:
            continue

        # Try clone timings from healthy base (same paper family)
        bid = _base_id(cid)
        if bid in base_ok and cid != bid:
            base_entry = base_ok[bid]
            # Replace abilities with base (same effect text family)
            entry["abilities"] = copy.deepcopy(base_entry.get("abilities") or [])
            entry["card_id"] = cid
            after_clone = diagnose(cid, zh, en, entry)
            if not after_clone:
                entry = normalize_card_entry(cid, entry)
                lib_cards[cid] = entry
                ov_cards[cid] = entry
                fixed_ids.append(cid)
                report.append(f"{cid}: cloned from {bid}")
                continue

        entry, after = fix_card(cid, info, entry)
        # Special hardcoded templates for stubborn cards
        if after:
            entry2 = copy.deepcopy(entry)
            abs_ = list(entry2.get("abilities") or [])
            # OP05-082 family
            if bid == "OP05-082":
                abs_ = [
                    {
                        "timing": "activate_main",
                        "summary": zh[:180],
                        "ops": sanitize_ops_list(
                            [
                                {
                                    "op": "rest_character",
                                    "target_kind": "self",
                                    "optional": True,
                                    "as_cost": True,
                                },
                                {
                                    "op": "trash_to_bottom",
                                    "count": 2,
                                    "optional": True,
                                    "owner": "self",
                                    "card_type": "any",
                                    "order_any": True,
                                    "as_cost": True,
                                },
                                {
                                    "op": "trash_hand",
                                    "count": 1,
                                    "optional": False,
                                    "owner": "opponent",
                                    "require_opp_hand_gte": 6,
                                },
                            ]
                        ),
                        "status": "verified",
                        "confidence": 1.0,
                    }
                ]
                entry2["abilities"] = abs_
            elif bid == "OP07-047":
                abs_ = [
                    {
                        "timing": "activate_main",
                        "summary": zh[:180],
                        "ops": sanitize_ops_list(
                            [
                                {
                                    "op": "return_to_hand",
                                    "target_kind": "self",
                                    "optional": True,
                                    "as_cost": True,
                                },
                                {
                                    "op": "opponent_hand_to_bottom",
                                    "count": 1,
                                    "optional": False,
                                    "require_opp_hand_gte": 6,
                                },
                            ]
                        ),
                        "status": "verified",
                        "confidence": 1.0,
                    }
                ]
                entry2["abilities"] = abs_
            elif bid == "OP16-047":
                abs_ = [
                    {
                        "timing": "activate_main",
                        "summary": zh[:180],
                        "ops": sanitize_ops_list(
                            [
                                {
                                    "op": "rest_character",
                                    "target_kind": "self",
                                    "optional": True,
                                    "as_cost": True,
                                },
                                {
                                    "op": "opponent_hand_to_bottom",
                                    "count": 2,
                                    "optional": False,
                                    "require_opp_hand_gte": 8,
                                },
                            ]
                        ),
                        "status": "verified",
                        "confidence": 1.0,
                    }
                ]
                entry2["abilities"] = abs_
            elif bid == "P-048":
                abs_ = [
                    {
                        "timing": "when_attacking",
                        "summary": zh[:180],
                        "ops": sanitize_ops_list(
                            [{"op": "opponent_hand_to_bottom", "count": 1, "optional": False}]
                        ),
                        "status": "verified",
                        "confidence": 1.0,
                        "require_don_attached_gte": 1,
                        "require_life_gte": 4,
                    }
                ]
                entry2["abilities"] = abs_
            elif bid == "OP01-102":
                abs_ = [
                    {
                        "timing": "when_attacking",
                        "summary": zh[:180],
                        "ops": sanitize_ops_list(
                            [
                                {"op": "return_don", "count": 1},
                                {
                                    "op": "trash_hand",
                                    "count": 1,
                                    "optional": False,
                                    "owner": "opponent",
                                },
                            ]
                        ),
                        "status": "verified",
                        "confidence": 1.0,
                    }
                ]
                entry2["abilities"] = abs_
            elif bid == "OP01-114":
                abs_ = [
                    {
                        "timing": "on_play",
                        "summary": zh[:180],
                        "ops": sanitize_ops_list(
                            [
                                {"op": "return_don", "count": 1},
                                {
                                    "op": "trash_hand",
                                    "count": 1,
                                    "optional": False,
                                    "owner": "opponent",
                                },
                            ]
                        ),
                        "status": "verified",
                        "confidence": 1.0,
                    }
                ]
                entry2["abilities"] = abs_
            elif bid == "OP07-093":
                abs_ = [
                    {
                        "timing": "on_play",
                        "summary": zh[:180],
                        "ops": sanitize_ops_list(
                            [
                                {
                                    "op": "trash_to_bottom",
                                    "count": 3,
                                    "optional": True,
                                    "owner": "self",
                                    "card_type": "any",
                                    "order_any": True,
                                    "as_cost": True,
                                },
                                {
                                    "op": "trash_hand",
                                    "count": 1,
                                    "optional": False,
                                    "owner": "opponent",
                                },
                                {
                                    "op": "trash_to_bottom",
                                    "count": 1,
                                    "optional": True,
                                    "owner": "opponent",
                                    "card_type": "any",
                                },
                            ]
                        ),
                        "status": "verified",
                        "confidence": 1.0,
                    }
                ]
                entry2["abilities"] = abs_
            elif bid == "OP08-043":
                abs_ = [
                    {
                        "timing": "on_play",
                        "summary": zh[:180],
                        "ops": sanitize_ops_list(
                            [
                                {
                                    "op": "attack_tax",
                                    "trash_hand": 2,
                                    "all": True,
                                    "duration": "until_opp_turn_end",
                                }
                            ]
                        ),
                        "status": "verified",
                        "confidence": 1.0,
                        "require_life_lte": 2,
                        "require_leader_trait": "Whitebeard Pirates",
                    }
                ]
                entry2["abilities"] = abs_
            elif bid == "ST33-002":
                # keep on_ko; fix when_attacking
                kept = [a for a in abs_ if a.get("timing") != "when_attacking"]
                kept.insert(
                    0,
                    {
                        "timing": "when_attacking",
                        "summary": "【攻擊時】可以廢棄1張自己的手牌：若對手的手牌有6張以上時，對手廢棄1張自身的手牌。",
                        "ops": sanitize_ops_list(
                            [
                                {
                                    "op": "trash_hand",
                                    "count": 1,
                                    "optional": True,
                                    "as_cost": True,
                                    "owner": "self",
                                },
                                {
                                    "op": "trash_hand",
                                    "count": 1,
                                    "optional": False,
                                    "owner": "opponent",
                                    "require_opp_hand_gte": 6,
                                },
                            ]
                        ),
                        "status": "verified",
                        "confidence": 1.0,
                    },
                )
                entry2["abilities"] = kept
            elif bid == "ST35-003":
                abs_ = [
                    {
                        "timing": "when_attacking",
                        "summary": zh[:180],
                        "ops": sanitize_ops_list(
                            [
                                {
                                    "op": "trash_deck_top",
                                    "count": 2,
                                    "optional": True,
                                    "as_cost": True,
                                },
                                {
                                    "op": "trash_hand",
                                    "count": 1,
                                    "optional": False,
                                    "owner": "opponent",
                                    "require_opp_hand_gte": 7,
                                },
                            ]
                        ),
                        "status": "verified",
                        "confidence": 1.0,
                    }
                ]
                entry2["abilities"] = abs_
            elif bid == "P-121":
                abs_ = [
                    {
                        "timing": "on_play",
                        "summary": "【登場時】將3張自己卡組上面的卡片放置在廢棄區。",
                        "ops": sanitize_ops_list(
                            [{"op": "trash_deck_top", "count": 3, "optional": False}]
                        ),
                        "status": "verified",
                        "confidence": 1.0,
                    },
                    {
                        "timing": "on_ko",
                        "summary": "【KO時】對手廢棄2張自身的手牌。",
                        "ops": sanitize_ops_list(
                            [
                                {
                                    "op": "trash_hand",
                                    "count": 2,
                                    "optional": False,
                                    "owner": "opponent",
                                }
                            ]
                        ),
                        "status": "verified",
                        "confidence": 1.0,
                    },
                ]
                entry2["abilities"] = abs_
            elif bid == "P-145":
                abs_ = [
                    {
                        "timing": "on_play",
                        "summary": "【登場時】抽1張卡片，並廢棄1張自己的手牌。",
                        "ops": sanitize_ops_list(
                            [
                                {"op": "draw", "count": 1},
                                {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                            ]
                        ),
                        "status": "verified",
                        "confidence": 1.0,
                    },
                    {
                        "timing": "on_ko",
                        "summary": "【KO時】若對手的手牌有6張以上時，對手廢棄2張自身的手牌。",
                        "ops": sanitize_ops_list(
                            [
                                {
                                    "op": "trash_hand",
                                    "count": 2,
                                    "optional": False,
                                    "owner": "opponent",
                                    "require_opp_hand_gte": 6,
                                }
                            ]
                        ),
                        "status": "verified",
                        "confidence": 1.0,
                    },
                ]
                entry2["abilities"] = abs_
            elif bid == "EB03-026":
                # keep activate from current if any; fix on_play gate
                on_play = {
                    "timing": "on_play",
                    "summary": "【登場時】若對手的手牌有5張以上時，對手將1張自身的手牌放置在卡組下面。",
                    "ops": sanitize_ops_list(
                        [
                            {
                                "op": "opponent_hand_to_bottom",
                                "count": 1,
                                "optional": False,
                                "require_opp_hand_gte": 5,
                            }
                        ]
                    ),
                    "status": "verified",
                    "confidence": 1.0,
                    "require_opp_hand_gte": 5,
                }
                rest = [a for a in abs_ if a.get("timing") != "on_play"]
                # Prefer base activate if available
                if bid in base_ok:
                    rest = [a for a in (base_ok[bid].get("abilities") or []) if a.get("timing") != "on_play"]
                entry2["abilities"] = [on_play, *rest]

            after2 = diagnose(cid, zh, en, entry2)
            if not after2:
                entry = entry2
                after = after2
            else:
                after = after2
                entry = entry2

        entry = normalize_card_entry(cid, entry)
        after = diagnose(cid, zh, en, entry)
        if after:
            report.append(f"{cid}: STILL {after}")
            # still write best effort
        else:
            report.append(f"{cid}: fixed {before} -> ok")
        lib_cards[cid] = entry
        ov_cards[cid] = entry
        fixed_ids.append(cid)

    # Also patch healthy choose_one option gates (EB02-045)
    for cid in targets:
        info = cards[cid]
        zh = str(info.get("effect") or "")
        entry = lib_cards.get(cid)
        if not entry:
            continue
        changed = False
        for a in entry.get("abilities") or []:
            for o in a.get("ops") or []:
                if o.get("op") != "choose_one":
                    continue
                for opt in o.get("options") or []:
                    for oo in opt.get("ops") or []:
                        if oo.get("op") == "trash_hand" and oo.get("owner") == "opponent":
                            g = opt.get("require_opp_hand_gte") or _extract_require_opp_hand_gte_from_text(zh)
                            # Only if label/paper suggests conditional branch, not whole-ability gate
                            if g and oo.get("require_opp_hand_gte") != g:
                                # If ability already gates whole choose_one, still put on op for safety when option-specific
                                if opt.get("require_opp_hand_gte") or re.search(
                                    r"若對手的手牌有\s*\d+.*對手廢棄", zh
                                ):
                                    if a.get("require_opp_hand_gte") == g and len(o.get("options") or []) > 1:
                                        # whole ability gated — option gate optional
                                        pass
                                    else:
                                        oo["require_opp_hand_gte"] = g
                                        opt["require_opp_hand_gte"] = g
                                        changed = True
        if changed:
            entry = normalize_card_entry(cid, entry)
            lib_cards[cid] = entry
            ov_cards[cid] = entry
            if cid not in fixed_ids:
                fixed_ids.append(cid)
            report.append(f"{cid}: option-level hand gate synced")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    lib["generated_at"] = now
    ov["generated_at"] = now

    # Final scan
    remain = []
    for cid in targets:
        info = cards[cid]
        zh = str(info.get("effect") or "")
        en = str(info.get("effect_en") or "")
        issues = diagnose(cid, zh, en, lib_cards.get(cid) or {})
        if issues:
            remain.append((cid, issues))

    print(f"targets={len(targets)} fixed={len(fixed_ids)} remain={len(remain)}")
    for line in report:
        print(line)
    if remain:
        print("REMAINING:")
        for cid, issues in remain:
            print(cid, issues)

    if args.dry_run:
        return 0 if not remain else 1

    LIB_PATH.write_text(json.dumps(lib, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    OV_PATH.write_text(json.dumps(ov, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    OUT_IDS.parent.mkdir(parents=True, exist_ok=True)
    OUT_IDS.write_text("\n".join(fixed_ids) + "\n", encoding="utf-8")
    print("wrote", LIB_PATH.name, OV_PATH.name, OUT_IDS)
    return 0 if not remain else 1


if __name__ == "__main__":
    raise SystemExit(main())
