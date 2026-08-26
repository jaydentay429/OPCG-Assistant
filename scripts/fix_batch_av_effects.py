#!/usr/bin/env python3
"""Batch AV: Yamato / Wano / Life / rest-all / trigger self_card fixes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

WANO = "Land of Wano|和之國|和之国"
MOMO = "Kouzuki Momonosuke|光月桃之助"
HIYORI = "Kouzuki Hiyori|光月日和"
EGGHEAD = "Egghead|蛋頭|蛋头"


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

    # OP06-022 — rested DON!! to own Character (not self/leader).
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP06-022",
        [
            {
                "timing": "activate_main",
                "summary": "Once: if opp Life≤3, attach up to 2 rested DON!! to 1 own Character",
                "ops": [
                    {
                        "op": "attach_don",
                        "count": 2,
                        "from_rested": True,
                        "as_rested": True,
                        "target_kind": "own_character",
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "require_opp_life_lte": 3,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST28-005",
        [
            {
                "timing": "your_turn",
                "summary": "DON!!×2: this +3000",
                "ops": [{"op": "buff_self", "amount": 3000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_attached_gte": 2,
            },
            {
                "timing": "on_play",
                "summary": "Look top 5; add up to 1 Land of Wano cost≥2",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": WANO,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "cost_gte": 2,
                        "reveal_adds": True,
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
        "OP06-101",
        [
            {
                "timing": "on_play",
                "summary": "Up to 1 own Leader/Character gains Banish this turn",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "banish",
                        "target_kind": "own_leader_or_character",
                        "duration": "turn",
                        "optional": True,
                        "count": 1,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "KO up to 1 opp Character cost≤5",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "cost_lte": 5,
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
        "OP06-106",
        [
            {
                "timing": "on_play",
                "summary": "You may Life→hand (top/bottom): hand→Life top",
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
                        "op": "hand_to_life",
                        "count": 1,
                        "optional": True,
                        "position": "top",
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
        "ST28-002",
        [
            {
                "timing": "your_turn",
                "summary": "DON!!×2: gain Blocker",
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
                "summary": "DON!!×2: gain Blocker",
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
                "timing": "on_play",
                "summary": "Land of Wano Leader gains Banish this turn",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "banish",
                        "target_kind": "leader",
                        "duration": "turn",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": WANO,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "PRB02-016",
        [
            {
                "timing": "activate_main",
                "summary": "You may rest this + Life→hand: up to 1 own Leader/Character +3000",
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
                        "op": "buff",
                        "amount": 3000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "turn",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "rest_self": True,
            },
            {
                "timing": "trigger",
                "summary": "Rest up to 1 opp Character cost≤4",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "cost_lte": 4,
                        "optional": True,
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

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST28-003",
        [
            {
                "timing": "trigger",
                "summary": "If Leader Wano and opp Life≤3: play this card",
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
                "require_leader_trait": WANO,
            },
        ],
    )

    # OP13-104 — trash cost ungated; add_life multicolor-gated. Blocker innate.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-104",
        [
            {
                "timing": "on_ko",
                "summary": "You may trash 1: if Leader multicolor, add top deck to Life",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {
                        "op": "add_life",
                        "count": 1,
                        "optional": True,
                        "position": "top",
                        "require_leader_multicolor": True,
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
        "OP06-107",
        [
            {
                "timing": "on_play",
                "summary": "Place up to 1 own Wano Character other than Momonosuke face-up on Life top/bottom",
                "ops": [
                    {
                        "op": "place_on_life",
                        "count": 1,
                        "owner": "self",
                        "position": "top_or_bottom",
                        "face": "up",
                        "target_kind": "own_character",
                        "optional": True,
                        "trait_contains": WANO,
                        "exclude_name": MOMO,
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
        "EB03-057",
        [
            {
                "timing": "on_play",
                "summary": "Attach up to 3 rested DON!! to Wano Leader",
                "ops": [
                    {
                        "op": "attach_don",
                        "count": 3,
                        "as_rested": True,
                        "from_rested": True,
                        "target_kind": "leader",
                        "optional": True,
                        "trait_contains": WANO,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "on_ko",
                "summary": "Trash up to 1 top opp Life",
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
                "summary": "If Life≤2: add up to 1 top deck to Life",
                "ops": [{"op": "add_life", "count": 1, "optional": True, "position": "top"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 2,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-119",
        [
            {
                "timing": "on_play",
                "summary": "You may trash 1: add Life; Then this +2 cost until opp end",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
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
                "summary": "Opp turn: add up to 1 top deck to Life",
                "ops": [{"op": "add_life", "count": 1, "optional": True, "position": "top"}],
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
        "EB01-013",
        [
            {
                "timing": "activate_main",
                "summary": "You may trash this: play up to 1 Wano cost≤5 other than Hiyori; Then draw 1",
                "ops": [
                    {
                        "op": "trash",
                        "target_kind": "self",
                        "optional": True,
                        "as_cost": True,
                    },
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 5,
                        "trait_contains": WANO,
                        "exclude_name": HIYORI,
                        "from_zone": "hand",
                    },
                    {"op": "draw", "count": 1},
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
        "OP06-035",
        [
            {
                "timing": "on_play",
                "summary": "Rest up to 2 total opp Characters or DON!!; Then Life top → hand",
                "ops": [
                    {
                        "op": "rest_opponent_char_or_don",
                        "count": 2,
                        "optional": True,
                    },
                    {
                        "op": "life_to_hand",
                        "count": 1,
                        "position": "top",
                        "optional": False,
                        "owner": "self",
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
        "OP06-118",
        [
            {
                "timing": "when_attacking",
                "summary": "Once: rest 1 DON!!: set this active",
                "ops": [
                    {
                        "op": "rest_don",
                        "count": 1,
                        "owner": "self",
                        "as_cost": True,
                    },
                    {
                        "op": "set_character_active",
                        "count": 1,
                        "target_kind": "self",
                        "optional": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
            {
                "timing": "activate_main",
                "summary": "Once: rest 2 DON!!: set this active",
                "ops": [
                    {
                        "op": "rest_don",
                        "count": 2,
                        "owner": "self",
                        "as_cost": True,
                    },
                    {
                        "op": "set_character_active",
                        "count": 1,
                        "target_kind": "self",
                        "optional": True,
                    },
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
        "OP06-115",
        [
            {
                "timing": "counter_event",
                "summary": "You may trash 1: up to 1 own Leader/Character +3000 this battle",
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
                "summary": "If Life=0: add up to 1 Life; Then trash 1",
                "ops": [
                    {"op": "add_life", "count": 1, "optional": True, "position": "top"},
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": False,
                        "owner": "self",
                    },
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
        "OP07-115",
        [
            {
                "timing": "counter_event",
                "summary": "If Life≤2: up to 1 own Leader/Character +3000 this battle",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 3000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "battle",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_life_lte": 2,
            },
            {
                "timing": "trigger",
                "summary": "Play up to 1 Egghead Character cost≤5 from trash",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 5,
                        "trait_contains": EGGHEAD,
                        "from_zone": "trash",
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
        "OP12-037",
        [
            {
                "timing": "on_play",
                "summary": "You may rest 3 DON!!: rest up to 2 total opp Characters or DON!!",
                "ops": [
                    {
                        "op": "rest_don",
                        "count": 3,
                        "owner": "self",
                        "as_cost": True,
                        "optional": True,
                    },
                    {
                        "op": "rest_opponent_char_or_don",
                        "count": 2,
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
        "OP06-041",
        [
            {
                "timing": "on_play",
                "summary": "Rest all opponent Characters",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "optional": False,
                        "all": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Play this Stage",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "stage",
                        "optional": False,
                        "from_zone": "hand_or_trash",
                        "self_card": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # Soft-fix: trigger 「使這張卡片登場」 missing self_card.
    for cid, entry in list(ov_cards.items()):
        info = catalog.get(cid) or {}
        zh = str(info.get("effect") or "")
        if "使這張卡片登場" not in zh and "Play this card" not in str(info.get("effect_en") or ""):
            continue
        abs_out = []
        changed = False
        for ab in entry.get("abilities") or []:
            ab = dict(ab)
            if ab.get("timing") != "trigger":
                abs_out.append(ab)
                continue
            ops = []
            for o in ab.get("ops") or []:
                o = dict(o)
                if o.get("op") == "play_from_hand" and not o.get("self_card"):
                    o["self_card"] = True
                    o["optional"] = False
                    ctype = str(info.get("card_type") or "").lower()
                    if "stage" in ctype:
                        o["card_type"] = "stage"
                    changed = True
                ops.append(o)
            ab["ops"] = ops
            abs_out.append(ab)
        if changed:
            entry2 = normalize_card_entry(
                cid, {"version": int(entry.get("version") or 1), "abilities": abs_out}
            )
            ov_cards[cid] = entry2
            lib_cards[cid] = {**entry2, "card_id": cid}
            n += 1

    # Soft-fix: 「角色卡全數」rest without all.
    for cid, entry in list(ov_cards.items()):
        info = catalog.get(cid) or {}
        zh = str(info.get("effect") or "")
        if "角色卡全數" not in zh and "Characters." not in str(info.get("effect_en") or ""):
            if "Rest all of your opponent's Characters" not in str(info.get("effect_en") or ""):
                continue
        abs_out = []
        changed = False
        for ab in entry.get("abilities") or []:
            ab = dict(ab)
            ops = []
            for o in ab.get("ops") or []:
                o = dict(o)
                if (
                    o.get("op") == "rest_opponent_character"
                    and not o.get("all")
                    and ("全數" in zh or "all of your opponent" in str(info.get("effect_en") or "").lower())
                ):
                    o["all"] = True
                    o["optional"] = False
                    changed = True
                ops.append(o)
            ab["ops"] = ops
            abs_out.append(ab)
        if changed:
            entry2 = normalize_card_entry(
                cid, {"version": int(entry.get("version") or 1), "abilities": abs_out}
            )
            ov_cards[cid] = entry2
            lib_cards[cid] = {**entry2, "card_id": cid}
            n += 1

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library(force=True)
    print(f"batch_av updated {n} card entries")


if __name__ == "__main__":
    main()
