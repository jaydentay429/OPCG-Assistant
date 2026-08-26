#!/usr/bin/env python3
"""Batch X: Hancock/Kuja package, Perfume Feet deny-blocker, look+attach, etc."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

AMAZON_KUJA = "Amazon Lily|亞馬遜百合|Kuja Pirates|九蛇海賊團"
KUJA = "Kuja Pirates|九蛇海賊團"
WARLORDS = "The Seven Warlords of the Sea|王下七武海"
THRILLER = "Thriller Bark Pirates|恐怖三桅帆船海賊團"


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


def _ko_life_ab() -> list[dict[str, Any]]:
    """OP14-041: DON×1 once when own Amazon/Kuja base≥5000 is KO'd → take opp life top."""
    body = {
        "once": True,
        "require_don_attached_gte": 1,
        "on_own_trait_ko": AMAZON_KUJA,
        "require_victim_base_power_gte": 5000,
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
        "status": "compiled",
        "confidence": 0.95,
        "summary": "[DON!!×1][Once] When own Amazon/Kuja base≥5000 KO'd: take opp Life top",
    }
    return [
        {"timing": "your_turn", **body},
        {"timing": "opponent_turn", **body},
    ]


def main() -> None:
    ov_path, lib_path = library_paths()
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    ov = json.loads(ov_path.read_text())
    lib = json.loads(lib_path.read_text())
    ov_cards = ov.setdefault("cards", {})
    lib_cards = lib.setdefault("cards", {})
    n = 0

    # OP14-041 Hancock Leader
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-041",
        [
            {
                "timing": "opponent_turn",
                "summary": "[Opp Turn] When you play a Character, draw 1",
                "ops": [{"op": "draw", "count": 1}],
                "status": "compiled",
                "confidence": 0.95,
                "on_own_play_character": True,
            },
            *_ko_life_ab(),
        ],
    )

    # EB04-058 — already correct (life≤2 → add life); reaffirm
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-058",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] If Life≤2: add up to 1 Life top",
                "ops": [{"op": "add_life", "count": 1, "optional": True, "position": "top"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 2,
            },
        ],
    )

    # OP06-058 — bilateral bottom (no ownership)
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP06-058",
        [
            {
                "timing": "on_play",
                "summary": "[Main] Bottom up to 2 Characters cost≤6 (either side)",
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
                "summary": "[Trigger] Bottom up to 1 Character cost≤5 (either side)",
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

    # OP06-106 Hiyori — life top/bottom as cost → hand to life top
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP06-106",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] May take Life top/bottom: put 1 hand on Life top",
                "ops": [
                    {
                        "op": "life_to_hand",
                        "count": 1,
                        "position": "top_or_bottom",
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {"op": "hand_to_life", "count": 1, "optional": True, "position": "top"},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP06-115 — counter + trigger life0
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP06-115",
        [
            {
                "timing": "counter_event",
                "summary": "[Counter] May trash 1 hand: +3000 battle to own Leader/Character",
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
                "summary": "[Trigger] If Life=0: may add Life top, then trash 1 hand",
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

    # OP07-057 Perfume Feet + similar OP12-077
    perfume = [
        {
            "timing": "on_play",
            "summary": "[Main] Up to 1 own Warlords Leader/Character +2000; deny Blocker when it attacks",
            "ops": [
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "own_leader_or_character",
                    "trait_contains": WARLORDS,
                    "duration": "turn",
                    "optional": True,
                    "also_deny_blocker_when_attacks": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "[Trigger] Draw 1",
            "ops": [{"op": "draw", "count": 1}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ]
    n += _write(ov_cards, lib_cards, catalog, "OP07-057", perfume)

    law_buff = [
        {
            "timing": "on_play",
            "summary": "[Main] Up to 1 own Law +2000; deny Blocker when it attacks",
            "ops": [
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "own_character",
                    "name_contains": "Trafalgar Law|托拉法爾加・羅|托拉法尔加・罗",
                    "duration": "turn",
                    "optional": True,
                    "also_deny_blocker_when_attacks": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "[Trigger] Draw 1",
            "ops": [{"op": "draw", "count": 1}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ]
    n += _write(ov_cards, lib_cards, catalog, "OP12-077", law_buff)

    # OP11-054 Nami — multicolor draw 3 place 2
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-054",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] If Leader multicolor: draw 3, place 2 hand top/bottom",
                "ops": [
                    {"op": "draw", "count": 3},
                    {
                        "op": "hand_to_deck",
                        "count": 2,
                        "position": "top_or_bottom",
                        "optional": False,
                        "owner": "self",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_multicolor": True,
            },
        ],
    )

    # OP14-104 Moria
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-104",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] Thriller Bark cost≤4 from trash: Life face-up OR play",
                "ops": [
                    {
                        "op": "choose_one",
                        "chooser": "self",
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
                "summary": "[Trigger] Play up to 1 Character cost≤4 from trash",
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

    # OP14-105 Gorgon Sisters — reveal 3 Amazon/Kuja → attach 1 rested DON each to Leader+all chars
    gorgon = [
        {
            "timing": "activate_main",
            "summary": "[Once] Reveal 3 Amazon/Kuja from hand: rested DON!!×1 to Leader and all Characters",
            "ops": [
                {
                    "op": "reveal_hand",
                    "count": 3,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                    "trait_contains": AMAZON_KUJA,
                },
                {
                    "op": "attach_don",
                    "count": 1,
                    "as_rested": True,
                    "from_rested": True,
                    "target_kind": "own_leader_or_character",
                    "all": True,
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
            "cost_don": 0,
            "rest_self": False,
        },
        {
            "timing": "trigger",
            "summary": "[Trigger] If Leader is Kuja: play this",
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
            "require_leader_trait": KUJA,
        },
    ]
    n += _write(ov_cards, lib_cards, catalog, "OP14-105", gorgon)

    # OP14-107 Shakuyaku — opp Life≤3 only (not own)
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-107",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] If opp Life≤3: draw 2, trash 2 hand",
                "ops": [
                    {"op": "draw", "count": 2},
                    {"op": "trash_hand", "count": 2, "optional": False, "owner": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_opp_life_lte": 3,
            },
            {
                "timing": "trigger",
                "summary": "[Trigger] If Leader is Kuja: play this",
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
                "require_leader_trait": KUJA,
            },
        ],
    )

    # OP14-112 Hancock
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-112",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] If Leader Warlords: add Life top, then take opp Life top",
                "ops": [
                    {"op": "add_life", "count": 1, "optional": True, "position": "top"},
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
                "require_leader_trait": WARLORDS,
            },
            {
                "timing": "trigger",
                "summary": "[Trigger] Play up to 1 hand Character power≤6000 with Trigger",
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

    # OP14-114 Ran — attach rested DON to Kuja Leader/Character
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-114",
        [
            {
                "timing": "activate_main",
                "summary": "[Once] Give up to 1 rested DON!! to 1 own Kuja Leader/Character",
                "ops": [
                    {
                        "op": "attach_don",
                        "count": 1,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "own_leader_or_character",
                        "trait_contains": KUJA,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "cost_don": 0,
                "rest_self": False,
            },
            {
                "timing": "trigger",
                "summary": "[Trigger] If Leader is Kuja: play this",
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
                "require_leader_trait": KUJA,
            },
        ],
    )

    # OP15-113 Zoro
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-113",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] May trash 1 hand: add Life top",
                "ops": [
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                    {"op": "add_life", "count": 1, "optional": True, "position": "top"},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP16-113 Marigold — Blocker when Life≤2 both turns
    blocker_life = {
        "require_life_lte": 2,
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
        "summary": "If Life≤2: this Character gains Blocker",
    }
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-113",
        [
            {
                "timing": "trigger",
                "summary": "[Trigger] If Leader is Kuja: play this",
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
                "require_leader_trait": KUJA,
            },
            {"timing": "your_turn", **blocker_life},
            {"timing": "opponent_turn", **blocker_life},
        ],
    )

    # OP16-119 Teach
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-119",
        [
            {
                "timing": "on_play",
                "summary": "[On Play] Look top 3: add up to 1 to Life top, rest bottom",
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
                "summary": "[Trigger] Negate up to 1 opp Character; KO up to 1 opp cost≤5",
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

    # ST17-004 Hancock — look 3 reorder then attach rested DON to Warlords
    st17 = [
        {
            "timing": "on_play",
            "summary": "[On Play] Look top 3 reorder top/bottom; rested DON!! to 1 Warlords Leader/Character",
            "ops": [
                {"op": "look_deck", "count": 3, "position": "top_or_bottom", "optional": False},
                {
                    "op": "attach_don",
                    "count": 1,
                    "as_rested": True,
                    "from_rested": True,
                    "target_kind": "own_leader_or_character",
                    "trait_contains": WARLORDS,
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ]
    n += _write(ov_cards, lib_cards, catalog, "ST17-004", st17)

    # Similar: P-109 look + attach (if same pattern)
    p109_text = str((catalog.get("P-109") or {}).get("effect") or "")
    if "任意變換排列順序放到卡組上面或下面" in p109_text and "附加最多1張休息" in p109_text:
        n += _write(
            ov_cards,
            lib_cards,
            catalog,
            "P-109",
            [
                {
                    "timing": "on_play",
                    "summary": "[On Play] Look top 3 reorder; then attach rested DON!!",
                    "ops": [
                        {"op": "look_deck", "count": 3, "position": "top_or_bottom", "optional": False},
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

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library()
    print(f"batch_x wrote {n} card entries")


if __name__ == "__main__":
    main()
