#!/usr/bin/env python3
"""Write battle encodings for OP17-106..119 (Big Mom + Rocks/Loki) into overrides."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

BMP = "Big Mom Pirates|BIG MOM海賊團|BIG MOM海贼团"
ROCKS = "Rocks Pirates|洛克斯海賊團|洛克斯海贼团"
LINLIN = "Charlotte Linlin|夏洛特・琳琳|夏洛特·琳琳|夏洛特玲玲"
COST12 = 12


def ab(**kwargs):
    kwargs.setdefault("status", "compiled")
    kwargs.setdefault("confidence", 0.9)
    return kwargs


def _both_turns(**kwargs) -> list[dict]:
    return [
        ab(timing="your_turn", **kwargs),
        ab(timing="opponent_turn", **kwargs),
    ]


def _trigger_play_this() -> dict:
    return ab(
        timing="trigger",
        summary="Play this card",
        ops=[
            {
                "op": "play_from_hand",
                "count": 1,
                "card_type": "character",
                "optional": False,
                "from_zone": "hand",
                "self_card": True,
            }
        ],
        confidence=0.95,
    )


def _linlin_counter(amount: int) -> dict:
    return ab(
        timing="counter_event",
        summary=f"Up to 1 Charlotte Linlin +{amount} this battle",
        ops=[
            {
                "op": "buff",
                "amount": amount,
                "target_kind": "own_leader_or_character",
                "name_contains": LINLIN,
                "optional": True,
                "duration": "battle",
            }
        ],
    )


def _bmp_rest_life_trash() -> list[dict]:
    return [
        {
            "op": "rest_don",
            "count": 2,
            "owner": "self",
            "as_cost": True,
            "optional": True,
        },
        {
            "op": "add_life",
            "count": 1,
            "optional": True,
            "position": "top",
        },
    ]


ENTRIES: dict[str, list[dict]] = {
    "OP17-106": [
        ab(
            timing="on_play",
            summary="Your Turn: may rest 2 DON!!; add 1 life top; opponent trashes 1 hand",
            ops=[
                *_bmp_rest_life_trash(),
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": False,
                    "owner": "opponent",
                },
            ],
            require_your_turn=True,
        ),
        _trigger_play_this(),
    ],
    "OP17-107": [_trigger_play_this()],
    "OP17-108": [
        ab(
            timing="trigger",
            summary="Rest up to 1 opp Character cost≤6",
            ops=[
                {
                    "op": "rest_character",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "cost_lte": 6,
                }
            ],
        ),
    ],
    "OP17-109": [
        ab(
            timing="on_play",
            summary="May trash 1 Trigger from hand: draw 3",
            ops=[
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "require_trigger": True,
                    "owner": "self",
                },
                {"op": "draw", "count": 3},
            ],
        ),
    ],
    "OP17-110": [
        ab(
            timing="on_play",
            summary="Your Turn: play up to 1 BMP Character cost≤6; this Character gains Rush this turn",
            ops=[
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 6,
                    "trait_contains": BMP,
                    "from_zone": "hand",
                },
                {
                    "op": "grant_keyword",
                    "keyword": "rush",
                    "target_kind": "self",
                    "duration": "turn",
                },
            ],
            require_your_turn=True,
        ),
        _trigger_play_this(),
    ],
    "OP17-111": [
        ab(
            timing="on_play",
            summary="May reveal 2 Trigger from hand: KO up to 2 opp Characters cost≤1",
            ops=[
                {
                    "op": "reveal_hand",
                    "count": 2,
                    "optional": True,
                    "as_cost": True,
                    "require_trigger": True,
                    "owner": "self",
                },
                {
                    "op": "ko",
                    "count": 2,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "cost_lte": 1,
                },
            ],
        ),
    ],
    "OP17-112": [
        ab(
            timing="your_turn",
            summary="Own Trigger Characters with 4000 base power become 8000 base",
            ops=[
                {
                    "op": "set_base_power",
                    "amount": 8000,
                    "target_kind": "own_characters",
                    "all": True,
                    "require_trigger": True,
                    "base_power_eq": 4000,
                }
            ],
        ),
        ab(
            timing="on_play",
            summary="Draw 1, then add 1 life top OR add 1 opp life top to owner's hand",
            ops=[
                {"op": "draw", "count": 1},
                {
                    "op": "choose_one",
                    "chooser": "self",
                    "options": [
                        {
                            "id": "add_life",
                            "label": "Add 1 deck top to life top",
                            "ops": [
                                {
                                    "op": "add_life",
                                    "count": 1,
                                    "optional": True,
                                    "position": "top",
                                }
                            ],
                        },
                        {
                            "id": "opp_life_hand",
                            "label": "Add 1 opp life top to owner's hand",
                            "ops": [
                                {
                                    "op": "life_to_hand",
                                    "count": 1,
                                    "position": "top",
                                    "optional": True,
                                    "owner": "opponent",
                                    "hand_owner": "life_owner",
                                }
                            ],
                        },
                    ],
                },
            ],
        ),
    ],
    "OP17-113": [
        ab(
            timing="on_play",
            summary="Look top 3; reveal up to 1 BMP to hand; rest to bottom in any order",
            ops=[
                {
                    "op": "search_deck",
                    "trait_contains": BMP,
                    "top_n": 3,
                    "max_add": 1,
                    "order_bottom": True,
                    "destination": "hand",
                }
            ],
        ),
    ],
    "OP17-114": [
        ab(
            timing="on_play",
            summary="Your Turn: may rest 2 DON!!; draw 1, add 1 life; up to 2 opp Characters −3000 this turn",
            ops=[
                {
                    "op": "rest_don",
                    "count": 2,
                    "owner": "self",
                    "as_cost": True,
                    "optional": True,
                },
                {"op": "draw", "count": 1},
                {
                    "op": "add_life",
                    "count": 1,
                    "optional": True,
                    "position": "top",
                },
                {
                    "op": "buff",
                    "amount": -3000,
                    "target_kind": "opponent_character",
                    "optional": True,
                    "duration": "turn",
                    "count": 2,
                },
            ],
            require_your_turn=True,
        ),
        _trigger_play_this(),
    ],
    "OP17-115": [
        ab(
            timing="on_play",
            summary="Charlotte Linlin Leader gains Unblockable this turn",
            ops=[
                {
                    "op": "grant_keyword",
                    "keyword": "blockerless",
                    "target_kind": "leader",
                    "name_contains": LINLIN,
                    "duration": "turn",
                }
            ],
        ),
        _linlin_counter(4000),
    ],
    "OP17-116": [
        ab(
            timing="on_play",
            summary="May rest 2 DON!!: KO up to 1 opp Stage",
            ops=[
                {
                    "op": "rest_don",
                    "count": 2,
                    "owner": "self",
                    "as_cost": True,
                    "optional": True,
                },
                {
                    "op": "ko",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_stage",
                },
            ],
        ),
        ab(
            timing="counter_event",
            summary="If 2+ own Trigger Characters: up to 1 Leader or Character +4000 this battle",
            ops=[
                {
                    "op": "buff",
                    "amount": 4000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                }
            ],
            require_own_trigger_chars_gte=2,
        ),
    ],
    "OP17-117": [
        _linlin_counter(3000),
        ab(
            timing="trigger",
            summary="Opponent may trash 3 hand or accept KO up to 1 opp Character cost≤6",
            ops=[
                {
                    "op": "choose_one",
                    "chooser": "opponent",
                    "options": [
                        {
                            "id": "trash3",
                            "label": "Trash 3 cards from hand",
                            "ops": [
                                {
                                    "op": "trash_hand",
                                    "count": 3,
                                    "optional": False,
                                    "owner": "opponent",
                                }
                            ],
                        },
                        {
                            "id": "accept_ko",
                            "label": "Do not trash; KO up to 1 Character cost≤6",
                            "ops": [
                                {
                                    "op": "ko",
                                    "count": 1,
                                    "optional": True,
                                    "target_kind": "opponent_character",
                                    "cost_lte": 6,
                                }
                            ],
                        },
                    ],
                }
            ],
        ),
    ],
    "OP17-118": [
        ab(
            timing="hand_cost",
            summary="If hand is only Characters without Counter, this card has +2000 Counter",
            ops=[
                {
                    "op": "hand_counter",
                    "amount": 2000,
                    "card_type": "character",
                    "add": False,
                }
            ],
            require_hand_only_chars_no_counter=True,
        ),
        ab(
            timing="on_play",
            summary="Draw 1; play up to 2 Rocks Pirates different names total cost≤9",
            ops=[
                {"op": "draw", "count": 1},
                {
                    "op": "play_from_hand",
                    "count": 2,
                    "card_type": "character",
                    "optional": True,
                    "trait_contains": ROCKS,
                    "different_names": True,
                    "total_cost_lte": 9,
                    "from_zone": "hand",
                },
            ],
        ),
    ],
    "OP17-119": [
        ab(
            timing="your_turn",
            summary="This Character +12 cost",
            ops=[
                {
                    "op": "grant_cost",
                    "amount": COST12,
                    "target_kind": "self",
                    "duration": "permanent",
                }
            ],
            confidence=0.95,
        ),
        ab(
            timing="opponent_turn",
            summary="This Character +12 cost and +3000",
            ops=[
                {
                    "op": "grant_cost",
                    "amount": COST12,
                    "target_kind": "self",
                    "duration": "permanent",
                },
                {"op": "buff_self", "amount": 3000},
            ],
            confidence=0.95,
        ),
        ab(
            timing="on_play",
            summary="KO opp Characters with total cost≤4",
            ops=[
                {
                    "op": "ko",
                    "count": 5,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "total_cost_lte": 4,
                }
            ],
        ),
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
