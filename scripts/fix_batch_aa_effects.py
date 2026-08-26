#!/usr/bin/env python3
"""Batch AA: Katakuri / Big Mom declare-cost, DON return, PRB02 Pudding, ST34, etc."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

BIG_MOM = "Big Mom Pirates|BIG MOM海賊團"
ANIMAL_OR_BM = "Animal Kingdom Pirates|百獸海賊團|Big Mom Pirates|BIG MOM海賊團"
KATAKURI = "Charlotte Katakuri|夏洛特・卡塔克利|夏洛特·卡塔克利"


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

    look_buff = [
        {
            "op": "return_don",
            "count": 1,
            "owner": "self",
            "as_cost": True,
        },
        {
            "op": "look_opp_deck",
            "count": 1,
            "position": "top",
            "optional": False,
        },
        {"op": "buff_self", "amount": 1000, "duration": "battle"},
    ]
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-062",
        [
            {
                "timing": "when_attacking",
                "summary": "Once/turn DON!!−1: look opp top 1; this Leader +1000 this battle",
                "ops": look_buff,
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
            {
                "timing": "on_opponent_attack",
                "summary": "Once/turn DON!!−1: look opp top 1; this Leader +1000 this battle",
                "ops": look_buff,
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP07-077",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Animal Kingdom or Big Mom: look 5, add up to 1 matching trait",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": ANIMAL_OR_BM,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": ANIMAL_OR_BM,
            },
            {
                "timing": "trigger",
                "summary": "Activate this card's Main effect",
                "ops": [{"op": "activate_timing", "timing": "on_play", "summary": "Activate this card's Main effect"}],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP08-062",
        [
            {
                "timing": "activate_main",
                "summary": "May trash self: if Big Mom Leader, play Katakuri cost≥3 ≤opp DON!! from hand",
                "ops": [
                    {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_gte": 3,
                        "name_contains": KATAKURI,
                        "cost_lte_opp_don_field": True,
                        "from_zone": "hand",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "cost_don": 0,
                "rest_self": False,
                "once": False,
                "require_leader_trait": BIG_MOM,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP08-077",
        [
            {
                "timing": "on_play",
                "summary": "DON!!−2: if Animal Kingdom or Big Mom Leader, KO up to 2 opp cost≤6",
                "ops": [
                    {"op": "return_don", "count": 2, "owner": "self", "as_cost": True},
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "count": 2,
                        "cost_lte": 6,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": ANIMAL_OR_BM,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-067",
        [
            {
                "timing": "end_of_your_turn",
                "summary": "Set up to 2 own Big Mom cost≥3 active; add up to 1 rested DON!!",
                "ops": [
                    {
                        "op": "set_character_active",
                        "count": 2,
                        "target_kind": "own_character",
                        "optional": True,
                        "trait_contains": BIG_MOM,
                        "cost_gte": 3,
                    },
                    {"op": "gain_don", "count": 1, "as_rested": True, "optional": True},
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
        "OP11-070",
        [
            {
                "timing": "on_play",
                "summary": "Look 5: add up to 1 Big Mom cost≥2",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": BIG_MOM,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "cost_gte": 2,
                        "destination": "hand",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "DON!!−1, rest this: look opp deck top 1",
                "ops": [
                    {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                    {"op": "look_opp_deck", "count": 1, "position": "top", "optional": False},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "cost_don": 0,
                "rest_self": True,
                "once": False,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-074",
        [
            {
                "timing": "activate_main",
                "summary": "Once: DON!!−1, rest: declare cost, reveal opp top; if match, rest opp cost≤4",
                "ops": [
                    {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                    {
                        "op": "look_opp_deck",
                        "count": 1,
                        "position": "top",
                        "optional": False,
                        "declare_cost": True,
                        "summary": "Declare a cost; reveal opp deck top; continue only if costs match",
                    },
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "cost_lte": 4,
                        "optional": True,
                        "if_declared_cost_match": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "cost_don": 0,
                "rest_self": True,
            },
        ],
    )

    # Similar declare-cost cards
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-066",
        [
            {
                "timing": "activate_main",
                "summary": "Rest: declare cost, reveal; if match KO base cost≤3; then up to 1 rested DON!!",
                "ops": [
                    {
                        "op": "look_opp_deck",
                        "count": 1,
                        "position": "top",
                        "optional": False,
                        "declare_cost": True,
                        "summary": "Declare a cost; reveal opp deck top; continue only if costs match",
                    },
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "base_cost_lte": 3,
                        "if_declared_cost_match": True,
                    },
                    {"op": "gain_don", "count": 1, "as_rested": True, "optional": True},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "cost_don": 0,
                "rest_self": True,
                "once": False,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-081",
        [
            {
                "timing": "on_play",
                "summary": "Declare cost, reveal opp top; if match KO base cost≤8",
                "ops": [
                    {
                        "op": "look_opp_deck",
                        "count": 1,
                        "position": "top",
                        "optional": False,
                        "declare_cost": True,
                        "summary": "Declare a cost; reveal opp deck top; continue only if costs match",
                    },
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "base_cost_lte": 8,
                        "if_declared_cost_match": True,
                    },
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
        "OP13-076",
        [
            {
                "timing": "on_play",
                "summary": "May rest 5 DON!!: if given DON!!≥1, opp Character −8000 this turn",
                "ops": [
                    {"op": "rest_don", "count": 5, "owner": "self", "as_cost": True, "optional": True},
                    {
                        "op": "buff",
                        "amount": -8000,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "count": 1,
                        "require_given_don_gte": 1,
                        "duration": "turn",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "counter_event",
                "summary": "May trash 1 hand: own Leader/Character +3000 this battle",
                "ops": [
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                    {
                        "op": "buff",
                        "amount": 3000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "battle",
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

    gate_draw_play = {
        "require_leader_trait": BIG_MOM,
        "require_opp_don_field_gte": 6,
    }
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "PRB02-010",
        [
            {
                "timing": "on_play",
                "summary": "DON!!−2: if Big Mom Leader and opp DON!!≥6, draw 2 then play Big Mom 6000–8000",
                "ops": [
                    {"op": "return_don", "count": 2, "owner": "self", "as_cost": True},
                    {"op": "draw", "count": 2, **gate_draw_play},
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "trait_contains": BIG_MOM,
                        "power_gte": 6000,
                        "power_lte": 8000,
                        "from_zone": "hand",
                        **gate_draw_play,
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
        "ST34-001",
        [
            {
                "timing": "on_don_returned",
                "summary": "Your turn once: if Big Mom Leader, add up to 2 rested DON!!",
                "ops": [{"op": "gain_don", "count": 2, "as_rested": True, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "require_leader_trait": BIG_MOM,
                "require_your_turn": True,
            },
            {
                "timing": "on_ko",
                "summary": "Play up to 1 Character power≤8000 from hand",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "power_lte": 8000,
                        "from_zone": "hand",
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
        "ST34-003",
        [
            {
                "timing": "on_play",
                "summary": "Look 3: add up to 1 Big Mom to hand",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": BIG_MOM,
                        "top_n": 3,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
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
        "ST34-004",
        [
            {
                "timing": "on_play",
                "summary": "DON!!−4, may trash 1: add top deck to life; opp Character base power 0 this turn",
                "ops": [
                    {"op": "return_don", "count": 4, "owner": "self", "as_cost": True},
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                    {"op": "add_life", "count": 1, "optional": True, "position": "top"},
                    {
                        "op": "set_base_power",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "amount": 0,
                        "duration": "turn",
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
        "ST34-005",
        [
            {
                "timing": "when_attacking",
                "summary": "DON!!−1: KO up to 1 opp base power≤2000",
                "ops": [
                    {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "base_power_lte": 2000,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library()
    print(f"batch_aa wrote {n} card entries")


if __name__ == "__main__":
    main()
