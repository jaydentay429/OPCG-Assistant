#!/usr/bin/env python3
"""Deterministic semantic fixes v32: from_trash zone, empty rebuilds, leave protect, negate.

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

OUT_IDS = ROOT / "meta" / "logs" / "ops_v32_fixed_ids.txt"


def _na(raw: dict[str, Any]) -> dict[str, Any] | None:
    return normalize_ability(raw)


def _rebuild(cid: str, abilities: list[dict[str, Any]]) -> dict[str, Any]:
    cleaned = [a for a in (_na(x) for x in abilities) if a]
    return normalize_card_entry(cid, {"version": 1, "abilities": cleaned})


def _protect_pair(summary: str, gates: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    gates = gates or {}
    out = []
    for timing in ("your_turn", "opponent_turn"):
        ab: dict[str, Any] = {
            "timing": timing,
            "summary": summary,
            "ops": [{"op": "cannot_be_removed", "target_kind": "self", "optional": False}],
            "status": "compiled",
            "confidence": 0.95,
        }
        ab.update(gates)
        out.append(ab)
    return out


# Patterns
OP10_082 = re.compile(
    r"cannot be removed from the field by your opponent'?s? effects\. \[Activate: Main\] You may trash this Character: Draw 1|"
    r"不會因對手的效果而離開場上。【啟動主要】可將這張角色卡放置在廢棄區：抽1|"
    r"不会因对手的效果而离开场上。【启动主要】可将这张角色卡放置在废弃区：抽1",
    re.I | re.S,
)
OP16_117 = re.compile(
    r"trash 1 card with a \[Trigger\] from your hand: Negate the effects|"
    r"廢棄1[張张]自己手牌中擁有【觸發器】|"
    r"废弃1[张張]自己手牌中拥有【触发器】",
    re.I | re.S,
)
OP16_079 = re.compile(
    r"When a \{Land of Wano\} type Character card is played from your trash|"
    r"自己廢棄區中擁有《和之國》特徵的角色卡登場時|"
    r"自己废弃区中拥有《和之国》特征的角色卡登场时",
    re.I | re.S,
)
OP04_055 = re.compile(
    r"trash 1 \[Ice Oni\] from your hand.{0,200}Play 1 \[Ice Oni\] from your trash|"
    r"廢棄1[張张].{0,20}「冰鬼」.{0,200}「冰鬼」登場|"
    r"废弃1[张張].{0,20}「冰鬼」.{0,200}「冰鬼」登场",
    re.I | re.S,
)
OP13_082 = re.compile(
    r"Leader is \[Imu\].{0,80}play up to 5 \{Five Elders\}|"
    r"領航卡是「伊姆」.{0,80}使最多5[張张].{0,40}《五老星》|"
    r"领航卡是「伊姆」.{0,80}使最多5[张張].{0,40}《五老星》",
    re.I | re.S,
)
OP16_098 = re.compile(
    r"trash this Character: Play up to 1 black \[Yamato\].{0,40}from your trash|"
    r"將這張角色卡放置在廢棄區：使最多1[張张]自己廢棄區中費用8的黑色「大和」登場|"
    r"将这张角色卡放置在废弃区：使最多1[张張]自己废弃区中费用8的黑色「大和」登场",
    re.I | re.S,
)
OP16_099 = re.compile(
    r"rest 6 of your DON!! cards: Trash 5 cards from the top of your deck\. Then, play up to 1 \{Land of Wano\}|"
    r"休息6[張张]自己的咚‼?卡：將5[張张]自己卡組上面的卡片放置在廢棄區。之後，使最多1[張张]自己廢棄區中費用6以下擁有《和之國》|"
    r"休息6[张張]自己的咚‼?卡：将5[张張]自己卡组上面的卡片放置在废弃区。之后，使最多1[张張]自己废弃区中费用6以下拥有《和之国》",
    re.I | re.S,
)
OP11_086 = re.compile(
    r"\[On Play\] Trash 1 card from your hand\. \[Activate: Main\] You may trash this Character: Play up to 1 \[Caribou\]|"
    r"【登場時】廢棄1[張张]自己的手牌。【啟動主要】可將這張角色卡放置在廢棄區：使最多1[張张]自己廢棄區中費用4以下的「格列佛」登場|"
    r"【登场时】废弃1[张張]自己的手牌。【启动主要】可将这张角色卡放置在废弃区：使最多1[张張]自己废弃区中费用4以下的「格列佛」登场",
    re.I | re.S,
)
REVIVE_SELF_TRASH = re.compile(
    r"trash 1 Character card with (\d+) power from your hand: Play this Character card from your trash|"
    r"廢棄1[張张]自己手牌中力量值(\d+)的角色卡：使這張角色卡從自己的廢棄區登場|"
    r"废弃1[张張]自己手牌中力量值(\d+)的角色卡：使这张角色卡从自己的废弃区登场",
    re.I | re.S,
)
OP15_088 = re.compile(
    r"This Character gains \+6 cost\. \[On Play\] You may trash 3 cards from the top of your deck: Play up to 1 \{Straw Hat Crew\}|"
    r"這張角色卡的費用\+6。【登場時】可將3[張张]自己卡組上面的卡片放置在廢棄區：使最多1[張张]自己廢棄區中費用2以下擁有《草帽一行人》|"
    r"这张角色卡的费用\+6。【登场时】可将3[张張]自己卡组上面的卡片放置在废弃区：使最多1[张張]自己废弃区中费用2以下拥有《草帽一行人》",
    re.I | re.S,
)
OP16_097 = re.compile(
    r"Add up to 1 \{Land of Wano\}.{0,60}from your trash to your hand\. Then, play up to 1 Character card with a cost of 2 or less from your hand|"
    r"將最多1[張张]自己廢棄區中費用6以下擁有《和之國》.{0,40}加入手牌。之後，使最多1[張张]自己手牌中費用2以下的角色卡登場|"
    r"将最多1[张張]自己废弃区中费用6以下拥有《和之国》.{0,40}加入手牌。之后，使最多1[张張]自己手牌中费用2以下的角色卡登场",
    re.I | re.S,
)
OP10_118 = re.compile(
    r"Once per turn, this Character cannot be K\.O\.'d by your opponent'?s? effects|"
    r"每回合1次，這張角色卡不會因對手的效果而遭到KO|"
    r"每回合1次，这张角色卡不会因对手的效果而遭到KO",
    re.I | re.S,
)
P081 = re.compile(
    r"return this Character to the owner's hand: If you have 3 or more blue \{Cross Guild\}|"
    r"將這張角色卡放回持有者的手牌：若場上有3[張张]以上自己藍色擁有《クロスギルド|Cross Guild|克羅斯公會》|"
    r"将这张角色卡放回持有者的手牌：若场上有3[张張]以上自己蓝色拥有《Cross Guild|克罗斯公会》",
    re.I | re.S,
)
OP06_074 = re.compile(
    r"Negate the effect of up to 1 of your opponent'?s Characters during this turn\. Then, if that Character has 5000 power or less, K\.O\.|"
    r"最多1[張张]對手的角色卡，在這個回合，效果無效。之後，若該[張张]?角色卡的力量值在5000以下時，(?:即)?KO|"
    r"最多1[张張]对手的角色卡，在这个回合，效果无效。之后，若该[张張]?角色卡的力量值在5000以下时，(?:即)?KO",
    re.I | re.S,
)
OP13_064 = re.compile(
    r"Your Leader and all of your Characters that do not have a type including \"Roger Pirates\" have their effects negated|"
    r"自己的領航卡和未擁有包含『羅傑海賊團』特徵的角色卡全數，效果無效|"
    r"自己的领航卡和未拥有包含『罗杰海贼团』特征的角色卡全数，效果无效",
    re.I | re.S,
)


def fix_card(cid: str, info: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any] | None:
    blob = effect_blob(info)

    if OP16_117.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "main_start",
                    "summary": "Trash 1 Trigger from hand: negate opp Character cost≤8 this turn",
                    "ops": [
                        {
                            "op": "trash_hand",
                            "count": 1,
                            "require_trigger": True,
                            "as_cost": True,
                            "optional": True,
                        },
                        {
                            "op": "negate_effects",
                            "target_kind": "opponent_character",
                            "cost_lte": 8,
                            "optional": True,
                        },
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                },
                {
                    "timing": "trigger",
                    "summary": "Add up to 1 Blackbeard Pirates from trash to hand",
                    "ops": [
                        {
                            "op": "add_from_trash",
                            "count": 1,
                            "trait_contains": "Blackbeard Pirates",
                            "optional": True,
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                },
            ],
        )

    if OP16_079.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "on_event",
                    "summary": "When Land of Wano Character is played from trash: that Character gains Rush this turn",
                    "ops": [
                        {
                            "op": "grant_keyword",
                            "keyword": "rush",
                            "target_kind": "own_character",
                            "trait_contains": "Land of Wano",
                            "duration": "turn",
                            "optional": False,
                            "count": 1,
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.85,
                    "on_play_from_trash": True,
                    "require_chars_trait": "Land of Wano",
                }
            ],
        )

    if OP10_082.search(blob):
        return _rebuild(
            cid,
            [
                *_protect_pair("Cannot be removed by opponent's effects"),
                {
                    "timing": "activate_main",
                    "summary": "Trash self: draw 1, play Blackbeard Pirates cost≤5 other than Kuzan from trash",
                    "ops": [
                        {"op": "trash", "target_kind": "self", "as_cost": True, "optional": True},
                        {"op": "draw", "count": 1},
                        {
                            "op": "play_from_hand",
                            "count": 1,
                            "from_zone": "trash",
                            "trait_contains": "Blackbeard Pirates",
                            "exclude_name": "Kuzan",
                            "cost_lte": 5,
                            "optional": True,
                        },
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                },
            ],
        )

    if OP04_055.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "main_start",
                    "summary": "Trash Ice Oni from hand + bottom cost≤4 Character: play Ice Oni from trash",
                    "ops": [
                        {
                            "op": "trash_hand",
                            "count": 1,
                            "name_contains": "Ice Oni",
                            "as_cost": True,
                            "optional": True,
                        },
                        {
                            "op": "return_to_bottom",
                            "target_kind": "any_character",
                            "cost_lte": 4,
                            "as_cost": True,
                            "optional": True,
                        },
                        {
                            "op": "play_from_hand",
                            "count": 1,
                            "from_zone": "trash",
                            "name_contains": "Ice Oni",
                            "optional": False,
                        },
                    ],
                    "status": "compiled",
                    "confidence": 0.9,
                },
                {
                    "timing": "trigger",
                    "summary": "Trigger: activate this card's [Main] effect",
                    "ops": [{"op": "activate_timing", "timing": "main_start"}],
                    "status": "compiled",
                    "confidence": 0.8,
                },
            ],
        )

    if OP13_082.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "activate_main",
                    "summary": "Imu: rest 1 DON + trash 1 hand: trash all own chars, play up to 5 Five Elders 5000 from trash",
                    "ops": [
                        {"op": "rest_don", "count": 1, "as_cost": True, "optional": True},
                        {"op": "trash_hand", "count": 1, "as_cost": True, "optional": True},
                        {"op": "trash", "target_kind": "own_character", "all": True, "optional": False},
                        {
                            "op": "play_from_hand",
                            "count": 5,
                            "from_zone": "trash",
                            "trait_contains": "Five Elders",
                            "power_lte": 5000,
                            "power_gte": 5000,
                            "different_names": True,
                            "optional": True,
                        },
                    ],
                    "status": "compiled",
                    "confidence": 0.9,
                    "require_leader_name": "Imu",
                }
            ],
        )

    if OP16_098.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "on_play",
                    "summary": "Draw 1 and trash 1 hand",
                    "ops": [
                        {"op": "draw", "count": 1},
                        {"op": "trash_hand", "count": 1, "optional": False},
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                },
                {
                    "timing": "activate_main",
                    "summary": "Trash self: play black Yamato cost 8 from trash",
                    "ops": [
                        {"op": "trash", "target_kind": "self", "as_cost": True, "optional": True},
                        {
                            "op": "play_from_hand",
                            "count": 1,
                            "from_zone": "trash",
                            "name_contains": "Yamato",
                            "color": "black",
                            "cost_eq": 8,
                            "optional": True,
                        },
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                },
            ],
        )

    if OP16_099.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "main_start",
                    "summary": "Rest 6 DON: trash top 5, play Land of Wano cost≤6 from trash",
                    "ops": [
                        {"op": "rest_don", "count": 6, "as_cost": True, "optional": True},
                        {"op": "trash_deck_top", "count": 5, "optional": False},
                        {
                            "op": "play_from_hand",
                            "count": 1,
                            "from_zone": "trash",
                            "trait_contains": "Land of Wano",
                            "cost_lte": 6,
                            "optional": True,
                        },
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                },
                {
                    "timing": "counter_event",
                    "summary": "Counter: Leader +3000 this battle",
                    "ops": [{"op": "buff", "amount": 3000, "target_kind": "leader", "duration": "battle"}],
                    "status": "compiled",
                    "confidence": 0.95,
                },
            ],
        )

    if OP11_086.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "on_play",
                    "summary": "Trash 1 card from hand",
                    "ops": [{"op": "trash_hand", "count": 1, "optional": False}],
                    "status": "compiled",
                    "confidence": 0.95,
                },
                {
                    "timing": "activate_main",
                    "summary": "Trash self: play Caribou cost≤4 from trash",
                    "ops": [
                        {"op": "trash", "target_kind": "self", "as_cost": True, "optional": True},
                        {
                            "op": "play_from_hand",
                            "count": 1,
                            "from_zone": "trash",
                            "name_contains": "Caribou",
                            "cost_lte": 4,
                            "optional": True,
                        },
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                },
            ],
        )

    m_rev = REVIVE_SELF_TRASH.search(blob)
    if m_rev and re.search(r"\[On K\.O\.\]|【KO時】|【KO时】", blob, re.I):
        pow_n = int(next(g for g in m_rev.groups() if g))
        abs_: list[dict[str, Any]] = []
        if re.search(r"would be removed.{0,80}K\.O\. this Character instead|即將離開場上.{0,40}替換成KO這張|即将离开场上.{0,40}替换成KO这张", blob, re.I | re.S):
            for timing in ("your_turn", "opponent_turn"):
                abs_.append(
                    {
                        "timing": timing,
                        "summary": "If own Character would leave by opp effect, may KO this instead",
                        "ops": [{"op": "replace_leave", "trigger": "opp_remove", "cost": "trash_self", "target": "own_filtered"}],
                        "status": "compiled",
                        "confidence": 0.85,
                    }
                )
        abs_.append(
            {
                "timing": "on_ko",
                "summary": f"Trash hand Character power {pow_n}: play this from trash",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "power_eq": pow_n,
                        "card_type": "character",
                        "as_cost": True,
                        "optional": True,
                    },
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "from_zone": "trash",
                        "self_card": True,
                        "optional": False,
                    },
                ],
                "status": "compiled",
                "confidence": 0.9,
            }
        )
        return _rebuild(cid, abs_)

    if OP15_088.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "your_turn",
                    "summary": "This Character gains +6 cost",
                    "ops": [{"op": "grant_cost", "amount": 6, "target_kind": "self"}],
                    "status": "compiled",
                    "confidence": 0.95,
                },
                {
                    "timing": "opponent_turn",
                    "summary": "This Character gains +6 cost",
                    "ops": [{"op": "grant_cost", "amount": 6, "target_kind": "self"}],
                    "status": "compiled",
                    "confidence": 0.95,
                },
                {
                    "timing": "on_play",
                    "summary": "Trash top 3: play Straw Hat Crew cost≤2 from trash",
                    "ops": [
                        {"op": "trash_deck_top", "count": 3, "as_cost": True, "optional": True},
                        {
                            "op": "play_from_hand",
                            "count": 1,
                            "from_zone": "trash",
                            "trait_contains": "Straw Hat Crew",
                            "cost_lte": 2,
                            "optional": True,
                        },
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                },
            ],
        )

    if OP16_097.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "on_play",
                    "summary": "Add Land of Wano cost≤6 from trash; then play cost≤2 from hand",
                    "ops": [
                        {
                            "op": "add_from_trash",
                            "count": 1,
                            "trait_contains": "Land of Wano",
                            "cost_lte": 6,
                            "optional": True,
                        },
                        {
                            "op": "play_from_hand",
                            "count": 1,
                            "from_zone": "hand",
                            "cost_lte": 2,
                            "optional": True,
                        },
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                }
            ],
        )

    if OP10_118.search(blob):
        abs_ = [
            {
                "timing": "your_turn",
                "summary": "Once per turn: cannot be K.O.'d by opponent's effects",
                "ops": [{"op": "cannot_be_ko", "target_kind": "self", "optional": False}],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
            {
                "timing": "opponent_turn",
                "summary": "Once per turn: cannot be K.O.'d by opponent's effects",
                "ops": [{"op": "cannot_be_ko", "target_kind": "self", "optional": False}],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
        ]
        if re.search(r"\[When Attacking\].{0,80}place 3 cards from your trash|【攻擊時】.{0,80}將3[張张]自己廢棄區|【攻击时】.{0,80}将3[张張]自己废弃区", blob, re.I | re.S):
            abs_.append(
                {
                    "timing": "when_attacking",
                    "summary": "Place 3 trash bottom: if opp hand≥5, trash 1 opp hand",
                    "ops": [
                        {"op": "trash_to_bottom", "count": 3, "as_cost": True, "optional": True},
                        {"op": "trash_hand", "count": 1, "owner": "opponent", "optional": False},
                    ],
                    "status": "compiled",
                    "confidence": 0.9,
                    "require_opp_hand_gte": 5,
                }
            )
        return _rebuild(cid, abs_)

    # P-081 family only — do not match other Cross Guild cards with similar return-to-hand lines.
    if cid.startswith("P-081") and (
        P081.search(blob) or "Cross Guild" in blob or "十字公會" in blob or "十字公会" in blob
    ):
        return _rebuild(
            cid,
            [
                {
                    "timing": "activate_main",
                    "summary": "Return self to hand: if ≥3 blue Cross Guild, play Cross Guild cost 5 from hand",
                    "ops": [
                        {"op": "return_to_hand", "target_kind": "self", "optional": True, "as_cost": True},
                        {
                            "op": "play_from_hand",
                            "count": 1,
                            "from_zone": "hand",
                            "trait_contains": "Cross Guild",
                            "color": "blue",
                            "cost_eq": 5,
                            "optional": True,
                        },
                    ],
                    "status": "compiled",
                    "confidence": 0.9,
                    "require_chars_trait": "Cross Guild",
                    "require_chars_trait_gte": 3,
                }
            ],
        )

    if OP06_074.search(blob):
        return _rebuild(
            cid,
            [
                {
                    "timing": "on_play",
                    "summary": "DON!!−1: negate opp Character this turn; if power≤5000 KO it",
                    "ops": [
                        {"op": "return_don", "count": 1, "as_cost": True, "optional": True},
                        {
                            "op": "negate_effects",
                            "target_kind": "opponent_character",
                            "optional": True,
                        },
                        {
                            "op": "ko",
                            "target_kind": "opponent_character",
                            "power_lte": 5000,
                            "optional": True,
                        },
                    ],
                    "status": "compiled",
                    "confidence": 0.85,
                }
            ],
        )

    if False and P081.search(blob):  # disabled broad match; kept for reference
        pass

    if OP13_064.search(blob):
        abs_ = []
        for timing in ("your_turn", "opponent_turn"):
            abs_.append(
                {
                    "timing": timing,
                    "summary": "Own Leader + non-Roger-Pirates Characters have effects negated",
                    "ops": [
                        {
                            "op": "negate_effects",
                            "target_kind": "own_character",
                            "all": True,
                            "exclude_trait": "Roger Pirates",
                            "include_leader": True,
                            "optional": False,
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.85,
                }
            )
        if re.search(r"\[On Play\] DON!! −3|【登場時】咚‼?−3|【登场时】咚‼?−3", blob, re.I):
            abs_.append(
                {
                    "timing": "on_play",
                    "summary": "DON!!−3: Leader +2000 until opp turn end",
                    "ops": [
                        {"op": "return_don", "count": 3, "as_cost": True, "optional": True},
                        {"op": "buff", "amount": 2000, "target_kind": "leader", "duration": "until_opp_turn_end"},
                    ],
                    "status": "compiled",
                    "confidence": 0.9,
                }
            )
        return _rebuild(cid, abs_)

    # Generic: flip play_from_hand hand→trash when paper clearly says from trash and op lacks it.
    changed = False
    abilities = []
    for a in entry.get("abilities") or []:
        ab = dict(a)
        ops = []
        for o in ab.get("ops") or []:
            op = dict(o)
            if op.get("op") == "play_from_hand" and str(op.get("from_zone") or "hand") != "trash":
                # Only flip if this ability's summary/text chunk implies trash play.
                chunk = str(ab.get("summary") or "") + " " + blob
                if re.search(
                    r"from your trash|從(?:自己的)?廢棄區|从(?:自己的)?废弃区",
                    chunk,
                    re.I,
                ) and not re.search(
                    r"from your hand(?!.*from your trash)|從(?:自己的)?手牌(?!.*廢棄)|从(?:自己的)?手牌(?!.*废弃)",
                    str(ab.get("summary") or ""),
                    re.I,
                ):
                    # Heuristic: if ability summary mentions trash play, or whole card has trash-play and this op is the play.
                    if re.search(r"from your trash|從(?:自己的)?廢棄區|从(?:自己的)?废弃区", str(ab.get("summary") or ""), re.I) or (
                        re.search(r"Play up to \d+.\{0,80}from your trash|使最多\d+[張张].{0,40}廢棄區|使最多\d+[张張].{0,40}废弃区", blob, re.I | re.S)
                        and ab.get("timing") in {"activate_main", "main_start", "on_ko", "on_play", "trigger"}
                    ):
                        op["from_zone"] = "trash"
                        changed = True
            ops.append(op)
        ab["ops"] = ops
        abilities.append(ab)
    if changed:
        return _rebuild(cid, abilities)

    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)

    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    q = json.loads((ROOT / "meta" / "effect_problem_queue.json").read_text())
    open_ids = [it["id"] for it in q["items"] if it.get("status") == "open"]
    seeds = [
        "OP10-082",
        "OP16-117",
        "OP16-079",
        "OP04-055",
        "OP13-082",
        "OP16-098",
        "OP16-099",
        "OP11-086",
        "OP16-014",
        "ST30-008",
        "OP15-088",
        "OP16-097",
        "OP10-118",
        "P-081-P1",
        "P-081-P2",
        "P-081-R1",
        "OP06-074",
        "OP13-064",
    ]
    for cid in seeds:
        if cid not in open_ids:
            open_ids.append(cid)
    for cid, info in catalog.items():
        blob = effect_blob(info)
        if any(
            r.search(blob)
            for r in (
                OP10_082,
                OP16_117,
                OP16_079,
                OP04_055,
                OP13_082,
                OP16_098,
                OP16_099,
                OP11_086,
                REVIVE_SELF_TRASH,
                OP15_088,
                OP16_097,
                OP10_118,
                P081,
                OP06_074,
                OP13_064,
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
