#!/usr/bin/env python3
"""Batch AE: Dressrosa / Rebecca / Leo / Sanji-style encoding fixes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

DRESSROSA = "Dressrosa|多雷斯羅薩"
REBECCA = "Rebecca|蕾貝卡"
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


def _bilingual_dressrosa(obj: dict[str, Any]) -> bool:
    changed = False
    for key in ("trait_contains", "require_leader_trait"):
        val = obj.get(key)
        if val == "Dressrosa":
            obj[key] = DRESSROSA
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

    # OP15-039 Rebecca Leader: permanent cannot_attack (not timed deny_attack).
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-039",
        [
            {
                "timing": "your_turn",
                "summary": "This Leader cannot attack",
                "ops": [{"op": "cannot_attack", "target_kind": "leader"}],
                "status": "compiled",
                "confidence": 0.98,
            },
            {
                "timing": "opponent_turn",
                "summary": "This Leader cannot attack",
                "ops": [{"op": "cannot_attack", "target_kind": "leader"}],
                "status": "compiled",
                "confidence": 0.98,
            },
            {
                "timing": "activate_main",
                "summary": "Rest this Leader and return 1 Dressrosa Character: play Dressrosa cost 3",
                "ops": [
                    {
                        "op": "return_to_hand",
                        "target_kind": "own_character",
                        "optional": False,
                        "as_cost": True,
                        "trait_contains": DRESSROSA,
                    },
                    {
                        "op": "play_from_hand",
                        "count": 1,
                        "card_type": "character",
                        "optional": True,
                        "cost_eq": 3,
                        "trait_contains": DRESSROSA,
                        "from_zone": "hand",
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "cost_don": 0,
                "rest_self": True,
                "once": False,
            },
        ],
    )

    # OP15-040 Viola — Dressrosa look-3.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-040",
        [
            {
                "timing": "on_play",
                "summary": "Look 3: add up to 1 Dressrosa, rest bottom any order",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": DRESSROSA,
                        "top_n": 3,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP15-052 Leo — place any own Character under deck (incl. victim).
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-052",
        [
            {
                "timing": "your_turn",
                "summary": "Replace opp remove of base power≤7000 by placing 1 Character under deck",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "own_filtered",
                        "cost": "return_own_to_bottom",
                        "base_power_lte": 7000,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "opponent_turn",
                "summary": "Replace opp remove of base power≤7000 by placing 1 Character under deck",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "own_filtered",
                        "cost": "return_own_to_bottom",
                        "base_power_lte": 7000,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP15-053 Rebecca — DON!!×1 Blocker + Dressrosa look-3.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-053",
        [
            {
                "timing": "your_turn",
                "summary": "[DON!! x1] gains Blocker",
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
                "summary": "[DON!! x1] gains Blocker",
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
                "timing": "on_play",
                "summary": "Look 3: add up to 1 Dressrosa",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": DRESSROSA,
                        "top_n": 3,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP15-042 Kyros — trash cost gated by Rebecca leader (bilingual).
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-042",
        [
            {
                "timing": "on_play",
                "summary": "You may trash 1: if Leader is Rebecca, gain Rush this turn",
                "ops": [
                    {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                    {
                        "op": "grant_keyword",
                        "keyword": "rush",
                        "target_kind": "self",
                        "duration": "turn",
                    },
                ],
                "status": "compiled",
                "confidence": 0.9,
                "require_leader_name": REBECCA,
            },
            {
                "timing": "on_ko",
                "summary": "Add this Character from trash to hand",
                "ops": [
                    {
                        "op": "add_from_trash",
                        "count": 1,
                        "optional": False,
                        "self_card": True,
                        "destination": "hand",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP15-047 Sanji — innate Blocker; on play grant Unblockable; drop bogus on_block.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-047",
        [
            {
                "timing": "on_play",
                "summary": "Up to 1 own Character gains Unblockable this turn",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "blockerless",
                        "target_kind": "own_character",
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

    # OP15-051 Luffy — opponent turn +3000 if Dressrosa leader.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP15-051",
        [
            {
                "timing": "opponent_turn",
                "summary": "If Leader has Dressrosa, +3000 power",
                "ops": [{"op": "buff_self", "amount": 3000}],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_trait": DRESSROSA,
            },
        ],
    )

    # OP16-056 Mr.3 — keep encoding; normalize via rewrite for certainty.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP16-056",
        [
            {
                "timing": "activate_main",
                "summary": "Trash this: draw 2; up to 1 opp cost≤9 cannot attack until opp end",
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
            },
        ],
    )

    # OP07-051 Hancock — exclude Luffy bilingual; bottom cost≤1 either side.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP07-051",
        [
            {
                "timing": "on_play",
                "summary": "Deny attack opp Character other than Luffy; then bottom cost≤1 Character",
                "ops": [
                    {
                        "op": "deny_attack",
                        "count": 1,
                        "optional": True,
                        "target_kind": "opponent_character",
                        "duration": "until_opp_turn_end",
                        "exclude_name": LUFFY,
                    },
                    {
                        "op": "return_to_bottom",
                        "count": 1,
                        "optional": True,
                        "target_kind": "any_character",
                        "cost_lte": 1,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP10-045 Cavendish — draw 2 trash 1 once.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP10-045",
        [
            {
                "timing": "when_attacking",
                "summary": "Once: draw 2 and trash 1 from hand",
                "ops": [
                    {"op": "draw", "count": 2},
                    {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            },
        ],
    )

    # OP10-046 Kyros — return any Character cost≤5.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP10-046",
        [
            {
                "timing": "on_play",
                "summary": "Return up to 1 Character with cost ≤5 to owner's hand",
                "ops": [
                    {
                        "op": "return_to_hand",
                        "target_kind": "any_character",
                        "optional": True,
                        "cost_lte": 5,
                        "count": 1,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP10-049 Sabo — replace leave return self to hand.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP10-049",
        [
            {
                "timing": "your_turn",
                "summary": "Replace opp remove of base cost≤7 other than Sabo by returning this to hand",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "own_filtered",
                        "cost": "return_self_to_hand",
                        "exclude_name": "Sabo|薩波|萨波",
                        "base_cost_lte": 7,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "opponent_turn",
                "summary": "Replace opp remove of base cost≤7 other than Sabo by returning this to hand",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "own_filtered",
                        "cost": "return_self_to_hand",
                        "exclude_name": "Sabo|薩波|萨波",
                        "base_cost_lte": 7,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP14-049 Jinbe.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP14-049",
        [
            {
                "timing": "your_turn",
                "summary": "When hand trashed by effect, gain Rush this turn",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "rush",
                        "target_kind": "self",
                        "duration": "turn",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "on_hand_trashed_by_effect": True,
            },
            {
                "timing": "opponent_turn",
                "summary": "When hand trashed by effect, gain Rush this turn",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "rush",
                        "target_kind": "self",
                        "duration": "turn",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "on_hand_trashed_by_effect": True,
            },
            {
                "timing": "on_play",
                "summary": "Rest 2 DON!!: draw 2 and return up to 1 Character cost≤7",
                "ops": [
                    {"op": "rest_don", "count": 2, "owner": "self", "as_cost": True, "optional": True},
                    {"op": "draw", "count": 2},
                    {
                        "op": "return_to_hand",
                        "target_kind": "any_character",
                        "optional": True,
                        "cost_lte": 7,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # OP06-058 Gravity Blade.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP06-058",
        [
            {
                "timing": "on_play",
                "summary": "Place up to 2 Characters cost≤6 at bottom in any order",
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
                "summary": "Place up to 1 Character cost≤5 at bottom",
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

    # Similar: strip bogus on_block that only re-grants innate Blocker.
    for cid in ("ST15-003", "OP05-066", "OP16-083", "OP12-021", "OP14-070"):
        entry = ov_cards.get(cid) or lib_cards.get(cid)
        if not entry:
            continue
        new_abs: list[dict[str, Any]] = []
        stripped = False
        for a in entry.get("abilities") or []:
            if a.get("timing") != "on_block":
                new_abs.append(a)
                continue
            ops = a.get("ops") or []
            if (
                len(ops) == 1
                and ops[0].get("op") == "grant_keyword"
                and ops[0].get("keyword") == "blocker"
                and ops[0].get("target_kind") == "self"
            ):
                stripped = True
                continue
            new_abs.append(a)
        if stripped:
            n += _write(ov_cards, lib_cards, catalog, cid, new_abs)

    # Similar: Dressrosa EN-only → bilingual in overrides + library.
    dress_n = 0
    for store in (ov_cards, lib_cards):
        for cid, entry in list(store.items()):
            changed = False
            for ab in entry.get("abilities") or []:
                if _bilingual_dressrosa(ab):
                    changed = True
                for op in ab.get("ops") or []:
                    if _bilingual_dressrosa(op):
                        changed = True
            if changed:
                store[cid] = normalize_card_entry(cid, entry)
                dress_n += 1
    n += dress_n // 2  # rough; both stores

    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n")
    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n")
    reload_effect_library()
    print(f"batch_ae updated entries≈{n}")


if __name__ == "__main__":
    main()
