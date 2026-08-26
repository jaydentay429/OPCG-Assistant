#!/usr/bin/env python3
"""Batch AO: Supernovas / skip-untap / innate Banish / rest-replace fixes."""

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
CAVENDISH = "Cavendish|卡文迪許|卡文迪许"


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

    # OP07-019 Bonney Leader.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP07-019",
        [
            {
                "timing": "on_opponent_attack",
                "summary": "Once: rest 1 DON!!: rest up to 1 opp Leader or Character",
                "ops": [
                    {"op": "rest_don", "count": 1, "owner": "self", "as_cost": True},
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "include_leader": True,
                        "optional": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
        ],
    )

    # ST02-007 Bonney.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST02-007",
        [
            {
                "timing": "activate_main",
                "summary": "Cost 1 DON + rest this: search top 5 for up to 1 Supernovas",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": SN,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "cost_don": 1,
                "rest_self": True,
                "once": False,
            },
        ],
    )

    # EB01-015 Apoo.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB01-015",
        [
            {
                "timing": "on_play",
                "summary": "Rest up to 1 opp Character cost≤2",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "cost_lte": 2,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP15-035 Laboon — rest 2 of your cards (Leader/Char/Stage/DON).
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-035",
        [
            {
                "timing": "your_turn",
                "summary": "If own base power≤7000 Character would leave by opp effect: may rest 2 own cards instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "own_filtered",
                        "cost": "rest_own",
                        "rest_count": 2,
                        "base_power_lte": 7000,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "opponent_turn",
                "summary": "If own base power≤7000 Character would leave by opp effect: may rest 2 own cards instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "own_filtered",
                        "cost": "rest_own",
                        "rest_count": 2,
                        "base_power_lte": 7000,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # ST24-002 Kid & Killer.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST24-002",
        [
            {
                "timing": "on_play",
                "summary": "Look top 5; add up to 1 Supernovas; rest bottom",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": SN,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "on_opponent_attack",
                "summary": "You may trash this: set up to 1 DON!! active",
                "ops": [
                    {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                    {"op": "active_don", "count": 1, "optional": True},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # PRB02-006 Zoro — Blocker innate; replace_rest vs opp Character effect.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "PRB02-006",
        [
            {
                "timing": "opponent_turn",
                "summary": "If this would be rested by opp Character effect: may rest 1 other own Character instead",
                "ops": [
                    {
                        "op": "replace_rest",
                        "target": "self",
                        "cost": "rest_other_character",
                        "rest_count": 1,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # EB01-012 Cavendish.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB01-012",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Supernovas and no other Cavendish: set up to 2 DON!! active",
                "ops": [{"op": "active_don", "count": 2, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": SN,
                "require_no_other_name": CAVENDISH,
            },
            {
                "timing": "when_attacking",
                "summary": "If Leader Supernovas and no other Cavendish: set up to 2 DON!! active",
                "ops": [{"op": "active_don", "count": 2, "optional": True}],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": SN,
                "require_no_other_name": CAVENDISH,
            },
        ],
    )

    # OP07-026 Bonney — skip untap Character or DON!!.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP07-026",
        [
            {
                "timing": "on_play",
                "summary": "Up to 1 opp rested Character or DON!! skips next Refresh",
                "ops": [
                    {
                        "op": "skip_untap",
                        "count": 1,
                        "target_kind": "opponent_character_or_don_rested",
                        "optional": True,
                        "include_don": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP08-023 Carrot.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP08-023",
        [
            {
                "timing": "on_play",
                "summary": "Up to 1 opp rested Character cost≤7 skips next Refresh",
                "ops": [
                    {
                        "op": "skip_untap",
                        "count": 1,
                        "target_kind": "opponent_character_rested",
                        "cost_lte": 7,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "when_attacking",
                "summary": "Up to 1 opp rested Character cost≤7 skips next Refresh",
                "ops": [
                    {
                        "op": "skip_untap",
                        "count": 1,
                        "target_kind": "opponent_character_rested",
                        "cost_lte": 7,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP10-030 Smoker — Banish is innate; do not grant_keyword.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP10-030",
        [
            {
                "timing": "activate_main",
                "summary": "Set up to 1 DON!! active; then cannot active DON via Character effects this turn",
                "ops": [
                    {"op": "active_don", "count": 1, "optional": True},
                    {"op": "cannot_active_don_by_character", "duration": "turn"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "cost_don": 0,
                "rest_self": False,
                "once": False,
            },
        ],
    )

    # Similar: P-045 innate Banish only — drop bogus grant abilities.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "P-045",
        [],
    )

    # OP12-118 Bonney.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-118",
        [
            {
                "timing": "on_play",
                "summary": "If rested cards≥8: draw 2, trash 1; then set up to 1 DON!! active",
                "ops": [
                    {"op": "draw", "count": 2},
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                    {"op": "active_don", "count": 1, "optional": True},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_rested_cards_gte": 8,
            },
        ],
    )

    # OP13-031 Law.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-031",
        [
            {
                "timing": "your_turn",
                "summary": "If Life≤1: gain Blocker",
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
                "require_life_lte": 1,
            },
            {
                "timing": "opponent_turn",
                "summary": "If Life≤1: gain Blocker",
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
                "require_life_lte": 1,
            },
            {
                "timing": "on_play",
                "summary": "You may return 1 own Character to hand: play up to 1 hand Character cost≤5 rested",
                "ops": [
                    {
                        "op": "return_to_hand",
                        "target_kind": "own_character",
                        "optional": True,
                        "as_cost": True,
                    },
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_lte": 5,
                        "as_rested": True,
                        "from_zone": "hand",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP16-030 Law.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-030",
        [
            {
                "timing": "on_play",
                "summary": "Up to 1 opp rested Character skips next Refresh",
                "ops": [
                    {
                        "op": "skip_untap",
                        "count": 1,
                        "target_kind": "opponent_character_rested",
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "end_of_your_turn",
                "summary": "Set all own green Characters cost≤5 as active",
                "ops": [
                    {
                        "op": "set_character_active",
                        "count": 5,
                        "target_kind": "own_character",
                        "optional": False,
                        "all": True,
                        "color": "green",
                        "cost_lte": 5,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # ST16-004 Jack.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST16-004",
        [
            {
                "timing": "on_play",
                "summary": "KO up to 1 opp rested Character",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character_rested",
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP04-031 Doflamingo — up to 3 rested Leader+Characters (not DON/Stage).
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP04-031",
        [
            {
                "timing": "on_play",
                "summary": "Up to 3 opp rested Leaders/Characters skip next Refresh",
                "ops": [
                    {
                        "op": "skip_untap",
                        "count": 3,
                        "target_kind": "opponent_character_rested",
                        "optional": True,
                        "include_leader": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # ST24-004 Law & Bepo.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "ST24-004",
        [
            {
                "timing": "on_play",
                "summary": "Rest up to 1 opp Character and skip its Refresh; then if opp rested≥2, Leader +2000 until opp end",
                "ops": [
                    {
                        "op": "rest_character",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "count": 1,
                        "also_skip_untap": True,
                    },
                    {
                        "op": "buff",
                        "amount": 2000,
                        "target_kind": "leader",
                        "optional": False,
                        "require_opp_rested_chars_gte": 2,
                        "duration": "until_opp_turn_end",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP13-040.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-040",
        [
            {
                "timing": "on_play",
                "summary": "You may rest 2 DON!!: up to 2 opp rested Characters cost≤7 skip next Refresh",
                "ops": [
                    {
                        "op": "rest_don",
                        "count": 2,
                        "owner": "self",
                        "as_cost": True,
                        "optional": True,
                    },
                    {
                        "op": "skip_untap",
                        "count": 2,
                        "target_kind": "opponent_character_rested",
                        "cost_lte": 7,
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

    # Strip innate-only Banish grant_keyword (detect_keywords already covers 【消失】).
    from battle.effects import detect_keywords, effect_blob

    for cid, info in catalog.items():
        keys = detect_keywords(info)
        if "banish" not in keys:
            continue
        blob = effect_blob(info)
        # Skip cards that also grant Banish conditionally / temporarily via effect text.
        if any(
            x in blob
            for x in (
                "獲得【消失】",
                "获得【消失】",
                "gains [Banish]",
                "gains【消失】",
                "獲得[消失]",
            )
        ):
            continue
        entry = ov_cards.get(cid) or lib_cards.get(cid)
        if not isinstance(entry, dict):
            continue
        abilities = []
        changed = False
        for ab in entry.get("abilities") or []:
            ab = dict(ab)
            ops = [
                o
                for o in (ab.get("ops") or [])
                if not (
                    isinstance(o, dict)
                    and o.get("op") == "grant_keyword"
                    and o.get("keyword") == "banish"
                    and o.get("target_kind") in {"self", None, ""}
                    and o.get("duration") == "permanent"
                )
            ]
            if len(ops) != len(ab.get("ops") or []):
                changed = True
            if not ops and ab.get("timing") in {"your_turn", "opponent_turn"}:
                changed = True
                continue
            ab["ops"] = ops
            if ops:
                abilities.append(ab)
            else:
                changed = True
        if changed:
            entry2 = normalize_card_entry(cid, {"version": int(entry.get("version") or 1), "abilities": abilities})
            ov_cards[cid] = entry2
            lib_cards[cid] = {**entry2, "card_id": cid}
            n += 1

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library(force=True)
    print(f"batch_ao updated {n} card entries")


if __name__ == "__main__":
    main()
