#!/usr/bin/env python3
"""Batch AR: exact base power / Mihawk OR Slash / Then-if multicolor / similar."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

SLASH = "Slash|斬|斩"
MUGGY = "Muggy Kingdom|西凱阿爾王國"
MIHAWK = "Dracule Mihawk|喬拉可爾・密佛格|乔拉可尔・密佛格"
WEEVIL = "Edward Weevil|艾德華・衛伯|艾德华・卫伯"
STRAW = "Straw Hat Crew|草帽一行人"


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
        "ST12-001",
        [
            {
                "timing": "when_attacking",
                "summary": "DON!!×1 once: return cost≥2 Character: set up to 1 own power≤7000 active",
                "ops": [
                    {
                        "op": "return_to_hand",
                        "target_kind": "own_character",
                        "optional": True,
                        "as_cost": True,
                        "cost_gte": 2,
                    },
                    {
                        "op": "set_character_active",
                        "count": 1,
                        "target_kind": "own_character",
                        "optional": True,
                        "power_lte": 7000,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "require_don_attached_gte": 1,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-034",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Slash: look top 5; add up to 1 Slash card or green Event",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": "",
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "or_event": True,
                        "color": "green",
                        "attr_contains": SLASH,
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_attribute": SLASH,
            },
        ],
    )

    # Exact base power 6000 (not ≥).
    replace_exact_6000 = [
        {
            "timing": "your_turn",
            "summary": "If own base power 6000 Character would leave by opp effect: may rest this instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "own_filtered",
                    "cost": "rest_self",
                    "base_power_eq": 6000,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "opponent_turn",
            "summary": "If own base power 6000 Character would leave by opp effect: may rest this instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "own_filtered",
                    "cost": "rest_self",
                    "base_power_eq": 6000,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ]
    n += _write(ov_cards, lib_cards, catalog, "ST30-011", replace_exact_6000)

    # Similar ST30-009 — trash this + draw 1; exact base power 6000.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST30-009",
        [
            {
                "timing": "your_turn",
                "summary": "If own base power 6000 would leave by opp: may trash this and draw 1 instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "own_filtered",
                        "cost": "trash_self",
                        "base_power_eq": 6000,
                        "then_draw": 1,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "opponent_turn",
                "summary": "If own base power 6000 would leave by opp: may trash this and draw 1 instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "own_filtered",
                        "cost": "trash_self",
                        "base_power_eq": 6000,
                        "then_draw": 1,
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
        "ST12-003",
        [
            {
                "timing": "on_play",
                "summary": "If Characters≤2: play up to 1 Muggy/Slash cost≤4 other than Mihawk rested",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 4,
                        "exclude_name": MIHAWK,
                        "trait_contains": MUGGY,
                        "attribute": SLASH,
                        "trait_or_attribute": True,
                        "as_rested": True,
                        "from_zone": "hand",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_chars_lte": 2,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "PRB02-006",
        [
            {
                "timing": "opponent_turn",
                "summary": "If this would be rested by opp Character effect: may rest 1 other own Character",
                "ops": [
                    {
                        "op": "replace_rest",
                        "target": "self",
                        "cost": "rest_other_character",
                        "rest_count": 1,
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
        "ST30-012",
        [
            {
                "timing": "on_play",
                "summary": "You may rest 1 DON!!: this gains Rush this turn",
                "ops": [
                    {
                        "op": "rest_don",
                        "count": 1,
                        "owner": "self",
                        "as_cost": True,
                        "optional": True,
                    },
                    {
                        "op": "grant_keyword",
                        "keyword": "rush",
                        "target_kind": "self",
                        "duration": "turn",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "when_attacking",
                "summary": "Rest up to 1 opp Blocker Character",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "require_blocker": True,
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
        "OP08-023",
        [
            {
                "timing": "on_play",
                "summary": "Up to 1 opp rested Character cost≤7 skips next Refresh",
                "ops": [
                    {
                        "op": "skip_untap",
                        "count": 1,
                        "target_kind": "opponent_character_rested",
                        "cost_lte": 7,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "when_attacking",
                "summary": "Up to 1 opp rested Character cost≤7 skips next Refresh",
                "ops": [
                    {
                        "op": "skip_untap",
                        "count": 1,
                        "target_kind": "opponent_character_rested",
                        "cost_lte": 7,
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
        "OP13-031",
        [
            {
                "timing": "your_turn",
                "summary": "If Life≤1: gain Blocker",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "self",
                        "duration": "permanent",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 1,
            },
            {
                "timing": "opponent_turn",
                "summary": "If Life≤1: gain Blocker",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "self",
                        "duration": "permanent",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 1,
            },
            {
                "timing": "on_play",
                "summary": "You may return 1 own Character: play up to 1 hand Character cost≤5 rested",
                "ops": [
                    {
                        "op": "return_to_hand",
                        "target_kind": "own_character",
                        "optional": True,
                        "as_cost": True,
                    },
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 5,
                        "as_rested": True,
                        "from_zone": "hand",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP13-118 — Then cannot-play is ungated; active DON gated by multicolor.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-118",
        [
            {
                "timing": "on_play",
                "summary": "If Leader multicolor: set up to 4 DON!! active. Then cannot play base cost≥5 Characters",
                "ops": [
                    {
                        "op": "active_don",
                        "count": 4,
                        "optional": True,
                        "require_leader_multicolor": True,
                    },
                    {
                        "op": "cannot_play_from_hand",
                        "duration": "turn",
                        "card_type": "character",
                        "base_cost_gte": 5,
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
        "OP15-032",
        [
            {
                "timing": "on_play",
                "summary": "Rest up to 1 opponent's card (Leader/Character/Stage/DON!!)",
                "ops": [
                    {
                        "op": "rest_character",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "count": 1,
                        "include_leader": True,
                        "include_don": True,
                        "include_stage": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "You may trash this: if Straw Hat Leader, set up to 1 own base cost≤8 active",
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
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP07-049",
        [
            {
                "timing": "on_play",
                "summary": "Play up to 1 Edward Weevil cost≤4 from hand rested",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 4,
                        "name_contains": WEEVIL,
                        "as_rested": True,
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
        "EB03-023",
        [
            {
                "timing": "on_play",
                "summary": "Look top 5; place at top or bottom in any order",
                "ops": [
                    {
                        "op": "look_deck",
                        "count": 5,
                        "position": "top_or_bottom",
                        "optional": False,
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
        "OP16-054",
        [
            {
                "timing": "on_play",
                "summary": "Draw 1",
                "ops": [{"op": "draw", "count": 1}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "your_turn",
                "summary": "DON!!×1: if hand≥5, this +3000",
                "ops": [{"op": "buff_self", "amount": 3000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_attached_gte": 1,
                "require_hand_gte": 5,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-055",
        [
            {
                "timing": "on_play",
                "summary": "Draw 1",
                "ops": [{"op": "draw", "count": 1}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "when_attacking",
                "summary": "DON!!×1: base power becomes equal to opp Leader power this turn",
                "ops": [{"op": "set_base_power_from_opponent_leader"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_attached_gte": 1,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST12-010",
        [
            {
                "timing": "on_play",
                "summary": "Reveal top 1; play up to 1 cost-2 Character; rest top or bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": "",
                        "top_n": 1,
                        "max_add": 1,
                        "order_bottom": False,
                        "to_top_or_bottom": True,
                        "cost_eq": 2,
                        "destination": "play",
                        "card_type": "character",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "when_attacking",
                "summary": "Once: if hand≤6, draw 1",
                "ops": [{"op": "draw", "count": 1}],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "require_hand_lte": 6,
            },
        ],
    )

    # Similar ST12-017
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST12-017",
        [
            {
                "timing": "on_play",
                "summary": "Reveal top 1; play up to 1 cost-2 Character; rest top or bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": "",
                        "top_n": 1,
                        "max_add": 1,
                        "order_bottom": False,
                        "to_top_or_bottom": True,
                        "cost_eq": 2,
                        "destination": "play",
                        "card_type": "character",
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
        "ST12-014",
        [
            {
                "timing": "on_play",
                "summary": "Look top 3; place at top or bottom in any order",
                "ops": [
                    {
                        "op": "look_deck",
                        "count": 3,
                        "position": "top_or_bottom",
                        "optional": False,
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
        "OP15-047",
        [
            {
                "timing": "on_play",
                "summary": "Up to 1 own Character gains Unblockable this turn",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blockerless",
                        "target_kind": "own_character",
                        "duration": "turn",
                        "optional": True,
                        "count": 1,
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
        "EB01-023",
        [
            {
                "timing": "on_play",
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
        "OP10-045",
        [
            {
                "timing": "when_attacking",
                "summary": "Once: draw 2 and trash 1",
                "ops": [
                    {"op": "draw", "count": 2},
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
        ],
    )

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library(force=True)
    print(f"batch_ar updated {n} card entries")


if __name__ == "__main__":
    main()
