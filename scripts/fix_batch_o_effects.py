#!/usr/bin/env python3
"""Batch O: fix user-reported card encodings + similar patterns.

Fixes:
- OP14-108: On Play was wrongly activate_timing(on_ko); wrong own-life gate
- OP07-107: Life≤1 must gate only play-this, not the draw
- OP16-102: Trigger must only activate On K.O. (no duplicate ops); name 蜂巢|Fullalead
- ST34-004: missing set_base_power 0; DON!!−4 then optional trash
- OP09-062 (+ rested DON!! gain peers): gain_don needs as_rested
- OP15-119: opponent Blocker watch via on_opp_blocker, not on_block
- OP09-078: Straw Hat trait gates buff only, not draw-2
- OP15-113: add_life is up-to (optional)
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

STRAW = "Straw Hat Crew|草帽一行人"
FULLALEAD = "Fullalead|蜂巢"

RESTED_GAIN = re.compile(
    r"(?:從咚‼?卡組追加|从咚‼?卡组追加|Add up to \d+ DON!! card from your DON!! deck).{0,40}"
    r"(?:休息狀態|休息状态|rest (?:it|them))",
    re.I,
)
RESTED_GAIN_ALT = re.compile(
    r"(?:追加最多\d+張休息狀態的咚|追加最多\d+张休息状态的咚|"
    r"Add up to \d+ DON!! card from your DON!! deck and rest)",
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


def _named(catalog: dict[str, Any], ov_cards: dict, lib_cards: dict) -> int:
    n = 0

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-108",
        [
            {
                "timing": "on_play",
                "summary": "If Leader multicolored and opp Life≤3: K.O. up to 1 opp Character with base power≤7000",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "base_power_lte": 7000,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_multicolor": True,
                "require_opp_life_lte": 3,
            },
            {
                "timing": "trigger",
                "summary": "Activate this card's [On Play] effect",
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
        "OP07-107",
        [
            {
                "timing": "trigger",
                "summary": "Draw 1; then if Life≤1, play this card",
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
                        "summary": "If Life≤1: play this card",
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
        "OP16-102",
        [
            {
                "timing": "on_ko",
                "summary": "Draw 1; play up to 1 Fullalead from hand or trash",
                "ops": [
                    {"op": "draw", "count": 1},
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "name_contains": FULLALEAD,
                        "from_zone": "hand_or_trash",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Activate this card's [On K.O.] effect",
                "ops": [{"op": "activate_timing", "timing": "on_ko"}],
                "status": "compiled",
                "confidence": 0.95,
            },
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
                "summary": "DON!!−4, may trash 1 hand: add up to 1 deck top to Life; then set up to 1 opp Character base power to 0 this turn",
                "ops": [
                    {"op": "return_don", "count": 4, "owner": "self", "as_cost": True},
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
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

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-062",
        [
            {
                "timing": "when_attacking",
                "summary": "May trash 1 Trigger from hand: add up to 1 rested DON!! from DON!! deck",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "require_trigger": True,
                    },
                    {"op": "gain_don", "count": 1, "as_rested": True, "optional": True},
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
        "OP09-078",
        [
            {
                "timing": "counter_event",
                "summary": "DON!!−2, may trash 1: if Straw Hat Leader, +4000 battle to own Leader/Character; then draw 2",
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
                        "duration": "battle",
                        "require_leader_trait": STRAW,
                    },
                    {"op": "draw", "count": 2},
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
        "OP15-113",
        [
            {
                "timing": "on_play",
                "summary": "May trash 1 hand: add up to 1 deck top to Life top",
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
            }
        ],
    )

    reveal_buff = [
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
            "summary": "+1000 per revealed Life card cost",
        },
    ]
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-119",
        [
            {
                "timing": "your_turn",
                "summary": "If DON!!≥6: this Character gains Rush",
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
                "summary": "If DON!!≥6: this Character gains Rush",
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
                "summary": "When opp plays Event: may reveal Life top; +1000 per cost this turn",
                "ops": list(reveal_buff),
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "your_turn",
                "summary": "When opp activates Blocker: may reveal Life top; +1000 per cost this turn",
                "ops": list(reveal_buff),
                "status": "compiled",
                "confidence": 0.95,
                "on_opp_blocker": True,
            },
            {
                "timing": "opponent_turn",
                "summary": "When opp activates Blocker: may reveal Life top; +1000 per cost this turn",
                "ops": list(reveal_buff),
                "status": "compiled",
                "confidence": 0.95,
                "on_opp_blocker": True,
            },
        ],
    )

    # Keep previously-good cards refreshed with clear summaries (no logic change).
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-058",
        [
            {
                "timing": "on_play",
                "summary": "If Life≤2: add up to 1 deck top to Life top",
                "ops": [{"op": "add_life", "count": 1, "optional": True, "position": "top"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 2,
            }
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-112",
        [
            {
                "timing": "trigger",
                "summary": "If Leader is multicolored: draw 2",
                "ops": [{"op": "draw", "count": 2}],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_multicolor": True,
            }
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
                "summary": "May Life→hand: if Straw Hat Leader add Life; then play up to 1 Sky Island cost≤5 from hand",
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
                        "trait_contains": "Sky Island|空島|空岛",
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
        "OP15-114",
        [
            {
                "timing": "on_play",
                "summary": "May flip Life top up: all opp Characters −2000 this turn; then K.O. all opp power≤0",
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
                "summary": "Once: attach up to 1 rested DON!! to 1 own Sky Island Leader/Character",
                "ops": [
                    {
                        "op": "attach_don",
                        "count": 1,
                        "as_rested": True,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "trait_contains": "Sky Island|空島|空岛",
                        "from_rested": True,
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
        "OP16-119",
        [
            {
                "timing": "on_play",
                "summary": "Look top 3; add up to 1 to Life top; rest to bottom in any order",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": "",
                        "top_n": 3,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "life",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Negate up to 1 opp Character this turn; then K.O. up to 1 opp cost≤5",
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
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "PRB02-012",
        [
            {
                "timing": "on_play",
                "summary": "Look top 5; reveal up to 1 Straw Hat other than Nami to hand; rest bottom",
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
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST29-004",
        [
            {
                "timing": "on_play",
                "summary": "Look top 4; reveal up to 1 Straw Hat to hand; rest bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": STRAW,
                        "top_n": 4,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "May trash 1 hand: play this card",
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
    return n


def _fix_rested_gain_don(catalog: dict[str, Any], ov_cards: dict, lib_cards: dict) -> int:
    """Any card whose paper adds rested DON!! from DON!! deck must set as_rested."""
    n = 0
    for cid in list(ov_cards.keys()) + [c for c in catalog if c not in ov_cards]:
        if cid not in catalog and cid not in ov_cards:
            continue
        if not re.match(r"^[A-Z0-9]+-\d+", str(cid)):
            continue
        paper = _paper(catalog, cid) if cid in catalog else ""
        # Prefer base paper for variants.
        base = re.sub(r"-(?:P|R)\d+$", "", cid)
        if not paper and base in catalog:
            paper = _paper(catalog, base)
        if not paper:
            continue
        if not (RESTED_GAIN.search(paper) or RESTED_GAIN_ALT.search(paper)):
            continue
        entry = ov_cards.get(cid) or lib_cards.get(cid)
        if not entry:
            continue
        abs_list = entry.get("abilities") or []
        changed = False
        new_abs: list[dict[str, Any]] = []
        for ab in abs_list:
            ab = dict(ab)
            ops = []
            for op in ab.get("ops") or []:
                op = dict(op)
                if op.get("op") == "gain_don" and not op.get("as_rested"):
                    op["as_rested"] = True
                    changed = True
                ops.append(op)
            ab["ops"] = ops
            new_abs.append(ab)
        if not changed:
            continue
        entry2 = normalize_card_entry(cid, {"version": 1, "abilities": new_abs})
        ov_cards[cid] = entry2
        lib_cards[cid] = {**entry2, "card_id": cid}
        n += 1
    return n


def main() -> int:
    ov_path, lib_path = library_paths()
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))
    ov_doc = json.loads(ov_path.read_text(encoding="utf-8"))
    lib_doc = json.loads(lib_path.read_text(encoding="utf-8"))
    ov_cards = ov_doc.setdefault("cards", {})
    lib_cards = lib_doc.setdefault("cards", {})

    n = _named(catalog, ov_cards, lib_cards)
    n += _fix_rested_gain_don(catalog, ov_cards, lib_cards)

    ov_doc["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    lib_doc["generated_at"] = ov_doc["generated_at"]
    ov_path.write_text(json.dumps(ov_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lib_path.write_text(json.dumps(lib_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    reload_effect_library()
    print(f"batch_o updated {n} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
