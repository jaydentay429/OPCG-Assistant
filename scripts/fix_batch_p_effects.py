#!/usr/bin/env python3
"""Batch P: OP10-099 family, trigger activate-on-play, OP10-109, OP15-105, ST36, EB04-059."""

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

SUPERNOVAS = "Supernovas|超新星"
KID_PIRATES = "Kid Pirates|基德海賊團|基德海贼团"
KID_NAME = 'Eustass"Captain"Kid|Eustass.Kid|尤斯塔斯・基德'
ROBIN = "Nico Robin|妮可・羅賓|妮可・罗宾"

ACTIVATE_ON_PLAY_TRIG = re.compile(
    r"【觸發器】發動這張卡片的【登場時】效果|"
    r"\[Trigger\]\s*Activate this card's \[On Play\] effect",
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


def _named(catalog: dict[str, Any], ov_cards: dict, lib_cards: dict) -> int:
    n = 0

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP10-099",
        [
            {
                "timing": "end_of_your_turn",
                "summary": "May flip Life top face-up: set up to 1 Supernovas cost 3–8 active; that Character gains Blocker until opp turn end",
                "ops": [
                    {
                        "op": "flip_life",
                        "face": "up",
                        "position": "top",
                        "optional": True,
                        "as_cost": True,
                    },
                    {
                        "op": "set_character_active",
                        "count": 1,
                        "target_kind": "own_character",
                        "optional": True,
                        "trait_contains": SUPERNOVAS,
                        "cost_lte": 8,
                        "cost_gte": 3,
                    },
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "own_character",
                        "duration": "until_opp_turn_end",
                        "same_target_as_prior": True,
                        "optional": False,
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
        "EB04-059",
        [
            {
                "timing": "on_play",
                "summary": "May flip Life top up: if fewer Characters than opp, K.O. up to 1 cost≤6 and up to 1 cost≤5",
                "ops": [
                    {
                        "op": "flip_life",
                        "face": "up",
                        "position": "top",
                        "optional": True,
                        "as_cost": True,
                    },
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "cost_lte": 6,
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
                "require_chars_deficit_gte": 1,
            },
            {
                "timing": "trigger",
                "summary": "Draw 2 and trash 1 from hand",
                "ops": [
                    {"op": "draw", "count": 2},
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
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
        "OP06-115",
        [
            {
                "timing": "counter_event",
                "summary": "May trash 1 hand: +3000 battle to own Leader/Character",
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
            {
                "timing": "trigger",
                "summary": "If Life=0: may add up to 1 Life; then trash 1 hand",
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

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP10-109",
        [
            {
                "timing": "on_ko",
                "summary": "Trash up to 1 card from top of opponent's Life",
                "ops": [
                    {
                        "op": "trash_life",
                        "count": 1,
                        "position": "top",
                        "optional": True,
                        "owner": "opponent",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Draw 2 and trash 1 from hand",
                "ops": [
                    {"op": "draw", "count": 2},
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
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
        "OP10-112",
        [
            {
                "timing": "on_play",
                "summary": "May rest this Character: trash up to 1 opp Life top",
                "ops": [
                    {
                        "op": "rest_character",
                        "target_kind": "self",
                        "optional": True,
                        "as_cost": True,
                        "count": 1,
                    },
                    {
                        "op": "trash_life",
                        "count": 1,
                        "position": "top",
                        "optional": True,
                        "owner": "opponent",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "end_of_your_turn",
                "summary": "If opp Life≤2: draw 1 and trash 1 hand",
                "ops": [
                    {"op": "draw", "count": 1},
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_opp_life_lte": 2,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-106",
        [
            {
                "timing": "on_play",
                "summary": "May Life top/bottom to hand: K.O. up to 1 opp cost≤5",
                "ops": [
                    {
                        "op": "life_to_hand",
                        "count": 1,
                        "position": "top_or_bottom",
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
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
            }
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-113",
        [
            {
                "timing": "on_play",
                "summary": "Look top 4; reveal up to 1 Trigger other than Lilith to hand; rest bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": "",
                        "top_n": 4,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": "Lilith|莉莉絲|莉莉丝",
                        "destination": "hand",
                        "require_trigger": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
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
        "OP13-116",
        [
            {
                "timing": "on_play",
                "summary": "Look top 5; reveal up to 1 Supernovas Character to hand; rest bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": SUPERNOVAS,
                        "top_n": 5,
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
                "summary": "Activate this card's [Main] effect",
                "ops": [{"op": "activate_timing", "timing": "on_play"}],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    replace_ops = [
        {
            "op": "replace_leave",
            "trigger": "opp_remove",
            "target": "own_filtered",
            "cost": "life_to_hand",
            "life_position": "top",
            "base_power_lte": 7000,
            "optional": True,
            "summary": "Life to hand instead of Character leaving",
        }
    ]
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-105",
        [
            {
                "timing": "your_turn",
                "summary": "If own Character base≤7000 would leave by opp effect: may Life→hand instead",
                "ops": list(replace_ops),
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "opponent_turn",
                "summary": "If own Character base≤7000 would leave by opp effect: may Life→hand instead",
                "ops": list(replace_ops),
                "status": "compiled",
                "confidence": 0.95,
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
                "summary": "Look top 3; add up to 1 to Life top; rest to bottom",
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
        "ST36-002",
        [
            {
                "timing": "on_play",
                "summary": "Your turn: if Kid Pirates Leader, add up to 1 deck top to Life",
                "ops": [{"op": "add_life", "count": 1, "optional": True, "position": "top"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": KID_PIRATES,
                "require_your_turn": True,
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

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST36-003",
        [
            {
                "timing": "trigger",
                "summary": "Draw 1; Supernovas Leader base power becomes 7000 this turn",
                "ops": [
                    {"op": "draw", "count": 1},
                    {
                        "op": "set_base_power",
                        "target_kind": "leader",
                        "optional": False,
                        "amount": 7000,
                        "duration": "turn",
                        "trait_contains": SUPERNOVAS,
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
        "ST36-004",
        [
            {
                "timing": "on_play",
                "summary": "May trash 1 Supernovas from hand: draw 2",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "trait_contains": SUPERNOVAS,
                        "owner": "self",
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
        "ST36-005",
        [
            {
                "timing": "on_opponent_attack",
                "summary": "Once: may flip Life top/bottom face-down: redirect attack to own Kid with base≥5000",
                "ops": [
                    {
                        "op": "flip_life",
                        "face": "down",
                        "position": "top_or_bottom",
                        "optional": True,
                        "as_cost": True,
                    },
                    {
                        "op": "redirect_attack",
                        "target_kind": "own_character",
                        "name_contains": KID_NAME,
                        "base_power_gte": 5000,
                        "optional": False,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
            {
                "timing": "activate_main",
                "summary": "Once: may flip Life top/bottom face-up: attach up to 1 rested DON!! to Leader",
                "ops": [
                    {
                        "op": "flip_life",
                        "face": "up",
                        "position": "top_or_bottom",
                        "optional": True,
                        "as_cost": True,
                    },
                    {
                        "op": "attach_don",
                        "count": 1,
                        "as_rested": True,
                        "target_kind": "leader",
                        "optional": True,
                        "from_rested": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
        ],
    )

    # Similar activate-[On Play] trigger fixes
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-102",
        [
            {
                "timing": "on_play",
                "summary": "If Leader is Nico Robin: look top 3; reveal up to 1 Trigger to hand; rest bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": "",
                        "top_n": 3,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "require_trigger": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_name": ROBIN,
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
        "OP06-013",
        [
            {
                "timing": "on_play",
                "summary": "Look top 3; reveal up to 1 FILM to hand; rest bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": "FILM",
                        "top_n": 3,
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
        "OP08-106",
        [
            {
                "timing": "on_play",
                "summary": "May trash 1 Trigger from hand: K.O. up to 1 opp cost≤5; then if hand≤3 draw 1",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "require_trigger": True,
                        "owner": "self",
                    },
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "cost_lte": 5,
                    },
                    {"op": "draw", "count": 1, "require_hand_lte": 3},
                ],
                "status": "compiled",
                "confidence": 0.95,
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
        "OP08-112",
        [
            {
                "timing": "on_play",
                "summary": "Up to 1 opp cost≤6 other than Luffy cannot attack until opp turn end",
                "ops": [
                    {
                        "op": "deny_attack",
                        "count": 1,
                        "optional": True,
                        "target_kind": "opponent_character",
                        "cost_lte": 6,
                        "duration": "until_opp_turn_end",
                        "exclude_name": "Monkey.D.Luffy|モンキー・D・ルフィ|蒙其・D・魯夫|蒙其·D·鲁夫",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
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

    # OP09-068: set this active then this gains Blocker
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-068",
        [
            {
                "timing": "end_of_your_turn",
                "summary": "May return 1+ DON!!: set this active; then this gains Blocker until opp turn end",
                "ops": [
                    {
                        "op": "return_don",
                        "count": 1,
                        "owner": "self",
                        "as_cost": True,
                    },
                    {
                        "op": "set_character_active",
                        "count": 1,
                        "target_kind": "self",
                        "optional": False,
                    },
                    {
                        "op": "grant_keyword",
                        "keyword": "blocker",
                        "target_kind": "self",
                        "duration": "until_opp_turn_end",
                    },
                ],
                "status": "compiled",
                "confidence": 0.9,
            }
        ],
    )
    return n


def _scan_activate_on_play_triggers(catalog: dict[str, Any], ov_cards: dict, lib_cards: dict) -> int:
    n = 0
    for cid, info in catalog.items():
        if not re.match(r"^[A-Z0-9]+-\d+$", cid):
            continue
        paper = _paper(catalog, cid)
        if not ACTIVATE_ON_PLAY_TRIG.search(paper):
            continue
        entry = ov_cards.get(cid) or lib_cards.get(cid)
        if not entry:
            continue
        abs_list = list(entry.get("abilities") or [])
        changed = False
        new_abs = []
        for ab in abs_list:
            ab = dict(ab)
            if ab.get("timing") == "trigger":
                ops = ab.get("ops") or []
                if not (len(ops) == 1 and ops[0].get("op") == "activate_timing" and ops[0].get("timing") == "on_play"):
                    ab["ops"] = [{"op": "activate_timing", "timing": "on_play"}]
                    ab["summary"] = "Activate this card's [On Play] effect"
                    ab["status"] = "compiled"
                    ab["confidence"] = 0.95
                    changed = True
            new_abs.append(ab)
        if changed:
            _store(ov_cards, lib_cards, cid, new_abs)
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
    n += _scan_activate_on_play_triggers(catalog, ov_cards, lib_cards)

    ov_doc["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    lib_doc["generated_at"] = ov_doc["generated_at"]
    ov_path.write_text(json.dumps(ov_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lib_path.write_text(json.dumps(lib_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    reload_effect_library()
    print(f"batch_p updated {n} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
