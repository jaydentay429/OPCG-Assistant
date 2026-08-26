#!/usr/bin/env python3
"""Batch AJ: Koala / Revolutionary Army / Then-if / play-watcher effect fixes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

RA = "Revolutionary Army|革命軍"
KOALA = "Koala|可亞拉|可亚拉"
ROBIN = "Nico Robin|妮可・羅賓|妮可・罗宾"
LUFFY = "Monkey.D.Luffy|蒙其・D・魯夫|蒙其·D·鲁夫"
KOALA_LUFFY = f"{KOALA}|{LUFFY}"


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

    # OP12-081 Koala Leader.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-081",
        [
            {
                "timing": "when_attacking",
                "summary": "When this Leader attacks opp Leader, if 2+ own Characters cost≥8, draw 1",
                "ops": [{"op": "draw", "count": 1}],
                "status": "compiled",
                "confidence": 0.95,
                "vs_leader_only": True,
                "require_chars_base_cost_gte": 8,
                "require_chars_base_cost_count_gte": 2,
            },
            {
                "timing": "on_opponent_play",
                "summary": "Once: may force opp Life top→hand when they play base cost≥8 or via Character effect",
                "ops": [
                    {
                        "op": "life_to_hand",
                        "count": 1,
                        "position": "top",
                        "optional": False,
                        "owner": "opponent",
                        "hand_owner": "life_owner",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "optional": True,
                "require_played_base_cost_gte": 8,
                "or_played_by_character_effect": True,
            },
        ],
    )

    # OP09-108 Kuma trigger.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-108",
        [
            {
                "timing": "trigger",
                "summary": "If Leader RA and total Life≤5, play this card",
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
                "require_total_life_lte": 5,
                "require_leader_trait": RA,
            },
        ],
    )

    # OP12-112 BABY5.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-112",
        [
            {
                "timing": "trigger",
                "summary": "If Leader multicolored, draw 2",
                "ops": [{"op": "draw", "count": 2}],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_multicolor": True,
            },
        ],
    )

    # EB04-058 Borsalino — innate Blocker + on_play.
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

    # OP12-119 Kuma — grant_cost until opp end.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-119",
        [
            {
                "timing": "on_play",
                "summary": "May trash 1: add Life top; then this +2 cost until opp end",
                "ops": [
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
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
                "summary": "Opponent's turn: add up to 1 deck top to Life top",
                "ops": [{"op": "add_life", "count": 1, "optional": True, "position": "top"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_opponent_turn": True,
            },
        ],
    )

    # OP14-108 Rayleigh.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-108",
        [
            {
                "timing": "on_play",
                "summary": "If Leader multicolor and opp Life≤3, KO up to 1 opp base power≤7000",
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
                "require_opp_life_lte": 3,
                "require_leader_multicolor": True,
            },
            {
                "timing": "trigger",
                "summary": "Activate this card's On Play effect",
                "ops": [{"op": "activate_timing", "timing": "on_play"}],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP12-086 Koala — RA other than Koala OR Nico Robin.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-086",
        [
            {
                "timing": "on_play",
                "summary": "If Leader RA: look 3, add up to 1 RA other than Koala or Nico Robin; trash rest",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": ROBIN,
                        "trait_contains": RA,
                        "top_n": 3,
                        "max_add": 1,
                        "trash_rest": True,
                        "order_bottom": False,
                        "exclude_name": KOALA,
                        "destination": "hand",
                        "name_or_trait": True,
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": RA,
            },
        ],
    )

    # EB03-042 Koala.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB03-042",
        [
            {
                "timing": "your_turn",
                "summary": "If Leader RA: +4 cost",
                "ops": [{"op": "grant_cost", "amount": 4, "target_kind": "self"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": RA,
            },
            {
                "timing": "opponent_turn",
                "summary": "If Leader RA: +4 cost",
                "ops": [{"op": "grant_cost", "amount": 4, "target_kind": "self"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": RA,
            },
            {
                "timing": "on_ko",
                "summary": "Opp turn: play up to 1 RA cost≤6 other than Koala or Nico Robin cost≤6 from hand/trash",
                "ops": [
                    {
                        "op": "choose_one",
                        "chooser": "self",
                        "options": [
                            {
                                "id": "opt0",
                                "label": "Play RA Character cost≤6 other than Koala",
                                "ops": [
                                    {
                                        "op": "play_from_hand",
                                        "count": 1,
                                        "card_type": "character",
                                        "optional": True,
                                        "cost_lte": 6,
                                        "exclude_name": KOALA,
                                        "trait_contains": RA,
                                        "from_zone": "hand_or_trash",
                                    }
                                ],
                            },
                            {
                                "id": "opt1",
                                "label": "Play Nico Robin cost≤6",
                                "ops": [
                                    {
                                        "op": "play_from_hand",
                                        "count": 1,
                                        "card_type": "character",
                                        "optional": True,
                                        "cost_lte": 6,
                                        "name_contains": ROBIN,
                                        "from_zone": "hand_or_trash",
                                    }
                                ],
                            },
                        ],
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_opponent_turn": True,
            },
        ],
    )

    # OP12-089 Hack.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-089",
        [
            {
                "timing": "your_turn",
                "summary": "If Leader RA: Blocker and +4 cost",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "self",
                        "duration": "permanent",
                    },
                    {"op": "grant_cost", "amount": 4, "target_kind": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": RA,
            },
            {
                "timing": "opponent_turn",
                "summary": "If Leader RA: Blocker and +4 cost",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "self",
                        "duration": "permanent",
                    },
                    {"op": "grant_cost", "amount": 4, "target_kind": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": RA,
            },
            {
                "timing": "on_ko",
                "summary": "If Leader RA: KO up to 1 opp base cost≤4",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "count": 1,
                        "base_cost_lte": 4,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": RA,
            },
        ],
    )

    # OP12-093 Morley.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-093",
        [
            {
                "timing": "your_turn",
                "summary": "If Leader RA: +4 cost",
                "ops": [
                    {
                        "op": "grant_cost",
                        "amount": 4,
                        "target_kind": "self",
                        "duration": "permanent",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": RA,
            },
            {
                "timing": "opponent_turn",
                "summary": "If Leader RA: +4 cost",
                "ops": [
                    {
                        "op": "grant_cost",
                        "amount": 4,
                        "target_kind": "self",
                        "duration": "permanent",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": RA,
            },
        ],
    )

    # OP12-087 Robin.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-087",
        [
            {
                "timing": "your_turn",
                "summary": "If Leader Koala or Luffy: Blocker and +3 cost",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "self",
                        "duration": "permanent",
                    },
                    {"op": "grant_cost", "amount": 3, "target_kind": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_name": KOALA_LUFFY,
            },
            {
                "timing": "opponent_turn",
                "summary": "If Leader Koala or Luffy: Blocker and +3 cost",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "self",
                        "duration": "permanent",
                    },
                    {"op": "grant_cost", "amount": 3, "target_kind": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_name": KOALA_LUFFY,
            },
            {
                "timing": "on_play",
                "summary": "May trash 1: if opp hand≥5, opp trashes 2",
                "ops": [
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                    {
                        "op": "trash_hand",
                        "count": 2,
                        "optional": False,
                        "owner": "opponent",
                        "require_opp_hand_gte": 5,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP12-094 Dragon — trash_to_bottom 3 RA as cost; then if Leader RA play cost≤6.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-094",
        [
            {
                "timing": "on_play",
                "summary": "May place 3 RA from trash under deck: if Leader RA, play up to 1 cost≤6 from trash",
                "ops": [
                    {
                        "op": "trash_to_bottom",
                        "count": 3,
                        "optional": True,
                        "owner": "self",
                        "card_type": "any",
                        "order_any": True,
                        "as_cost": True,
                        "trait_contains": RA,
                    },
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 6,
                        "from_zone": "trash",
                        "require_leader_trait": RA,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP12-097 Captains Assembled.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-097",
        [
            {
                "timing": "on_play",
                "summary": "Look 3: add up to 1 RA other than this Event; trash rest",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": RA,
                        "top_n": 3,
                        "max_add": 1,
                        "trash_rest": True,
                        "order_bottom": False,
                        "exclude_name": "Captains Assembled|軍隊長集結|军队长集结",
                        "destination": "hand",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Activate this card's Main effect",
                "ops": [
                    {
                        "op": "activate_timing",
                        "timing": "on_play",
                        "summary": "Activate this card's Main effect",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP12-098 — +2000; then if own RA cost≥8, same card +2000.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-098",
        [
            {
                "timing": "counter_event",
                "summary": "+2000; if own RA Character cost≥8, same card +2000 more",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "battle",
                    },
                    {
                        "op": "buff",
                        "amount": 2000,
                        "same_target_as_prior": True,
                        "duration": "battle",
                        "require_own_char_cost_gte": 8,
                        "require_chars_trait": RA,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Draw 1 and trash 1 from deck top",
                "ops": [
                    {"op": "draw", "count": 1},
                    {"op": "trash_deck_top", "count": 1, "optional": False},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # Similar: OP06-038 already correct; similar Dragon-like trash_to_bottom costs already OK.

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library()
    print(f"batch_aj updated entries≈{n}")


if __name__ == "__main__":
    main()
