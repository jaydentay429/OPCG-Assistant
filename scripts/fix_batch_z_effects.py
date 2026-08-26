#!/usr/bin/env python3
"""Batch Z: Luffy turn-start search, Thunder Bagua, Sanji reveal-play, etc."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

STRAW = "Straw Hat Crew|草帽一行人"
SANJI = "Sanji|香吉士|香吉士"
LUFFY = "Monkey.D.Luffy|蒙其・D・魯夫|蒙其·D·鲁夫"


def _variants(catalog: dict[str, Any], base: str) -> list[str]:
    out = [base]
    out.extend(sorted(k for k in catalog if k.startswith(base + "-")))
    return [c for c in out if c in catalog or c == base]


def _write(ov_cards: dict, lib_cards: dict, catalog: dict, cid: str, abilities: list[dict[str, Any]]) -> int:
    n = 0
    for vid in _variants(catalog, cid):
        entry = normalize_card_entry(vid, {"version": 1, "abilities": abilities})
        ov_cards[vid] = entry
        lib_cards[vid] = {**entry, "card_id": vid}
        n += 1
    return n


def main() -> None:
    ov_path, lib_path = library_paths()
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    ov = json.loads(ov_path.read_text())
    lib = json.loads(lib_path.read_text())
    ov_cards = ov.setdefault("cards", {})
    lib_cards = lib.setdefault("cards", {})
    n = 0

    # OP11-040 Luffy — turn start optional search; rest top OR bottom
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-040",
        [
            {
                "timing": "turn_start",
                "summary": "[Start of Your Turn] If DON!!≥8: look 5, add up to 1 Straw Hat; rest top or bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": STRAW,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "to_top_or_bottom": True,
                        "destination": "hand",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_field_gte": 8,
                "optional": True,
            },
        ],
    )

    # EB01-061 Mr.2
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB01-061",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] Add up to 1 active DON!!",
                "ops": [{"op": "gain_don", "count": 1, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "when_attacking",
                "summary": "[When Attacking] This Character's base power = chosen opp Character power this turn",
                "ops": [
                    {
                        "op": "set_base_power_from_character",
                        "target_kind": "opponent_character",
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP01-070 Mihawk — bilateral bottom cost≤7
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP01-070",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] Bottom up to 1 Character cost≤7 (either side)",
                "ops": [
                    {
                        "op": "return_to_bottom",
                        "count": 1,
                        "optional": True,
                        "target_kind": "any_character",
                        "cost_lte": 7,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP01-119 Thunder Bagua — buff always; life≤2 gain rested DON; trigger ACTIVE DON
    # Similar OP04-075
    for cid, buff_amt in (("OP01-119", 4000), ("OP04-075", 6000)):
        n += _write(
            ov_cards,
            lib_cards,
            catalog,
            cid,
            [
                {
                    "timing": "counter_event",
                    "summary": f"[Counter] Up to 1 own Leader/Character +{buff_amt} this battle",
                    "ops": [
                        {
                            "op": "buff",
                            "amount": buff_amt,
                            "target_kind": "own_leader_or_character",
                            "optional": True,
                            "duration": "battle",
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                },
                {
                    "timing": "counter_event",
                    "summary": "Then if Life≤2: add up to 1 rested DON!!",
                    "ops": [{"op": "gain_don", "count": 1, "as_rested": True, "optional": True}],
                    "status": "compiled",
                    "confidence": 0.95,
                    "require_life_lte": 2,
                },
                {
                    "timing": "trigger",
                    "summary": "[Trigger] Add up to 1 active DON!!",
                    "ops": [{"op": "gain_don", "count": 1, "optional": True}],
                    "status": "compiled",
                    "confidence": 0.95,
                },
            ],
        )

    # OP04-056 Gum-Gum Red Roc
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP04-056",
        [
            {
                "timing": "on_play",
                "summary": "[Main] Bottom up to 1 Character (either side)",
                "ops": [
                    {
                        "op": "return_to_bottom",
                        "count": 1,
                        "optional": True,
                        "target_kind": "any_character",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "[Trigger] Bottom up to 1 Character cost≤4 (either side)",
                "ops": [
                    {
                        "op": "return_to_bottom",
                        "count": 1,
                        "optional": True,
                        "target_kind": "any_character",
                        "cost_lte": 4,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP05-067 Zorojuro
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP05-067",
        [
            {
                "timing": "when_attacking",
                "summary": "[When Attacking] If Life≤3: add up to 1 active DON!!",
                "ops": [{"op": "gain_don", "count": 1, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 3,
            },
        ],
    )

    # OP06-119 Sanji — reveal top 1, play cost≤9 other than Sanji, rest bottom
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP06-119",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] Reveal top 1: play up to 1 Character cost≤9 other than Sanji; rest bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": "",
                        "top_n": 1,
                        "max_add": 1,
                        "order_bottom": True,
                        "cost_lte": 9,
                        "exclude_name": SANJI,
                        "destination": "play",
                        "card_type": "character",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP07-051 Hancock
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP07-051",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] Deny attack on opp Character other than Luffy; bottom cost≤1 either side",
                "ops": [
                    {
                        "op": "deny_attack",
                        "count": 1,
                        "optional": True,
                        "target_kind": "opponent_character",
                        "duration": "until_opp_turn_end",
                        "exclude_name": LUFFY,
                    },
                    {
                        "op": "return_to_bottom",
                        "count": 1,
                        "optional": True,
                        "target_kind": "any_character",
                        "cost_lte": 1,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP08-076 — second gain if opp has Character power≥6000 (current)
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP08-076",
        [
            {
                "timing": "on_play",
                "summary": "[Main] Gain 1 DON!!; if opp has Character power≥6000, gain another",
                "ops": [
                    {"op": "gain_don", "count": 1, "optional": True},
                    {
                        "op": "gain_don",
                        "count": 1,
                        "optional": True,
                        "require_opp_char_power_gte": 6000,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "[Trigger] Add up to 1 active DON!!",
                "ops": [{"op": "gain_don", "count": 1, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP09-078 Gum-Gum Giant — Straw Hat gates buff AND draw
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-078",
        [
            {
                "timing": "counter_event",
                "summary": "[Counter] DON!!−2, may trash 1: if Straw Hat Leader, +4000 then draw 2",
                "ops": [
                    {"op": "return_don", "count": 2, "owner": "self", "as_cost": True},
                    {"op": "trash_hand", "count": 1, "optional": True, "owner": "self"},
                    {
                        "op": "buff",
                        "amount": 4000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "require_leader_trait": STRAW,
                        "duration": "battle",
                    },
                    {
                        "op": "draw",
                        "count": 2,
                        "require_leader_trait": STRAW,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP11-054 Nami — reaffirm
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-054",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] If Leader multicolor: draw 3, place 2 hand top/bottom",
                "ops": [
                    {"op": "draw", "count": 3},
                    {
                        "op": "hand_to_deck",
                        "count": 2,
                        "position": "top_or_bottom",
                        "optional": False,
                        "owner": "self",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_multicolor": True,
            },
        ],
    )

    # OP11-080 Gear 2
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-080",
        [
            {
                "timing": "on_play",
                "summary": "[Main] May rest 2 DON!!: if Leader includes blue, add 1 rested DON!!",
                "ops": [
                    {"op": "rest_don", "count": 2, "owner": "self", "as_cost": True, "optional": True},
                    {"op": "gain_don", "count": 1, "as_rested": True, "optional": True},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_color": "blue|藍|蓝",
            },
            {
                "timing": "counter_event",
                "summary": "[Counter] Up to 1 own Leader +3000 this battle",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 3000,
                        "target_kind": "leader",
                        "optional": True,
                        "duration": "battle",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP13-043 Otama — trash mandatory
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-043",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] If Life≤3: draw 2, trash 1 hand",
                "ops": [
                    {"op": "draw", "count": 2},
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 3,
            },
        ],
    )

    # OP16-056 Mr.3
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-056",
        [
            {
                "timing": "activate_main",
                "summary": "Trash this: draw 2; deny attack on opp Character cost≤9 until opp End",
                "ops": [
                    {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                    {"op": "draw", "count": 2},
                    {
                        "op": "deny_attack",
                        "count": 1,
                        "optional": True,
                        "target_kind": "opponent_character",
                        "cost_lte": 9,
                        "duration": "until_opp_turn_end",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "cost_don": 0,
                "rest_self": False,
                "once": False,
            },
        ],
    )

    # P-107 Roger
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "P-107",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] If either side has 10 DON!!: Leader +2000 until opp End",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "leader",
                        "optional": False,
                        "duration": "until_opp_turn_end",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_either_don_field_gte": 10,
            },
        ],
    )

    # ST18-001 Usopp
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST18-001",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] If DON!!≥8: rest up to 1 opp Character cost≤5",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "cost_lte": 5,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_field_gte": 8,
            },
        ],
    )

    # Similar reveal-top-1 play: OP08-052 was wrong (top 5) — fix if same pattern
    op8052 = str((catalog.get("OP08-052") or {}).get("effect") or "")
    if "公開1張自己卡組上面的卡片，並使最多1張費用4以下" in op8052:
        n += _write(
            ov_cards,
            lib_cards,
            catalog,
            "OP08-052",
            [
                {
                    "timing": "on_play",
                    "summary": "[On Play] Reveal top 1: play Whitebeard cost≤4; rest top or bottom",
                    "ops": [
                        {
                            "op": "search_deck",
                            "name_contains": "",
                            "trait_contains": "Whitebeard Pirates|白鬍子海賊團",
                            "top_n": 1,
                            "max_add": 1,
                            "order_bottom": True,
                            "to_top_or_bottom": True,
                            "cost_lte": 4,
                            "destination": "play",
                            "card_type": "character",
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                },
            ],
        )

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library()
    print(f"batch_z wrote {n} card entries")


if __name__ == "__main__":
    main()
