#!/usr/bin/env python3
"""Batch R: ST30-001 family, optional rest DON, OP13-031/ST31-001 both-turn keywords."""

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

STRAW = "Straw Hat Crew|草帽一行人"
SUPER_OR_STRAW = "Supernovas|超新星|Straw Hat Crew|草帽一行人"
ACE = "Portgas.D.Ace|波特卡斯・D・艾斯"
LUFFY = "Monkey.D.Luffy|蒙其・D・魯夫"
RAYLEIGH = "Silvers Rayleigh|席爾巴斯・雷利"
SANJI = "Sanji|香吉士"
NAMI = "Nami|娜美"

MAY_REST_DON_COST = re.compile(
    r"可將\s*\d*\s*張?自己的咚‼卡置為休息狀態|"
    r"You may rest \d+ of your DON!!",
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


def _patch_optional_rest_don(ov_cards: dict, lib_cards: dict, catalog: dict) -> int:
    """Add optional:true on rest_don as_cost when paper says 可將…咚‼."""
    n = 0
    for cid, info in catalog.items():
        paper = _paper(catalog, cid)
        if not MAY_REST_DON_COST.search(paper):
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
                if o.get("op") == "rest_don" and o.get("as_cost") and not o.get("optional"):
                    o["optional"] = True
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
        "ST30-001",
        [
            {
                "timing": "your_turn",
                "summary": "If own Character base power≥7000: this Leader −2000",
                "ops": [{"op": "buff_self", "amount": -2000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_own_char_base_power_gte": 7000,
            },
            {
                "timing": "opponent_turn",
                "summary": "If own Character base power≥7000: this Leader −2000",
                "ops": [{"op": "buff_self", "amount": -2000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_own_char_base_power_gte": 7000,
            },
            {
                "timing": "opponent_turn",
                "summary": "[Opp Turn] All own Ace and Luffy +3000",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 3000,
                        "target_kind": "own_character",
                        "optional": False,
                        "all": True,
                        "name_contains": ACE,
                    },
                    {
                        "op": "buff",
                        "amount": 3000,
                        "target_kind": "own_character",
                        "optional": False,
                        "all": True,
                        "name_contains": LUFFY,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    nami_search = {
        "timing": "on_play",
        "summary": "Look top 5: add up to 1 Straw Hat other than Nami; rest bottom",
        "ops": [
            {
                "op": "search_deck",
                "name_contains": "",
                "trait_contains": STRAW,
                "top_n": 5,
                "max_add": 1,
                "order_bottom": True,
                "exclude_name": NAMI,
                "destination": "hand",
            }
        ],
        "status": "compiled",
        "confidence": 0.95,
    }
    n += _write(ov_cards, lib_cards, catalog, "EB02-017", [nami_search])
    n += _write(ov_cards, lib_cards, catalog, "OP01-016", [nami_search])

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP04-016",
        [
            {
                "timing": "counter_event",
                "summary": "May trash 1: own Leader/Character +3000 this battle",
                "ops": [
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
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
                "summary": "Opp Leader/Character −3000 this turn",
                "ops": [
                    {
                        "op": "buff",
                        "amount": -3000,
                        "optional": True,
                        "target_kind": "opponent_leader_or_character",
                        "always_choose": True,
                        "duration": "turn",
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
        "OP10-005",
        [
            {
                "timing": "your_turn",
                "summary": "[Your Turn] This Character +3000",
                "ops": [{"op": "buff_self", "amount": 3000}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "on_ko",
                "summary": "[On K.O.] Draw 1",
                "ops": [{"op": "draw", "count": 1}],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-015",
        [
            {
                "timing": "your_turn",
                "summary": "If given DON!! ≥2: this Character +2000",
                "ops": [{"op": "buff_self", "amount": 2000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_given_don_gte": 2,
            },
            {
                "timing": "opponent_turn",
                "summary": "If given DON!! ≥2: this Character +2000",
                "ops": [{"op": "buff_self", "amount": 2000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_given_don_gte": 2,
            },
            {
                "timing": "on_play",
                "summary": "May reveal 2 Events: play red power≤3000; attach up to 1 rested DON!!",
                "ops": [
                    {
                        "op": "reveal_hand",
                        "count": 2,
                        "optional": True,
                        "as_cost": True,
                        "card_type": "event",
                        "owner": "self",
                    },
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "power_lte": 3000,
                        "color": "red",
                        "from_zone": "hand",
                    },
                    {
                        "op": "attach_don",
                        "count": 1,
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
        "OP12-018",
        [
            {
                "timing": "counter_event",
                "summary": "Own Character or Rayleigh +2000 battle; may rest 1 DON!!: all opp −1000 turn",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "own_character",
                        "optional": True,
                        "include_leader_if_name": RAYLEIGH,
                        "duration": "battle",
                        "summary": "Own Character or Silvers Rayleigh +2000",
                    },
                    {
                        "op": "rest_don",
                        "count": 1,
                        "owner": "self",
                        "as_cost": True,
                        "optional": True,
                    },
                    {
                        "op": "buff",
                        "amount": -1000,
                        "target_kind": "opponent_leader_or_character",
                        "optional": False,
                        "all": True,
                        "duration": "turn",
                        "summary": "If DON!! rested: all opp Leader and Characters −1000",
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
        "OP12-037",
        [
            {
                "timing": "on_play",
                "summary": "May rest 3 DON!!: rest up to 2 opp Characters or DON!!",
                "ops": [
                    {"op": "rest_don", "count": 3, "owner": "self", "as_cost": True, "optional": True},
                    {"op": "rest_opponent_char_or_don", "count": 2, "optional": True},
                ],
                "status": "compiled",
                "confidence": 0.95,
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

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-031",
        [
            {
                "timing": "your_turn",
                "summary": "If Life≤1: gains Blocker",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "self",
                        "duration": "permanent",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 1,
            },
            {
                "timing": "opponent_turn",
                "summary": "If Life≤1: gains Blocker",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "self",
                        "duration": "permanent",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 1,
            },
            {
                "timing": "on_play",
                "summary": "May return 1 own Character: play cost≤5 rested from hand",
                "ops": [
                    {
                        "op": "return_to_hand",
                        "target_kind": "own_character",
                        "optional": True,
                        "as_cost": True,
                    },
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 5,
                        "as_rested": True,
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
        "OP13-040",
        [
            {
                "timing": "on_play",
                "summary": "May rest 2 DON!!: up to 2 opp rested cost≤7 skip next untap",
                "ops": [
                    {"op": "rest_don", "count": 2, "owner": "self", "as_cost": True, "optional": True},
                    {
                        "op": "skip_untap",
                        "count": 2,
                        "target_kind": "opponent_character_rested",
                        "cost_lte": 7,
                        "optional": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
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

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-019",
        [
            {
                "timing": "on_play",
                "summary": "Look top 4: add up to 1 Supernovas or Straw Hat Character",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": SUPER_OR_STRAW,
                        "top_n": 4,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "card_type": "character",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Draw 1",
                "ops": [{"op": "draw", "count": 1}],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST21-014",
        [
            {
                "timing": "when_attacking",
                "summary": "Attach up to 1 rested DON!! to Leader or Character",
                "ops": [
                    {
                        "op": "attach_don",
                        "count": 1,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                    }
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
        "ST21-017",
        [
            {
                "timing": "on_play",
                "summary": "Opp Character −5000; if own power≥6000, K.O. opp power≤2000",
                "ops": [
                    {
                        "op": "buff",
                        "amount": -5000,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "duration": "turn",
                    },
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "power_lte": 2000,
                        "require_own_char_power_gte": 6000,
                    },
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

    for base in ("ST30-012", "ST30-007"):
        if base == "ST30-012":
            abs_ = [
                {
                    "timing": "on_play",
                    "summary": "May rest 1 DON!!: gain Rush this turn",
                    "ops": [
                        {
                            "op": "rest_don",
                            "count": 1,
                            "owner": "self",
                            "as_cost": True,
                            "optional": True,
                        },
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
                {
                    "timing": "when_attacking",
                    "summary": "Rest up to 1 opp Blocker Character",
                    "ops": [
                        {
                            "op": "rest_opponent_character",
                            "count": 1,
                            "require_blocker": True,
                            "optional": True,
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                },
            ]
        else:
            abs_ = [
                {
                    "timing": "on_play",
                    "summary": "May rest 1 DON!!: gain Rush this turn",
                    "ops": [
                        {
                            "op": "rest_don",
                            "count": 1,
                            "owner": "self",
                            "as_cost": True,
                            "optional": True,
                        },
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
                {
                    "timing": "when_attacking",
                    "summary": "Opp Character −1000 this turn",
                    "ops": [
                        {
                            "op": "buff",
                            "amount": -1000,
                            "target_kind": "opponent_character",
                            "optional": True,
                            "duration": "turn",
                        }
                    ],
                    "status": "compiled",
                    "confidence": 0.95,
                },
            ]
        n += _write(ov_cards, lib_cards, catalog, base, abs_)

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST31-001",
        [
            {
                "timing": "your_turn",
                "summary": "[DON!! x2] gains Rush",
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
                "require_don_attached_gte": 2,
            },
            {
                "timing": "opponent_turn",
                "summary": "[DON!! x2] gains Rush",
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
                "require_don_attached_gte": 2,
            },
            {
                "timing": "on_play",
                "summary": "Draw 1; play up to 1 Straw Hat cost≤5 other than Sanji",
                "ops": [
                    {"op": "draw", "count": 1},
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 5,
                        "exclude_name": SANJI,
                        "trait_contains": STRAW,
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
        "ST31-005",
        [
            {
                "timing": "on_play",
                "summary": "Look top 5: add up to 1 Straw Hat; rest bottom",
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
                "summary": "Rest this Stage: attach up to 1 rested DON!! to own Luffy",
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

    n += _patch_optional_rest_don(ov_cards, lib_cards, catalog)

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library(force=True)
    print(f"batch_r wrote {n} card entries (+ optional rest_don scan)")


if __name__ == "__main__":
    main()
