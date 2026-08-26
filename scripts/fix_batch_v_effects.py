#!/usr/bin/env python3
"""Batch V: Navy hand-trash package, OP06-043/051, deny_blocker targets, blue Garp."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

NAVY = "Navy|海軍"
GARP = "Monkey.D.Garp|蒙其・D・卡普|蒙其·D·卡普"
SENGOKU = "Sengoku|戰國|战国"
TASHIGI = "Tashigi|達絲琪|达丝琪"


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

    # OP12-040 Kuzan leader: Navy-source hand trash → draw equal (both turns)
    draw_eq = {
        "op": "draw",
        "count": 1,
        "equal_trashed": True,
        "summary": "Draw equal to cards trashed",
    }
    kuzan = {
        "status": "compiled",
        "confidence": 0.95,
        "on_hand_trash_by_own_effect": True,
        "require_effect_source_trait": NAVY,
        "ops": [draw_eq],
    }
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-040",
        [
            {**kuzan, "timing": "your_turn", "summary": "When Navy effect trashes your hand: draw equal"},
            {**kuzan, "timing": "opponent_turn", "summary": "When Navy effect trashes your hand: draw equal"},
        ],
    )

    # EB04-022 — keep; assert opp hand bottom gate
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-022",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] May trash 2: if opp hand≥6, opp bottoms 2",
                "ops": [
                    {"op": "trash_hand", "count": 2, "optional": True, "as_cost": True, "owner": "self"},
                    {
                        "op": "opponent_hand_to_bottom",
                        "count": 2,
                        "optional": False,
                        "require_opp_hand_gte": 6,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "when_attacking",
                "summary": "[DON!! x1][When Attacking] May trash 1: opp Character −2000",
                "ops": [
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                    {
                        "op": "buff",
                        "amount": -2000,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "duration": "turn",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_attached_gte": 1,
            },
        ],
    )

    # EB04-026
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-026",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] Bottom up to 1 opp cost≤1 Character",
                "ops": [
                    {
                        "op": "return_to_bottom",
                        "count": 1,
                        "optional": True,
                        "target_kind": "opponent_character",
                        "cost_lte": 1,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "when_attacking",
                "summary": "[When Attacking] Draw 1 and trash 1 from hand",
                "ops": [
                    {"op": "draw", "count": 1},
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # EB04-028: trash always; Navy gate on deny_attack only
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-028",
        [
            {
                "timing": "on_play",
                "summary": "[Main] May trash 1: if Leader Navy, deny attack ≤10000 x2 until opp end",
                "ops": [
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                    {
                        "op": "deny_attack",
                        "count": 2,
                        "optional": True,
                        "target_kind": "opponent_character",
                        "power_lte": 10000,
                        "duration": "until_opp_turn_end",
                        "require_leader_trait": NAVY,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "[Trigger] Return up to 1 cost≤5 Character (either side)",
                "ops": [
                    {
                        "op": "return_to_hand",
                        "target_kind": "any_character",
                        "optional": True,
                        "cost_lte": 5,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP06-043: trash + bottom cost≤2 (either) as cost → self +3000
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP06-043",
        [
            {
                "timing": "activate_main",
                "summary": "[Once] May trash 1 and bottom cost≤2 Character: this +3000",
                "ops": [
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                    {
                        "op": "return_to_bottom",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "target_kind": "any_character",
                        "cost_lte": 2,
                    },
                    {"op": "buff_self", "amount": 3000, "duration": "turn"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "cost_don": 0,
                "rest_self": False,
            }
        ],
    )

    # OP06-050 Tashigi search
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP06-050",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] Look 5: add up to 1 Navy other than Tashigi",
                "ops": [
                    {
                        "op": "search_deck",
                        "trait_contains": NAVY,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": TASHIGI,
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            }
        ],
    )

    # OP06-051: trash 2 → opponent returns 1 of their Characters
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP06-051",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] May trash 2: opponent returns 1 of their Characters",
                "ops": [
                    {"op": "trash_hand", "count": 2, "optional": True, "as_cost": True, "owner": "self"},
                    {
                        "op": "return_to_hand",
                        "target_kind": "opponent_character",
                        "optional": False,
                        "chooser": "opponent",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            }
        ],
    )

    # OP06-058 already correct — reassert
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP06-058",
        [
            {
                "timing": "on_play",
                "summary": "[Main] Bottom up to 2 cost≤6 Characters (either)",
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
                "summary": "[Trigger] Bottom up to 1 cost≤5 Character (either)",
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

    # OP12-043 Kuzan char
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-043",
        [
            {
                "timing": "your_turn",
                "summary": "If hand≥5: this Character cost +1",
                "ops": [{"op": "grant_cost", "amount": 1, "target_kind": "self", "duration": "permanent"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_hand_gte": 5,
            },
            {
                "timing": "opponent_turn",
                "summary": "If hand≥5: this Character cost +1",
                "ops": [{"op": "grant_cost", "amount": 1, "target_kind": "self", "duration": "permanent"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_hand_gte": 5,
            },
            {
                "timing": "on_play",
                "summary": "[On Play] May trash 1: deny attack 1 opp Character until opp end",
                "ops": [
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                    {
                        "op": "deny_attack",
                        "count": 1,
                        "optional": True,
                        "target_kind": "opponent_character",
                        "duration": "until_opp_turn_end",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP12-044 Sakazuki
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-044",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] If Leader Navy: draw 2",
                "ops": [{"op": "draw", "count": 2}],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": NAVY,
            },
            {
                "timing": "activate_main",
                "summary": "[Once] May trash 1: attach 1 rested DON to Leader or Character",
                "ops": [
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
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
                "once": True,
                "cost_don": 0,
                "rest_self": False,
            },
        ],
    )

    # OP12-047 Sengoku
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-047",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] May trash 1: look 5, add up to 2 Navy other than Sengoku",
                "ops": [
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                    {
                        "op": "search_deck",
                        "trait_contains": NAVY,
                        "top_n": 5,
                        "max_add": 2,
                        "order_bottom": True,
                        "exclude_name": SENGOKU,
                        "reveal_adds": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            }
        ],
    )

    # OP12-051 Hina: targeted deny_blocker base cost ≤4
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-051",
        [
            {
                "timing": "activate_main",
                "summary": "May rest this and trash 1: up to 1 opp base cost≤4 cannot Blocker",
                "ops": [
                    {
                        "op": "rest_character",
                        "target_kind": "self",
                        "optional": True,
                        "as_cost": True,
                        "count": 1,
                    },
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                    {
                        "op": "deny_blocker",
                        "count": 1,
                        "optional": True,
                        "target_kind": "opponent_character",
                        "base_cost_lte": 4,
                        "duration": "turn",
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

    # OP12-056 Garp — blue Navy power≤8000
    garp_play = {
        "op": "play_from_hand",
        "count": 1,
        "card_type": "character",
        "optional": True,
        "power_lte": 8000,
        "exclude_name": GARP,
        "trait_contains": NAVY,
        "color": "blue",
        "from_zone": "hand",
    }
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-056",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] May trash 1: play blue Navy ≤8000 power other than Garp",
                "ops": [
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                    garp_play,
                ],
                "status": "compiled",
                "confidence": 0.95,
            }
        ],
    )

    # OP12-057
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-057",
        [
            {
                "timing": "counter_event",
                "summary": "[Counter] +4000 then trash 1",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 4000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "battle",
                    },
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "[Trigger] May trash 1: draw 1",
                "ops": [
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                    {"op": "draw", "count": 1},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP14-049 Jimbei (+ similar OP14-045 already rush)
    rush = {
        "op": "grant_keyword",
        "keyword": "rush",
        "target_kind": "self",
        "duration": "turn",
    }
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-049",
        [
            {
                "timing": "your_turn",
                "summary": "When hand trashed by effect: gain Rush this turn",
                "ops": [rush],
                "status": "compiled",
                "confidence": 0.95,
                "on_hand_trashed_by_effect": True,
            },
            {
                "timing": "opponent_turn",
                "summary": "When hand trashed by effect: gain Rush this turn",
                "ops": [rush],
                "status": "compiled",
                "confidence": 0.95,
                "on_hand_trashed_by_effect": True,
            },
            {
                "timing": "on_play",
                "summary": "[On Play] May rest 2 DON: draw 2 and return cost≤7 Character",
                "ops": [
                    {"op": "rest_don", "count": 2, "owner": "self", "as_cost": True, "optional": True},
                    {"op": "draw", "count": 2},
                    {
                        "op": "return_to_hand",
                        "target_kind": "any_character",
                        "optional": True,
                        "cost_lte": 7,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # Similar: OP14-045 rush on hand trash
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-045",
        [
            {
                "timing": "your_turn",
                "summary": "When hand trashed by effect: gain Rush",
                "ops": [rush],
                "status": "compiled",
                "confidence": 0.95,
                "on_hand_trashed_by_effect": True,
            },
            {
                "timing": "opponent_turn",
                "summary": "When hand trashed by effect: gain Rush",
                "ops": [rush],
                "status": "compiled",
                "confidence": 0.95,
                "on_hand_trashed_by_effect": True,
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

    # OP16-056 confirm
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-056",
        [
            {
                "timing": "activate_main",
                "summary": "Trash this: draw 2, deny attack cost≤9 until opp end",
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

    # ST33-001
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST33-001",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] May trash 1: draw 1",
                "ops": [
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                    {"op": "draw", "count": 1},
                ],
                "status": "compiled",
                "confidence": 0.95,
            }
        ],
    )

    # ST33-003
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST33-003",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] May trash 1: bottom up to 2 opp cost≤2",
                "ops": [
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                    {
                        "op": "return_to_bottom",
                        "count": 2,
                        "optional": True,
                        "target_kind": "opponent_character",
                        "cost_lte": 2,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            }
        ],
    )

    # ST33-004 Kizaru hand cost when hand trashed this turn
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST33-004",
        [
            {
                "timing": "hand_cost",
                "summary": "During turn hand trashed by effect: this card in hand −3 cost",
                "ops": [{"op": "hand_cost_reduce", "amount": -3}],
                "status": "compiled",
                "confidence": 0.95,
                "require_hand_trashed_by_effect_this_turn": True,
            }
        ],
    )

    # ST33-005 Garp — blue + Leader Navy
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST33-005",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] If Leader Navy: play blue Navy ≤8000 other than Garp",
                "ops": [garp_play],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": NAVY,
            }
        ],
    )

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library()
    print(f"batch_v wrote {n} card entries")


if __name__ == "__main__":
    main()
