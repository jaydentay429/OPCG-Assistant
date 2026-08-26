#!/usr/bin/env python3
"""Batch Q: OP11-041 life-leave, Thriller Bark triggers, OP13-119 bounce→opp play, OP14-104."""

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

THRILLER = "Thriller Bark Pirates|恐怖三桅帆船海賊團"
HOGBACK = "Dr. Hogback|Dr.Hogback|赫古巴庫醫生"
STRAW = "Straw Hat Crew|草帽一行人"
BB = "Blackbeard Pirates|黑鬍子海賊團|黑胡子海贼团"

THRILLER_TRIG = re.compile(
    r"使最多1張自己廢棄區中費用4以下擁有《恐怖三桅帆船海賊團》特徵的角色卡，以休息狀態登場"
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


def _thriller_trigger_op() -> dict[str, Any]:
    return {
        "op": "play_from_hand",
        "count": 1,
        "card_type": "character",
        "optional": True,
        "cost_lte": 4,
        "trait_contains": THRILLER,
        "as_rested": True,
        "from_zone": "trash",
    }


def _nami_leader_abilities() -> list[dict[str, Any]]:
    return [
        {
            "timing": "your_turn",
            "summary": "[Your Turn][Once] When a Life card leaves: if hand≤7, may draw 1",
            "ops": [{"op": "draw", "count": 1}],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
            "optional": True,
            "on_life_leave": True,
            "on_life_leave_from": "either",
            "require_hand_lte": 7,
        },
        {
            "timing": "on_opponent_attack",
            "summary": "[DON!! x1][On Opp Attack][Once] May trash 1: Leader +2000 this turn",
            "ops": [
                {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "leader",
                    "optional": True,
                    "duration": "turn",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
            "require_don_attached_gte": 1,
            "optional": True,
        },
    ]


def _op13_119_abilities(*, bounce_play_cost: int) -> list[dict[str, Any]]:
    return [
        {
            "timing": "your_turn",
            "summary": "If Life≤3: this Character gains Rush",
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
            "require_life_lte": 3,
        },
        {
            "timing": "opponent_turn",
            "summary": "If Life≤3: this Character gains Rush",
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
            "require_life_lte": 3,
        },
        {
            "timing": "on_play",
            "summary": "Attach up to 1 rested DON!! to Leader; may bounce opp cost≤5; if you do, opp plays cost≤N",
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
                    "op": "return_to_hand",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "cost_lte": 5,
                },
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": bounce_play_cost,
                    "from_zone": "hand",
                    "owner": "opponent",
                    "if_returned": True,
                    "summary": f"If bounced: opponent plays up to 1 cost≤{bounce_play_cost}",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ]


def main() -> None:
    ov_path, lib_path = library_paths()
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    ov = json.loads(ov_path.read_text())
    lib = json.loads(lib_path.read_text())
    ov_cards = ov.setdefault("cards", {})
    lib_cards = lib.setdefault("cards", {})
    n = 0

    n += _write(ov_cards, lib_cards, catalog, "OP11-041", _nami_leader_abilities())

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP08-105",
        [
            {
                "timing": "trigger",
                "summary": "Trigger: draw 2, trash 1",
                "ops": [
                    {"op": "draw", "count": 2},
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "your_turn",
                "summary": "[DON!! x1][Your Turn][Once] When opp Life leaves: draw 2, trash 1",
                "ops": [
                    {"op": "draw", "count": 2},
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "require_don_attached_gte": 1,
                "on_life_leave": True,
                "on_life_leave_from": "opponent",
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-099",
        [
            {
                "timing": "your_turn",
                "summary": "[Your Turn] When Life leaves: draw 1; then cannot draw by own effects this turn",
                "ops": [
                    {"op": "draw", "count": 1, "on_life_leave": True},
                    {"op": "cannot_draw_by_effect", "duration": "turn"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "on_life_leave": True,
                "on_life_leave_from": "either",
            }
        ],
    )

    # Thriller Bark trigger pack (+ keep non-trigger abilities where present)
    thriller_bases = ["OP14-089", "OP14-100", "OP14-102", "OP14-109", "OP14-117"]
    for base in thriller_bases:
        for vid in _variants(catalog, base):
            paper = _paper(catalog, vid)
            if not THRILLER_TRIG.search(paper):
                continue
            prev = ov_cards.get(vid) or lib_cards.get(vid) or {"abilities": []}
            kept = [a for a in (prev.get("abilities") or []) if a.get("timing") != "trigger"]
            kept.append(
                {
                    "timing": "trigger",
                    "summary": "Play up to 1 Thriller Bark cost≤4 from trash rested",
                    "ops": [_thriller_trigger_op()],
                    "status": "compiled",
                    "confidence": 0.95,
                }
            )
            _store(ov_cards, lib_cards, vid, kept)
            n += 1

    # OP14-110: bilingual Hogback exclude; keep OP14-111 trigger aligned
    for vid in _variants(catalog, "OP14-110"):
        abs_ = [
            {
                "timing": "on_ko",
                "summary": "Play up to 1 cost≤4 Trigger Character from trash other than Hogback",
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
                "ops": [_thriller_trigger_op()],
                "status": "compiled",
                "confidence": 0.95,
            },
        ]
        _store(ov_cards, lib_cards, vid, abs_)
        n += 1

    for vid in _variants(catalog, "OP14-111"):
        abs_ = [
            {
                "timing": "on_play",
                "summary": "Up to 1 opp cost≤6 cannot attack until opp next End Phase",
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
                "summary": "Up to 1 opp cost≤6 cannot attack until opp next End Phase",
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
                "ops": [_thriller_trigger_op()],
                "status": "compiled",
                "confidence": 0.95,
            },
        ]
        _store(ov_cards, lib_cards, vid, abs_)
        n += 1

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-104",
        [
            {
                "timing": "on_play",
                "summary": "From trash Thriller Bark cost≤4: add face-up to Life top OR play",
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
                                        "card_type": "character",
                                        "cost_lte": 4,
                                        "trait_contains": THRILLER,
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
                "summary": "Play up to 1 cost≤4 Character from trash",
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

    # OP13-119: P5 ZH uses cost≤8 for opp play; others ≤4
    for vid in _variants(catalog, "OP13-119"):
        paper = _paper(catalog, vid)
        bounce_cost = 8 if re.search(r"費用8以下的角色卡登場|cost of 8 or less", paper, re.I) else 4
        _store(ov_cards, lib_cards, vid, _op13_119_abilities(bounce_play_cost=bounce_cost))
        n += 1

    # Re-affirm already-good batch cards so variants stay aligned
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB03-053",
        [
            {
                "timing": "on_play",
                "summary": "Attach up to 1 rested DON!! to Leader",
                "ops": [
                    {
                        "op": "attach_don",
                        "count": 1,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "leader",
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "on_play",
                "summary": "If opp Life≥3: add up to 1 opp Life top to owner's hand",
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
                "require_opp_life_gte": 3,
            },
            {
                "timing": "on_ko",
                "summary": "May flip Life top up: play up to 1 power≤6000 from hand",
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

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB03-055",
        [
            {
                "timing": "on_play",
                "summary": "May trash Life top: if Leader Straw Hat, add up to 2 deck to Life top",
                "ops": [
                    {
                        "op": "trash_life",
                        "count": 1,
                        "position": "top",
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {
                        "op": "add_life",
                        "count": 2,
                        "optional": True,
                        "position": "top",
                        "require_leader_trait": STRAW,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "on_ko",
                "summary": "[Opp Turn][On K.O.] May deal 1 damage",
                "ops": [{"op": "deal_life_damage", "count": 1, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
                "require_opponent_turn": True,
            },
        ],
    )

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
        "OP06-106",
        [
            {
                "timing": "on_play",
                "summary": "May Life top/bottom to hand: hand to Life top",
                "ops": [
                    {
                        "op": "life_to_hand",
                        "count": 1,
                        "position": "top_or_bottom",
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {"op": "hand_to_life", "count": 1, "optional": True},
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
        "OP13-042",
        [
            {
                "timing": "on_play",
                "summary": "Draw 2, trash 1; attach up to 2 rested DON!! each to Leader and 1 Character",
                "ops": [
                    {"op": "draw", "count": 2},
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                    {
                        "op": "attach_don",
                        "count": 2,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "leader",
                        "optional": True,
                    },
                    {
                        "op": "attach_don",
                        "count": 2,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "own_character",
                        "optional": True,
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
        "OP14-108",
        [
            {
                "timing": "on_play",
                "summary": "If Leader multicolor and opp Life≤3: K.O. up to 1 base power≤7000",
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
        "OP16-056",
        [
            {
                "timing": "activate_main",
                "summary": "May trash this: draw 2; up to 1 opp cost≤9 cannot attack until opp end",
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

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-104",
        [
            {
                "timing": "when_attacking",
                "summary": "Choose up to 1 opp Character: this base power becomes that power this turn",
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
            {
                "timing": "trigger",
                "summary": "Draw 1; play up to 1 Blackbeard cost 1 from trash",
                "ops": [
                    {"op": "draw", "count": 1},
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_eq": 1,
                        "trait_contains": BB,
                        "from_zone": "trash",
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
        "PRB02-008",
        [
            {
                "timing": "on_ko",
                "summary": "[On K.O.] Draw 2",
                "ops": [{"op": "draw", "count": 2}],
                "status": "compiled",
                "confidence": 0.95,
            }
        ],
    )

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library(force=True)
    print(f"batch_q wrote {n} card entries")


if __name__ == "__main__":
    main()
