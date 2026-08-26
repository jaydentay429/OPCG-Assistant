#!/usr/bin/env python3
"""Batch AF: Sabo / Thriller Bark / life-gate / Egghead effect fixes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

THRILLER = "Thriller Bark Pirates|恐怖三桅帆船海賊團"
REV = "Revolutionary Army|革命軍"
SKY = "Sky Island|空島|空岛"
EGG_STRAW = "Egghead|蛋頭|Straw Hat Crew|草帽一行人"
HOGBACK = "Dr. Hogback|Dr.Hogback|赫古巴庫醫生"
BONNEY = "Jewelry Bonney|珠寶・波妮"
SABO_ACE_LUFFY = (
    "Sabo|薩波|萨波|Portgas.D.Ace|波特卡斯・D・艾斯|波特卡斯·D·艾斯|"
    "Monkey.D.Luffy|蒙其・D・魯夫|蒙其·D·鲁夫"
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


def _bilingual_rev(obj: dict[str, Any]) -> bool:
    changed = False
    for key in ("trait_contains", "require_leader_trait"):
        val = obj.get(key)
        if val == "Revolutionary Army":
            obj[key] = REV
            changed = True
    return changed


def main() -> None:
    ov_path, lib_path = library_paths()
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    ov = json.loads(ov_path.read_text())
    lib = json.loads(lib_path.read_text())
    ov_cards = ov.setdefault("cards", {})
    lib_cards = lib.setdefault("cards", {})
    n = 0

    # ST13-001 Sabo Leader — place cost≥3 power≥7000 Character face-up on Life: buff +2000.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST13-001",
        [
            {
                "timing": "activate_main",
                "summary": "[DON!! x1] Once: place cost≥3 power≥7000 Character face-up on Life: +2000 until next turn",
                "ops": [
                    {
                        "op": "place_on_life",
                        "count": 1,
                        "owner": "self",
                        "position": "top",
                        "face": "up",
                        "target_kind": "own_character",
                        "optional": True,
                        "as_cost": True,
                        "cost_gte": 3,
                        "power_gte": 7000,
                    },
                    {
                        "op": "buff",
                        "amount": 2000,
                        "optional": True,
                        "count": 1,
                        "target_kind": "own_character",
                        "duration": "next_turn",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "cost_don": 0,
                "rest_self": False,
                "require_don_attached_gte": 1,
            },
        ],
    )

    # OP14-102 Kumashi — Trigger play Thriller Bark ≤4 rested from trash.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-102",
        [
            {
                "timing": "trigger",
                "summary": "Play up to 1 Thriller Bark cost≤4 from trash rested",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 4,
                        "trait_contains": THRILLER,
                        "as_rested": True,
                        "from_zone": "trash",
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
                "summary": "If opp Life≤3: add up to 1 deck top to Life top",
                "ops": [{"op": "add_life", "count": 1, "optional": True, "position": "top"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_opp_life_lte": 3,
            },
            {
                "timing": "trigger",
                "summary": "If opp Life≤3: play this card",
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

    # OP09-108 Bartholomew Kuma — Rev Army + total Life≤5.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-108",
        [
            {
                "timing": "trigger",
                "summary": "If Leader Rev Army and total Life≤5: play this",
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
                "require_leader_trait": REV,
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
                "summary": "If Leader multicolor: draw 2",
                "ops": [{"op": "draw", "count": 2}],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_multicolor": True,
            },
        ],
    )

    # OP14-110 Dr. Hogback.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-110",
        [
            {
                "timing": "on_ko",
                "summary": "Play up to 1 Trigger Character cost≤4 other than Hogback from trash",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 4,
                        "exclude_name": HOGBACK,
                        "from_zone": "trash",
                        "require_trigger": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Play up to 1 Thriller Bark cost≤4 from trash rested",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 4,
                        "trait_contains": THRILLER,
                        "as_rested": True,
                        "from_zone": "trash",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP14-111 Perona.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-111",
        [
            {
                "timing": "on_play",
                "summary": "Deny attack opp cost≤6 until opp end",
                "ops": [
                    {
                        "op": "deny_attack",
                        "count": 1,
                        "optional": True,
                        "target_kind": "opponent_character",
                        "cost_lte": 6,
                        "duration": "until_opp_turn_end",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "on_ko",
                "summary": "Deny attack opp cost≤6 until opp end",
                "ops": [
                    {
                        "op": "deny_attack",
                        "count": 1,
                        "optional": True,
                        "target_kind": "opponent_character",
                        "cost_lte": 6,
                        "duration": "until_opp_turn_end",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Play up to 1 Thriller Bark cost≤4 from trash rested",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 4,
                        "trait_contains": THRILLER,
                        "as_rested": True,
                        "from_zone": "trash",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP15-113 Zoro.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-113",
        [
            {
                "timing": "on_play",
                "summary": "May trash 1: add up to 1 deck top to Life",
                "ops": [
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                    {"op": "add_life", "count": 1, "optional": True, "position": "top"},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # EB03-053 Nami — single on_play (attach then conditional life steal).
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB03-053",
        [
            {
                "timing": "on_play",
                "summary": "Attach up to 1 rested DON!! to Leader; then if opp Life≥3, take opp Life top to hand",
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
                "summary": "May flip Life top face-up: play up to 1 Character power≤6000 from hand",
                "ops": [
                    {"op": "flip_life", "face": "up", "position": "top", "optional": True, "as_cost": True},
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

    # OP15-114 Wyper.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-114",
        [
            {
                "timing": "on_play",
                "summary": "May flip Life face-up: all opp Characters −2000 then KO power≤0",
                "ops": [
                    {"op": "flip_life", "face": "up", "position": "top", "optional": True, "as_cost": True},
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
                "summary": "Once: attach up to 1 rested DON!! to Sky Island Leader/Character",
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

    # OP14-108 Rayleigh.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-108",
        [
            {
                "timing": "on_play",
                "summary": "If multicolor Leader and opp Life≤3: KO up to 1 opp base power≤7000",
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

    # OP14-104 Moria.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-104",
        [
            {
                "timing": "on_play",
                "summary": "Choose: Thriller Bark ≤4 from trash to Life face-up or play it",
                "ops": [
                    {
                        "op": "choose_one",
                        "chooser": "self",
                        "optional": True,
                        "options": [
                            {
                                "id": "to_life",
                                "label": "以正面加入生命組",
                                "ops": [
                                    {
                                        "op": "add_from_trash",
                                        "count": 1,
                                        "optional": True,
                                        "trait_contains": THRILLER,
                                        "card_type": "character",
                                        "cost_lte": 4,
                                        "destination": "life",
                                        "face": "up",
                                        "position": "top",
                                    }
                                ],
                            },
                            {
                                "id": "play",
                                "label": "登場",
                                "ops": [
                                    {
                                        "op": "play_from_hand",
                                        "count": 1,
                                        "card_type": "character",
                                        "optional": True,
                                        "cost_lte": 4,
                                        "trait_contains": THRILLER,
                                        "from_zone": "trash",
                                    }
                                ],
                            },
                        ],
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Play up to 1 Character cost≤4 from trash",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 4,
                        "from_zone": "trash",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # EB04-002 Bonney.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-002",
        [
            {
                "timing": "on_play",
                "summary": "Look 4: add up to 1 Egghead/Straw Hat other than Bonney",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": EGG_STRAW,
                        "top_n": 4,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": BONNEY,
                        "destination": "hand",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP13-016 Garp.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-016",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Sabo/Ace/Luffy: look 4, add up to 1 cost≥3",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": "",
                        "top_n": 4,
                        "max_add": 1,
                        "order_bottom": True,
                        "cost_gte": 3,
                        "destination": "hand",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_name": SABO_ACE_LUFFY,
            },
        ],
    )

    # EB04-007 Zoro.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-007",
        [
            {
                "timing": "on_play",
                "summary": "Leader +2000 until opp end",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "leader",
                        "optional": False,
                        "duration": "until_opp_turn_end",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "Once: if opp has Character power≥8000, gain Rush: Character",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "rush_character",
                        "target_kind": "self",
                        "duration": "turn",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "cost_don": 0,
                "rest_self": False,
                "require_opp_char_power_gte": 8000,
            },
        ],
    )

    # Similar: Revolutionary Army EN-only → bilingual.
    rev_n = 0
    for store in (ov_cards, lib_cards):
        for cid, entry in list(store.items()):
            changed = False
            for ab in entry.get("abilities") or []:
                if _bilingual_rev(ab):
                    changed = True
                for op in ab.get("ops") or []:
                    if _bilingual_rev(op):
                        changed = True
            if changed:
                store[cid] = normalize_card_entry(cid, entry)
                rev_n += 1
    n += rev_n // 2

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library()
    print(f"batch_af updated entries≈{n}")


if __name__ == "__main__":
    main()
