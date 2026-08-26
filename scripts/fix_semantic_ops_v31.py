#!/usr/bin/env python3
"""Deterministic semantic fixes v31: cannot_be_removed, exclude_name, empty/choose_one/grant_cost.

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
from battle.effects import _parse_exclude_name, effect_blob  # noqa: E402

OUT_IDS = ROOT / "meta" / "logs" / "ops_v31_fixed_ids.txt"


def _na(raw: dict[str, Any]) -> dict[str, Any] | None:
    return normalize_ability(raw)


def _rebuild(cid: str, abilities: list[dict[str, Any]]) -> dict[str, Any]:
    cleaned = [a for a in (_na(x) for x in abilities) if a]
    return normalize_card_entry(cid, {"version": 1, "abilities": cleaned})


def _protect_pair(
    *,
    summary: str,
    gates: dict[str, Any],
    target_kind: str = "self",
    extra_ops: list[dict[str, Any]] | None = None,
    all_own: bool = False,
    trait: str = "",
    color: str = "",
    exclude_name: str = "",
    cost_lte: int | None = None,
    opp: bool = False,
) -> list[dict[str, Any]]:
    op: dict[str, Any] = {
        "op": "cannot_be_removed",
        "target_kind": "opponent_character" if opp else ("own_character" if all_own else target_kind),
        "optional": False,
    }
    if all_own or opp:
        op["all"] = True
    if trait:
        op["trait_contains"] = trait
    if color:
        op["color"] = color
    if exclude_name:
        op["exclude_name"] = exclude_name
    if cost_lte is not None:
        op["cost_lte"] = cost_lte
    ops = [op, *(extra_ops or [])]
    out = []
    for timing in ("your_turn", "opponent_turn"):
        ab: dict[str, Any] = {
            "timing": timing,
            "summary": summary,
            "ops": [dict(x) for x in ops],
            "status": "compiled",
            "confidence": 0.95,
        }
        ab.update(gates)
        out.append(ab)
    return out


REMOVED_FIELD = re.compile(
    r"cannot be removed from the field by your opponent'?s? effects|"
    r"不會因對手的效果而離開場上|不会因对手的效果而离开场上|"
    r"不會因對手的效果離場|不会因对手的效果离场",
    re.I,
)
SCIENTIST_PROTECT = re.compile(
    r"yellow \{Scientist\}.{0,40}cannot be removed|"
    r"黃色擁有《科學家》.{0,40}不會因對手|"
    r"黄色拥有《科学家》.{0,40}不会因对手",
    re.I | re.S,
)
TRASH7_PROTECT = re.compile(
    r"7 or more cards in your trash.{0,80}cannot be removed|"
    r"廢棄區有7[張张]以上.{0,80}不會因對手|"
    r"废弃区有7[张張]以上.{0,80}不会因对手",
    re.I | re.S,
)
TRASH7_RUSH = re.compile(
    r"cannot be removed from the field by your opponent'?s? effects and gains \[Rush\]|"
    r"不會因對手的效果而離開場上，並獲得【速攻】|"
    r"不会因对手的效果而离开场上，并获得【速攻】",
    re.I,
)
TRASH7_BLOCKER = re.compile(
    r"cannot be removed from the field by your opponent'?s? effects and gains \[Blocker\]|"
    r"不會因對手的效果而離開場上，並獲得【防禦】|"
    r"不会因对手的效果而离开场上，并获得【防御】",
    re.I,
)
ALL_DON_RESTED = re.compile(
    r"If all of your DON!! cards are rested.{0,40}cannot be removed|"
    r"若自己的咚!!?卡全部在休息狀態時.{0,40}不會因對手|"
    r"若自己的咚!!?卡全部在休息状态时.{0,40}不会因对手",
    re.I | re.S,
)
OPP_PROTECT_FROM_YOU = re.compile(
    r"All of your opponent'?s Characters cannot be removed from the field by your effects|"
    r"對手的角色卡全數不會因自己的效果而離開場上|"
    r"对手的角色卡全数不会因自己的效果而离开场上",
    re.I,
)
DON_LTE_PROTECT = re.compile(
    r"6 or less DON!! cards on your field.{0,60}cannot be removed|"
    r"咚!!?卡在6[張张]以下時.{0,40}不會因對手|"
    r"咚!!?卡在6[张張]以下时.{0,40}不会因对手",
    re.I | re.S,
)
CHOOSE_KW3 = re.compile(
    r"gains \[Double Attack\], \[Banish\] or \[Blocker\]|"
    r"獲得【雙重攻擊】、【消失】或【防禦】|"
    r"获得【双重攻击】、【消失】或【防御】",
    re.I,
)
GRANT_COST_SELF = re.compile(
    r"^This Character gains \+(\d+) cost\.|"
    r"^這張角色卡的費用\+(\d+)。|"
    r"^这张角色卡的费用\+(\d+)。",
    re.I | re.M,
)
GRANT_COST_GATED = re.compile(
    r"2 or more Characters with a base cost of 5 or more.{0,40}gains \+1 cost|"
    r"2[張张]以上自己原本費用5以上的角色卡時.{0,40}費用\+1|"
    r"2[张張]以上自己原本费用5以上的角色卡时.{0,40}费用\+1",
    re.I | re.S,
)
TURN_START_SEARCH8 = re.compile(
    r"start of your turn.{0,40}8 or more DON!!.{0,80}look at 5|"
    r"自己的回合開始時.{0,40}咚!!?卡有8[張张]以上.{0,80}查看5|"
    r"自己的回合开始时.{0,40}咚!!?卡有8[张張]以上.{0,80}查看5",
    re.I | re.S,
)
MINKS_ACTIVE = re.compile(
    r"If this Character is active.{0,40}\{Minks\}.{0,80}other than \[Pekoms\]|"
    r"若這張角色卡為活動狀態時.{0,40}《純毛族》.{0,80}除了「波哥姆斯」|"
    r"若这张角色卡为活动状态时.{0,40}《纯毛族》.{0,80}除了「波哥姆斯」",
    re.I | re.S,
)
COUNTER_TOTAL2 = re.compile(
    r"Give up to a total of 2 of your opponent'?s Leader or Character cards −?3000|"
    r"合計最多2[張张]對手的領航卡或角色卡.{0,20}力量[值]?−?3000|"
    r"合计最多2[张張]对手的领航卡或角色卡.{0,20}力量[值]?−?3000",
    re.I | re.S,
)
END_TURN_SUPERNOVA = re.compile(
    r"\{Supernovas\} type Characters with a cost of 3 to 8 as active.{0,80}gains \[Blocker\] until|"
    r"《超新星》.{0,40}費用3至8.{0,80}獲得【防禦】|"
    r"《超新星》.{0,40}费用3至8.{0,80}获得【防御】",
    re.I | re.S,
)
P090 = re.compile(
    r"other than \[Charlotte Smoothie\].{0,40}from your hand|"
    r"除了「夏洛特・斯姆吉」以外.{0,40}登場|"
    r"除了「夏洛特・斯姆吉」以外.{0,40}登场",
    re.I | re.S,
)


def _fix_inverted_exclude(entry: dict[str, Any], blob: str) -> dict[str, Any] | None:
    excl = _parse_exclude_name(blob)
    if not excl:
        return None
    changed = False
    abilities = []
    for a in entry.get("abilities") or []:
        ab = dict(a)
        ops = []
        for o in ab.get("ops") or []:
            op = dict(o)
            nc = str(op.get("name_contains") or "").strip()
            if nc and (nc.lower() == excl.lower() or excl.lower() in nc.lower() or nc.lower() in excl.lower()):
                op.pop("name_contains", None)
                op["exclude_name"] = excl
                changed = True
            elif not op.get("exclude_name") and excl and op.get("op") in {
                "grant_keyword",
                "play_from_hand",
                "cannot_be_ko",
                "cannot_be_removed",
                "buff",
                "set_character_active",
            }:
                # Paper has exclude; attach when op selects own/hand characters.
                if op.get("op") in {"grant_keyword", "play_from_hand"} and (
                    op.get("trait_contains") or op.get("target_kind") in {"own_character", "own_characters"} or op.get("color")
                ):
                    op["exclude_name"] = excl
                    changed = True
            ops.append(op)
        ab["ops"] = ops
        abilities.append(ab)
    if not changed:
        return None
    return _rebuild(str(entry.get("card_id") or ""), abilities)


def fix_card(cid: str, info: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any] | None:
    blob = effect_blob(info)
    base = re.sub(r"-P\d+$", "", cid)

    if SCIENTIST_PROTECT.search(blob):
        abs_ = _protect_pair(
            summary="Life≤2: yellow Scientists cannot be removed by opp effects",
            gates={"require_life_lte": 2},
            all_own=True,
            trait="Scientist",
            color="yellow",
        )
        if re.search(r"\[DON!! x1\].{0,40}\[Blocker\]|【咚‼?×1】.{0,40}【防禦】|【咚‼?×1】.{0,40}【防御】", blob, re.I | re.S):
            for timing in ("your_turn", "opponent_turn"):
                abs_.append(
                    {
                        "timing": timing,
                        "summary": "DON!!x1: this Character gains Blocker",
                        "ops": [{"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"}],
                        "status": "compiled",
                        "confidence": 0.95,
                        "require_don_attached_gte": 1,
                    }
                )
        return _rebuild(cid, abs_)

    if ALL_DON_RESTED.search(blob):
        return _rebuild(
            cid,
            _protect_pair(
                summary="All DON!! rested: cannot be removed by opp effects",
                gates={"require_all_don_rested": True},
            ),
        )

    if OPP_PROTECT_FROM_YOU.search(blob):
        abs_ = _protect_pair(
            summary="Opponent Characters cannot be removed by your effects",
            gates={},
            opp=True,
        )
        # Keep activate_main body if present in current entry.
        for a in entry.get("abilities") or []:
            if a.get("timing") == "activate_main" and (a.get("ops") or []):
                abs_.append(dict(a))
                break
        else:
            # Minimal activate from paper for OP14-079 family when missing.
            if re.search(r"\[Activate: Main\].{0,40}Baroque Works|【啟動主要】.{0,40}B・W|【启动主要】.{0,40}B・W", blob, re.I | re.S):
                abs_.append(
                    {
                        "timing": "activate_main",
                        "summary": "KO 1 own B・W: opp char cost −10 this turn, then trash deck top",
                        "ops": [
                            {
                                "op": "ko",
                                "target_kind": "own_character",
                                "trait_contains": "B・W",
                                "optional": True,
                                "as_cost": True,
                            },
                            {
                                "op": "reduce_cost",
                                "amount": -10,
                                "target_kind": "opponent_character",
                                "optional": True,
                                "duration": "turn",
                            },
                            {"op": "trash_deck_top", "count": 1, "owner": "opponent", "optional": False},
                        ],
                        "status": "compiled",
                        "confidence": 0.9,
                        "once": True,
                    }
                )
        return _rebuild(cid, abs_)

    if DON_LTE_PROTECT.search(blob):
        abs_ = _protect_pair(
            summary="DON!!≤6: cannot be removed +2000",
            gates={"require_don_field_lte": 6},
            extra_ops=[{"op": "buff_self", "amount": 2000}],
        )
        if re.search(r"\[Activate: Main\].{0,40}DON!! −1|【啟動主要】.{0,40}咚‼?−1|【启动主要】.{0,40}咚‼?−1", blob, re.I | re.S):
            abs_.append(
                {
                    "timing": "activate_main",
                    "summary": "DON!!−1: gain Blocker until opp turn end; trash 1 hand",
                    "ops": [
                        {"op": "return_don", "count": 1, "as_cost": True, "optional": True},
                        {
                            "op": "grant_keyword",
                            "keyword": "blocker",
                            "target_kind": "self",
                            "duration": "until_opp_turn_end",
                        },
                        {"op": "trash_hand", "count": 1, "optional": False},
                    ],
                    "status": "compiled",
                    "confidence": 0.9,
                }
            )
        return _rebuild(cid, abs_)

    if TRASH7_RUSH.search(blob) or (TRASH7_PROTECT.search(blob) and re.search(r"\[Rush\]|【速攻】", blob)):
        abs_ = _protect_pair(
            summary="Trash≥7: cannot be removed + Rush",
            gates={"require_trash_gte": 7},
            extra_ops=[{"op": "grant_keyword", "keyword": "rush", "target_kind": "self", "duration": "permanent"}],
        )
        if re.search(r"\[When Attacking\].{0,80}10 or more|【攻擊時】.{0,80}10[張张]以上|【攻击时】.{0,80}10[张張]以上", blob, re.I | re.S):
            abs_.append(
                {
                    "timing": "when_attacking",
                    "summary": "Trash≥10: give up to 1 opp Character −2000",
                    "ops": [
                        {
                            "op": "buff",
                            "amount": -2000,
                            "target_kind": "opponent_character",
                            "optional": True,
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.9,
                    "require_trash_gte": 10,
                }
            )
        return _rebuild(cid, abs_)

    if TRASH7_BLOCKER.search(blob):
        abs_ = _protect_pair(
            summary="Trash≥7: cannot be removed + Blocker",
            gates={"require_trash_gte": 7},
            extra_ops=[{"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"}],
        )
        if re.search(r"\[On Play\].{0,80}trash 1 card from your hand|【登場時】.{0,80}廢棄1[張张]自己的手牌|【登场时】.{0,80}废弃1", blob, re.I | re.S):
            abs_.append(
                {
                    "timing": "on_play",
                    "summary": "Trash 1 hand: KO opp base cost≤5",
                    "ops": [
                        {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                        {"op": "ko", "target_kind": "opponent_character", "optional": True, "base_cost_lte": 5},
                    ],
                    "status": "compiled",
                    "confidence": 0.9,
                }
            )
        return _rebuild(cid, abs_)

    if TRASH7_PROTECT.search(blob):
        abs_ = _protect_pair(
            summary="Trash≥7: cannot be removed by opp effects",
            gates={"require_trash_gte": 7},
        )
        if re.search(r"\[Your Turn\].{0,80}Five Elder|【自己的回合】.{0,80}五老星|【自己的回合】.{0,80}五老星", blob, re.I | re.S):
            abs_.append(
                {
                    "timing": "your_turn",
                    "summary": "Trash≥10: Five Elders base power → 7000",
                    "ops": [
                        {
                            "op": "set_base_power",
                            "amount": 7000,
                            "target_kind": "own_character",
                            "all": True,
                            "trait_contains": "Five Elders",
                            "optional": False,
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.9,
                    "require_trash_gte": 10,
                }
            )
        return _rebuild(cid, abs_)

    if CHOOSE_KW3.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "activate_main",
                    "summary": "Once: choose Double Attack / Banish / Blocker until opp turn end",
                    "ops": [
                        {
                            "op": "choose_one",
                            "chooser": "self",
                            "options": [
                                {
                                    "id": "da",
                                    "label": "Double Attack",
                                    "ops": [
                                        {
                                            "op": "grant_keyword",
                                            "keyword": "double_attack",
                                            "target_kind": "self",
                                            "duration": "until_opp_turn_end",
                                        }
                                    ],
                                },
                                {
                                    "id": "banish",
                                    "label": "Banish",
                                    "ops": [
                                        {
                                            "op": "grant_keyword",
                                            "keyword": "banish",
                                            "target_kind": "self",
                                            "duration": "until_opp_turn_end",
                                        }
                                    ],
                                },
                                {
                                    "id": "blocker",
                                    "label": "Blocker",
                                    "ops": [
                                        {
                                            "op": "grant_keyword",
                                            "keyword": "blocker",
                                            "target_kind": "self",
                                            "duration": "until_opp_turn_end",
                                        }
                                    ],
                                },
                            ],
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                    "once": True,
                    "require_leader_trait": "Blackbeard Pirates",
                }
            ],
        )

    if TURN_START_SEARCH8.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "turn_start",
                    "summary": "DON!!≥8: look top 5, add Straw Hat Crew, rest top or bottom",
                    "ops": [
                        {
                            "op": "search_deck",
                            "trait_contains": "Straw Hat Crew",
                            "top_n": 5,
                            "max_add": 1,
                            "order_bottom": False,
                            "destination": "hand",
                            "optional": True,
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.9,
                    "require_don_field_gte": 8,
                }
            ],
        )

    if GRANT_COST_GATED.search(blob):
        abs_ = [
            {
                "timing": "your_turn",
                "summary": "If ≥2 own base-cost≥5 Characters: this Character +1 cost",
                "ops": [{"op": "grant_cost", "amount": 1, "target_kind": "self"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_chars_base_cost_gte": 5,
                "require_chars_base_cost_count_gte": 2,
            },
            {
                "timing": "opponent_turn",
                "summary": "If ≥2 own base-cost≥5 Characters: this Character +1 cost",
                "ops": [{"op": "grant_cost", "amount": 1, "target_kind": "self"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_chars_base_cost_gte": 5,
                "require_chars_base_cost_count_gte": 2,
            },
        ]
        if re.search(r"\[On Play\].{0,80}base cost of 1 or less|【登場時】.{0,80}原本費用1以下|【登场时】.{0,80}原本费用1以下", blob, re.I | re.S):
            abs_.append(
                {
                    "timing": "on_play",
                    "summary": "Place up to 1 opp base cost≤1 at deck bottom",
                    "ops": [
                        {
                            "op": "return_to_bottom",
                            "target_kind": "opponent_character",
                            "base_cost_lte": 1,
                            "optional": True,
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.9,
                }
            )
        return _rebuild(cid, abs_)

    m_gc = GRANT_COST_SELF.search(blob)
    if m_gc and re.search(r"\[Activate: Main\].{0,40}rest this Character|【啟動主要】.{0,40}置為休息|【启动主要】.{0,40}置为休息", blob, re.I | re.S):
        amt = int(next(g for g in m_gc.groups() if g))
        return _rebuild(
            cid,
            [
                {
                    "timing": "your_turn",
                    "summary": f"This Character gains +{amt} cost",
                    "ops": [{"op": "grant_cost", "amount": amt, "target_kind": "self"}],
                    "status": "compiled",
                    "confidence": 0.95,
                },
                {
                    "timing": "opponent_turn",
                    "summary": f"This Character gains +{amt} cost",
                    "ops": [{"op": "grant_cost", "amount": amt, "target_kind": "self"}],
                    "status": "compiled",
                    "confidence": 0.95,
                },
                {
                    "timing": "activate_main",
                    "summary": "Rest this Character: draw 1, trash 1, KO opp cost≤3",
                    "ops": [
                        {"op": "draw", "count": 1, "optional": False},
                        {"op": "trash_hand", "count": 1, "optional": False},
                        {
                            "op": "ko",
                            "target_kind": "opponent_character",
                            "cost_lte": 3,
                            "optional": True,
                        },
                    ],
                    "status": "compiled",
                    "confidence": 0.9,
                    "rest_self": True,
                },
            ],
        )

    if MINKS_ACTIVE.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "your_turn",
                    "summary": "While active: Minks cost≤3 other than Pekoms cannot be K.O.'d by effects",
                    "ops": [
                        {
                            "op": "cannot_be_ko",
                            "target_kind": "own_character",
                            "all": True,
                            "trait_contains": "Minks",
                            "exclude_name": "Pekoms",
                            "cost_lte": 3,
                            "optional": False,
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_source_active": True,
                },
                {
                    "timing": "opponent_turn",
                    "summary": "While active: Minks cost≤3 other than Pekoms cannot be K.O.'d by effects",
                    "ops": [
                        {
                            "op": "cannot_be_ko",
                            "target_kind": "own_character",
                            "all": True,
                            "trait_contains": "Minks",
                            "exclude_name": "Pekoms",
                            "cost_lte": 3,
                            "optional": False,
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_source_active": True,
                },
            ],
        )

    if COUNTER_TOTAL2.search(blob) and re.search(r"\[Counter\]|【反擊】|【反击】", blob, re.I):
        return _rebuild(
            cid,
            [
                {
                    "timing": "counter_event",
                    "summary": "Counter DON!!−1: −3000 to up to 2 opp Leader/Characters",
                    "ops": [
                        {"op": "return_don", "count": 1, "as_cost": True, "optional": True},
                        {
                            "op": "buff",
                            "amount": -3000,
                            "target_kind": "opponent_leader_or_character",
                            "optional": True,
                            "summary": "−3000 (1/2)",
                        },
                        {
                            "op": "buff",
                            "amount": -3000,
                            "target_kind": "opponent_leader_or_character",
                            "optional": True,
                            "summary": "−3000 (2/2)",
                        },
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                },
                {
                    "timing": "trigger",
                    "summary": "Trigger opp DON!!≥6: opp returns 1",
                    "ops": [{"op": "return_don", "count": 1, "owner": "opponent"}],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_opp_don_field_gte": 6,
                },
            ],
        )

    if END_TURN_SUPERNOVA.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "end_of_your_turn",
                    "summary": "Flip life face-up: active Supernovas cost 3-8; Blocker until opp turn end",
                    "ops": [
                        {"op": "flip_life", "face": "up", "position": "top", "optional": True, "as_cost": True},
                        {
                            "op": "set_character_active",
                            "count": 1,
                            "target_kind": "own_character",
                            "trait_contains": "Supernovas",
                            "optional": True,
                            "cost_gte": 3,
                            "cost_lte": 8,
                        },
                        {
                            "op": "grant_keyword",
                            "keyword": "blocker",
                            "target_kind": "own_character",
                            "trait_contains": "Supernovas",
                            "duration": "until_opp_turn_end",
                            "optional": True,
                            "cost_gte": 3,
                            "cost_lte": 8,
                        },
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                }
            ],
        )

    if P090.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "on_ko",
                    "summary": "Opp turn On K.O.: DON!!−1 play Big Mom Pirates cost≤opp DON except Smoothie",
                    "ops": [
                        {"op": "return_don", "count": 1, "as_cost": True, "optional": True},
                        {
                            "op": "play_from_hand",
                            "count": 1,
                            "card_type": "character",
                            "trait_contains": "Big Mom Pirates",
                            "exclude_name": "Charlotte Smoothie",
                            "cost_lte_opp_don_field": True,
                            "optional": True,
                        },
                    ],
                    "status": "compiled",
                    "confidence": 0.9,
                    "require_opponent_turn": True,
                }
            ],
        )

    # Generic: invert name_contains that should be exclude_name.
    fixed = _fix_inverted_exclude({"card_id": cid, "abilities": list(entry.get("abilities") or [])}, blob)
    if fixed:
        return fixed

    # P-variants: copy cleaner base when available.
    if cid != base:
        be = get_card_entry(base)
        if be and len(be.get("abilities") or []) >= 1:
            if any(
                r.search(blob)
                for r in (
                    SCIENTIST_PROTECT,
                    TRASH7_PROTECT,
                    ALL_DON_RESTED,
                    COUNTER_TOTAL2,
                    END_TURN_SUPERNOVA,
                )
            ):
                return _rebuild(cid, [dict(a) for a in be["abilities"]])

    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)

    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    q = json.loads((ROOT / "meta" / "effect_problem_queue.json").read_text())
    open_ids = [it["id"] for it in q["items"] if it.get("status") == "open"]
    seeds = [
        "EB04-057",
        "OP13-080",
        "OP13-084",
        "OP13-091",
        "OP02-027",
        "OP14-079",
        "OP15-060",
        "OP12-012",
        "OP12-007",
        "ST21-015",
        "P-090",
        "OP11-040",
        "OP09-084",
        "OP08-084",
        "OP12-042",
        "OP02-089",
        "OP02-089-P1",
        "OP02-089-P2",
        "OP02-089-P3",
        "OP10-099",
        "OP08-029",
        "OP14-091",
        "ST31-001",
    ]
    for cid in seeds:
        if cid not in open_ids:
            open_ids.append(cid)
    for cid, info in catalog.items():
        blob = effect_blob(info)
        if any(
            r.search(blob)
            for r in (
                SCIENTIST_PROTECT,
                TRASH7_PROTECT,
                TRASH7_RUSH,
                TRASH7_BLOCKER,
                ALL_DON_RESTED,
                OPP_PROTECT_FROM_YOU,
                DON_LTE_PROTECT,
                CHOOSE_KW3,
                TURN_START_SEARCH8,
                GRANT_COST_GATED,
                MINKS_ACTIVE,
                COUNTER_TOTAL2,
                END_TURN_SUPERNOVA,
                P090,
            )
        ) or _parse_exclude_name(blob):
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
        prev = cards.get(cid) or entry
        if json.dumps(prev.get("abilities"), sort_keys=True, ensure_ascii=False) == json.dumps(
            out.get("abilities"), sort_keys=True, ensure_ascii=False
        ):
            continue
        cards[cid] = out
        overrides[cid] = out
        fixed.append(cid)

    raw["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    lib_path.write_text(json.dumps(raw, ensure_ascii=False, separators=(",", ":")))
    ovr["cards"] = overrides
    ovr["generated_at"] = raw["generated_at"]
    ovr_path.write_text(json.dumps(ovr, ensure_ascii=False, separators=(",", ":")))
    reload_effect_library(force=True)

    OUT_IDS.parent.mkdir(parents=True, exist_ok=True)
    OUT_IDS.write_text("\n".join(fixed) + ("\n" if fixed else ""))
    print(json.dumps({"fixed": len(fixed), "ids_file": str(OUT_IDS)}, ensure_ascii=False))
    for cid in seeds:
        if cid in fixed:
            e = get_card_entry(cid)
            print(
                cid,
                [(a.get("timing"), [o.get("op") for o in a.get("ops") or []]) for a in (e or {}).get("abilities") or []],
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
