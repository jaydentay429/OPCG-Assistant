#!/usr/bin/env python3
"""Batch AN: Life-leave Enel / total-life KO / Sky Island effect fixes."""

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

    # OP05-098 Enel Leader — when own Life becomes 0 on opp turn.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP05-098",
        [
            {
                "timing": "opponent_turn",
                "summary": "Opp turn once: when own Life becomes 0, add 1 Life then trash 1 hand",
                "ops": [
                    {"op": "add_life", "count": 1, "position": "top"},
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "on_life_leave": True,
                "on_life_leave_from": "self",
                "require_life_lte": 0,
            },
        ],
    )

    # EB01-056 Flampe.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB01-056",
        [
            {
                "timing": "on_play",
                "summary": "You may Life top/bottom to hand: draw 1",
                "ops": [
                    {
                        "op": "life_to_hand",
                        "count": 1,
                        "position": "top_or_bottom",
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {"op": "draw", "count": 1},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP11-106 Zeus.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-106",
        [
            {
                "timing": "on_play",
                "summary": "You may Life top/bottom to hand: KO up to 1 opp cost≤5",
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

    # EB04-053 Sentomaru — Blocker innate; On Block if Life≤2 draw.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-053",
        [
            {
                "timing": "on_block",
                "summary": "If Life≤2, draw 1",
                "ops": [{"op": "draw", "count": 1}],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 2,
            },
        ],
    )

    # OP06-104 Kikunojo — keep.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP06-104",
        [
            {
                "timing": "on_ko",
                "summary": "If opp Life≤3, add up to 1 deck top to Life top",
                "ops": [{"op": "add_life", "count": 1, "optional": True, "position": "top"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_opp_life_lte": 3,
            },
            {
                "timing": "trigger",
                "summary": "If opp Life≤3, play this card",
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
                "require_opp_life_lte": 3,
            },
        ],
    )

    # OP07-107 Franky Trigger.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP07-107",
        [
            {
                "timing": "trigger",
                "summary": "Draw 1; then if Life≤1 play this card",
                "ops": [
                    {"op": "draw", "count": 1},
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": False,
                        "from_zone": "hand",
                        "self_card": True,
                        "require_life_lte": 1,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP15-113 Zoro.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-113",
        [
            {
                "timing": "on_play",
                "summary": "You may trash 1 hand: add up to 1 deck top to Life top",
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

    # EB04-058 Borsalino.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-058",
        [
            {
                "timing": "on_play",
                "summary": "If Life≤2, add up to 1 deck top to Life top",
                "ops": [{"op": "add_life", "count": 1, "optional": True, "position": "top"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 2,
            },
        ],
    )

    # OP15-114 Wyper.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-114",
        [
            {
                "timing": "on_play",
                "summary": "You may flip top Life face-up: all opp −2000; then KO all opp power≤0",
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
                "summary": "Once: attach up to 1 rested DON!! to own Sky Island Leader/Character",
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
                "cost_don": 0,
                "rest_self": False,
            },
        ],
    )

    # OP16-119 Teach.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-119",
        [
            {
                "timing": "on_play",
                "summary": "Look top 3; add up to 1 to Life; rest bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": "",
                        "top_n": 3,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "life",
                        "reveal_adds": False,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Negate up to 1 opp Character; then KO up to 1 opp cost≤5",
                "ops": [
                    {
                        "op": "negate_effects",
                        "count": 1,
                        "optional": True,
                        "duration": "turn",
                        "target_kind": "opponent_character",
                        "include_characters": True,
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

    # EB02-052 Enel — Rush both turns; When Attacking Then-if.
    rush_ab = {
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
    }
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB02-052",
        [
            rush_ab,
            {
                **rush_ab,
                "timing": "opponent_turn",
            },
            {
                "timing": "when_attacking",
                "summary": "You may trash 1: if Life≤1 add Life; then this Character +1000 this turn",
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
                    {
                        "op": "buff_self",
                        "amount": 1000,
                        "duration": "turn",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # EB04-061 Luffy.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-061",
        [
            {
                "timing": "hand_cost",
                "summary": "If Life≤1, this card in hand costs −1",
                "ops": [{"op": "hand_cost_reduce", "amount": -1}],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 1,
            },
            {
                "timing": "on_play",
                "summary": "You may trash 1: Leader +2000 until opp end; then this gains Blocker until opp end",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "leader",
                        "optional": False,
                        "duration": "until_opp_turn_end",
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

    # OP06-115.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP06-115",
        [
            {
                "timing": "counter_event",
                "summary": "You may trash 1: up to 1 own Leader/Character +3000 this battle",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
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
            {
                "timing": "trigger",
                "summary": "If Life=0: add up to 1 Life; then trash 1 hand",
                "ops": [
                    {"op": "add_life", "count": 1, "optional": True, "position": "top"},
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 0,
            },
        ],
    )

    # EB01-059 Thunderbolt — KO then life to 1; Trigger KO cost≤total life.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB01-059",
        [
            {
                "timing": "on_play",
                "summary": "KO up to 1 opp Character; then trash Life until 1 remains",
                "ops": [
                    {"op": "ko", "target_kind": "opponent_character", "optional": True},
                    {
                        "op": "trash_life",
                        "count": 1,
                        "position": "top",
                        "optional": False,
                        "owner": "self",
                        "until_life_eq": 1,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "KO up to 1 opp Character with cost ≤ total Life",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "cost_lte_total_life": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # Similar: OP04-112 total-life KO + Then-if add life.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP04-112",
        [
            {
                "timing": "on_play",
                "summary": "KO up to 1 opp cost≤total Life; then if Life≤1 add up to 1 Life",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "cost_lte_total_life": True,
                    },
                    {
                        "op": "add_life",
                        "count": 1,
                        "optional": True,
                        "position": "top",
                        "require_life_lte": 1,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # Similar: ST29-013 Trigger KO cost≤total life.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST29-013",
        [
            {
                "timing": "trigger",
                "summary": "KO up to 1 opp Character with cost ≤ total Life",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "cost_lte_total_life": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # Bulk: any KO missing cost_lte_total_life when paper says 雙方生命值卡合計.
    for cid, info in catalog.items():
        text = str(info.get("effect") or "")
        if "雙方生命值卡合計" not in text and "双方生命值卡合计" not in text:
            continue
        if "費用" not in text and "费用" not in text:
            continue
        entry = ov_cards.get(cid) or lib_cards.get(cid)
        if not isinstance(entry, dict):
            continue
        changed = False
        abilities = []
        for ab in entry.get("abilities") or []:
            ab = dict(ab)
            ops = []
            for op in ab.get("ops") or []:
                op = dict(op)
                if op.get("op") in {"ko", "rest_opponent_character"} and not op.get("cost_lte_total_life"):
                    # Only when this ability text context is total-life cost (heuristic: no fixed cost_lte).
                    if op.get("cost_lte") is None and op.get("base_cost_lte") is None:
                        op["cost_lte_total_life"] = True
                        op["optional"] = True if op.get("optional") is None else op.get("optional")
                        changed = True
                ops.append(op)
            ab["ops"] = ops
            abilities.append(ab)
        if changed:
            entry2 = normalize_card_entry(cid, {"version": int(entry.get("version") or 1), "abilities": abilities})
            ov_cards[cid] = entry2
            lib_cards[cid] = {**entry2, "card_id": cid}
            n += 1

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library(force=True)
    print(f"batch_an updated {n} card entries")


if __name__ == "__main__":
    main()
