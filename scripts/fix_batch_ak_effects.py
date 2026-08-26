#!/usr/bin/env python3
"""Batch AK: Supernova / attach DON / DON×Blocker / source-power gate fixes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

SN = "Supernovas|超新星"
HEART = "Heart Pirates|哈特海賊團"
SH = "Straw Hat Crew|草帽一行人"
HAWKINS = "Basil Hawkins|巴吉魯・霍金斯|巴基尔・霍金斯"
LUFFY = "Monkey.D.Luffy|蒙其・D・魯夫|蒙其·D·鲁夫"


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

    # OP14-001 Law Leader.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-001",
        [
            {
                "timing": "activate_main",
                "summary": "Once: select 2 own Supernovas/Heart Pirates Characters; swap base power this turn",
                "ops": [
                    {
                        "op": "swap_base_power",
                        "count": 2,
                        "target_kind": "own_character",
                        "trait_any": [SN, HEART],
                        "duration": "turn",
                        "optional": False,
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

    # OP14-005 Killer — attach rested DON to Leader or Character.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-005",
        [
            {
                "timing": "activate_main",
                "summary": "Once: attach up to 1 rested DON!! to Leader or Character",
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
                "once": True,
                "cost_don": 0,
                "rest_self": False,
            },
        ],
    )

    # OP14-010 Hawkins.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-010",
        [
            {
                "timing": "on_ko",
                "summary": "Look 5: play up to 1 Supernovas Character power≤2000 other than Hawkins",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": SN,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": HAWKINS,
                        "destination": "play",
                        "card_type": "character",
                        "power_lte": 2000,
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP14-013 Luffy.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-013",
        [
            {
                "timing": "on_play",
                "summary": "Look 5: add up to 1 Supernovas other than Luffy",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": SN,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": LUFFY,
                        "destination": "hand",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "when_attacking",
                "summary": "Up to 1 opp Character −1000 this turn",
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
        ],
    )

    # ST21-003 Sanji.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST21-003",
        [
            {
                "timing": "on_play",
                "summary": "Up to 1 own Straw Hat Character power≥6000 gains Blockerless this turn",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blockerless",
                        "target_kind": "own_character",
                        "trait_contains": SH,
                        "power_gte": 6000,
                        "duration": "turn",
                        "optional": True,
                        "count": 1,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP14-004 Cavendish.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-004",
        [
            {
                "timing": "your_turn",
                "summary": "If this Character power≥5000, gains Rush",
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
                "require_source_power_gte": 5000,
            },
            {
                "timing": "opponent_turn",
                "summary": "If this Character power≥5000, gains Rush",
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
                "require_source_power_gte": 5000,
            },
        ],
    )

    # OP14-011 Bartolomeo — DON!!×2 Blocker both turns.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-011",
        [
            {
                "timing": "your_turn",
                "summary": "DON!!×2: gains Blocker",
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
                "require_don_attached_gte": 2,
            },
            {
                "timing": "opponent_turn",
                "summary": "DON!!×2: gains Blocker",
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
                "require_don_attached_gte": 2,
            },
        ],
    )

    # EB04-005 Law — cannot attack UNLESS opp has 2+ base≥5000 (engine inverts).
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-005",
        [
            {
                "timing": "your_turn",
                "summary": "Cannot attack unless opponent has 2+ Characters base power≥5000",
                "ops": [{"op": "cannot_attack", "target_kind": "self"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_opp_chars_base_power_gte": 5000,
                "require_opp_chars_count_gte": 2,
            },
        ],
    )

    # OP14-002 Uruki — gate on source power≥5000.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-002",
        [
            {
                "timing": "when_attacking",
                "summary": "If this power≥5000: draw 1; KO up to 1 opp base power≤3000",
                "ops": [
                    {"op": "draw", "count": 1},
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "base_power_lte": 3000,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_source_power_gte": 5000,
            },
        ],
    )

    # OP14-014 Kid.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-014",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Supernovas: play up to 1 red Character power≤2000 from hand",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "power_lte": 2000,
                        "color": "red",
                        "from_zone": "hand",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": SN,
            },
        ],
    )

    # OP14-016 Drake.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-016",
        [
            {
                "timing": "opponent_turn",
                "summary": "Once: if own Supernovas would leave by opp effect, may Leader −2000 instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "own_filtered",
                        "cost": "self_power_minus",
                        "amount": -2000,
                        "life_position": "top",
                        "trait_contains": SN,
                        "optional": True,
                        "apply_to": "leader",
                        "once": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
            {
                "timing": "when_attacking",
                "summary": "DON!!×1: up to 1 opp Character −2000 this turn",
                "ops": [
                    {
                        "op": "buff",
                        "amount": -2000,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "duration": "turn",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_attached_gte": 1,
            },
        ],
    )

    # OP14-015 Zoro — innate Rush + when attacking.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-015",
        [
            {
                "timing": "when_attacking",
                "summary": "Up to 1 opp Character −1000 this turn",
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
        ],
    )

    # OP14-009 Law — innate Rush; swap Leader + Character base power this battle.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-009",
        [
            {
                "timing": "on_opponent_attack",
                "summary": "Once: may trash 2: swap Leader and 1 Character base power this battle",
                "ops": [
                    {"op": "trash_hand", "count": 2, "optional": True, "as_cost": True, "owner": "self"},
                    {
                        "op": "swap_base_power",
                        "count": 2,
                        "target_kind": "own_leader_or_character",
                        "require_leader_and_character": True,
                        "duration": "battle",
                        "optional": False,
                        "include_leader": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
        ],
    )

    # OP09-118 / OP14-018 — reaffirm prior fixes.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-118",
        [
            {
                "timing": "your_turn",
                "summary": "On opp Blocker: if either Life is 0, you win",
                "ops": [{"op": "win_game"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_either_life_lte": 0,
                "on_opp_blocker": True,
            },
            {
                "timing": "opponent_turn",
                "summary": "On opp Blocker: if either Life is 0, you win",
                "ops": [{"op": "win_game"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_either_life_lte": 0,
                "on_opp_blocker": True,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-018",
        [
            {
                "timing": "counter_event",
                "summary": "If any Character power≥8000: own Leader/Character +4000 this battle",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 4000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "battle",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_field_char_power_gte": 8000,
            },
            {
                "timing": "trigger",
                "summary": "Play up to 1 red Character power≤2000 from hand",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "power_lte": 2000,
                        "color": "red",
                        "from_zone": "hand",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP14-019 — Supernovas OR Straw Hat Character.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-019",
        [
            {
                "timing": "on_play",
                "summary": "Look 4: add up to 1 Supernovas or Straw Hat Character",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": "",
                        "trait_any": [SN, SH],
                        "top_n": 4,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "card_type": "character",
                        "reveal_adds": True,
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

    # Similar: source power gates.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-006",
        [
            {
                "timing": "when_attacking",
                "summary": "If this power≥5000: up to 1 opp Character −2000 this turn",
                "ops": [
                    {
                        "op": "buff",
                        "amount": -2000,
                        "target_kind": "opponent_character",
                        "optional": True,
                        "duration": "turn",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_source_power_gte": 5000,
            },
        ],
    )
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-012",
        [
            {
                "timing": "when_attacking",
                "summary": "If this power≥5000: attach up to 2 rested DON!! to Leader or Character",
                "ops": [
                    {
                        "op": "attach_don",
                        "count": 2,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_source_power_gte": 5000,
            },
        ],
    )

    # Similar: P-004 DON×1 Blocker both turns.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "P-004",
        [
            {
                "timing": "your_turn",
                "summary": "DON!!×1: gains Blocker",
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
                "require_don_attached_gte": 1,
            },
            {
                "timing": "opponent_turn",
                "summary": "DON!!×1: gains Blocker",
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
                "require_don_attached_gte": 1,
            },
        ],
    )

    # Similar simple 「附加休息咚!!在領航或角色」with wrong target_kind=self.
    simple_attach = {
        "EB01-007": 1,
        "OP03-009": 1,
        "OP11-016": 1,
        "OP16-052": 1,
        "P-069": 1,
        "ST01-007": 1,
        "ST23-005": 1,
        "ST01-001": 1,
    }
    for cid, cnt in simple_attach.items():
        n += _write(
            ov_cards,
            lib_cards,
            catalog,
            cid,
            [
                {
                    "timing": "activate_main",
                    "summary": f"Once: attach up to {cnt} rested DON!! to Leader or Character",
                    "ops": [
                        {
                            "op": "attach_don",
                            "count": cnt,
                            "as_rested": True,
                            "from_rested": True,
                            "target_kind": "own_leader_or_character",
                            "optional": True,
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

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library()
    print(f"batch_ak updated entries≈{n}")


if __name__ == "__main__":
    main()
