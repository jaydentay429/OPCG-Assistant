#!/usr/bin/env python3
"""Write battle encodings for OP17-031..045 into card_effect_overrides.json."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

RH = "Red-Haired Pirates|紅髮海賊團|红发海贼团"
ROCKS = "Rocks Pirates|洛克斯海賊團|洛克斯海贼团"
SHANKS = "Shanks|香克斯"
JOHN = "Captain John|約翰船長|约翰船长"


def ab(**kwargs):
    kwargs.setdefault("status", "compiled")
    kwargs.setdefault("confidence", 0.9)
    return kwargs


def _replace_leave(op: dict) -> list[dict]:
    return [
        ab(timing="your_turn", summary=op["summary"], ops=[op]),
        ab(timing="opponent_turn", summary=op["summary"], ops=[op]),
    ]


def _blocker() -> dict:
    return ab(
        timing="your_turn",
        summary="Blocker",
        ops=[
            {
                "op": "grant_keyword",
                "keyword": "blocker",
                "target_kind": "self",
                "duration": "permanent",
            }
        ],
        confidence=0.95,
    )


ENTRIES: dict[str, list[dict]] = {
    "OP17-031": [
        ab(
            timing="on_play",
            summary="Draw 1; rest up to 1 opponent Character cost≤8",
            ops=[
                {"op": "draw", "count": 1},
                {
                    "op": "rest_opponent_character",
                    "count": 1,
                    "cost_lte": 8,
                    "optional": True,
                },
            ],
        ),
        ab(
            timing="end_of_your_turn",
            summary="Set up to 1 Red-Haired Pirates Character active",
            ops=[
                {
                    "op": "set_character_active",
                    "count": 1,
                    "target_kind": "own_character",
                    "trait_contains": RH,
                    "optional": True,
                }
            ],
        ),
    ],
    "OP17-032": [
        ab(
            timing="on_play",
            summary="Look top 3; reveal up to 1 Red-Haired Pirates to hand; rest bottom",
            ops=[
                {
                    "op": "search_deck",
                    "top_n": 3,
                    "max_add": 1,
                    "trait_contains": RH,
                    "order_bottom": True,
                    "destination": "hand",
                }
            ],
        )
    ],
    "OP17-033": [
        ab(
            timing="on_play",
            summary="Look top 3; reveal up to 1 Red-Haired Pirates to hand; rest bottom",
            ops=[
                {
                    "op": "search_deck",
                    "top_n": 3,
                    "max_add": 1,
                    "trait_contains": RH,
                    "order_bottom": True,
                    "destination": "hand",
                }
            ],
        ),
        ab(
            timing="on_opponent_attack",
            summary="May trash this Character: rest up to 1 opponent Leader or Character",
            ops=[
                {
                    "op": "trash",
                    "target_kind": "self",
                    "as_cost": True,
                    "optional": True,
                },
                {
                    "op": "rest_character",
                    "target_kind": "opponent_leader_or_character",
                    "count": 1,
                    "optional": True,
                },
            ],
        ),
    ],
    "OP17-034": [
        ab(
            timing="activate_main",
            summary="Once: if opp Leader ≥6000 power, active 1 DON; then RH Leader base 6000 until opp next End",
            ops=[
                {"op": "active_don", "count": 1, "optional": True},
                {
                    "op": "set_base_power",
                    "target_kind": "leader",
                    "amount": 6000,
                    "duration": "until_opp_turn_end",
                    "optional": False,
                },
            ],
            once=True,
            cost_don=0,
            rest_self=False,
            require_opp_leader_power_gte=6000,
            require_leader_trait=RH,
        )
    ],
    "OP17-035": [],
    "OP17-036": [
        ab(
            timing="on_play",
            summary="May rest 6 DON!!: rest 1 opp Character; then KO up to 2 rested opp cost≤6",
            ops=[
                {
                    "op": "rest_don",
                    "count": 6,
                    "owner": "self",
                    "as_cost": True,
                    "optional": True,
                },
                {
                    "op": "rest_opponent_character",
                    "count": 1,
                    "optional": True,
                },
                {
                    "op": "ko",
                    "count": 2,
                    "target_kind": "opponent_character_rested",
                    "cost_lte": 6,
                    "optional": True,
                },
            ],
        ),
        ab(
            timing="counter_event",
            summary="Up to 1 Shanks +4000 this battle",
            ops=[
                {
                    "op": "buff",
                    "amount": 4000,
                    "target_kind": "own_leader_or_character",
                    "name_contains": SHANKS,
                    "optional": True,
                    "duration": "battle",
                }
            ],
        ),
    ],
    "OP17-037": [
        ab(
            timing="on_play",
            summary="Look top 5; reveal up to 1 Red-Haired Pirates to hand; rest bottom",
            ops=[
                {
                    "op": "search_deck",
                    "top_n": 5,
                    "max_add": 1,
                    "trait_contains": RH,
                    "order_bottom": True,
                    "destination": "hand",
                }
            ],
        ),
        ab(
            timing="counter_event",
            summary="May rest 1 of your cards: up to 1 own Leader or Character +3000 this battle",
            ops=[
                {
                    "op": "rest_character",
                    "target_kind": "own_character",
                    "count": 1,
                    "include_leader": True,
                    "include_stage": True,
                    "include_don": True,
                    "as_cost": True,
                    "optional": True,
                },
                {
                    "op": "buff",
                    "amount": 3000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                },
            ],
        ),
    ],
    "OP17-038": [
        ab(
            timing="on_play",
            summary="May rest 4 of your cards: rest up to 1 opponent Character",
            ops=[
                {
                    "op": "rest_character",
                    "target_kind": "own_character",
                    "count": 4,
                    "include_leader": True,
                    "include_stage": True,
                    "include_don": True,
                    "as_cost": True,
                    "optional": True,
                },
                {
                    "op": "rest_opponent_character",
                    "count": 1,
                    "optional": True,
                },
            ],
        ),
        ab(
            timing="counter_event",
            summary="May trash 1 hand: up to 1 own Leader or Character +3000 this battle",
            ops=[
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
        ),
    ],
    "OP17-039": [
        ab(
            timing="when_attacking",
            summary="May trash 1 hand: reveal top 1; if Rocks Pirates draw 2",
            ops=[
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {"op": "look_deck", "count": 1, "position": "top", "optional": False},
                {
                    "op": "draw",
                    "count": 2,
                    "if_revealed_trait_includes": ROCKS,
                },
            ],
        )
    ],
    "OP17-040": [
        ab(
            timing="on_play",
            summary="Draw 1",
            ops=[{"op": "draw", "count": 1}],
        ),
        ab(
            timing="on_own_leader_battle",
            summary="Once: when Rocks Pirates Leader attacks or is attacked, may trash 1 hand: Leader +3000 this battle",
            ops=[
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
                    "target_kind": "leader",
                    "duration": "battle",
                },
            ],
            once=True,
            require_leader_trait=ROCKS,
        ),
    ],
    "OP17-041": [
        _blocker(),
        ab(
            timing="on_play",
            summary="May trash 1 hand: all opponent Characters base cost 1 to bottom",
            ops=[
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {
                    "op": "return_to_bottom",
                    "target_kind": "opponent_character",
                    "base_cost_eq": 1,
                    "all": True,
                    "optional": False,
                },
            ],
        ),
    ],
    "OP17-042": [
        _blocker(),
        ab(
            timing="on_play",
            summary="May reveal 3 Rocks Pirates from hand: up to 1 opp Character −3000 this turn",
            ops=[
                {
                    "op": "reveal_hand",
                    "count": 3,
                    "optional": True,
                    "as_cost": True,
                    "trait_contains": ROCKS,
                    "owner": "self",
                },
                {
                    "op": "buff",
                    "amount": -3000,
                    "target_kind": "opponent_character",
                    "optional": True,
                    "duration": "turn",
                },
            ],
        ),
    ],
    "OP17-043": _replace_leave(
        {
            "op": "replace_leave",
            "trigger": "any_leave",
            "target": "self",
            "cost": "trash_hand",
            "count": 2,
            "life_position": "top",
            "optional": True,
            "summary": "Trash 2 hand instead of this Character leaving the field",
        }
    )
    + [
        ab(
            timing="on_play",
            summary="Leader base power 6000 until opponent's next End Phase",
            ops=[
                {
                    "op": "set_base_power",
                    "target_kind": "leader",
                    "amount": 6000,
                    "duration": "until_opp_turn_end",
                    "optional": False,
                }
            ],
        )
    ],
    "OP17-044": [
        ab(
            timing="your_turn",
            summary="If Leader Rocks Pirates and this rested: opponent can only attack Captain John",
            ops=[
                {
                    "op": "taunt",
                    "target_kind": "self",
                    "while_rested": True,
                    "name_contains": JOHN,
                }
            ],
            require_leader_trait=ROCKS,
            while_rested=True,
        ),
        ab(
            timing="opponent_turn",
            summary="If Leader Rocks Pirates and this rested: opponent can only attack Captain John",
            ops=[
                {
                    "op": "taunt",
                    "target_kind": "self",
                    "while_rested": True,
                    "name_contains": JOHN,
                }
            ],
            require_leader_trait=ROCKS,
            while_rested=True,
        ),
        ab(
            timing="activate_main",
            summary="May rest this: draw 1 and trash 1 hand",
            ops=[
                {"op": "draw", "count": 1},
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": False,
                    "owner": "self",
                },
            ],
            cost_don=0,
            rest_self=True,
            once=False,
        ),
    ],
    "OP17-045": _replace_leave(
        {
            "op": "replace_leave",
            "trigger": "opp_remove",
            "target": "own_filtered",
            "cost": "trash_hand",
            "count": 2,
            "life_position": "top",
            "optional": True,
            "summary": "Trash 2 hand instead of own Character removed by opponent's effect",
        }
    )
    + [
        ab(
            timing="on_play",
            summary="Draw 1",
            ops=[{"op": "draw", "count": 1}],
        )
    ],
}


def main() -> int:
    ov_path = ROOT / "index" / "card_effect_overrides.json"
    ov = json.loads(ov_path.read_text(encoding="utf-8"))
    ov_cards = ov.setdefault("cards", {})
    lib_path, _ = library_paths()
    lib = json.loads(lib_path.read_text(encoding="utf-8"))
    cards = lib.setdefault("cards", {})
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))

    n = 0
    for base, abilities in ENTRIES.items():
        variants = [base] + sorted(k for k in catalog if k.startswith(base + "-"))
        entry = normalize_card_entry(base, {"version": 1, "card_id": base, "abilities": abilities})
        for cid in variants:
            if cid not in catalog and cid != base:
                continue
            packed = dict(entry)
            packed["card_id"] = cid
            ov_cards[cid] = packed
            cards[cid] = packed
            n += 1
            print("override", cid, [a.get("timing") for a in packed["abilities"]])

    ov["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lib["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    tmp = lib_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(lib, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(lib_path)
    reload_effect_library(force=True)
    print(f"wrote {n} override entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
