#!/usr/bin/env python3
"""Batch T: ST21-001 attach targets, OP06-018 main, rush both turns, similar DON attach."""

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
EGG_OR_STRAW = "Egghead|蛋頭|Straw Hat Crew|草帽一行人"
SUPER_OR_STRAW = "Supernovas|超新星|Straw Hat Crew|草帽一行人"
LUFFY = "Monkey.D.Luffy|蒙其・D・魯夫|蒙其·D·鲁夫"
RAYLEIGH = "Silvers Rayleigh|席爾巴斯・雷利"
SANJI = "Sanji|香吉士"
ZORO = "Roronoa Zoro|羅羅亞・索隆"
NAMI = "Nami|娜美"
BONNEY = "Jewelry Bonney|珠寶・波妮"


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


def _attach2_rested(target_kind: str, **extra: Any) -> dict[str, Any]:
    op: dict[str, Any] = {
        "op": "attach_don",
        "count": 2,
        "as_rested": True,
        "from_rested": True,
        "target_kind": target_kind,
        "optional": True,
    }
    op.update(extra)
    return op


def main() -> None:
    ov_path, lib_path = library_paths()
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    ov = json.loads(ov_path.read_text())
    lib = json.loads(lib_path.read_text())
    ov_cards = ov.setdefault("cards", {})
    lib_cards = lib.setdefault("cards", {})
    n = 0

    # ST21-001: Characters only (not Leader)
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST21-001",
        [
            {
                "timing": "activate_main",
                "summary": "[DON!! x1][Once] Attach up to 2 rested DON!! to 1 own Character",
                "ops": [_attach2_rested("own_character")],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "cost_don": 0,
                "rest_self": False,
                "require_don_attached_gte": 1,
            }
        ],
    )

    # Similar: OP05-008 Leader or Character
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP05-008",
        [
            {
                "timing": "activate_main",
                "summary": "[DON!! x1][Once] Attach up to 2 rested DON!! to Leader or 1 Character",
                "ops": [_attach2_rested("own_leader_or_character")],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "cost_don": 0,
                "rest_self": False,
                "require_don_attached_gte": 1,
            }
        ],
    )

    # Similar: OP06-022 Characters only
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP06-022",
        [
            {
                "timing": "activate_main",
                "summary": "[Once] If opp Life≤3: attach up to 2 rested DON!! to 1 own Character",
                "ops": [_attach2_rested("own_character")],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "cost_don": 0,
                "rest_self": False,
                "require_opp_life_lte": 3,
            }
        ],
    )

    # ST21-009: Straw Hat Leader or Character + rested DON
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST21-009",
        [
            {
                "timing": "activate_main",
                "summary": "[Once] Attach up to 2 rested DON!! to 1 own Straw Hat Leader or Character",
                "ops": [_attach2_rested("own_leader_or_character", trait_contains=STRAW)],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "cost_don": 0,
                "rest_self": False,
            }
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-002",
        [
            {
                "timing": "on_play",
                "summary": "Look top 4: add up to 1 Egghead/Straw Hat other than Bonney",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": EGG_OR_STRAW,
                        "top_n": 4,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": BONNEY,
                        "destination": "hand",
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
        "OP01-016",
        [
            {
                "timing": "on_play",
                "summary": "Look top 5: add up to 1 Straw Hat other than Nami",
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
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP04-016",
        [
            {
                "timing": "counter_event",
                "summary": "May trash 1: own Leader/Character +3000 battle",
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
                        "target_kind": "opponent_leader_or_character",
                        "optional": True,
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
        "OP06-017",
        [
            {
                "timing": "on_play",
                "summary": "May Life top to hand: own Leader/Character +3000 this turn",
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
                        "op": "buff",
                        "amount": 3000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "turn",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "counter_event",
                "summary": "May Life top to hand: own Leader/Character +3000 this turn",
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
                        "op": "buff",
                        "amount": 3000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
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
        "OP06-018",
        [
            {
                "timing": "on_play",
                "summary": "+3000; if opp has power≥7000 Character, another +1000",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 3000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "turn",
                    },
                    {
                        "op": "buff",
                        "amount": 1000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "turn",
                        "require_opp_char_power_gte": 7000,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "K.O. up to 1 opp power≤5000",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "power_lte": 5000,
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
        "OP11-012",
        [
            {
                "timing": "on_opp_event",
                "summary": "[Your Turn][Once] When opp activates Event: all own Characters +2000 this turn",
                "ops": [
                    {
                        "op": "buff_all_own",
                        "amount": 2000,
                        "include_leader": False,
                        "duration": "turn",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "require_your_turn": True,
            }
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
                "summary": "If given DON!! ≥2: +2000",
                "ops": [{"op": "buff_self", "amount": 2000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_given_don_gte": 2,
            },
            {
                "timing": "opponent_turn",
                "summary": "If given DON!! ≥2: +2000",
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
                "summary": "Own Character or Rayleigh +2000 battle; may rest 1 DON!!: all opp −1000",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "own_character",
                        "optional": True,
                        "include_leader_if_name": RAYLEIGH,
                        "duration": "battle",
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
        "OP13-015",
        [
            {
                "timing": "activate_main",
                "summary": "Rest this: up to 1 own Luffy +2000 this turn",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "count": 1,
                        "name_contains": LUFFY,
                        "duration": "turn",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "cost_don": 0,
                "rest_self": True,
                "once": False,
            }
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
            }
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
        "ST21-015",
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
                "timing": "on_ko",
                "summary": "Play up to 1 red power≤6000 other than Zoro from hand",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "power_lte": 6000,
                        "exclude_name": ZORO,
                        "color": "red",
                        "from_zone": "hand",
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
                        "duration": "turn",
                        "per_own_chars": 1,
                        "per_own_trait": STRAW,
                        "include_leader": True,
                        "include_stage": True,
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
                "summary": "Look top 5: add up to 1 Straw Hat",
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

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library(force=True)
    print(f"batch_t wrote {n} card entries")


if __name__ == "__main__":
    main()
