#!/usr/bin/env python3
"""Batch AM: Straw Hat / DON-return cost / ST26-005 base-power effect fixes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

SH = "Straw Hat Crew|草帽一行人"
HEART = "Heart Pirates|哈特海賊團"
KOALA_LUFFY = "Koala|可亞拉|可亚拉|Monkey.D.Luffy|蒙其・D・魯夫|蒙其·D·鲁夫"
CHOPPER = "Tony Tony.Chopper|多尼多尼・喬巴|托尼托尼・乔巴"
NAMI = "Nami|娜美"


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

    # OP09-061 Luffy Leader.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-061",
        [
            {
                "timing": "your_turn",
                "summary": "DON×1: all own Characters +1 cost",
                "ops": [
                    {
                        "op": "grant_cost",
                        "amount": 1,
                        "target_kind": "all_own",
                        "all": True,
                        "summary": "Own Characters gain +1 cost",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_attached_gte": 1,
            },
            {
                "timing": "on_don_returned",
                "summary": "Your turn once: when ≥2 field DON returned, gain 1 active + 1 rested DON",
                "ops": [
                    {"op": "gain_don", "count": 1, "optional": True},
                    {"op": "gain_don", "count": 1, "as_rested": True, "optional": True},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "require_your_turn": True,
                "on_return_don_from_field_gte": 2,
            },
        ],
    )

    # OP09-069 Law — SH or Heart, cost≥2.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-069",
        [
            {
                "timing": "on_play",
                "summary": "Look top 4; add up to 1 Straw Hat/Heart cost≥2; rest bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": "",
                        "trait_any": [SH, HEART],
                        "top_n": 4,
                        "max_add": 1,
                        "order_bottom": True,
                        "cost_gte": 2,
                        "destination": "hand",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # PRB02-012 Nami.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "PRB02-012",
        [
            {
                "timing": "on_play",
                "summary": "Look top 5; add up to 1 Straw Hat other than Nami; rest bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": SH,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "exclude_name": NAMI,
                        "destination": "hand",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Play this card",
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
            },
        ],
    )

    # ST18-001 Usopp.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST18-001",
        [
            {
                "timing": "on_play",
                "summary": "If own DON field≥8, rest up to 1 opp Character cost≤5",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "cost_lte": 5,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_field_gte": 8,
            },
        ],
    )

    # ST26-003 Robin — DON−2: gain up to 1 active DON.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST26-003",
        [
            {
                "timing": "on_play",
                "summary": "DON!! −2: add up to 1 active DON!!",
                "ops": [
                    {"op": "return_don", "count": 2, "owner": "self", "as_cost": True},
                    {"op": "gain_don", "count": 1, "optional": True},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP09-076 Zoro — may return ≥1 DON: gain up to 1 active DON. (was missing return_don)
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-076",
        [
            {
                "timing": "on_play",
                "summary": "You may return 1+ field DON!!: add up to 1 active DON!!",
                "ops": [
                    {
                        "op": "return_don",
                        "any_number": True,
                        "count": 10,
                        "owner": "self",
                        "as_cost": True,
                        "optional": True,
                    },
                    {"op": "gain_don", "count": 1, "optional": True},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP09-072 Franky — DON−2 as cost; optional trash; draw 2.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-072",
        [
            {
                "timing": "on_play",
                "summary": "DON!! −2; you may trash 1 hand: draw 2",
                "ops": [
                    {"op": "return_don", "count": 2, "owner": "self", "as_cost": True},
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "owner": "self",
                    },
                    {"op": "draw", "count": 2},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # ST26-005 Luffy — DON−2: if multicolor Leader + opp DON≥5, SH Leader base power →7000 until opp end.
    st26_ops = [
        {"op": "return_don", "count": 2, "owner": "self", "as_cost": True},
        {
            "op": "set_base_power",
            "amount": 7000,
            "target_kind": "leader",
            "optional": False,
            "trait_contains": SH,
            "duration": "until_opp_turn_end",
            "require_leader_multicolor": True,
            "require_opp_don_field_gte": 5,
            "summary": "SH Leader base power becomes 7000 until opp End Phase",
        },
    ]
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST26-005",
        [
            {
                "timing": "on_play",
                "summary": "DON!! −2: if multicolor Leader and opp DON≥5, SH Leader base=7000 until opp end",
                "ops": st26_ops,
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "when_attacking",
                "summary": "DON!! −2: if multicolor Leader and opp DON≥5, SH Leader base=7000 until opp end",
                "ops": [dict(o) for o in st26_ops],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP09-065 Sanji.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-065",
        [
            {
                "timing": "on_play",
                "summary": "You may return 1+ DON!!: gain Rush this turn; then rest up to 1 opp cost≤6",
                "ops": [
                    {
                        "op": "return_don",
                        "any_number": True,
                        "count": 10,
                        "owner": "self",
                        "as_cost": True,
                        "optional": True,
                    },
                    {
                        "op": "grant_keyword",
                        "keyword": "rush",
                        "target_kind": "self",
                        "duration": "turn",
                    },
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "cost_lte": 6,
                        "optional": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP09-119 Luffy.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-119",
        [
            {
                "timing": "on_play",
                "summary": "You may return 1+ DON!!: draw 1 and gain Rush this turn",
                "ops": [
                    {
                        "op": "return_don",
                        "any_number": True,
                        "count": 10,
                        "owner": "self",
                        "as_cost": True,
                        "optional": True,
                    },
                    {"op": "draw", "count": 1},
                    {
                        "op": "grant_keyword",
                        "keyword": "rush",
                        "target_kind": "self",
                        "duration": "turn",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP05-119 Gear 5 — keep prior shape.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP05-119",
        [
            {
                "timing": "on_play",
                "summary": "DON!! −10: bottom all other own Characters; then extra turn",
                "ops": [
                    {"op": "return_don", "count": 10, "owner": "self", "as_cost": True},
                    {
                        "op": "return_to_bottom",
                        "count": 1,
                        "optional": False,
                        "all": True,
                        "exclude_self": True,
                        "target_kind": "own_character",
                        "summary": "Place all other own Characters at deck bottom",
                    },
                    {"op": "extra_turn", "summary": "Gain an additional own turn after this one"},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "Once: cost 1 DON — add up to 1 active DON!!",
                "ops": [{"op": "gain_don", "count": 1, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "cost_don": 1,
                "rest_self": False,
            },
        ],
    )

    # OP15-085 Chopper — trash self cost; If Leader SH add from trash (If on add op).
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-085",
        [
            {
                "timing": "on_play",
                "summary": "Trash top 3 of deck",
                "ops": [{"op": "trash_deck_top", "count": 3, "optional": False}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "You may trash this: if Leader Straw Hat, add up to 1 SH Character other than Chopper from trash",
                "ops": [
                    {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                    {
                        "op": "add_from_trash",
                        "count": 1,
                        "optional": True,
                        "name_exclude": CHOPPER,
                        "trait_contains": SH,
                        "card_type": "character",
                        "destination": "hand",
                        "require_leader_trait": SH,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "cost_don": 0,
                "rest_self": False,
                "once": False,
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
                "summary": "If Leader Koala/Luffy: gain Blocker and +3 cost",
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
                "summary": "If Leader Koala/Luffy: gain Blocker and +3 cost",
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
                "summary": "You may trash 1 hand: if opp hand≥5, opponent trashes 2",
                "ops": [
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "as_cost": True,
                        "owner": "self",
                    },
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

    # OP15-086 Nami.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-086",
        [
            {
                "timing": "on_play",
                "summary": "If Leader SH: play up to 1 SH Character cost≤7 from trash with Rush",
                "ops": [
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 7,
                        "trait_contains": SH,
                        "from_zone": "trash",
                    },
                    {
                        "op": "grant_keyword",
                        "keyword": "rush",
                        "target_kind": "own_character",
                        "duration": "turn",
                        "effect_played_only": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": SH,
            },
        ],
    )

    # OP15-078.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-078",
        [
            {
                "timing": "on_play",
                "summary": "DON!! −2: draw 1; then rest up to 1 opp Character power≤5000",
                "ops": [
                    {"op": "return_don", "count": 2, "owner": "self", "as_cost": True},
                    {"op": "draw", "count": 1},
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "power_lte": 5000,
                        "optional": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "counter_event",
                "summary": "Up to 1 own Leader/Character +1000 this battle; then if DON field≤6 draw 1",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 1000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "battle",
                    },
                    {"op": "draw", "count": 1, "require_don_field_lte": 6},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP09-078 Giant — DON−2; may trash; If Leader SH buff; Then draw 2 (Then ungated).
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP09-078",
        [
            {
                "timing": "counter_event",
                "summary": "DON!! −2; you may trash 1: if Leader SH, +4000 battle; then draw 2",
                "ops": [
                    {"op": "return_don", "count": 2, "owner": "self", "as_cost": True},
                    {
                        "op": "trash_hand",
                        "count": 1,
                        "optional": True,
                        "owner": "self",
                    },
                    {
                        "op": "buff",
                        "amount": 4000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "require_leader_trait": SH,
                        "duration": "battle",
                    },
                    {"op": "draw", "count": 2},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # Similar: other「可將1張以上自己場上的咚」already OK (065/068/070/073/119).
    # Similar Then-if counter: DON−2, may trash, if Leader … Then draw — ensure draw ungated.
    for cid, info in catalog.items():
        text = str(info.get("effect") or "")
        en = str(info.get("effect_en") or "")
        if "咚‼-2" not in text and "DON!! −2" not in en and "DON!! -2" not in en:
            continue
        if "可以廢棄1張自己的手牌" not in text and "You may trash 1 card from your hand" not in en:
            continue
        if "之後，抽" not in text and "Then, draw" not in en:
            continue
        entry = ov_cards.get(cid) or lib_cards.get(cid)
        if not isinstance(entry, dict):
            continue
        changed = False
        abilities = []
        for ab in entry.get("abilities") or []:
            ab = dict(ab)
            ops = []
            for op in ab.get("ops") or []:
                op = dict(op)
                # Draw after Then should not keep leader-trait gate when paper is If…buff. Then draw.
                if op.get("op") == "draw" and op.get("require_leader_trait") and "之後，抽" in text:
                    op.pop("require_leader_trait", None)
                    changed = True
                if (
                    op.get("op") == "trash_hand"
                    and op.get("as_cost")
                    and op.get("optional")
                    and op.get("owner", "self") == "self"
                ):
                    # Optional trash after mandatory DON−2 should not abort follow-ups on skip.
                    op.pop("as_cost", None)
                    changed = True
                if op.get("op") == "return_don" and not op.get("as_cost"):
                    op["as_cost"] = True
                    changed = True
                ops.append(op)
            ab["ops"] = ops
            abilities.append(ab)
        if changed:
            entry2 = normalize_card_entry(cid, {"version": int(entry.get("version") or 1), "abilities": abilities})
            ov_cards[cid] = entry2
            lib_cards[cid] = {**entry2, "card_id": cid}
            n += 1

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library(force=True)
    print(f"batch_am updated {n} card entries")


if __name__ == "__main__":
    main()
