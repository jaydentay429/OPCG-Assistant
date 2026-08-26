#!/usr/bin/env python3
"""Batch AD: Fish-Man / Merfolk / Neptunian effect fixes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

FISH = "Fish-Man|Merfolk|魚人族|人魚族"
FISH_ONLY = "Fish-Man|魚人族"
NEPT_ISLAND = "Neptunian|Fish-Man Island|海王類|魚人島"
NEPT = "Neptunian|海王類"
STRAW = "Straw Hat Crew|草帽一行人"
NOAH = "The Ark Noah|方舟諾亞"


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

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-021",
        [
            {
                "timing": "end_of_your_turn",
                "summary": "If hand≤6: set up to 1 Fish-Man/Merfolk Character and up to 1 DON!! active",
                "ops": [
                    {
                        "op": "set_character_active",
                        "count": 1,
                        "target_kind": "own_character",
                        "optional": True,
                        "trait_contains": FISH,
                    },
                    {"op": "active_don", "count": 1, "optional": True},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_hand_lte": 6,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP06-025",
        [
            {
                "timing": "on_play",
                "summary": "Look 4: add up to 1 Fish-Man/Merfolk other than Camie",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": FISH,
                        "top_n": 4,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": "Camie|海咪",
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
        "OP11-030",
        [
            {
                "timing": "activate_main",
                "summary": "Rest 1 DON!! and this Character: look 5, add up to 1 Neptunian/Fish-Man Island",
                "ops": [
                    {"op": "rest_don", "count": 1, "owner": "self", "as_cost": True},
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": NEPT_ISLAND,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "reveal_adds": True,
                    },
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
        "OP06-033",
        [
            {
                "timing": "on_play",
                "summary": "May trash Fish-Man from hand OR Ark Noah from hand/field: KO up to 1 rested opp Character",
                "ops": [
                    {
                        "op": "choose_one",
                        "chooser": "self",
                        "optional": True,
                        "as_cost": True,
                        "summary": "廢棄魚人族手牌，或廢棄手牌/場上的方舟諾亞",
                        "options": [
                            {
                                "id": "fish_hand",
                                "label": "廢棄1張魚人族手牌",
                                "ops": [
                                    {
                                        "op": "trash_hand",
                                        "count": 1,
                                        "optional": False,
                                        "as_cost": True,
                                        "owner": "self",
                                        "trait_contains": FISH_ONLY,
                                    }
                                ],
                            },
                            {
                                "id": "noah_hand",
                                "label": "廢棄手牌中的方舟諾亞",
                                "ops": [
                                    {
                                        "op": "trash_hand",
                                        "count": 1,
                                        "optional": False,
                                        "as_cost": True,
                                        "owner": "self",
                                        "name_contains": NOAH,
                                    }
                                ],
                            },
                            {
                                "id": "noah_field",
                                "label": "廢棄場上的方舟諾亞",
                                "ops": [
                                    {
                                        "op": "trash",
                                        "target_kind": "own_stage",
                                        "optional": False,
                                        "as_cost": True,
                                        "name_contains": NOAH,
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "op": "ko",
                        "target_kind": "opponent_character_rested",
                        "optional": True,
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
        "EB04-018",
        [
            {
                "timing": "on_play",
                "summary": "May rest this Character: KO up to 1 rested opp Character power≤8000",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character_rested",
                        "optional": True,
                        "power_lte": 8000,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "rest_self": True,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-016",
        [
            {
                "timing": "activate_main",
                "summary": "Set up to 1 DON!! active; then cannot active DON!! by Character effects this turn",
                "ops": [
                    {"op": "active_don", "count": 1, "optional": True},
                    {"op": "cannot_active_don_by_character", "duration": "turn"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "cost_don": 0,
                "rest_self": False,
                "once": False,
            },
            {
                "timing": "when_attacking",
                "summary": "If ≥3 Neptunian Characters: rest up to 1 opp cost≤8",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "cost_lte": 8,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_chars_trait_gte": 3,
                "require_chars_trait": NEPT,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-031",
        [
            {
                "timing": "on_play",
                "summary": "If Fish-Man/Merfolk Leader: rest up to 1 opp cost≤5",
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
                "require_leader_trait": FISH,
            },
            {
                "timing": "activate_main",
                "summary": "Once: up to 1 own Fish-Man/Merfolk gains rush_character this turn",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "rush_character",
                        "count": 1,
                        "target_kind": "own_character",
                        "trait_contains": FISH,
                        "optional": True,
                        "duration": "turn",
                        "summary": "Up to 1 own Fish-Man/Merfolk can attack Characters the turn played",
                    }
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
        "OP15-032",
        [
            {
                "timing": "on_play",
                "summary": "Rest up to 1 opponent card (Leader/Character/Stage/DON!!)",
                "ops": [
                    {
                        "op": "rest_character",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "count": 1,
                        "include_leader": True,
                        "include_don": True,
                        "include_stage": True,
                        "summary": "Rest up to 1 opponent card (Leader/Character/Stage/DON!!)",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "May trash this: if Straw Hat Leader, set up to 1 own base cost≤8 active",
                "ops": [
                    {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                    {
                        "op": "set_character_active",
                        "count": 1,
                        "target_kind": "own_character",
                        "optional": True,
                        "base_cost_lte": 8,
                        "require_leader_trait": STRAW,
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
        "EB04-015",
        [
            {
                "timing": "on_ko",
                "summary": "May rest 1 own card: if Fish-Man/Merfolk Leader, play green cost≤6 from hand",
                "ops": [
                    {
                        "op": "rest_character",
                        "target_kind": "own_character",
                        "optional": True,
                        "as_cost": True,
                        "count": 1,
                        "include_leader": True,
                        "include_don": True,
                        "include_stage": True,
                        "summary": "Rest 1 of your cards (Leader/Character/Stage/DON!!)",
                    },
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 6,
                        "color": "green",
                        "from_zone": "hand",
                        "require_leader_trait": FISH,
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
        "ST24-004",
        [
            {
                "timing": "on_play",
                "summary": "Rest up to 1 opp Character + skip untap; if opp has ≥2 rested, Leader +2000 until opp End",
                "ops": [
                    {
                        "op": "rest_character",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "count": 1,
                        "also_skip_untap": True,
                    },
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "leader",
                        "optional": False,
                        "duration": "until_opp_turn_end",
                        "require_opp_rested_chars_gte": 2,
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
        "OP11-037",
        [
            {
                "timing": "on_play",
                "summary": "Look 4: add up to 1 Neptunian/Fish-Man Island Character",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": NEPT_ISLAND,
                        "top_n": 4,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "card_type": "character",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Draw 1",
                "ops": [{"op": "draw", "count": 1}],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-039",
        [
            {
                "timing": "counter_event",
                "summary": "Up to 1 own Fish-Man/Merfolk Leader/Character +3000 this battle; rest opp cost≤3",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 3000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "trait_contains": FISH,
                        "duration": "battle",
                    },
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "cost_lte": 3,
                        "optional": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Rest up to 1 opp cost≤4",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "cost_lte": 4,
                        "optional": True,
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
        "EB04-020",
        [
            {
                "timing": "counter_event",
                "summary": "Up to 1 own Fish-Man Leader/Character +3000 this battle; set up to 1 own Fish-Man active",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 3000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "trait_contains": FISH_ONLY,
                        "duration": "battle",
                    },
                    {
                        "op": "set_character_active",
                        "count": 1,
                        "target_kind": "own_character",
                        "optional": True,
                        "trait_contains": FISH_ONLY,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Rest up to 1 opp cost≤4",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "cost_lte": 4,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # Similar: Jinbe-style end turn untap Fish-Man
    # Similar Camie-style searches already covered via variants

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library()
    print(f"batch_ad wrote {n} card entries")


if __name__ == "__main__":
    main()
