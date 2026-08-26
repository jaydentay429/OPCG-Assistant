#!/usr/bin/env python3
"""Batch AX: Thriller Bark / Hogback gate / Stage / Then-attach fixes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

TB = "Thriller Bark Pirates|恐怖三桅帆船海賊團|恐怖三桅帆船海贼团"
HOGBACK = "Dr. Hogback|赫古巴庫醫生|赫古巴库医生"
OARS = "Oars|歐斯|欧斯"
MORIA = "Gecko Moria|月光・摩利亞|月光・莫利亚|摩利亞"
HURRY = (
    "Hurry Up and Make Me the Pirate King!|"
    "快讓我成為海賊王吧!!!|"
    "快让我成为海盗王吧!!!"
)
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

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-080",
        [
            {
                "timing": "activate_main",
                "summary": "Once: you may KO 1 own Thriller Bark Character: Leader+all Characters +1000",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "own_character",
                        "optional": True,
                        "as_cost": True,
                        "trait_contains": TB,
                    },
                    {
                        "op": "buff_all_own",
                        "amount": 1000,
                        "include_leader": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
            {
                "timing": "when_attacking",
                "summary": "You may trash 3: add up to 1 top deck to Life",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 3,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {"op": "add_life", "count": 1, "optional": True, "position": "top"},
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
        "OP06-091",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Thriller Bark: trash 5 from deck top",
                "ops": [{"op": "trash_deck_top", "count": 5, "optional": False}],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": TB,
            },
        ],
    )

    # OP15-084 — hand≤6 only on KO, not on_play.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-084",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Thriller Bark: trash 5 from deck top",
                "ops": [{"op": "trash_deck_top", "count": 5, "optional": False}],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": TB,
            },
            {
                "timing": "on_ko",
                "summary": "If hand≤6: draw 1",
                "ops": [{"op": "draw", "count": 1}],
                "status": "compiled",
                "confidence": 0.95,
                "require_hand_lte": 6,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP06-082",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Thriller Bark: draw 2 trash 2",
                "ops": [
                    {"op": "draw", "count": 2},
                    {
                        "op": "trash_hand",
                        "count": 2,
                        "optional": False,
                        "owner": "self",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": TB,
            },
            {
                "timing": "on_ko",
                "summary": "If Leader Thriller Bark: draw 2 trash 2",
                "ops": [
                    {"op": "draw", "count": 2},
                    {
                        "op": "trash_hand",
                        "count": 2,
                        "optional": False,
                        "owner": "self",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": TB,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP06-090",
        [
            {
                "timing": "on_play",
                "summary": "You may trash_to_bottom 2: add up to 1 Thriller Bark other than Hogback from trash",
                "ops": [
                    {
                        "op": "trash_to_bottom",
                        "count": 2,
                        "optional": True,
                        "owner": "self",
                        "card_type": "any",
                        "order_any": True,
                        "as_cost": True,
                    },
                    {
                        "op": "add_from_trash",
                        "count": 1,
                        "optional": True,
                        "exclude_name": HOGBACK,
                        "name_exclude": HOGBACK,
                        "trait_contains": TB,
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
        "OP15-080",
        [
            {
                "timing": "your_turn",
                "summary": "If Moria on field power≥10000 and no other Oars: this +7000",
                "ops": [{"op": "buff_self", "amount": 7000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_own_char_power_gte": 10000,
                "require_own_name_contains": MORIA,
                "require_no_other_name": OARS,
            },
            {
                "timing": "opponent_turn",
                "summary": "If Moria on field power≥10000 and no other Oars: this +7000",
                "ops": [{"op": "buff_self", "amount": 7000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_own_char_power_gte": 10000,
                "require_own_name_contains": MORIA,
                "require_no_other_name": OARS,
            },
            {
                "timing": "on_ko",
                "summary": "You may trash_to_bottom 3: play this from trash",
                "ops": [
                    {
                        "op": "trash_to_bottom",
                        "count": 3,
                        "optional": True,
                        "owner": "self",
                        "card_type": "any",
                        "order_any": True,
                        "as_cost": True,
                    },
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": False,
                        "from_zone": "trash",
                        "self_card": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # PRB02-013 — Then attach_don ungated.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "PRB02-013",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Thriller Bark: play up to 1 cost≤4 from trash rested; Then attach up to 1 rested DON!!",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 4,
                        "as_rested": True,
                        "from_zone": "trash",
                        "require_leader_trait": TB,
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
        "P-100",
        [
            {
                "timing": "when_attacking",
                "summary": "Negate all opp Leader and Character effects this turn",
                "ops": [
                    {
                        "op": "negate_effects",
                        "optional": False,
                        "target_kind": "opponent_all",
                        "all": True,
                        "include_leader": True,
                        "include_characters": True,
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
                        "trait_contains": TB,
                        "as_rested": True,
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
        "OP14-111",
        [
            {
                "timing": "on_play",
                "summary": "Up to 1 opp Character cost≤6 cannot attack until opp end",
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
                "summary": "Up to 1 opp Character cost≤6 cannot attack until opp end",
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
                        "trait_contains": TB,
                        "as_rested": True,
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
        "OP15-113",
        [
            {
                "timing": "on_play",
                "summary": "You may trash 1: add up to 1 top deck to Life",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
                    {"op": "add_life", "count": 1, "optional": True, "position": "top"},
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
        "OP14-104",
        [
            {
                "timing": "on_play",
                "summary": "Choose: Thriller Bark cost≤4 from trash → Life face-up top OR play it",
                "ops": [
                    {
                        "op": "choose_one",
                        "chooser": "self",
                        "optional": True,
                        "options": [
                            {
                                "id": "to_life",
                                "label": "Add face-up to Life top",
                                "ops": [
                                    {
                                        "op": "add_from_trash",
                                        "count": 1,
                                        "optional": True,
                                        "trait_contains": TB,
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
                                "label": "Play from trash",
                                "ops": [
                                    {
                                        "op": "play_from_hand",
                                        "count": 1,
                                        "card_type": "character",
                                        "optional": True,
                                        "cost_lte": 4,
                                        "trait_contains": TB,
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

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP06-098",
        [
            {
                "timing": "activate_main",
                "summary": "DON!!−1 + rest this Stage: if Leader Thriller Bark, play up to 1 Thriller Bark cost≤2 from trash rested",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 2,
                        "trait_contains": TB,
                        "as_rested": True,
                        "from_zone": "trash",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "cost_don": 1,
                "rest_self": True,
                "require_leader_trait": TB,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-097",
        [
            {
                "timing": "on_play",
                "summary": "Look top 3; add up to 1 Thriller Bark other than this; trash rest",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": TB,
                        "top_n": 3,
                        "max_add": 1,
                        "trash_rest": True,
                        "order_bottom": False,
                        "exclude_name": HURRY,
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

    # Soft-fix: play_from_hand with require_leader_trait on ability + Then attach_don.
    for cid, entry in list(ov_cards.items()):
        info = catalog.get(cid) or {}
        zh = str(info.get("effect") or "")
        if "之後" not in zh or "附加最多" not in zh or "廢棄區" not in zh:
            continue
        abs_out = []
        changed = False
        for ab in entry.get("abilities") or []:
            ab = dict(ab)
            if ab.get("timing") != "on_play" or not ab.get("require_leader_trait"):
                abs_out.append(ab)
                continue
            ops = ab.get("ops") or []
            if not any(o.get("op") == "attach_don" for o in ops):
                abs_out.append(ab)
                continue
            if not any(o.get("op") == "play_from_hand" for o in ops):
                abs_out.append(ab)
                continue
            trait = ab.pop("require_leader_trait")
            new_ops = []
            for o in ops:
                o = dict(o)
                if o.get("op") == "play_from_hand":
                    o["require_leader_trait"] = trait
                    changed = True
                new_ops.append(o)
            ab["ops"] = new_ops
            abs_out.append(ab)
            changed = True
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
    print(f"batch_ax updated {n} card entries")


if __name__ == "__main__":
    main()
