#!/usr/bin/env python3
"""Batch AQ: Sky Island / cost≤opp life / Then-if / P-120 / multi-ability timing."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

SKY = "Sky Island|空島|空岛"
STRAW = "Straw Hat Crew|草帽一行人"
LUFFY = "Monkey.D.Luffy|蒙其・D・魯夫|蒙其·D·鲁夫|モンキー・D・ルフィ"
SHURA = "Shura|修羅|修罗"
HOTORI = "Hotori|中悟"


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

    # Fill P-120 paper text locally (was empty).
    if "P-120" in catalog:
        catalog["P-120"] = {
            **catalog["P-120"],
            "name": catalog["P-120"].get("name") or "香吉士",
            "name_en": "Sanji",
            "card_type": "Character",
            "cost": catalog["P-120"].get("cost") or 6,
            "power": catalog["P-120"].get("power") or 6000,
            "effect": "手牌中這張卡片，在對手的生命值卡離開的回合中，費用-2。",
            "effect_en": (
                "If a card has been removed from your opponent's Life cards during this turn, "
                "give this card in your hand −2 cost."
            ),
        }
        (ROOT / "index" / "cards_by_id.json").write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
        )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-098",
        [
            {
                "timing": "your_turn",
                "summary": "If own Sky Island base power≥6000 would leave by opp: may life top to hand instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "own_filtered",
                        "cost": "life_to_hand",
                        "life_position": "top",
                        "trait_contains": SKY,
                        "base_power_gte": 6000,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "opponent_turn",
                "summary": "If own Sky Island base power≥6000 would leave by opp: may life top to hand instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "own_filtered",
                        "cost": "life_to_hand",
                        "life_position": "top",
                        "trait_contains": SKY,
                        "base_power_gte": 6000,
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
        "OP15-108",
        [
            {
                "timing": "on_play",
                "summary": "Look top 3; add up to 1 Sky Island",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": SKY,
                        "top_n": 3,
                        "max_add": 1,
                        "order_bottom": True,
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
        "OP05-106",
        [
            {
                "timing": "on_play",
                "summary": "Look top 5; add up to 1 Sky Island other than Shura",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": SKY,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": SHURA,
                        "destination": "hand",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Play this card",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": False,
                        "from_zone": "hand_or_trash",
                        "self_card": True,
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
        "OP11-106",
        [
            {
                "timing": "on_play",
                "summary": "You may life top/bottom to hand: KO up to 1 opp Character cost≤5",
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
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "cost_lte": 5,
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
        "OP15-102",
        [
            {
                "timing": "hand_cost",
                "summary": "If own Sky Island Character power≥7000: this card in hand −3 cost",
                "ops": [{"op": "hand_cost_reduce", "amount": -3}],
                "status": "compiled",
                "confidence": 0.95,
                "require_own_char_power_gte": 7000,
                "require_chars_trait": SKY,
            },
            {
                "timing": "on_play",
                "summary": "Rest up to 1 opp Character with cost ≤ opponent Life",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "optional": True,
                        "cost_lte_opp_life": True,
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
        "OP15-113",
        [
            {
                "timing": "on_play",
                "summary": "You may trash 1: add up to 1 deck top to Life top",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {"op": "add_life", "count": 1, "optional": True, "position": "top"},
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
        "OP05-102",
        [
            {
                "timing": "on_play",
                "summary": "KO up to 1 opp Character with cost ≤ opponent Life",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "cost_lte_opp_life": True,
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
        "OP12-099",
        [
            {
                "timing": "your_turn",
                "summary": "When any Life leaves: draw 1; then cannot draw by own effects this turn",
                "ops": [
                    {"op": "draw", "count": 1, "on_life_leave": True},
                    {"op": "cannot_draw_by_effect", "duration": "turn"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "on_life_leave": True,
                "on_life_leave_from": "either",
            },
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
                "summary": "If Life ≤2: add up to 1 deck top to Life top",
                "ops": [{"op": "add_life", "count": 1, "optional": True, "position": "top"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 2,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-114",
        [
            {
                "timing": "on_play",
                "summary": "You may flip Life top face-up: all opp Characters −2000; Then KO all opp power≤0",
                "ops": [
                    {
                        "op": "flip_life",
                        "face": "up",
                        "position": "top",
                        "optional": True,
                        "as_cost": True,
                    },
                    {
                        "op": "buff",
                        "amount": -2000,
                        "target_kind": "opponent_character",
                        "optional": False,
                        "all": True,
                        "duration": "turn",
                    },
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": False,
                        "power_lte": 0,
                        "all": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "Once: attach up to 1 rested DON!! to own Sky Island Leader or Character",
                "ops": [
                    {
                        "op": "attach_don",
                        "count": 1,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "trait_contains": SKY,
                    }
                ],
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
        "OP15-119",
        [
            {
                "timing": "your_turn",
                "summary": "If DON!! on field ≥6: gain Rush",
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
                "require_don_field_gte": 6,
            },
            {
                "timing": "opponent_turn",
                "summary": "If DON!! on field ≥6: gain Rush",
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
                "require_don_field_gte": 6,
            },
            {
                "timing": "on_opp_event",
                "summary": "Reveal up to 1 Life top; +1000 per cost on revealed card",
                "ops": [
                    {
                        "op": "reveal_life",
                        "count": 1,
                        "position": "top",
                        "optional": True,
                        "owner": "self",
                    },
                    {
                        "op": "buff_self",
                        "amount": 1000,
                        "per_revealed_cost": True,
                        "duration": "turn",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "your_turn",
                "summary": "On opp Blocker: reveal up to 1 Life top; +1000 per cost",
                "ops": [
                    {
                        "op": "reveal_life",
                        "count": 1,
                        "position": "top",
                        "optional": True,
                        "owner": "self",
                    },
                    {
                        "op": "buff_self",
                        "amount": 1000,
                        "per_revealed_cost": True,
                        "duration": "turn",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "on_opp_blocker": True,
            },
            {
                "timing": "opponent_turn",
                "summary": "On opp Blocker: reveal up to 1 Life top; +1000 per cost",
                "ops": [
                    {
                        "op": "reveal_life",
                        "count": 1,
                        "position": "top",
                        "optional": True,
                        "owner": "self",
                    },
                    {
                        "op": "buff_self",
                        "amount": 1000,
                        "per_revealed_cost": True,
                        "duration": "turn",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "on_opp_blocker": True,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "P-120",
        [
            {
                "timing": "hand_cost",
                "summary": "If opponent Life left this turn: this card in hand −2 cost",
                "ops": [{"op": "hand_cost_reduce", "amount": -2}],
                "status": "compiled",
                "confidence": 0.95,
                "require_opp_life_left_this_turn": True,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-109",
        [
            {
                "timing": "on_play",
                "summary": "You may life top to hand: if Straw Hat Leader add Life; Then play Sky Island cost≤5",
                "ops": [
                    {
                        "op": "life_to_hand",
                        "count": 1,
                        "position": "top",
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {
                        "op": "add_life",
                        "count": 1,
                        "optional": True,
                        "position": "top",
                        "require_leader_trait": STRAW,
                    },
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 5,
                        "trait_contains": SKY,
                        "from_zone": "hand",
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
        "EB02-052",
        [
            {
                "timing": "your_turn",
                "summary": "If Leader Sky Island: gain Rush",
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
                "require_leader_trait": SKY,
            },
            {
                "timing": "opponent_turn",
                "summary": "If Leader Sky Island: gain Rush",
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
                "require_leader_trait": SKY,
            },
            {
                "timing": "when_attacking",
                "summary": "You may trash 1: if Life≤1 add Life; Then +1000",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {
                        "op": "add_life",
                        "count": 1,
                        "optional": True,
                        "position": "top",
                        "require_life_lte": 1,
                    },
                    {"op": "buff_self", "amount": 1000, "duration": "turn"},
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
        "ST29-016",
        [
            {
                "timing": "on_play",
                "summary": "Your Monkey.D.Luffy Leader gains Unblockable this turn",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blockerless",
                        "target_kind": "leader",
                        "name_contains": LUFFY,
                        "duration": "turn",
                        "optional": False,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_name": LUFFY,
            },
            {
                "timing": "counter_event",
                "summary": "Leader +3000 this battle",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 3000,
                        "target_kind": "leader",
                        "optional": False,
                        "duration": "battle",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP15-116 — Then ungated after Straw Hat Life trash.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-116",
        [
            {
                "timing": "on_play",
                "summary": "If Straw Hat Leader: trash Life top. Then add Life + trash 1 hand",
                "ops": [
                    {
                        "op": "trash_life",
                        "count": 1,
                        "position": "top",
                        "optional": False,
                        "owner": "self",
                        "require_leader_trait": STRAW,
                    },
                    {"op": "add_life", "count": 1, "optional": True, "position": "top"},
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "counter_event",
                "summary": "Leader +4000 this battle",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 4000,
                        "target_kind": "leader",
                        "optional": False,
                        "duration": "battle",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # Similar cost ≤ opp Life.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP05-103",
        [
            {
                "timing": "on_play",
                "summary": "If you have Hotori: KO up to 1 opp Character cost ≤ opp Life",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "cost_lte_opp_life": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_own_name_contains": HOTORI,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP05-116",
        [
            {
                "timing": "on_play",
                "summary": "KO up to 1 opp Character with cost ≤ opponent Life",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "cost_lte_opp_life": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Activate this card's Main effect",
                "ops": [{"op": "activate_timing", "timing": "on_play"}],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP10-110",
        [
            {
                "timing": "on_play",
                "summary": "Rest up to 1 opp Character with cost ≤ opponent Life",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "optional": True,
                        "cost_lte_opp_life": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "If Life ≤2: play this",
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
                "require_life_lte": 2,
            },
        ],
    )

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library(force=True)
    print(f"batch_aq updated {n} card entries")


if __name__ == "__main__":
    main()
