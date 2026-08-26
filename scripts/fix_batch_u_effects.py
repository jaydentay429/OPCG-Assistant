#!/usr/bin/env python3
"""Batch U: OP16 Impel Down package, OP13-057 deny_blocker, OP06/07 events."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

IMPEL = "Impel Down|推進城"
PRISONER = "Prisoner of Impel Down|推進城的囚犯"


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


def _buggy_leave_abilities() -> list[dict[str, Any]]:
    play = {
        "op": "play_from_hand",
        "count": 1,
        "card_type": "character",
        "optional": True,
        "name_contains": PRISONER,
        "from_zone": "hand",
    }
    base = {
        "status": "compiled",
        "confidence": 0.95,
        "once": True,
        "require_don_attached_gte": 1,
        "optional": True,
        "on_own_trait_leave_or_ko": IMPEL,
        "on_any_leave": True,
        "ops": [play],
    }
    return [
        {
            **base,
            "timing": "your_turn",
            "summary": "[DON!! x1][Once] When own Impel Down Character leaves: play Prisoner from hand",
        },
        {
            **base,
            "timing": "opponent_turn",
            "summary": "[DON!! x1][Once] When own Impel Down Character leaves: play Prisoner from hand",
        },
    ]


def main() -> None:
    ov_path, lib_path = library_paths()
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    ov = json.loads(ov_path.read_text())
    lib = json.loads(lib_path.read_text())
    ov_cards = ov.setdefault("cards", {})
    lib_cards = lib.setdefault("cards", {})
    n = 0

    # OP16-041 Buggy leader: any leave, leader watcher (engine), no require_chars_trait
    n += _write(ov_cards, lib_cards, catalog, "OP16-041", _buggy_leave_abilities())

    # OP06-058: bilateral bottom (already correct; re-assert)
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP06-058",
        [
            {
                "timing": "on_play",
                "summary": "[Main] Bottom up to 2 cost≤6 Characters (either side)",
                "ops": [
                    {
                        "op": "return_to_bottom",
                        "count": 2,
                        "optional": True,
                        "target_kind": "any_character",
                        "cost_lte": 6,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "[Trigger] Bottom up to 1 cost≤5 Character (either side)",
                "ops": [
                    {
                        "op": "return_to_bottom",
                        "count": 1,
                        "optional": True,
                        "target_kind": "any_character",
                        "cost_lte": 5,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP07-056: counter cost return + battle buff; trigger draw+bottom
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP07-056",
        [
            {
                "timing": "counter_event",
                "summary": "[Counter] May return cost≥2 Character: +4000 to Leader or Character this battle",
                "ops": [
                    {
                        "op": "return_to_hand",
                        "target_kind": "own_character",
                        "optional": True,
                        "as_cost": True,
                        "cost_gte": 2,
                    },
                    {
                        "op": "buff",
                        "amount": 4000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "count": 1,
                        "duration": "battle",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "[Trigger] Draw 2, place 2 from hand to bottom",
                "ops": [
                    {"op": "draw", "count": 2},
                    {
                        "op": "hand_to_deck",
                        "count": 2,
                        "position": "bottom",
                        "optional": False,
                        "owner": "self",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP13-057: rest DON always; deny_blocker only if life≤1 and when Leader attacks
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-057",
        [
            {
                "timing": "on_play",
                "summary": "[Main] May rest 1 DON: if life≤1, deny Blocker when Leader attacks this turn",
                "ops": [
                    {"op": "rest_don", "count": 1, "owner": "self", "as_cost": True, "optional": True},
                    {
                        "op": "deny_blocker",
                        "duration": "turn",
                        "when_leader_attacks": True,
                        "require_life_lte": 1,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "counter_event",
                "summary": "[Counter] Leader +3000 this battle",
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

    # OP16-045 Crocodile: Blocker is keyword text; on play bounce cost → play Impel ≤2
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-045",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] May return cost≥2 Character: play Impel Down cost≤2 from hand",
                "ops": [
                    {
                        "op": "return_to_hand",
                        "target_kind": "own_character",
                        "optional": True,
                        "as_cost": True,
                        "cost_gte": 2,
                    },
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 2,
                        "trait_contains": IMPEL,
                        "from_zone": "hand",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            }
        ],
    )

    # OP16-048 Buggy char
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-048",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] If Leader Impel Down: draw 1 and play Prisoner from hand",
                "ops": [
                    {"op": "draw", "count": 1},
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "name_contains": PRISONER,
                        "from_zone": "hand",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": IMPEL,
            },
            {
                "timing": "on_opponent_attack",
                "summary": "[Once] When opponent attacks: grant Blocker to 1 Prisoner this turn",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "own_character",
                        "name_contains": PRISONER,
                        "duration": "turn",
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "optional": True,
            },
        ],
    )

    # OP16-054 Mr.1
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-054",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] Draw 1",
                "ops": [{"op": "draw", "count": 1}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "your_turn",
                "summary": "[DON!! x1][Your Turn] If hand≥5: this Character +3000",
                "ops": [{"op": "buff_self", "amount": 3000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_attached_gte": 1,
                "require_hand_gte": 5,
            },
        ],
    )

    # OP16-055 Mr.2
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-055",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] Draw 1",
                "ops": [{"op": "draw", "count": 1}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "when_attacking",
                "summary": "[DON!! x1][When Attacking] Base power = opponent Leader power this turn",
                "ops": [{"op": "set_base_power_from_opponent_leader"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_attached_gte": 1,
            },
        ],
    )

    # OP16-056 Mr.3 (confirm encoding)
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-056",
        [
            {
                "timing": "activate_main",
                "summary": "[Activate Main] Trash this: draw 2, deny attack cost≤9 until opp end",
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
            }
        ],
    )

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library()
    print(f"batch_u wrote {n} card entries")


if __name__ == "__main__":
    main()
