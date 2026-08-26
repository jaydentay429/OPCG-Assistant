#!/usr/bin/env python3
"""Batch AG: Shandian / Sky Island / Kalgara effect fixes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

SHANDIAN = "Shandian Warrior|香朵拉的戰士"
SKY = "Sky Island|空島|空岛"
UPPER = "Upper Yard|神之島|God's Island"
NOLAND = "Mont Blanc Noland|蒙布朗・諾蘭德|蒙布朗·諾蘭德"
KALGARA = "Kalgara|卡爾葛拉|Calgara"


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


def _bilingual_shandian(obj: dict[str, Any]) -> bool:
    changed = False
    for key in ("trait_contains", "require_leader_trait"):
        if obj.get(key) == "Shandian Warrior":
            obj[key] = SHANDIAN
            changed = True
    return changed


def _bilingual_sky(obj: dict[str, Any]) -> bool:
    changed = False
    for key in ("trait_contains", "require_leader_trait"):
        if obj.get(key) == "Sky Island":
            obj[key] = SKY
            changed = True
    return changed


def main() -> None:
    ov_path, lib_path = library_paths()
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    ov = json.loads(ov_path.read_text())
    lib = json.loads(lib_path.read_text())
    ov_cards = ov.setdefault("cards", {})
    lib_cards = lib.setdefault("cards", {})
    n = 0

    # OP08-098 Kalgara Leader — play Shandian cost≤own DON!!; if played, Life top to hand.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP08-098",
        [
            {
                "timing": "when_attacking",
                "summary": "[DON!! x1] Play Shandian Warrior cost≤own DON!!; if you do, Life top to hand",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "trait_contains": SHANDIAN,
                        "cost_lte_own_don_field": True,
                        "from_zone": "hand",
                    },
                    {
                        "op": "life_to_hand",
                        "count": 1,
                        "position": "top",
                        "optional": True,
                        "owner": "self",
                        "if_played": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_attached_gte": 1,
            },
        ],
    )

    # OP15-108 Nami — Sky Island look 3.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-108",
        [
            {
                "timing": "on_play",
                "summary": "Look 3: add up to 1 Sky Island",
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

    # OP11-106 Zeus — already correct; normalize.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-106",
        [
            {
                "timing": "on_play",
                "summary": "May take Life top/bottom to hand: KO up to 1 opp cost≤5",
                "ops": [
                    {
                        "op": "life_to_hand",
                        "count": 1,
                        "position": "top_or_bottom",
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {"op": "ko", "target_kind": "opponent_character", "optional": True, "cost_lte": 5},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP15-101 Kalgara — trash: look 5 for Noland OR Shandian, max 2.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-101",
        [
            {
                "timing": "on_play",
                "summary": "May trash 1: look 5, add up to 2 Noland or Shandian Warrior",
                "ops": [
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                    {
                        "op": "search_deck",
                        "name_contains": NOLAND,
                        "trait_contains": SHANDIAN,
                        "name_or_trait": True,
                        "top_n": 5,
                        "max_add": 2,
                        "order_bottom": True,
                        "destination": "hand",
                        "reveal_adds": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP15-110 Braham.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-110",
        [
            {
                "timing": "on_ko",
                "summary": "If Leader Shandian Warrior: add up to 1 deck top to Life",
                "ops": [{"op": "add_life", "count": 1, "optional": True, "position": "top"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": SHANDIAN,
            },
        ],
    )

    # OP08-110 Wyper — search Upper Yard then play Stage Upper Yard.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP08-110",
        [
            {
                "timing": "on_play",
                "summary": "Look 5: add Upper Yard; then play up to 1 Upper Yard Stage from hand",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": UPPER,
                        "trait_contains": "",
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "reveal_adds": True,
                    },
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "stage",
                        "optional": True,
                        "name_contains": UPPER,
                        "from_zone": "hand",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP08-109 Noland — Shandian leader + Kalgara on field.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP08-109",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Shandian and own Kalgara: add up to 1 deck top to Life",
                "ops": [{"op": "add_life", "count": 1, "optional": True, "position": "top"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": SHANDIAN,
                "require_own_name_on_field": KALGARA,
            },
        ],
    )

    # OP12-099 Kalgara — keep life-leave draw lock.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-099",
        [
            {
                "timing": "your_turn",
                "summary": "When Life leaves (either): draw 1; then cannot draw by own effects this turn",
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

    # EB04-058 Borsalino — innate Blocker + Life≤2 add life.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-058",
        [
            {
                "timing": "on_play",
                "summary": "If Life≤2: add up to 1 deck top to Life",
                "ops": [{"op": "add_life", "count": 1, "optional": True, "position": "top"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 2,
            },
        ],
    )

    # OP15-119 Luffy — keep rush + reveal life on opp event/blocker.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-119",
        [
            {
                "timing": "your_turn",
                "summary": "If own DON!! field ≥6: gains Rush",
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
                "summary": "If own DON!! field ≥6: gains Rush",
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
                "summary": "Reveal up to 1 Life top; +1000 per revealed cost",
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
                "summary": "On opp Blocker: reveal Life; +1000 per cost",
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
                "summary": "On opp Blocker: reveal Life; +1000 per cost",
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

    # OP05-117 Upper Yard Stage.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP05-117",
        [
            {
                "timing": "on_play",
                "summary": "Look 5: add up to 1 Sky Island",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": SKY,
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
        ],
    )

    # OP08-115 — buff gated by Shandian; Then play Upper Yard always.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP08-115",
        [
            {
                "timing": "counter_event",
                "summary": "If Leader Shandian: +3000 battle; then play up to 1 Upper Yard",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 3000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "battle",
                        "require_leader_trait": SHANDIAN,
                    },
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "stage",
                        "optional": True,
                        "name_contains": UPPER,
                        "from_zone": "hand",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Draw 2 and trash 1",
                "ops": [
                    {"op": "draw", "count": 2},
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # Similar: Shandian / Sky Island EN-only → bilingual.
    for store in (ov_cards, lib_cards):
        for cid, entry in list(store.items()):
            changed = False
            for ab in entry.get("abilities") or []:
                if _bilingual_shandian(ab) or _bilingual_sky(ab):
                    changed = True
                if ab.get("require_own_name_on_field") in {"Calgara", "Kalgara"}:
                    ab["require_own_name_on_field"] = KALGARA
                    changed = True
                for op in ab.get("ops") or []:
                    if _bilingual_shandian(op) or _bilingual_sky(op):
                        changed = True
                    if op.get("name_contains") in {"Upper Yard", "God's Island"}:
                        op["name_contains"] = UPPER
                        changed = True
                    if op.get("op") == "play_from_hand" and op.get("name_contains") == UPPER and op.get("card_type") == "character":
                        # Upper Yard is a Stage.
                        op["card_type"] = "stage"
                        changed = True
            if changed:
                store[cid] = normalize_card_entry(cid, entry)
                n += 1

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library()
    print(f"batch_ag updated entries≈{n}")


if __name__ == "__main__":
    main()
