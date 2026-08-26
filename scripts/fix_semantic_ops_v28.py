#!/usr/bin/env python3
"""Deterministic semantic fixes v28: gates, life-damage, opp-KO draw, don/rest.

Dual-writes library + overrides.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from battle.effect_library import get_card_entry, library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_ability, normalize_card_entry  # noqa: E402
from battle.effects import effect_blob  # noqa: E402
from fix_semantic_gates_v2 import _timing_chunk, _trim_cross_timing  # noqa: E402

OUT_IDS = ROOT / "meta" / "logs" / "ops_v28_fixed_ids.txt"

LIFE_DMG_TRASH_RE = re.compile(
    r"\[DON!!\s*x1\].{0,60}?deals damage to your opponent's Life.{0,40}?trash\s*(\d+)\s*cards? from the top of your deck|"
    r"【咚‼?×1】.{0,60}?造成對手生命值傷害時，可[將将](\d+)[張张].{0,30}?卡組上面|"
    r"【咚‼?×1】.{0,60}?造成对手生命值伤害时，可[将將](\d+)[张張].{0,30}?卡组上面",
    re.I | re.S,
)
OPP_KO_DRAW_RE = re.compile(
    r"When your opponent's Character is K\.O\.?'?d,\s*draw\s*1|"
    r"對手的角色卡遭到KO時，抽1[張张]|对手的角色卡遭到KO时，抽1[张張]",
    re.I,
)
PLAY_NO_BASE_RE = re.compile(
    r"When you play a Character with no base effect from your hand|"
    r"使自己原本沒有效果的角色卡從手牌中登場|使自己原本没有效果的角色卡从手牌中登场",
    re.I,
)
NAME_FIELD_GRANT_RE = re.compile(
    r"If you have a \[([^\]]+)\] Character, this Character gains \[Blocker\]|"
    r"若場上有自己的角色卡「([^」]+)」時，這張角色卡獲得【防禦】|"
    r"若场上有自己的角色卡「([^」]+)」时，这张角色卡获得【防御】",
    re.I,
)
HAND0_DRAW_RE = re.compile(
    r"If you have 0 cards in your hand, draw\s*(\d+)|"
    r"若自己的手牌為0[張张]時，抽(\d+)|若自己的手牌为0[张張]时，抽(\d+)",
    re.I,
)
OWN_NAME_DRAW_RE = re.compile(
    r"If you have \[([^\]]+)\], draw\s*(\d+).{0,40}trash\s*1|"
    r"若場上有自己的「([^」]+)」時，抽(\d+).{0,40}廢棄1|"
    r"若场上有自己的「([^」]+)」时，抽(\d+).{0,40}废弃1",
    re.I,
)
TRASH_OWN_RED_COST_RE = re.compile(
    r"You may trash 1 of your red Characters with\s*(\d+)\s*power or more\s*:|"
    r"可[將将]1[張张]自己力量值(\d+)以上紅色的角色卡放置到廢棄區\s*[：:]|"
    r"可[将將]1[张張]自己力量值(\d+)以上红色的角色卡放置到废弃区\s*[：:]",
    re.I,
)
GAIN_DON_THEN_OPP_POW_RE = re.compile(
    r"Add up to 1 DON!! card from your DON!! deck and set it as active\.\s*"
    r"Then, if your opponent has a Character with\s*(\d+)\s*power or more,\s*"
    r"add up to 1 DON!!|"
    r"追加最多1[張张].{0,30}活動狀態的咚.{0,40}若場上有對手力量值(\d+)以上|"
    r"追加最多1[张張].{0,30}活动状态的咚.{0,40}若场上有对手力量值(\d+)以上",
    re.I | re.S,
)
REST_OPP_DON_RE = re.compile(
    r"Rest up to 1 of your opponent's DON!! cards|"
    r"將最多1[張张]對手的咚‼?卡置為休息|将最多1[张張]对手的咚‼?卡置为休息",
    re.I,
)
ON_BLOCK_REST2_RE = re.compile(
    r"\[On Block\].{0,40}rest\s*2 of your DON!!|"
    r"【防禦時】可[將将]2[張张]自己的咚|"
    r"【防御时】可[将將]2[张張]自己的咚",
    re.I | re.S,
)
OPP_TURN_ON_KO_RE = re.compile(
    r"\[Opponent's Turn\]\s*\[On K\.O\.\]|"
    r"【對方回合中】【KO時】|【对方回合中】【KO时】",
    re.I,
)
DENY_BLOCKER_COST0_RE = re.compile(
    r"If there is a Character with a cost of 0.{0,80}"
    r"cannot activate the \[Blocker\] of any Character with a cost of\s*(\d+)\s*or less|"
    r"若場上有費用0的角色卡時.{0,80}費用(\d+)以下的角色卡無法發動【防禦】|"
    r"若场上有费用0的角色卡时.{0,80}费用(\d+)以下的角色卡无法发动【防御】",
    re.I | re.S,
)
PLAY_FROM_DECK_NAME_RE = re.compile(
    r"Play up to 1 \[([^\]]+)\] with a cost of\s*(\d+)\s*or less from your deck|"
    r"使最多1[張张]自己卡組中費用(\d+)以下的「([^」]+)」登場|"
    r"使最多1[张張]自己卡组中费用(\d+)以下的「([^」]+)」登场|"
    r"從自己的卡組使最多1[張张]費用(\d+)以下的「([^」]+)」登場|"
    r"从自己的卡组使最多1[张張]费用(\d+)以下的「([^」]+)」登场",
    re.I,
)
GERMA_TRASH_PLAY_RE = re.compile(
    r"Play up to\s*(\d+)\s*\{GERMA 66\} type Character cards with different card names "
    r"and\s*(\d+)\s*power or less from your trash|"
    r"使最多(\d+)[張张]自己廢棄區中卡片名稱不同力量值(\d+)以下擁有《杰爾馬66》|"
    r"使最多(\d+)[张張]自己废弃区中卡片名称不同力量值(\d+)以下拥有《杰尔马66》",
    re.I,
)
LIFE_LESS_DON_RE = re.compile(
    r"\[DON!!\s*x1\].{0,40}less Life cards than your opponent|"
    r"【咚‼?×1】若自己的生命值卡張數比對手少|"
    r"【咚‼?×1】若自己的生命值卡张数比对手少",
    re.I | re.S,
)
MANGROVE_ADD_RE = re.compile(
    r"Add up to 1 black Character card with a cost of\s*(\d+)\s*to\s*(\d+)\s*from your trash to your hand|"
    r"將最多1[張张]自己廢棄區中費用(\d+)至(\d+)黑色的角色卡加入手牌|"
    r"将最多1[张張]自己废弃区中费用(\d+)至(\d+)黑色的角色卡加入手牌",
    re.I,
)


def _ensure_ability(abilities: list[dict[str, Any]], timing: str, predicate) -> dict[str, Any] | None:
    for a in abilities:
        if a.get("timing") == timing and predicate(a):
            return a
    return None


def fix_card(cid: str, info: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any] | None:
    blob = effect_blob(info)
    abs_in = [dict(a) for a in (entry.get("abilities") or []) if isinstance(a, dict)]
    changed = False
    new_abs: list[dict[str, Any]] = [dict(a) for a in abs_in]

    # --- pass existing abilities ---
    for a in new_abs:
        t = str(a.get("timing") or "")
        chunk = _trim_cross_timing(_timing_chunk(blob, t), t) or ""
        ops = [dict(o) for o in (a.get("ops") or []) if isinstance(o, dict)]

        # OP02-049: hand == 0
        if t == "end_of_your_turn" and HAND0_DRAW_RE.search(chunk or blob):
            if a.get("require_hand_lte") != 0:
                a["require_hand_lte"] = 0
                changed = True

        # OP02-031: name on field for blocker
        m_name = NAME_FIELD_GRANT_RE.search(chunk or blob)
        if t in {"your_turn", "opponent_turn"} and m_name:
            nm = next(g for g in m_name.groups() if g)
            if a.get("require_own_name_on_field") != nm:
                a["require_own_name_on_field"] = nm
                changed = True

        # OP02-052: Mohji gate
        m_own = OWN_NAME_DRAW_RE.search(chunk or blob)
        if t == "on_play" and m_own:
            nm = next(g for g in m_own.groups() if g and not str(g).isdigit())
            if nm and a.get("require_own_name_on_field") != nm:
                a["require_own_name_on_field"] = nm
                changed = True

        # OP03-012: trash own red power as cost
        m_tr = TRASH_OWN_RED_COST_RE.search(chunk or blob)
        if t == "when_attacking" and m_tr:
            pow_n = int(next(g for g in m_tr.groups() if g))
            if not any(o.get("op") == "trash" and o.get("as_cost") for o in ops):
                ops = [
                    {
                        "op": "trash",
                        "target_kind": "own_character",
                        "optional": True,
                        "as_cost": True,
                        "color": "red",
                        "power_gte": pow_n,
                    }
                ] + ops
                changed = True

        # OP03-051 on_ko: drop bogus trash opponent
        if t == "on_ko" and re.search(r"trash\s*\d+\s*cards? from the top of your deck|卡組上面的卡片放置到廢棄區|卡组上面的卡片放置到废弃区", chunk or blob, re.I):
            if any(o.get("op") == "trash" and o.get("target_kind") == "opponent_character" for o in ops):
                ops = [o for o in ops if not (o.get("op") == "trash" and o.get("target_kind") == "opponent_character")]
                changed = True

        # EB04-044 / replace_leave keep + leader trait
        if t == "your_turn" and any(o.get("op") == "replace_leave" for o in ops):
            if re.search(r"Navy|海軍|海军", blob) and not a.get("require_leader_trait"):
                a["require_leader_trait"] = "Navy"
                changed = True

        # OP03-108: life less than opponent on don_attached
        if t in {"don_attached", "your_turn"} and LIFE_LESS_DON_RE.search(blob):
            if not a.get("require_life_less_than_opponent"):
                a["require_life_less_than_opponent"] = True
                changed = True
            # strip stray reduce/extra without gate bleed is handled by gate

        # OP04-020: keep your_turn aura; drop reduce_cost select if static present
        if t == "your_turn" and re.search(r"Give all of your opponent's Characters −1 cost|對手的角色卡全數費用-1|对手的角色卡全数费用-1", chunk or blob, re.I):
            a["require_don_attached_gte"] = max(int(a.get("require_don_attached_gte") or 0), 1)
            cleaned = []
            for o in ops:
                if o.get("op") == "reduce_cost":
                    changed = True
                    continue
                cleaned.append(o)
            if not any(o.get("op") == "static_reduce_opp_cost" for o in cleaned):
                cleaned.insert(0, {"op": "static_reduce_opp_cost", "amount": -1})
                changed = True
            ops = cleaned
            a["status"] = "compiled"
            a["confidence"] = max(float(a.get("confidence") or 0), 0.9)
            changed = True

        # OP06-062 activate: rest opponent DON
        if t == "activate_main" and REST_OPP_DON_RE.search(chunk or blob):
            new_ops = []
            for o in ops:
                if o.get("op") == "rest_opponent_character":
                    new_ops.append({"op": "rest_don", "count": 1, "owner": "opponent", "optional": True})
                    changed = True
                else:
                    new_ops.append(o)
            if not any(o.get("op") == "rest_don" and o.get("owner") == "opponent" for o in new_ops):
                new_ops.append({"op": "rest_don", "count": 1, "owner": "opponent", "optional": True})
                changed = True
            ops = new_ops

        # OP06-062 on_play: play from trash GERMA
        m_g = GERMA_TRASH_PLAY_RE.search(chunk or blob)
        if t == "on_play" and m_g:
            gs = [g for g in m_g.groups() if g]
            cnt = int(gs[0])
            pow_n = int(gs[1])
            for o in ops:
                if o.get("op") == "play_from_hand":
                    o["from_zone"] = "trash"
                    o["count"] = cnt
                    o["power_lte"] = pow_n
                    o["trait_contains"] = "GERMA 66"
                    o["different_names"] = True
                    o["optional"] = True
                    changed = True

        # OP08-076: second gain_don instead of set_character_active
        m_gd = GAIN_DON_THEN_OPP_POW_RE.search(chunk or blob)
        if t == "main_start" and m_gd:
            pow_n = int(next(g for g in m_gd.groups() if g))
            cleaned = [o for o in ops if o.get("op") != "set_character_active"]
            if not any(o.get("op") == "gain_don" for o in cleaned):
                cleaned.append({"op": "gain_don", "count": 1})
            if not any(o.get("op") == "gain_don" and o.get("require_opp_char_base_power_gte") for o in cleaned):
                cleaned.append(
                    {
                        "op": "gain_don",
                        "count": 1,
                        "require_opp_char_base_power_gte": pow_n,
                    }
                )
                changed = True
            elif any(o.get("op") == "set_character_active" for o in ops):
                changed = True
            ops = cleaned

        # OP10-077: rest 2 don as cost
        if t == "on_block" and ON_BLOCK_REST2_RE.search(blob):
            for o in ops:
                if o.get("op") == "rest_don":
                    if int(o.get("count") or 0) != 2 or not o.get("as_cost"):
                        o["count"] = 2
                        o["as_cost"] = True
                        changed = True

        # EB03-055: opponent turn on KO
        if t == "on_ko" and OPP_TURN_ON_KO_RE.search(blob):
            if not a.get("require_opponent_turn"):
                a["require_opponent_turn"] = True
                changed = True

        # OP02-101: cost 0 field + deny cost_lte
        m_db = DENY_BLOCKER_COST0_RE.search(chunk or blob)
        if t == "when_attacking" and m_db:
            clte = int(next(g for g in m_db.groups() if g))
            if a.get("require_field_char_cost_eq") != 0:
                a["require_field_char_cost_eq"] = 0
                changed = True
            for o in ops:
                if o.get("op") == "deny_blocker":
                    if o.get("power_lte") is not None:
                        o.pop("power_lte", None)
                        changed = True
                    if o.get("cost_lte") != clte:
                        o["cost_lte"] = clte
                        changed = True

        # OP08-073 / ST03-007 style: play named from deck
        m_pd = PLAY_FROM_DECK_NAME_RE.search(chunk or blob)
        if t in {"on_ko", "activate_main"} and m_pd:
            groups = [g for g in m_pd.groups() if g]
            # patterns vary: name then cost OR cost then name
            if groups[0].isdigit():
                cost_n, name = int(groups[0]), groups[1]
            else:
                name, cost_n = groups[0], int(groups[1])
            for o in ops:
                if o.get("op") in {"play_from_hand", "search_deck"}:
                    if o.get("op") == "play_from_hand":
                        o["from_zone"] = "deck"
                        o["name_contains"] = name
                        o["cost_lte"] = cost_n
                        o["optional"] = True
                        changed = True
                    else:
                        o["name_contains"] = name
                        o["cost_lte"] = cost_n
                        o["destination"] = "play"
                        o["shuffle"] = True
                        changed = True
            if t == "activate_main" and not any(
                o.get("op") in {"play_from_hand", "search_deck"} for o in ops
            ):
                ops.append(
                    {
                        "op": "search_deck",
                        "name_contains": name,
                        "top_n": 8,
                        "max_add": 1,
                        "destination": "play",
                        "cost_lte": cost_n,
                        "shuffle": True,
                        "card_type": "character",
                    }
                )
                changed = True
            if t == "on_ko" and not a.get("require_opponent_turn") and re.search(
                r"Opponent's Turn|對方回合|对方回合", blob, re.I
            ):
                a["require_opponent_turn"] = True
                changed = True

        # OP05-088: cleanup mangled ops
        m_add = MANGROVE_ADD_RE.search(chunk or blob)
        if t == "activate_main" and m_add and re.search(r"place 2 cards from your trash at the bottom|廢棄區中的卡片依任意順序放到卡組下面|废弃区中的卡片依任意顺序放到卡组下面", chunk or blob, re.I):
            c_lo = int(m_add.group(1) or m_add.group(3) or m_add.group(5) or 3)
            c_hi = int(m_add.group(2) or m_add.group(4) or m_add.group(6) or 5)
            ops = [
                {"op": "rest_don", "count": 1, "as_cost": True},
                {"op": "rest_character", "target_kind": "self", "optional": True, "as_cost": True},
                {"op": "trash_to_bottom", "count": 2, "optional": False, "owner": "self", "order_any": True, "as_cost": True},
                {
                    "op": "add_from_trash",
                    "count": 1,
                    "optional": True,
                    "card_type": "character",
                    "color": "black",
                    "cost_gte": c_lo,
                    "cost_lte": c_hi,
                },
            ]
            a["rest_self"] = True
            a["cost_don"] = 1
            changed = True

        # keep local ops mutations on the ability
        a["ops"] = [dict(o) for o in ops if isinstance(o, dict) and o.get("op")]

    # --- inject missing abilities ---
    # Restore EB04-044 replace_leave if text has it but ops missing
    if re.search(
        r"would be removed from the field.{0,80}trash 1 card from your hand instead|"
        r"即將離開場上時，可以替換成廢棄1[張张]自己的手牌|"
        r"即将离开场上时，可以替换成废弃1[张張]自己的手牌",
        blob,
        re.I,
    ) and not any(any(o.get("op") == "replace_leave" for o in (a.get("ops") or [])) for a in new_abs):
        new_abs.insert(
            0,
            normalize_ability(
                {
                    "timing": "your_turn",
                    "summary": "Trash 1 hand instead of leaving",
                    "ops": [
                        {
                            "op": "replace_leave",
                            "trigger": "opp_remove",
                            "target": "self",
                            "cost": "trash_hand",
                            "once": True,
                            "optional": True,
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.9,
                    "once": True,
                    "require_leader_trait": "Navy",
                }
            ),
        )
        changed = True

    # Life-damage trash (OP03-047/051/041 family)
    m_life = LIFE_DMG_TRASH_RE.search(blob)
    if m_life:
        n = int(next(g for g in m_life.groups() if g))
        existing = next(
            (
                a
                for a in new_abs
                if a.get("timing") == "when_attacking"
                and any(o.get("op") == "trash_deck_top" for o in (a.get("ops") or []))
                and (a.get("on_life_damage") or a.get("require_don_attached_gte"))
            ),
            None,
        )
        if existing:
            for o in existing.get("ops") or []:
                if o.get("op") == "trash_deck_top" and int(o.get("count") or 0) != n:
                    o["count"] = n
                    o["optional"] = True
                    changed = True
            if not existing.get("on_life_damage"):
                existing["on_life_damage"] = True
                changed = True
            if int(existing.get("require_don_attached_gte") or 0) < 1:
                existing["require_don_attached_gte"] = 1
                changed = True
            # drop bogus deal_life_damage
            before = len(existing.get("ops") or [])
            existing["ops"] = [o for o in (existing.get("ops") or []) if o.get("op") != "deal_life_damage"]
            if len(existing.get("ops") or []) != before:
                changed = True
        else:
            new_abs.append(
                normalize_ability(
                    {
                        "timing": "when_attacking",
                        "summary": f"DON!!x1: when attack deals Life damage, may trash top {n}",
                        "ops": [{"op": "trash_deck_top", "count": n, "optional": True}],
                        "status": "compiled",
                        "confidence": 0.9,
                        "require_don_attached_gte": 1,
                        "on_life_damage": True,
                    }
                )
            )
            changed = True

    # EB04-044: opp KO draw
    if OPP_KO_DRAW_RE.search(blob) and not any(
        any(o.get("op") == "draw" and o.get("on_opp_ko") for o in (a.get("ops") or []))
        or (a.get("on_opp_ko") and any(o.get("op") == "draw" for o in (a.get("ops") or [])))
        for a in new_abs
    ):
        new_abs.append(
            normalize_ability(
                {
                    "timing": "your_turn",
                    "summary": "When opponent's Character is K.O.'d, draw 1",
                    "ops": [{"op": "draw", "count": 1, "on_opp_ko": True}],
                    "status": "compiled",
                    "confidence": 0.95,
                    "once": True,
                    "on_opp_ko": True,
                }
            )
        )
        changed = True

    # OP02-026: play no-base-effect → active_don
    if PLAY_NO_BASE_RE.search(blob) and (
        not new_abs
        or not any(any(o.get("op") == "active_don" for o in (a.get("ops") or [])) for a in new_abs)
    ):
        new_abs = [
            a
            for a in new_abs
            if not (a.get("timing") == "on_play" and any(o.get("op") == "choose_target" for o in (a.get("ops") or [])))
        ]
        new_abs.append(
            normalize_ability(
                {
                    "timing": "your_turn",
                    "summary": "Once: when you play a no-base-effect Character from hand, if chars≤3, active up to 2 DON!!",
                    "ops": [{"op": "active_don", "count": 2}],
                    "status": "compiled",
                    "confidence": 0.9,
                    "once": True,
                    "require_chars_lte": 3,
                    "require_play_no_base_effect_from_hand": True,
                }
            )
        )
        changed = True

    # Mark OP01-061-style gain_don with on_opp_ko when text matches
    if re.search(r"When your opponent's Character is K\.O\.?'?d,\s*add up to 1 DON!!|對手的角色卡遭到KO時.{0,20}追加|对手的角色卡遭到KO时.{0,20}追加", blob, re.I):
        for a in new_abs:
            if a.get("timing") == "your_turn" and any(o.get("op") == "gain_don" for o in (a.get("ops") or [])):
                if not a.get("on_opp_ko"):
                    a["on_opp_ko"] = True
                    for o in a.get("ops") or []:
                        if o.get("op") == "gain_don":
                            o["on_opp_ko"] = True
                    changed = True

    if not changed:
        return None
    cleaned = [a for a in (normalize_ability(x) for x in new_abs) if a]
    if not cleaned:
        return None
    return normalize_card_entry(cid, {"version": 1, "abilities": cleaned})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)

    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    q = json.loads((ROOT / "meta" / "effect_problem_queue.json").read_text())
    open_ids = [it["id"] for it in q["items"] if it.get("status") == "open"]
    # seed high-value known IDs even if queue status drifted
    for cid in [
        "EB04-044",
        "OP02-026",
        "OP02-031",
        "OP02-049",
        "OP02-052",
        "OP02-101",
        "OP03-012",
        "OP03-041",
        "OP03-047",
        "OP03-051",
        "OP03-108",
        "OP04-020",
        "OP05-088",
        "OP06-062",
        "OP08-073",
        "OP08-076",
        "OP10-077",
        "EB03-055",
        "ST03-007",
        "OP01-004",
        "OP01-062",
    ]:
        if cid not in open_ids:
            open_ids.append(cid)
    # also scan catalog for life-damage / play-no-base patterns
    for cid, info in catalog.items():
        blob = effect_blob(info)
        if LIFE_DMG_TRASH_RE.search(blob) or PLAY_NO_BASE_RE.search(blob) or OPP_KO_DRAW_RE.search(blob):
            if cid not in open_ids:
                open_ids.append(cid)
    if args.limit:
        open_ids = open_ids[: args.limit]

    lib_path, ovr_path = library_paths()
    raw = json.loads(lib_path.read_text())
    cards = raw["cards"]
    ovr = json.loads(ovr_path.read_text())
    overrides = ovr.get("cards") or {}

    fixed: list[str] = []
    for cid in open_ids:
        info = catalog.get(cid) or {}
        entry = cards.get(cid) or get_card_entry(cid) or {"card_id": cid, "version": 1, "abilities": []}
        out = fix_card(cid, info, entry)
        if not out:
            continue
        cards[cid] = out
        overrides[cid] = out
        fixed.append(cid)

    import time as _time

    raw["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    lib_path.write_text(json.dumps(raw, ensure_ascii=False, separators=(",", ":")))
    ovr["cards"] = overrides
    ovr["generated_at"] = raw["generated_at"]
    ovr_path.write_text(json.dumps(ovr, ensure_ascii=False, separators=(",", ":")))
    reload_effect_library(force=True)

    OUT_IDS.parent.mkdir(parents=True, exist_ok=True)
    OUT_IDS.write_text("\n".join(fixed) + ("\n" if fixed else ""))
    print(json.dumps({"fixed": len(fixed), "ids_file": str(OUT_IDS)}, ensure_ascii=False))
    for cid in [
        "EB04-044",
        "OP02-026",
        "OP02-031",
        "OP02-049",
        "OP02-052",
        "OP03-012",
        "OP03-047",
        "OP03-051",
        "OP03-108",
        "OP04-020",
        "OP06-062",
        "OP08-076",
        "OP10-077",
        "EB03-055",
        "OP02-101",
        "ST03-007",
        "OP08-073",
        "OP05-088",
        "OP01-004",
        "OP01-062",
    ]:
        if cid in fixed:
            print(cid, json.dumps(get_card_entry(cid), ensure_ascii=False)[:220])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
