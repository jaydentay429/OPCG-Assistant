#!/usr/bin/env python3
"""Batch AB: Luffy DON gates, 1+ DON return, Straw Hat / Jack / Kaido fixes."""

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
LUFFY = "Monkey.D.Luffy|蒙其・D・魯夫|蒙其·D·鲁夫"
LEADERS_OP13 = (
    "Sabo|薩波|萨波|Portgas.D.Ace|波特卡斯・D・艾斯|波特卡斯·D·艾斯|"
    "Monkey.D.Luffy|蒙其・D・魯夫|蒙其·D·鲁夫"
)


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


def _return_don_1_plus(*, optional: bool = True) -> dict[str, Any]:
    return {
        "op": "return_don",
        "count": 10,
        "owner": "self",
        "as_cost": True,
        "optional": optional,
        "any_number": True,
        "summary": "Return 1 or more DON!! to DON deck",
    }


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
        "ST10-002",
        [
            {
                "timing": "activate_main",
                "summary": "Once: if DON!! field is 0 or ≥8, gain up to 1 active DON!!",
                "ops": [{"op": "gain_don", "count": 1, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "cost_don": 0,
                "rest_self": False,
                "require_don_field_0_or_gte": 8,
            },
        ],
    )

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

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP01-016",
        [
            {
                "timing": "on_play",
                "summary": "Look 5: add up to 1 Straw Hat other than Nami",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": STRAW,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": "Nami|娜美",
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
        "OP05-067",
        [
            {
                "timing": "when_attacking",
                "summary": "If Life ≤3: gain up to 1 active DON!!",
                "ops": [{"op": "gain_don", "count": 1, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 3,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP05-119",
        [
            {
                "timing": "on_play",
                "summary": "DON!!−10: bottom all other own Characters; then extra turn",
                "ops": [
                    {"op": "return_don", "count": 10, "owner": "self", "as_cost": True},
                    {
                        "op": "return_to_bottom",
                        "count": 1,
                        "optional": False,
                        "all": True,
                        "exclude_self": True,
                        "target_kind": "own_character",
                        "summary": "Place all other own Characters at deck bottom",
                    },
                    {"op": "extra_turn", "summary": "Gain an additional own turn after this one"},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "Once: rest 1 DON!!: gain up to 1 active DON!!",
                "ops": [{"op": "gain_don", "count": 1, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "cost_don": 1,
                "rest_self": False,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP07-064",
        [
            {
                "timing": "hand_cost",
                "summary": "If own DON!! field ≤ opp−2: this card in hand cost −3",
                "ops": [{"op": "hand_cost_reduce", "amount": -3}],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_field_deficit_gte": 2,
            },
        ],
    )

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

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP08-119",
        [
            {
                "timing": "when_attacking",
                "summary": "DON!!−10: KO all other Characters; add life; trash opp life top",
                "ops": [
                    {"op": "return_don", "count": 10, "owner": "self", "as_cost": True},
                    {
                        "op": "ko",
                        "target_kind": "any_character",
                        "optional": False,
                        "exclude_self": True,
                        "all": True,
                    },
                    {"op": "add_life", "count": 1, "optional": True, "position": "top"},
                    {
                        "op": "trash_life",
                        "count": 1,
                        "position": "top",
                        "optional": True,
                        "owner": "opponent",
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
        "OP09-004",
        [
            {
                "timing": "your_turn",
                "summary": "All opponent Characters −1000",
                "ops": [
                    {
                        "op": "buff",
                        "amount": -1000,
                        "target_kind": "opponent_character",
                        "optional": False,
                        "all": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "opponent_turn",
                "summary": "All opponent Characters −1000",
                "ops": [
                    {
                        "op": "buff",
                        "amount": -1000,
                        "target_kind": "opponent_character",
                        "optional": False,
                        "all": True,
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
        "OP09-078",
        [
            {
                "timing": "counter_event",
                "summary": "[Counter] DON!!−2, may trash 1: if Straw Hat Leader, +4000 then draw 2",
                "ops": [
                    {"op": "return_don", "count": 2, "owner": "self", "as_cost": True},
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {
                        "op": "buff",
                        "amount": 4000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "require_leader_trait": STRAW,
                        "duration": "battle",
                    },
                    {"op": "draw", "count": 2, "require_leader_trait": STRAW},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # 「可將1張以上…咚‼放回」family
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-119",
        [
            {
                "timing": "on_play",
                "summary": "May return 1+ DON!!: draw 1 and gain Rush this turn",
                "ops": [
                    _return_don_1_plus(),
                    {"op": "draw", "count": 1},
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
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-065",
        [
            {
                "timing": "on_play",
                "summary": "May return 1+ DON!!: Rush this turn; then rest opp cost≤6",
                "ops": [
                    _return_don_1_plus(),
                    {
                        "op": "grant_keyword",
                        "keyword": "rush",
                        "target_kind": "self",
                        "duration": "turn",
                    },
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "cost_lte": 6,
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
        "OP09-068",
        [
            {
                "timing": "end_of_your_turn",
                "summary": "May return 1+ DON!!: set self active; Blocker until opp turn end",
                "ops": [
                    _return_don_1_plus(),
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
        "OP09-070",
        [
            {
                "timing": "on_play",
                "summary": "May return 1+ DON!!: attach up to 2 rested DON!! to Leader/Character",
                "ops": [
                    _return_don_1_plus(),
                    {
                        "op": "attach_don",
                        "count": 2,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "own_leader_or_character",
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
        "OP09-073",
        [
            {
                "timing": "when_attacking",
                "summary": "May return 1+ DON!!: up to 2 opp Characters −2000 this turn",
                "ops": [
                    _return_don_1_plus(),
                    {
                        "op": "buff",
                        "amount": -2000,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "count": 2,
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
        "OP13-016",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Sabo/Ace/Luffy: look 4, add up to 1 cost≥3",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": "",
                        "top_n": 4,
                        "max_add": 1,
                        "order_bottom": True,
                        "cost_gte": 3,
                        "destination": "hand",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_name": LEADERS_OP13,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-077",
        [
            {
                "timing": "on_play",
                "summary": "DON!!−1: draw 1; skip untap up to 1 opp rested power≤6000",
                "ops": [
                    {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                    {"op": "draw", "count": 1},
                    {
                        "op": "skip_untap",
                        "count": 1,
                        "target_kind": "opponent_character_rested",
                        "power_lte": 6000,
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
        "ST18-001",
        [
            {
                "timing": "on_play",
                "summary": "If DON!!≥8: rest up to 1 opp cost≤5",
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

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST21-003",
        [
            {
                "timing": "on_play",
                "summary": "Up to 1 own Straw Hat power≥6000: blockerless this turn",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blockerless",
                        "target_kind": "own_character",
                        "trait_contains": STRAW,
                        "power_gte": 6000,
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
        "ST31-004",
        [
            {
                "timing": "your_turn",
                "summary": "If given DON!! ≥3: gains Rush",
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
                "require_given_don_gte": 3,
            },
            {
                "timing": "opponent_turn",
                "summary": "If given DON!! ≥3: gains Rush",
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
                "require_given_don_gte": 3,
            },
            {
                "timing": "on_play",
                "summary": "Per own Straw Hat card: up to 1 opp Character −1000 this turn",
                "ops": [
                    {
                        "op": "buff",
                        "amount": -1000,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "include_leader": True,
                        "include_stage": True,
                        "duration": "turn",
                        "per_own_chars": 1,
                        "per_own_trait": STRAW,
                        "per_choose": True,
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
        "ST31-005",
        [
            {
                "timing": "on_play",
                "summary": "Look 5: add up to 1 Straw Hat",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": STRAW,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "Rest this Stage: attach up to 1 rested DON!! to own Monkey.D.Luffy",
                "ops": [
                    {
                        "op": "attach_don",
                        "count": 1,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "name_contains": LUFFY,
                    }
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
    print(f"batch_ab wrote {n} card entries")


if __name__ == "__main__":
    main()
