#!/usr/bin/env python3
"""Batch W: Law/Rosinante package, Navy stages, gate-after-cost fixes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

LAW = "Trafalgar Law|托拉法爾加・羅|托拉法尔加・罗"
ROSINANTE = "Donquixote Rosinante|唐吉訶德・羅希南特|唐吉诃德・罗西南迪"
NAVY = "Navy|海軍"
KOBY = "Koby|克比"
SUPERNOVAS = "Supernovas|超新星"


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

    replace_law = {
        "op": "replace_leave",
        "trigger": "ko",
        "target": "own_filtered",
        "cost": "life_to_hand",
        "life_position": "top",
        "name_contains": LAW,
        "optional": True,
    }
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-061",
        [
            {
                "timing": "your_turn",
                "summary": "[Once] If your Law would be KO'd, may take top Life instead",
                "ops": [replace_law],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
            {
                "timing": "opponent_turn",
                "summary": "[Once] If your Law would be KO'd, may take top Life instead",
                "ops": [replace_law],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
            {
                "timing": "activate_main",
                "summary": "[Once] DON!!−1: next Law cost≥4 from hand −2",
                "ops": [
                    {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                    {
                        "op": "hand_cost_reduce",
                        "amount": -2,
                        "name_contains": LAW,
                        "cost_gte": 4,
                        "next_only": True,
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
        "EB03-062",
        [
            {
                "timing": "activate_main",
                "summary": "Trash 1 hand + this: add Life top, play Law cost≤7",
                "ops": [
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                    {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                    {"op": "add_life", "count": 1, "optional": True, "position": "top"},
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 7,
                        "name_contains": LAW,
                        "from_zone": "hand",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "cost_don": 0,
                "rest_self": False,
                "once": False,
            },
            {
                "timing": "your_turn",
                "summary": "[Rush]",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "rush",
                        "target_kind": "self",
                        "duration": "permanent",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "opponent_turn",
                "summary": "[Rush]",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "rush",
                        "target_kind": "self",
                        "duration": "permanent",
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
        "EB04-038",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] If own DON ≤ opp DON: draw 1 then gain 1 active DON",
                "ops": [
                    {"op": "draw", "count": 1},
                    {"op": "gain_don", "count": 1, "optional": True},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_field_deficit_gte": 0,
            }
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-058",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] If life≤2: add top deck to Life",
                "ops": [{"op": "add_life", "count": 1, "optional": True, "position": "top"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 2,
            }
        ],
    )

    # EB04-059: flip cost always; deficit only on KOs
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-059",
        [
            {
                "timing": "on_play",
                "summary": "[Main] May flip top Life up: if fewer chars, KO cost≤6 and ≤5",
                "ops": [
                    {"op": "flip_life", "face": "up", "position": "top", "optional": True, "as_cost": True},
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "cost_lte": 6,
                        "require_chars_deficit_gte": 1,
                    },
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "cost_lte": 5,
                        "require_chars_deficit_gte": 1,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "[Trigger] Draw 2, trash 1",
                "ops": [
                    {"op": "draw", "count": 2},
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
        "OP09-077",
        [
            {
                "timing": "on_play",
                "summary": "[Main] DON!!−2: KO opp Character power≤6000",
                "ops": [
                    {"op": "return_don", "count": 2, "as_cost": True, "owner": "self"},
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "power_lte": 6000,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "[Trigger] Gain 1 active DON",
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
        "OP12-108",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] Look 5: add up to 1 Law",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": LAW,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            }
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-115",
        [
            {
                "timing": "counter_event",
                "summary": "[Counter] +2000; if life≤2 add Law from trash",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "battle",
                    },
                    {
                        "op": "add_from_trash",
                        "count": 1,
                        "optional": True,
                        "name_contains": LAW,
                        "require_life_lte": 2,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            }
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
                "summary": "[Main] May rest 5 DON: if given DON, opp Character −8000",
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
                "summary": "[Counter] May trash 1: +3000 this battle",
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
                "summary": "[Main] DON!!−2: draw 1, rest opp Character power≤5000",
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
                "summary": "[Counter] +1000; if DON field≤6 draw 1",
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
        "OP16-064",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] Look 5: add Navy other than Koby",
                "ops": [
                    {
                        "op": "search_deck",
                        "trait_contains": NAVY,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": KOBY,
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            }
        ],
    )

    # OP16-065: Navy gate on gain_don only
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-065",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] DON!!−1: opp Character −6000 until opp end",
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
                "summary": "[Once] May rest 1 DON: if Leader Navy, gain up to 2 DON",
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

    # OP16-067: search then trash 1
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-067",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] Look 5: add Navy, then trash 1 from hand",
                "ops": [
                    {
                        "op": "search_deck",
                        "trait_contains": NAVY,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "reveal_adds": True,
                    },
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
            }
        ],
    )

    # Similar: OP13-086-P1 was missing trash_hand
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-086",
        [
            {
                "timing": "on_play",
                "summary": "Look 3: Celestial Dragons other than Shalria to hand; trash rest; trash 1 hand",
                "ops": [
                    {
                        "op": "search_deck",
                        "trait_contains": "Celestial Dragons|天龍人|天龙人",
                        "top_n": 3,
                        "max_add": 1,
                        "trash_rest": True,
                        "exclude_name": "Saint Shalria|夏露莉雅宮|夏露莉雅宫",
                        "destination": "hand",
                        "reveal_adds": True,
                    },
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
            }
        ],
    )

    # OP16-078: DON−1 + rest stage (no double cost_don)
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-078",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] Look 5: add Navy",
                "ops": [
                    {
                        "op": "search_deck",
                        "trait_contains": NAVY,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "reveal_adds": True,
                        "destination": "hand",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "DON!!−1, rest this Stage: draw 1, trash 1",
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

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "P-088",
        [
            {
                "timing": "trigger",
                "summary": "[Trigger] If Leader Supernovas and total life≤5: play this",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": False,
                        "from_zone": "hand",
                        "self_card": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_total_life_lte": 5,
                "require_leader_trait": SUPERNOVAS,
            }
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "P-093",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] If own DON ≤ opp DON: gain 1 rested DON",
                "ops": [{"op": "gain_don", "count": 1, "as_rested": True, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_field_deficit_gte": 0,
            }
        ],
    )

    # ST10-010: opp hand gate on trash only; no fake on_block
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST10-010",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] DON!!−1: if opp hand≥7, trash 2 from opp hand",
                "ops": [
                    {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                    {
                        "op": "trash_hand",
                        "count": 2,
                        "optional": False,
                        "owner": "opponent",
                        "require_opp_hand_gte": 7,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            }
        ],
    )

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library()
    print(f"batch_w wrote {n} card entries")


if __name__ == "__main__":
    main()
