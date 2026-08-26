#!/usr/bin/env python3
"""Batch AL: Life peek/reorder, base-cost KO, Then-if Linlin-style gates."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

BM = "BIG MOM海賊団|BIG MOM海賊團|Big Mom Pirates"
WARLORDS = "The Seven Warlords of the Sea|王下七武海"
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

    # OP03-099 Katakuri Leader — look top Life self/opp; +1000 battle.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP03-099",
        [
            {
                "timing": "when_attacking",
                "summary": "DON×1: look up to 1 top Life (self or opp); place top/bottom; then Leader +1000 this battle",
                "ops": [
                    {
                        "op": "reorder_life",
                        "owner": "self_or_opponent",
                        "look_top": True,
                        "count": 1,
                        "optional": True,
                        "summary": "Look up to 1 top Life; place top or bottom",
                    },
                    {
                        "op": "buff",
                        "amount": 1000,
                        "target_kind": "leader",
                        "optional": False,
                        "duration": "battle",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_attached_gte": 1,
            },
        ],
    )

    # Similar look-top Life encodings.
    for cid, timing, extra_ops, gates in (
        (
            "OP10-116",
            "activate_main",
            [
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "cost_lte": 5,
                }
            ],
            {},
        ),
        ("OP03-104", "on_play", [], {}),
        ("EB02-053", "on_play", [], {}),
        ("ST07-008", "on_play", [], {}),
    ):
        ops = [
            {
                "op": "reorder_life",
                "owner": "self_or_opponent",
                "look_top": True,
                "count": 1,
                "optional": True,
                "summary": "Look up to 1 top Life; place top or bottom",
            },
            *extra_ops,
        ]
        abs_list: list[dict[str, Any]] = [
            {
                "timing": timing,
                "summary": catalog.get(cid, {}).get("effect", "")[:160]
                or "Look up to 1 top Life; place top or bottom",
                "ops": ops,
                "status": "compiled",
                "confidence": 0.95,
                **gates,
            }
        ]
        if cid == "EB02-053":
            abs_list.append(
                {
                    "timing": "on_ko",
                    "summary": "Look up to 1 top Life; place top or bottom",
                    "ops": [
                        {
                            "op": "reorder_life",
                            "owner": "self_or_opponent",
                            "look_top": True,
                            "count": 1,
                            "optional": True,
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                }
            )
        if cid == "OP10-116":
            abs_list.append(
                {
                    "timing": "trigger",
                    "summary": "Draw 2; trash 1 from hand",
                    "ops": [
                        {"op": "draw", "count": 2},
                        {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                }
            )
        # Preserve OP03-104 blocker innate (no grant).
        n += _write(ov_cards, lib_cards, catalog, cid, abs_list)

    # ST07-003: look Life then if Life < opp gain Rush (single ability).
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST07-003",
        [
            {
                "timing": "on_play",
                "summary": "Look up to 1 top Life self/opp; then if Life < opp Life, gain Rush this turn",
                "ops": [
                    {
                        "op": "reorder_life",
                        "owner": "self_or_opponent",
                        "look_top": True,
                        "count": 1,
                        "optional": True,
                        "summary": "Look up to 1 top Life; place top or bottom",
                    },
                    {
                        "op": "grant_keyword",
                        "keyword": "rush",
                        "target_kind": "self",
                        "duration": "turn",
                        "optional": False,
                        "require_life_less_than_opponent": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP06-101 Ana — OK; refresh clean.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP06-101",
        [
            {
                "timing": "on_play",
                "summary": "Up to 1 own Leader/Character gains Banish this turn",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "banish",
                        "target_kind": "own_leader_or_character",
                        "duration": "turn",
                        "optional": True,
                        "count": 1,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "KO up to 1 opp Character cost≤5",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "cost_lte": 5,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # ST07-007 Brulee — Trigger play self; Blocker innate.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST07-007",
        [
            {
                "timing": "trigger",
                "summary": "Play this card",
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
            },
        ],
    )

    # OP04-100 Capone — Trigger deny attack Leader or Character.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP04-100",
        [
            {
                "timing": "trigger",
                "summary": "Up to 1 opp Leader/Character cannot attack this turn",
                "ops": [
                    {
                        "op": "deny_attack",
                        "count": 1,
                        "optional": True,
                        "target_kind": "opponent_leader_or_character",
                        "duration": "turn",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP06-104 Kikunojo.
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

    # EB03-056 Belo Betty — flip Life cost; KO base cost ≤3.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB03-056",
        [
            {
                "timing": "on_play",
                "summary": "You may flip top Life face-up: KO up to 1 opp Character base cost≤3",
                "ops": [
                    {
                        "op": "flip_life",
                        "face": "up",
                        "position": "top",
                        "optional": True,
                        "as_cost": True,
                    },
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "base_cost_lte": 3,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP05-105.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP05-105",
        [
            {
                "timing": "trigger",
                "summary": "You may trash 1 hand: play this card",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": False,
                        "from_zone": "hand",
                        "self_card": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # EB03-053 Nami — keep prior fix shape.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB03-053",
        [
            {
                "timing": "on_play",
                "summary": "Attach up to 1 rested DON!! to Leader; then if opp Life≥3, opp Life top to owner's hand",
                "ops": [
                    {
                        "op": "attach_don",
                        "count": 1,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "leader",
                        "optional": True,
                    },
                    {
                        "op": "life_to_hand",
                        "count": 1,
                        "position": "top",
                        "optional": True,
                        "owner": "opponent",
                        "hand_owner": "life_owner",
                        "require_opp_life_gte": 3,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "on_ko",
                "summary": "You may flip top Life face-up: play up to 1 hand Character power≤6000",
                "ops": [
                    {
                        "op": "flip_life",
                        "face": "up",
                        "position": "top",
                        "optional": True,
                        "as_cost": True,
                    },
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "power_lte": 6000,
                        "from_zone": "hand",
                    },
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
                "summary": "You may flip top Life face-up: all opp Characters −2000; then KO all opp power≤0",
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

    # OP12-119 Kuma.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-119",
        [
            {
                "timing": "on_play",
                "summary": "You may trash 1 hand: add Life; then this Character +2 cost until opp End Phase",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {"op": "add_life", "count": 1, "optional": True, "position": "top"},
                    {
                        "op": "grant_cost",
                        "amount": 2,
                        "target_kind": "self",
                        "duration": "until_opp_turn_end",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "on_ko",
                "summary": "Opp turn: add up to 1 deck top to Life top",
                "ops": [{"op": "add_life", "count": 1, "optional": True, "position": "top"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_opponent_turn": True,
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
                "summary": "Look top 3; add up to 1 to Life top; rest to deck bottom any order",
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
                "summary": "Negate up to 1 opp Character this turn; then KO up to 1 opp cost≤5",
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

    # OP03-114 Linlin — If BM Leader: add Life. Then trash opp Life (Then ungated).
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP03-114",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Big Mom Pirates: add Life; then trash up to 1 opp Life top",
                "ops": [
                    {
                        "op": "add_life",
                        "count": 1,
                        "optional": True,
                        "position": "top",
                        "require_leader_trait": BM,
                    },
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

    # Similar: OP14-112 Warlords Then-if.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-112",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Warlords: add Life; then opp Life top to owner's hand",
                "ops": [
                    {
                        "op": "add_life",
                        "count": 1,
                        "optional": True,
                        "position": "top",
                        "require_leader_trait": WARLORDS,
                    },
                    {
                        "op": "life_to_hand",
                        "count": 1,
                        "position": "top",
                        "optional": True,
                        "owner": "opponent",
                        "hand_owner": "life_owner",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Play up to 1 hand Character power≤6000 with Trigger",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "power_lte": 6000,
                        "from_zone": "hand",
                        "require_trigger": True,
                    }
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
                "summary": "You may trash 1 hand: up to 1 own Leader/Character +3000 this battle",
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

    # Full Life reorder cards (not look-top).
    for cid in ("OP13-105", "ST13-012", "ST13-017"):
        entry = ov_cards.get(cid) or lib_cards.get(cid)
        if not entry:
            continue
        # Only ensure reorder_life owner self without look_top / self_or_opponent.
        abilities = []
        for ab in entry.get("abilities") or []:
            ab = dict(ab)
            ops = []
            for op in ab.get("ops") or []:
                op = dict(op)
                if op.get("op") == "reorder_life":
                    op["owner"] = "self"
                    op.pop("look_top", None)
                    op.pop("count", None)
                    op["optional"] = False
                ops.append(op)
            ab["ops"] = ops
            abilities.append(ab)
        n += _write(ov_cards, lib_cards, catalog, cid, abilities)

    for cid in ("ST13-016", "ST13-004"):
        entry = ov_cards.get(cid) or lib_cards.get(cid)
        if not entry:
            continue
        abilities = []
        for ab in entry.get("abilities") or []:
            ab = dict(ab)
            ops = []
            for op in ab.get("ops") or []:
                op = dict(op)
                if op.get("op") == "reorder_life":
                    op["owner"] = "self"
                    op["to_deck_top"] = True
                    op.pop("look_top", None)
                ops.append(op)
            ab["ops"] = ops
            abilities.append(ab)
        n += _write(ov_cards, lib_cards, catalog, cid, abilities)

    # Bulk: 原本費用 → base_cost_lte on KO/rest.
    paper = catalog
    for cid, info in paper.items():
        text = str(info.get("effect") or "")
        if "原本費用" not in text and "原本费用" not in text:
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
                if op.get("op") in {"ko", "rest_opponent_character"} and op.get("cost_lte") is not None:
                    # Prefer base when paper says 原本.
                    if op.get("base_cost_lte") is None:
                        op["base_cost_lte"] = int(op["cost_lte"])
                    op.pop("cost_lte", None)
                    changed = True
                ops.append(op)
            ab["ops"] = ops
            abilities.append(ab)
        if changed:
            entry2 = normalize_card_entry(cid, {"version": int(entry.get("version") or 1), "abilities": abilities})
            ov_cards[cid] = entry2
            lib_cards[cid] = {**entry2, "card_id": cid}
            n += 1

    # OP12-029: KO rested base cost ≤1 (paper), rest cost ≤2 is 费用 not 原本.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-029",
        [
            {
                "timing": "on_play",
                "summary": "Rest up to 1 opp cost≤2; then KO up to 1 rested opp base cost≤1",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "cost_lte": 2,
                        "optional": True,
                    },
                    {
                        "op": "ko",
                        "target_kind": "opponent_character_rested",
                        "optional": True,
                        "base_cost_lte": 1,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library(force=True)
    print(f"batch_al updated {n} card entries")


if __name__ == "__main__":
    main()
