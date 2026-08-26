#!/usr/bin/env python3
"""Batch AC: Navy / Sengoku / Borsalino DON fixes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

NAVY = "Navy|海軍"
ADMIRAL = "Admiral|上將|上将"
ANIMAL = "Animal Kingdom Pirates|百獸海賊團"


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


def _gain_active_then_rested() -> list[dict[str, Any]]:
    return [
        {"op": "gain_don", "count": 1, "optional": True},
        {"op": "gain_don", "count": 1, "as_rested": True, "optional": True},
    ]


def main() -> None:
    ov_path, lib_path = library_paths()
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    ov = json.loads(ov_path.read_text())
    lib = json.loads(lib_path.read_text())
    ov_cards = ov.setdefault("cards", {})
    lib_cards = lib.setdefault("cards", {})
    n = 0

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-060",
        [
            {
                "timing": "activate_main",
                "summary": "May return 8 active DON!!: play up to 3 different-name Admiral from hand",
                "ops": [
                    {
                        "op": "return_don",
                        "count": 8,
                        "owner": "self",
                        "as_cost": True,
                        "optional": True,
                        "active_only": True,
                        "summary": "Return 8 active DON!! to DON deck",
                    },
                    {
                        "op": "play_from_hand",
                        "count": 3,
                        "card_type": "character",
                        "optional": True,
                        "trait_contains": ADMIRAL,
                        "different_names": True,
                        "from_zone": "hand",
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

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP07-076",
        [
            {
                "timing": "counter_event",
                "summary": "DON!!−1: own Leader/Character +2000 this battle; rest up to 1 opp Character",
                "ops": [
                    {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "battle",
                    },
                    {"op": "rest_opponent_character", "count": 1, "optional": True},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Add up to 1 active DON!!",
                "ops": [{"op": "gain_don", "count": 1, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-078",
        [
            {
                "timing": "on_play",
                "summary": "DON!!−2: draw 1; rest opp power≤5000",
                "ops": [
                    {"op": "return_don", "count": 2, "owner": "self", "as_cost": True},
                    {"op": "draw", "count": 1},
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "power_lte": 5000,
                        "optional": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "counter_event",
                "summary": "Own Leader/Character +1000 this battle; if own DON!!≤6 draw 1",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 1000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "battle",
                    },
                    {"op": "draw", "count": 1, "require_don_field_lte": 6},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-063",
        [
            {
                "timing": "on_play",
                "summary": "Add up to 2 rested DON!!",
                "ops": [{"op": "gain_don", "count": 2, "as_rested": True, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "Once DON!!−1: up to 1 opp Character cannot Blocker this turn",
                "ops": [
                    {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                    {
                        "op": "deny_blocker",
                        "duration": "turn",
                        "optional": True,
                        "count": 1,
                        "target_kind": "opponent_character",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "cost_don": 0,
                "rest_self": False,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-064",
        [
            {
                "timing": "on_play",
                "summary": "Look 5: add up to 1 Navy other than Koby",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": NAVY,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": "Koby|克比",
                        "destination": "hand",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-065",
        [
            {
                "timing": "on_play",
                "summary": "DON!!−1: opp Character −6000 until opp End Phase",
                "ops": [
                    {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                    {
                        "op": "buff",
                        "amount": -6000,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "duration": "until_opp_turn_end",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "Once: may rest 1 DON!!: if Navy Leader, gain up to 2 active DON!!",
                "ops": [
                    {"op": "rest_don", "count": 1, "owner": "self", "as_cost": True, "optional": True},
                    {
                        "op": "gain_don",
                        "count": 2,
                        "optional": True,
                        "require_leader_trait": NAVY,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "cost_don": 0,
                "rest_self": False,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-066",
        [
            {
                "timing": "on_play",
                "summary": "If Navy Leader: gain up to 2 rested DON!!; then draw 2 and trash 2",
                "ops": [
                    {"op": "gain_don", "count": 2, "as_rested": True, "optional": True},
                    {"op": "draw", "count": 2},
                    {"op": "trash_hand", "count": 2, "optional": False, "owner": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": NAVY,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-067",
        [
            {
                "timing": "on_play",
                "summary": "Look 5: add up to 1 Navy; then trash 1 hand",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": NAVY,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "reveal_adds": True,
                    },
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-073",
        [
            {
                "timing": "on_play",
                "summary": "Gain up to 1 active DON!! and up to 1 rested DON!!",
                "ops": _gain_active_then_rested(),
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "end_of_your_turn",
                "summary": "DON!!−2: set this Character active; Blocker until opp End Phase",
                "ops": [
                    {"op": "return_don", "count": 2, "owner": "self", "as_cost": True},
                    {
                        "op": "set_character_active",
                        "count": 1,
                        "target_kind": "self",
                        "optional": False,
                    },
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "self",
                        "duration": "until_opp_turn_end",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-075",
        [
            {
                "timing": "on_play",
                "summary": "If Navy Leader: gain up to 1 active and up to 1 rested DON!!",
                "ops": _gain_active_then_rested(),
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": NAVY,
            },
        ],
    )

    # Similar active+rested DON patterns
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-061",
        [
            {
                "timing": "your_turn",
                "summary": "DON!!×1: own Characters cost +1",
                "ops": [
                    {
                        "op": "grant_cost",
                        "amount": 1,
                        "target_kind": "all_own",
                        "all": True,
                        "summary": "Own Characters gain +1 cost",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_attached_gte": 1,
            },
            {
                "timing": "on_don_returned",
                "summary": "Your turn once when 2+ DON returned: gain up to 1 active and up to 1 rested DON!!",
                "ops": _gain_active_then_rested(),
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "require_your_turn": True,
                "on_return_don_from_field_gte": 2,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-031",
        [
            {
                "timing": "your_turn",
                "summary": "May return 1 field DON!! instead of K.O.",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "ko",
                        "target": "self",
                        "cost": "return_don",
                        "don_count": 1,
                        "life_position": "top",
                        "optional": True,
                        "summary": "Return 1 field DON!! instead of K.O.",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "Once: if Animal Kingdom Leader and no other KING: gain 1 active + 1 rested DON!!",
                "ops": _gain_active_then_rested(),
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "require_leader_trait": ANIMAL,
                "require_no_other_name": "KING|キング",
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-076",
        [
            {
                "timing": "on_play",
                "summary": "May rest 3 DON!!: up to 3 own Admiral +2000 this turn",
                "ops": [
                    {"op": "rest_don", "count": 3, "owner": "self", "as_cost": True, "optional": True},
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "own_character",
                        "optional": True,
                        "count": 3,
                        "trait_contains": ADMIRAL,
                        "duration": "turn",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "counter_event",
                "summary": "If own Admiral on field: up to 1 own Leader/Character +4000 this battle",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 4000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "battle",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_chars_trait": ADMIRAL,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-077",
        [
            {
                "timing": "on_play",
                "summary": "Look 5: add up to 2 Navy; then trash 1 hand",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": NAVY,
                        "top_n": 5,
                        "max_add": 2,
                        "order_bottom": True,
                        "destination": "hand",
                        "reveal_adds": True,
                    },
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-078",
        [
            {
                "timing": "on_play",
                "summary": "Look 5: add up to 1 Navy",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": NAVY,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "DON!!−1, rest this Stage: draw 1 and trash 1 hand",
                "ops": [
                    {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                    {"op": "draw", "count": 1},
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "cost_don": 0,
                "rest_self": True,
                "once": False,
            },
        ],
    )

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library()
    print(f"batch_ac wrote {n} card entries")


if __name__ == "__main__":
    main()
