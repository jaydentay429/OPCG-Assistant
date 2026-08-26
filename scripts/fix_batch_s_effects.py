#!/usr/bin/env python3
"""Batch S: Foxy package, OP13-076 given DON, ST34 optional trash cost, OP10-075 gate."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

FOXY = "Foxy Pirates|弗克西海賊團"
ITOMIMIZU = "Itomimizu|線蚯蚓"

DON_MAY_TRASH = re.compile(
    r"咚‼-\d+\s*,?\s*可以廢棄|"
    r"DON!!\s*[−\-]\d+\s*,?\s*you may trash",
    re.I,
)


def _paper(catalog: dict[str, Any], cid: str) -> str:
    info = catalog.get(cid) or {}
    return " ".join(
        str(info.get(k) or "")
        for k in ("effect", "effect_text", "text", "trigger", "effect_en", "trigger_en")
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


def _store(ov_cards: dict, lib_cards: dict, cid: str, abilities: list[dict[str, Any]]) -> None:
    entry = normalize_card_entry(cid, {"version": 1, "abilities": abilities})
    ov_cards[cid] = entry
    lib_cards[cid] = {**entry, "card_id": cid}


def _fix_don_may_trash_costs(ov_cards: dict, lib_cards: dict, catalog: dict) -> int:
    """DON!! −N, you may trash 1: … — trash is optional but must not cancel the then-clause."""
    n = 0
    for cid in list(catalog.keys()):
        if not DON_MAY_TRASH.search(_paper(catalog, cid)):
            continue
        prev = ov_cards.get(cid) or lib_cards.get(cid)
        if not prev:
            continue
        changed = False
        abs_ = []
        for a in prev.get("abilities") or []:
            a = dict(a)
            ops = []
            for o in a.get("ops") or []:
                o = dict(o)
                if o.get("op") == "trash_hand" and o.get("optional") and o.get("as_cost"):
                    # Keep optional pick; drop as_cost so skip does not wipe remaining ops.
                    o.pop("as_cost", None)
                    changed = True
                ops.append(o)
            a["ops"] = ops
            abs_.append(a)
        if changed:
            _store(ov_cards, lib_cards, cid, abs_)
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
        "OP07-059",
        [
            {
                "timing": "when_attacking",
                "summary": "DON!! −3: if 3+ Foxy Pirates, skip untap on opp rested Leader and up to 1 Character",
                "ops": [
                    {"op": "return_don", "count": 3, "owner": "self", "as_cost": True},
                    {
                        "op": "skip_untap",
                        "count": 1,
                        "target_kind": "leader",
                        "optional": False,
                        "require_rested": True,
                        "require_chars_trait": FOXY,
                        "require_chars_trait_gte": 3,
                    },
                    {
                        "op": "skip_untap",
                        "count": 1,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "require_chars_trait": FOXY,
                        "require_chars_trait_gte": 3,
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
        "EB01-061",
        [
            {
                "timing": "on_play",
                "summary": "Add up to 1 active DON!!",
                "ops": [{"op": "gain_don", "count": 1}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "when_attacking",
                "summary": "Copy up to 1 opp Character's power as this base power this turn",
                "ops": [
                    {
                        "op": "set_base_power_from_character",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "summary": "Choose a Character to copy power from",
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
        "EB04-033",
        [
            {
                "timing": "on_play",
                "summary": "DON!! −1: if 3+ Foxy Pirates, K.O. up to 1 base power≤6000",
                "ops": [
                    {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "base_power_lte": 6000,
                        "require_chars_trait": FOXY,
                        "require_chars_trait_gte": 3,
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
        "EB04-036",
        [
            {
                "timing": "on_play",
                "summary": "DON!! −1: if Leader Foxy, draw 2 trash 1; rest up to 1 opp cost≤9",
                "ops": [
                    {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                    {"op": "draw", "count": 2},
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "cost_lte": 9,
                        "optional": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": FOXY,
            },
            {
                "timing": "activate_main",
                "summary": "[Once] Add up to 1 rested DON!!",
                "ops": [{"op": "gain_don", "count": 1, "as_rested": True}],
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
        "EB04-037",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Foxy: look top 5, add up to 1 Foxy card",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": FOXY,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": FOXY,
            }
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP07-060",
        [
            {
                "timing": "activate_main",
                "summary": "[Once] If Leader Foxy and no other Itomimizu: add up to 1 rested DON!!",
                "ops": [{"op": "gain_don", "count": 1, "as_rested": True}],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "cost_don": 0,
                "rest_self": False,
                "require_leader_trait": FOXY,
                "require_no_other_name": ITOMIMIZU,
            }
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP07-066",
        [
            {
                "timing": "on_play",
                "summary": "If own DON!! ≤ opp DON!!: add up to 1 rested DON!!",
                "ops": [{"op": "gain_don", "count": 1, "as_rested": True}],
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
        "OP07-071",
        [
            {
                "timing": "opponent_turn",
                "summary": "If Leader Foxy: all opp Characters −1000",
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
                "require_leader_trait": FOXY,
            },
            {
                "timing": "activate_main",
                "summary": "[Once] Add up to 1 rested DON!!",
                "ops": [{"op": "gain_don", "count": 1, "as_rested": True}],
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
        "OP07-072",
        [
            {
                "timing": "on_play",
                "summary": "DON!! −1: search Foxy; play purple power≤4000 from hand",
                "ops": [
                    {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": FOXY,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                    },
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "power_lte": 4000,
                        "color": "purple",
                        "from_zone": "hand",
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
        "OP10-075",
        [
            {
                "timing": "activate_main",
                "summary": "May trash this: if own DON!! ≤ opp DON!!, draw 1",
                "ops": [
                    {
                        "op": "trash",
                        "target_kind": "self",
                        "optional": True,
                        "as_cost": True,
                        "summary": "Trash this Character",
                    },
                    {
                        "op": "draw",
                        "count": 1,
                        "require_don_field_deficit_gte": 0,
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

    # Similar: trash self then conditional gain_don
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP07-074",
        [
            {
                "timing": "activate_main",
                "summary": "May trash this: if Leader Foxy, add up to 1 rested DON!!",
                "ops": [
                    {
                        "op": "trash",
                        "target_kind": "self",
                        "optional": True,
                        "as_cost": True,
                        "summary": "Trash this Character",
                    },
                    {
                        "op": "gain_don",
                        "count": 1,
                        "as_rested": True,
                        "require_leader_trait": FOXY,
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

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-076",
        [
            {
                "timing": "on_play",
                "summary": "May rest 5 DON!!: if any given DON!!, opp Character −8000",
                "ops": [
                    {
                        "op": "rest_don",
                        "count": 5,
                        "owner": "self",
                        "as_cost": True,
                        "optional": True,
                    },
                    {
                        "op": "buff",
                        "amount": -8000,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "count": 1,
                        "duration": "turn",
                        "require_given_don_gte": 1,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "counter_event",
                "summary": "May trash 1: own Leader/Character +3000 battle",
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
                "summary": "DON!! −2: draw 1; rest up to 1 opp power≤5000",
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
                "summary": "Own Leader/Character +1000 battle; if field DON!! ≤6, draw 1",
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
                "summary": "If field DON!! ≥8: rest up to 1 opp cost≤5",
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
            }
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST34-004",
        [
            {
                "timing": "on_play",
                "summary": "DON!! −4, may trash 1: add Life top; set up to 1 opp base power to 0 this turn",
                "ops": [
                    {"op": "return_don", "count": 4, "owner": "self", "as_cost": True},
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "owner": "self",
                    },
                    {"op": "add_life", "count": 1, "optional": True, "position": "top"},
                    {
                        "op": "set_base_power",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "amount": 0,
                        "duration": "turn",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            }
        ],
    )

    n += _fix_don_may_trash_costs(ov_cards, lib_cards, catalog)

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library(force=True)
    print(f"batch_s wrote {n} card entries (+ don/may-trash scan)")


if __name__ == "__main__":
    main()
