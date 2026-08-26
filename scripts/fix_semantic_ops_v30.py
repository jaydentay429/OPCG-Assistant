#!/usr/bin/env python3
"""Deterministic semantic fixes v30: gate bleed, durations, grant_cost, continuous auras.

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

OUT_IDS = ROOT / "meta" / "logs" / "ops_v30_fixed_ids.txt"


def _na(raw: dict[str, Any]) -> dict[str, Any] | None:
    return normalize_ability(raw)


def _rebuild(cid: str, abilities: list[dict[str, Any]]) -> dict[str, Any]:
    cleaned = [a for a in (_na(x) for x in abilities) if a]
    return normalize_card_entry(cid, {"version": 1, "abilities": cleaned})


def fix_card(cid: str, info: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any] | None:
    blob = effect_blob(info)
    base = re.sub(r"-P\d+$", "", cid)
    # Prefer copying a cleaner base compile for parallel arts when texts match.
    if cid != base:
        be = get_card_entry(base)
        bb = effect_blob(info)  # same catalog entry content for P variants usually
        if be and len(be.get("abilities") or []) >= 1:
            # copy if base looks more complete for shared patterns
            if OPP_DON_MAIN_TRIG.search(blob) or NEXT_COST.search(blob) or SWORD_NAVY.search(blob) or DRAW_UNTIL.search(blob):
                out = _rebuild(cid, [dict(a) for a in be["abilities"]])
                return out

    # --- card-specific / pattern rebuilds ---
    if OPP_DON_MAIN_TRIG.search(blob) and re.search(r"\[Main\].{0,80}Add up to 1 DON!!|【主要】.{0,40}追加最多1", blob, re.I | re.S):
        # OP02-090/091 family: main gain_don ungated; trigger opp don>=N return
        m = OPP_DON_MAIN_TRIG.search(blob)
        n = int(next(g for g in m.groups() if g)) if m else 6
        return _rebuild(
            cid,
            [
                {
                    "timing": "main_start",
                    "summary": "Main: add up to 1 active DON!!",
                    "ops": [{"op": "gain_don", "count": 1}],
                    "status": "compiled",
                    "confidence": 0.95,
                },
                {
                    "timing": "trigger",
                    "summary": f"Trigger: if opp DON!!>={n}, opp returns 1 DON!!",
                    "ops": [{"op": "return_don", "count": 1, "owner": "opponent"}],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_opp_don_field_gte": n,
                },
            ],
        )

    if DRESSROSA_RUSH.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "your_turn",
                    "summary": "Dressrosa Leader: Dressrosa chars can attack chars the turn played",
                    "ops": [
                        {
                            "op": "allow_attack_active",
                            "count": 5,
                            "target_kind": "own_character",
                            "trait_contains": "Dressrosa",
                            "optional": False,
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_leader_trait": "Dressrosa",
                }
            ],
        )

    if GERMA_BLOCKER_DON.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "your_turn",
                    "summary": "GERMA Leader + DON deficit ≥2: gain Blocker",
                    "ops": [{"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"}],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_leader_trait": "GERMA 66",
                    "require_don_field_deficit_gte": 2,
                },
                {
                    "timing": "opponent_turn",
                    "summary": "GERMA Leader + DON deficit ≥2: gain Blocker",
                    "ops": [{"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"}],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_leader_trait": "GERMA 66",
                    "require_don_field_deficit_gte": 2,
                },
            ],
        )

    if SCIENTIST_PROTECT.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "your_turn",
                    "summary": "Life≤2: yellow Scientists cannot be removed by opp effects",
                    "ops": [
                        {
                            "op": "cannot_be_ko",
                            "target_kind": "own_character",
                            "all": True,
                            "trait_contains": "Scientist",
                            "color": "yellow",
                            "optional": False,
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_life_lte": 2,
                },
                {
                    "timing": "opponent_turn",
                    "summary": "Life≤2: yellow Scientists cannot be removed by opp effects",
                    "ops": [
                        {
                            "op": "cannot_be_ko",
                            "target_kind": "own_character",
                            "all": True,
                            "trait_contains": "Scientist",
                            "color": "yellow",
                            "optional": False,
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_life_lte": 2,
                },
                {
                    "timing": "your_turn",
                    "summary": "DON!!x1: this Character gains Blocker",
                    "ops": [{"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"}],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_don_attached_gte": 1,
                },
                {
                    "timing": "opponent_turn",
                    "summary": "DON!!x1: this Character gains Blocker",
                    "ops": [{"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"}],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_don_attached_gte": 1,
                },
            ],
        )

    if TRIGGER_BLOCKER_HAND.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "trigger",
                    "summary": "Egghead char gains Blocker this turn, then add this to hand",
                    "ops": [
                        {
                            "op": "grant_keyword",
                            "keyword": "blocker",
                            "target_kind": "own_character",
                            "trait_contains": "Egghead",
                            "duration": "turn",
                            "optional": True,
                            "count": 1,
                        },
                        {"op": "return_to_hand", "target_kind": "self", "optional": False, "self_card": True},
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                }
            ],
        )

    if END_TURN_SUPERNOVA.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "end_of_your_turn",
                    "summary": "Flip life face-up: active Supernovas cost 3-8; gains Blocker until opp turn end",
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
                        },
                    ],
                    "status": "compiled",
                    "confidence": 0.9,
                }
            ],
        )

    if SHIRAHOSHI_RUSH.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "your_turn",
                    "summary": "If Leader is Shirahoshi, can attack Characters the turn played",
                    "ops": [
                        {
                            "op": "allow_attack_active",
                            "count": 1,
                            "target_kind": "self",
                            "optional": False,
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_leader_name": "Shirahoshi",
                }
            ],
        )

    if GIVEN_DON_BLOCKER.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "your_turn",
                    "summary": "If given DON!! ≥2, gain Blocker",
                    "ops": [{"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"}],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_given_don_gte": 2,
                },
                {
                    "timing": "opponent_turn",
                    "summary": "If given DON!! ≥2, gain Blocker",
                    "ops": [{"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"}],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_given_don_gte": 2,
                },
            ],
        )

    if DON_FIELD_LTE_BLOCKER.search(blob):
        m = DON_FIELD_LTE_BLOCKER.search(blob)
        n = int(next(g for g in m.groups() if g))
        return _rebuild(
            cid,
            [
                {
                    "timing": "your_turn",
                    "summary": f"If DON!! on field ≤{n}, gain Blocker",
                    "ops": [{"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"}],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_don_field_lte": n,
                },
                {
                    "timing": "opponent_turn",
                    "summary": f"If DON!! on field ≤{n}, gain Blocker",
                    "ops": [{"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"}],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_don_field_lte": n,
                },
            ],
        )

    if REVO_BLOCKER_COST.search(blob):
        abs_: list[dict[str, Any]] = [
            {
                "timing": "your_turn",
                "summary": "Revolutionary Leader: gain Blocker and +4 cost",
                "ops": [
                    {"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"},
                    {"op": "grant_cost", "amount": 4, "target_kind": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": "Revolutionary Army",
            },
            {
                "timing": "opponent_turn",
                "summary": "Revolutionary Leader: gain Blocker and +4 cost",
                "ops": [
                    {"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"},
                    {"op": "grant_cost", "amount": 4, "target_kind": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": "Revolutionary Army",
            },
        ]
        if ON_PLAY_LIFE_ATTACH.search(blob):
            abs_.insert(
                0,
                {
                    "timing": "on_play",
                    "summary": "May life_to_hand: attach 1 rested DON!!",
                    "ops": [
                        {
                            "op": "life_to_hand",
                            "count": 1,
                            "position": "top_or_bottom",
                            "optional": True,
                            "as_cost": True,
                            "owner": "self",
                        },
                        {
                            "op": "attach_don",
                            "count": 1,
                            "as_rested": True,
                            "target_kind": "own_leader_or_character",
                            "optional": True,
                        },
                    ],
                    "status": "compiled",
                    "confidence": 0.9,
                },
            )
        return _rebuild(cid, abs_)

    if BASE_COST5_BLOCKER_COST.search(blob):
        abs_ = [
            {
                "timing": "your_turn",
                "summary": "If 2+ chars base cost≥5: Blocker and +1 cost",
                "ops": [
                    {"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"},
                    {"op": "grant_cost", "amount": 1, "target_kind": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_chars_base_cost_gte": 5,
                "require_chars_base_cost_count_gte": 2,
            },
            {
                "timing": "opponent_turn",
                "summary": "If 2+ chars base cost≥5: Blocker and +1 cost",
                "ops": [
                    {"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"},
                    {"op": "grant_cost", "amount": 1, "target_kind": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_chars_base_cost_gte": 5,
                "require_chars_base_cost_count_gte": 2,
            },
        ]
        if re.search(r"gains?\s*[+＋]\s*5000\s*power|力量值\s*[+＋]\s*5000", blob, re.I):
            # opponent turn power only
            abs_.append(
                {
                    "timing": "opponent_turn",
                    "summary": "Opponent turn: +5000 if base-cost gate",
                    "ops": [{"op": "buff_self", "amount": 5000}],
                    "status": "compiled",
                    "confidence": 0.9,
                    "require_chars_base_cost_gte": 5,
                    "require_chars_base_cost_count_gte": 2,
                }
            )
        if ON_KO_BUGGY_DRAW.search(blob):
            abs_.append(
                {
                    "timing": "on_ko",
                    "summary": "If Leader Buggy and hand≤3, draw 1",
                    "ops": [{"op": "draw", "count": 1}],
                    "status": "compiled",
                    "confidence": 0.9,
                    "require_leader_name": "Buggy",
                    "require_hand_lte": 3,
                }
            )
        return _rebuild(cid, abs_)

    if CHOOSE_DRAW_OR_BLOCKER.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "main_start",
                    "summary": "Choose: draw 2 OR Dressrosa char gains Blocker until opp end",
                    "ops": [
                        {
                            "op": "choose_one",
                            "chooser": "self",
                            "options": [
                                {"id": "draw", "label": "Draw 2", "ops": [{"op": "draw", "count": 2}]},
                                {
                                    "id": "blocker",
                                    "label": "Dressrosa gains Blocker",
                                    "ops": [
                                        {
                                            "op": "grant_keyword",
                                            "keyword": "blocker",
                                            "target_kind": "own_character",
                                            "trait_contains": "Dressrosa",
                                            "duration": "until_opp_turn_end",
                                            "optional": True,
                                            "count": 1,
                                        }
                                    ],
                                },
                            ],
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                }
            ],
        )

    if KOALA_LUFFY_ROBIN.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "your_turn",
                    "summary": "If Leader Koala or Luffy: Blocker and +3 cost",
                    "ops": [
                        {"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"},
                        {"op": "grant_cost", "amount": 3, "target_kind": "self"},
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_leader_name": "Koala|Monkey.D.Luffy|Luffy|魯夫|可亞拉",
                },
                {
                    "timing": "opponent_turn",
                    "summary": "If Leader Koala or Luffy: Blocker and +3 cost",
                    "ops": [
                        {"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"},
                        {"op": "grant_cost", "amount": 3, "target_kind": "self"},
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_leader_name": "Koala|Monkey.D.Luffy|Luffy|魯夫|可亞拉",
                },
                {
                    "timing": "on_play",
                    "summary": "Trash 1 hand: if opp hand≥5, opp trashes 2",
                    "ops": [
                        {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                        {"op": "trash_hand", "count": 2, "optional": False, "owner": "opponent"},
                    ],
                    "status": "compiled",
                    "confidence": 0.9,
                    "require_opp_hand_gte": 5,
                },
            ],
        )

    if TRASH7_PROTECT_PLAY.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "your_turn",
                    "summary": "Trash≥7: cannot be removed + Blocker",
                    "ops": [
                        {"op": "cannot_be_ko", "target_kind": "self", "optional": False},
                        {"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"},
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_trash_gte": 7,
                },
                {
                    "timing": "opponent_turn",
                    "summary": "Trash≥7: cannot be removed + Blocker",
                    "ops": [
                        {"op": "cannot_be_ko", "target_kind": "self", "optional": False},
                        {"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"},
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_trash_gte": 7,
                },
                {
                    "timing": "on_play",
                    "summary": "Trash 1 hand: KO opp base cost≤5",
                    "ops": [
                        {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                        {"op": "ko", "target_kind": "opponent_character", "optional": True, "base_cost_lte": 5},
                    ],
                    "status": "compiled",
                    "confidence": 0.9,
                },
            ],
        )

    if DON1_BLOCKER_SEARCH.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "your_turn",
                    "summary": "DON!!x1: gain Blocker",
                    "ops": [{"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"}],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_don_attached_gte": 1,
                },
                {
                    "timing": "opponent_turn",
                    "summary": "DON!!x1: gain Blocker",
                    "ops": [{"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"}],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_don_attached_gte": 1,
                },
                {
                    "timing": "on_play",
                    "summary": "Look top 3: add Dressrosa, rest bottom",
                    "ops": [
                        {
                            "op": "search_deck",
                            "trait_contains": "Dressrosa",
                            "top_n": 3,
                            "max_add": 1,
                            "order_bottom": True,
                            "destination": "hand",
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.9,
                },
            ],
        )

    if ODEN_REPLACE_ACTIVE.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "your_turn",
                    "summary": "Trash 2 hand instead of leaving by opp effect",
                    "ops": [
                        {
                            "op": "replace_leave",
                            "trigger": "opp_remove",
                            "target": "self",
                            "cost": "trash_hand",
                            "trash_count": 2,
                            "once": True,
                            "optional": True,
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.9,
                    "once": True,
                },
                {
                    "timing": "activate_main",
                    "summary": "Rest 3 DON + return 1 own other char: set self active",
                    "ops": [
                        {"op": "rest_don", "count": 3, "as_cost": True},
                        {
                            "op": "return_to_hand",
                            "target_kind": "own_character",
                            "optional": True,
                            "as_cost": True,
                            "exclude_self": True,
                        },
                        {"op": "set_character_active", "count": 1, "target_kind": "self", "optional": True},
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                    "once": True,
                    "cost_don": 3,
                },
            ],
        )

    # Generic incremental fixes on existing entry
    abs_in = [dict(a) for a in (entry.get("abilities") or []) if isinstance(a, dict)]
    changed = False
    new_abs: list[dict[str, Any]] = []
    for a in abs_in:
        t = str(a.get("timing") or "")
        ops = [dict(o) for o in (a.get("ops") or []) if isinstance(o, dict)]

        # Strip mistaken main don gate when paper main has none (OP02-091 already rebuilt)
        if t == "main_start" and a.get("require_don_field_gte") and re.search(
            r"\[Main\] Add up to 1 DON!!|【主要】從咚|【主要】从咚", blob, re.I
        ):
            a.pop("require_don_field_gte", None)
            changed = True

        # Fix grant_keyword permanent → until_opp_turn_end when paper says so
        if re.search(r"until the end of your opponent'?s next|下一個對手結束|下一个对手结束|對手的下個回合結束|对手的下个回合结束", blob, re.I):
            for o in ops:
                if o.get("op") == "grant_keyword" and o.get("duration") == "permanent":
                    o["duration"] = "until_opp_turn_end"
                    changed = True

        # Drop attach_don bleed on given-don blocker cards
        if GIVEN_DON_BLOCKER.search(blob) and t in {"your_turn", "opponent_turn"}:
            before = len(ops)
            ops = [o for o in ops if o.get("op") != "attach_don"]
            if len(ops) != before:
                changed = True
            if not a.get("require_given_don_gte"):
                a["require_given_don_gte"] = 2
                changed = True

        a["ops"] = ops
        if ops:
            new_abs.append(a)

    if changed:
        return _rebuild(cid, new_abs)
    return None


# --- regexes ---
OPP_DON_MAIN_TRIG = re.compile(
    r"If your opponent has\s*(\d+)\s*or more DON!! cards on their field|"
    r"若對手場上的咚‼?卡有\s*(\d+)\s*[張张]以上|若对手场上的咚‼?卡有\s*(\d+)\s*[张張]以上",
    re.I,
)
DRESSROSA_RUSH = re.compile(
    r"Leader has the \{Dressrosa\} type.{0,80}Dressrosa\} type Characters can attack Characters|"
    r"領航卡擁有《多雷斯羅薩》.{0,80}《多雷斯羅薩》特徵的角色卡.{0,40}登場的回合即可攻擊|"
    r"领航卡拥有《多雷斯罗萨》.{0,80}《多雷斯罗萨》特征的角色卡.{0,40}登场的回合即可攻击",
    re.I | re.S,
)
GERMA_BLOCKER_DON = re.compile(
    r"Leader has the \{GERMA 66\}.{0,120}at least 2 less.{0,80}gains \[Blocker\]|"
    r"領航卡擁有《杰爾馬66》.{0,120}少2[張张].{0,80}獲得【防禦】|"
    r"领航卡拥有《杰尔马66》.{0,120}少2[张張].{0,80}获得【防御】",
    re.I | re.S,
)
SCIENTIST_PROTECT = re.compile(
    r"yellow \{Scientist\} type Characters cannot be removed|"
    r"黃色擁有《科學家》特徵的角色卡全數不|黄色拥有《科学家》特征的角色卡全数不",
    re.I,
)
TRIGGER_BLOCKER_HAND = re.compile(
    r"\[Trigger\] Up to 1 of your \{Egghead\} type Characters gains \[Blocker\] during this turn\.\s*Then, add this card to your hand|"
    r"【觸發器】最多1[張张]自己擁有《蛋頭》.{0,40}獲得【防禦】。之後，將這張卡片加入手牌|"
    r"【触发器】最多1[张張]自己拥有《蛋头》.{0,40}获得【防御】。之后，将这张卡片加入手牌",
    re.I | re.S,
)
END_TURN_SUPERNOVA = re.compile(
    r"\{Supernovas\} type Characters with a cost of 3 to 8 as active.{0,80}gains \[Blocker\] until|"
    r"《超新星》.{0,40}費用3至8.{0,80}獲得【防禦】|"
    r"《超新星》.{0,40}费用3至8.{0,80}获得【防御】",
    re.I | re.S,
)
SHIRAHOSHI_RUSH = re.compile(
    r"Leader is \[Shirahoshi\].{0,60}attack Characters on the turn|"
    r"領航卡是「白星」.{0,40}登場的回合即可攻擊角色|"
    r"领航卡是「白星」.{0,40}登场的回合即可攻击角色",
    re.I | re.S,
)
GIVEN_DON_BLOCKER = re.compile(
    r"total of 2 or more given DON!! cards.{0,40}gains \[Blocker\]|"
    r"已附加的咚‼?卡合計2[張张]以上.{0,40}獲得【防禦】|"
    r"已附加的咚‼?卡合计2[张張]以上.{0,40}获得【防御】",
    re.I | re.S,
)
DON_FIELD_LTE_BLOCKER = re.compile(
    r"If you have\s*(\d+)\s*or less DON!! cards on your field.{0,40}gains \[Blocker\]|"
    r"若自己場上的咚‼?卡在(\d+)[張张]以下時.{0,40}獲得【防禦】|"
    r"若自己场上的咚‼?卡在(\d+)[张張]以下时.{0,40}获得【防御】",
    re.I | re.S,
)
REVO_BLOCKER_COST = re.compile(
    r"Leader has the \{Revolutionary Army\} type.{0,40}gains \[Blocker\] and \+4 cost|"
    r"領航卡擁有《革命軍》.{0,40}獲得【防禦】.{0,20}費用\+4|"
    r"领航卡拥有《革命军》.{0,40}获得【防御】.{0,20}费用\+4",
    re.I | re.S,
)
ON_PLAY_LIFE_ATTACH = re.compile(
    r"\[On Play\] You may add 1 card from the top or bottom of your Life|"
    r"【登場時】可[將将]1[張张]自己生命值區",
    re.I,
)
BASE_COST5_BLOCKER_COST = re.compile(
    r"2 or more Characters with a base cost of 5 or more.{0,40}gains \[Blocker\] and \+1 cost|"
    r"2[張张]以上自己原本費用5以上的角色卡時.{0,40}獲得【防禦】.{0,20}費用\+1|"
    r"2[张張]以上自己原本费用5以上的角色卡时.{0,40}获得【防御】.{0,20}费用\+1",
    re.I | re.S,
)
ON_KO_BUGGY_DRAW = re.compile(
    r"\[On K\.O\.\] If your Leader is \[Buggy\].{0,40}draw 1|"
    r"【KO時】若自己的領航卡是「巴其」.{0,40}抽1|"
    r"【KO时】若自己的领航卡是「巴其」.{0,40}抽1",
    re.I | re.S,
)
CHOOSE_DRAW_OR_BLOCKER = re.compile(
    r"Choose one:.{0,20}Draw 2 cards\..{0,40}\{Dressrosa\}.{0,60}Blocker\} until|"
    r"選擇下列其中一項。.{0,20}抽2[張张].{0,40}《多雷斯羅薩》.{0,60}【防禦】|"
    r"选择下列其中一项。.{0,20}抽2[张張].{0,40}《多雷斯罗萨》.{0,60}【防御】",
    re.I | re.S,
)
KOALA_LUFFY_ROBIN = re.compile(
    r"Leader is \[Koala\] or \[Monkey\.D\.Luffy\].{0,40}gains \[Blocker\] and \+3 cost|"
    r"領航卡是「可亞拉」或「蒙其・D・魯夫」.{0,40}獲得【防禦】.{0,20}費用\+3|"
    r"领航卡是「可亚拉」或「蒙其・D・路飞」.{0,40}获得【防御】.{0,20}费用\+3",
    re.I | re.S,
)
TRASH7_PROTECT_PLAY = re.compile(
    r"7 or more cards in your trash.{0,80}cannot be removed.{0,80}\[Blocker\].{0,40}\[On Play\]|"
    r"廢棄區有7[張张]以上.{0,80}無法離開.{0,40}【防禦】.{0,40}【登場時】|"
    r"废弃区有7[张張]以上.{0,80}无法离开.{0,40}【防御】.{0,40}【登场时】",
    re.I | re.S,
)
DON1_BLOCKER_SEARCH = re.compile(
    r"\[DON!! x1\] This Character gains \[Blocker\]\. \[On Play\] Look at 3|"
    r"【咚‼?×1】這張角色卡獲得【防禦】。【登場時】|"
    r"【咚‼?×1】这张角色卡获得【防御】。【登场时】",
    re.I | re.S,
)
ODEN_REPLACE_ACTIVE = re.compile(
    r"trash 2 cards from your hand instead\. \[Activate: Main\].{0,80}rest 3 of your DON!!|"
    r"替換成廢棄2[張张]自己的手牌。【啟動主要】.{0,80}休息3|"
    r"替换成废弃2[张張]自己的手牌。【启动主要】.{0,80}休息3",
    re.I | re.S,
)
NEXT_COST = re.compile(r"the next time you play a \{Land of Wano\}|接下來使自己手牌中費用3以上擁有《和之國》", re.I)
SWORD_NAVY = re.compile(r"\{SWORD\} type Characters can attack|《SWORD》特徵的角色卡在登場的回合", re.I)
DRAW_UNTIL = re.compile(r"Draw card\(s\) so that you have 3|抽取卡片使自己的手牌有3", re.I)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)

    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    q = json.loads((ROOT / "meta" / "effect_problem_queue.json").read_text())
    open_ids = [it["id"] for it in q["items"] if it.get("status") == "open"]
    seeds = [
        "EB04-057",
        "OP02-091",
        "OP02-090",
        "OP04-096",
        "OP06-072",
        "OP07-103",
        "OP10-099",
        "OP11-027",
        "OP13-112",
        "OP15-068",
        "P-105",
        "ST25-002",
        "ST25-005",
        "OP15-055",
        "OP12-087",
        "OP13-091",
        "OP15-053",
        "ST22-005",
        "OP02-025-P1",
        "OP02-051-P1",
        "OP11-001-P1",
        "OP02-089-P1",
        "OP02-089-P2",
        "OP02-089-P3",
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
                DRESSROSA_RUSH,
                GERMA_BLOCKER_DON,
                GIVEN_DON_BLOCKER,
                DON_FIELD_LTE_BLOCKER,
                REVO_BLOCKER_COST,
                BASE_COST5_BLOCKER_COST,
                CHOOSE_DRAW_OR_BLOCKER,
                KOALA_LUFFY_ROBIN,
                TRASH7_PROTECT_PLAY,
                DON1_BLOCKER_SEARCH,
                ODEN_REPLACE_ACTIVE,
                SHIRAHOSHI_RUSH,
                TRIGGER_BLOCKER_HAND,
                END_TURN_SUPERNOVA,
            )
        ):
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
        # skip no-op writes
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
                json.dumps(
                    [
                        (
                            a.get("timing"),
                            [o.get("op") for o in a.get("ops") or []],
                            {k: a.get(k) for k in a if str(k).startswith("require_") or k == "once"},
                        )
                        for a in (e or {}).get("abilities") or []
                    ],
                    ensure_ascii=False,
                )[:260],
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
