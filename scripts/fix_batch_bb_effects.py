#!/usr/bin/env python3
"""Batch BB: Shirahoshi / Neptunian / OP13-118 Then-if / Megalo fixes."""

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

NEPTUNIAN = "Neptunian|Sea Creature|海王類"
FISH_ISLAND = "Fish-Man Island|魚人島"
SHIRA = "Shirahoshi|白星"
SHIRA_PRINCESS = "Shirahoshi|白星公主"
MEGALO = "Megalo|梅卡洛"
NEPT_OR_ISLAND = [NEPTUNIAN, FISH_ISLAND]


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
        "OP11-022",
        [
            {
                "timing": "your_turn",
                "summary": "This Leader cannot attack",
                "ops": [{"op": "cannot_attack", "target_kind": "leader"}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "opponent_turn",
                "summary": "This Leader cannot attack",
                "ops": [{"op": "cannot_attack", "target_kind": "leader"}],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "activate_main",
                "summary": "Once: rest 1 DON!! + flip Life face-up: play Neptunian or Megalo cost≤ field DON!!",
                "ops": [
                    {
                        "op": "rest_don",
                        "count": 1,
                        "owner": "self",
                        "as_cost": True,
                        "optional": True,
                    },
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
                        "name_contains": MEGALO,
                        "trait_contains": NEPTUNIAN,
                        "name_or_trait": True,
                        "cost_lte_own_don_field": True,
                        "from_zone": "hand",
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
        "OP11-100",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Shirahoshi: you may flip Life face-down: draw 1",
                "ops": [
                    {
                        "op": "flip_life",
                        "face": "down",
                        "position": "top",
                        "optional": True,
                        "as_cost": True,
                    },
                    {"op": "draw", "count": 1},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_name": SHIRA,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP12-102",
        [
            {
                "timing": "your_turn",
                "summary": "Instead of own base-cost≤6 leaving by opp effect: flip Life face-up",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "own_filtered",
                        "cost": "flip_life",
                        "face": "up",
                        "life_position": "top",
                        "base_cost_lte": 6,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "opponent_turn",
                "summary": "Instead of own base-cost≤6 leaving by opp effect: flip Life face-up",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "own_filtered",
                        "cost": "flip_life",
                        "face": "up",
                        "life_position": "top",
                        "base_cost_lte": 6,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "opponent_turn",
                "summary": "If no other base-cost-2 Shirahoshi: Neptunian Characters +2000",
                "ops": [
                    {
                        "op": "buff_all_own",
                        "amount": 2000,
                        "include_leader": False,
                        "trait_contains": NEPTUNIAN,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_no_other_name": SHIRA_PRINCESS,
                "require_no_other_base_cost_eq": 2,
            },
        ],
    )

    # EB03-052 — add_life gated; Then Neptunian buff ungated.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB03-052",
        [
            {
                "timing": "activate_main",
                "summary": "Trash this: if Leader Shirahoshi Princess, add Life; Then Neptunian +1000",
                "ops": [
                    {
                        "op": "trash",
                        "target_kind": "self",
                        "optional": True,
                        "as_cost": True,
                    },
                    {
                        "op": "add_life",
                        "count": 1,
                        "optional": False,
                        "position": "top",
                        "require_leader_name": SHIRA_PRINCESS,
                    },
                    {
                        "op": "buff",
                        "amount": 1000,
                        "target_kind": "own_character",
                        "optional": False,
                        "all": True,
                        "trait_contains": NEPTUNIAN,
                        "duration": "turn",
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
        "OP11-107",
        [
            {
                "timing": "activate_main",
                "summary": "Once: if Leader Shirahoshi, flip Life face-down: active this at end of turn",
                "ops": [
                    {
                        "op": "flip_life",
                        "face": "down",
                        "position": "top",
                        "optional": True,
                        "as_cost": True,
                    },
                    {
                        "op": "set_character_active",
                        "count": 1,
                        "target_kind": "self",
                        "optional": False,
                        "at_end_of_turn": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
                "require_leader_name": SHIRA,
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
        "OP11-030",
        [
            {
                "timing": "activate_main",
                "summary": "Rest 1 DON!! + this: look top 5; add up to 1 Neptunian or Fish-Man Island",
                "ops": [
                    {
                        "op": "rest_don",
                        "count": 1,
                        "owner": "self",
                        "as_cost": True,
                        "optional": True,
                    },
                    {
                        "op": "search_deck",
                        "name_contains": "",
                        "trait_contains": "",
                        "trait_any": NEPT_OR_ISLAND,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "reveal_adds": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.95,
                "rest_self": True,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-036",
        [
            {
                "timing": "on_play",
                "summary": "If Leader Shirahoshi: look top 5; add up to 1 Neptunian or Shirahoshi",
                "ops": [
                    {
                        "op": "search_deck",
                        "name_contains": SHIRA,
                        "trait_contains": NEPTUNIAN,
                        "name_or_trait": True,
                        "top_n": 5,
                        "max_add": 1,
                        "order_bottom": True,
                        "destination": "hand",
                        "reveal_adds": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_name": SHIRA,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-018",
        [
            {
                "timing": "on_play",
                "summary": "You may rest this: KO up to 1 opp rested Character power≤8000",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character_rested",
                        "optional": True,
                        "power_lte": 8000,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "rest_self": True,
            },
        ],
    )

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "EB04-016",
        [
            {
                "timing": "activate_main",
                "summary": "Active up to 1 DON!!; Then cannot active DON!! by Character effects this turn",
                "ops": [
                    {"op": "active_don", "count": 1, "optional": True},
                    {"op": "cannot_active_don_by_character", "duration": "turn"},
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "when_attacking",
                "summary": "If 3+ Neptunian Characters: rest up to 1 opp Character cost≤8",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "cost_lte": 8,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_chars_trait_gte": 3,
                "require_chars_trait": NEPTUNIAN,
            },
        ],
    )

    # OP13-118 — active_don gated by multicolor; Then cannot play ungated.
    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP13-118",
        [
            {
                "timing": "on_play",
                "summary": "If Leader multicolor: active up to 4 DON!!; Then cannot play base-cost≥5 Characters this turn",
                "ops": [
                    {
                        "op": "active_don",
                        "count": 4,
                        "optional": True,
                        "require_leader_multicolor": True,
                    },
                    {
                        "op": "cannot_play_from_hand",
                        "duration": "turn",
                        "card_type": "character",
                        "base_cost_gte": 5,
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
        "OP06-035",
        [
            {
                "timing": "on_play",
                "summary": "Rest up to 2 opp Characters or DON!!; Then Life→hand",
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
        "EB04-011",
        [
            {
                "timing": "on_play",
                "summary": "Draw 1 per own Neptunian; Then trash equal from hand",
                "ops": [
                    {
                        "op": "draw",
                        "count": 1,
                        "per_own_trait": NEPTUNIAN,
                        "then_trash_equal": True,
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

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP11-115",
        [
            {
                "timing": "counter_event",
                "summary": "If Leader Shirahoshi: up to 1 own Leader/Character +4000 this battle",
                "ops": [
                    {
                        "op": "buff",
                        "amount": 4000,
                        "target_kind": "own_leader_or_character",
                        "optional": True,
                        "duration": "battle",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_leader_name": SHIRA,
            },
            {
                "timing": "trigger",
                "summary": "KO up to 1 opp Character cost≤2",
                "ops": [
                    {
                        "op": "ko",
                        "target_kind": "opponent_character",
                        "optional": True,
                        "cost_lte": 2,
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
        "OP13-040",
        [
            {
                "timing": "on_play",
                "summary": "Rest 2 DON!!: up to 2 opp rested cost≤7 skip untap next Refresh",
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

    n += _write(
        ov_cards,
        lib_cards,
        catalog,
        "OP08-036",
        [
            {
                "timing": "on_play",
                "summary": "All opp rested Characters cost≤7 skip untap next Refresh",
                "ops": [
                    {
                        "op": "skip_untap",
                        "count": 1,
                        "target_kind": "opponent_character_rested",
                        "cost_lte": 7,
                        "optional": False,
                        "all": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
            {
                "timing": "trigger",
                "summary": "Rest up to 1 opp Character",
                "ops": [
                    {
                        "op": "rest_opponent_character",
                        "count": 1,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
            },
        ],
    )

    # Soft-fix: 「若多種顏色，A。之後，無法…登場」— active gated, cannot_play ungated.
    multi_then = re.compile(
        r"【登場時】若自己的領航卡有多種顏色時，.{2,60}。之後，.{0,40}無法"
    )
    for cid, entry in list(ov_cards.items()):
        info = catalog.get(cid) or {}
        zh = str(info.get("effect") or "")
        if not multi_then.search(zh):
            continue
        abs_out = []
        changed = False
        for ab in entry.get("abilities") or []:
            ab = dict(ab)
            if ab.get("timing") != "on_play":
                abs_out.append(ab)
                continue
            ops = [dict(o) for o in (ab.get("ops") or [])]
            # Ensure active_don / gain before cannot_play; gate only the first effect.
            act_i = next((i for i, o in enumerate(ops) if o.get("op") in {"active_don", "gain_don"}), None)
            ban_i = next((i for i, o in enumerate(ops) if o.get("op") == "cannot_play_from_hand"), None)
            if act_i is not None and ban_i is not None and act_i > ban_i:
                ops[act_i], ops[ban_i] = ops[ban_i], ops[act_i]
                act_i, ban_i = ban_i, act_i
                changed = True
            if act_i is not None:
                if ab.get("require_leader_multicolor"):
                    ops[act_i]["require_leader_multicolor"] = True
                    ab.pop("require_leader_multicolor", None)
                    changed = True
                elif not ops[act_i].get("require_leader_multicolor"):
                    ops[act_i]["require_leader_multicolor"] = True
                    changed = True
            if ban_i is not None and ops[ban_i].get("require_leader_multicolor"):
                ops[ban_i].pop("require_leader_multicolor", None)
                changed = True
            ab["ops"] = ops
            abs_out.append(ab)
        if changed:
            entry2 = normalize_card_entry(
                cid, {"version": int(entry.get("version") or 1), "abilities": abs_out}
            )
            ov_cards[cid] = entry2
            lib_cards[cid] = {**entry2, "card_id": cid}
            n += 1

    # Soft-fix: strip innate rush_character grant_keyword permanent on your_turn/opponent_turn
    # when paper has printed 【速攻：角色】.
    for cid, entry in list(ov_cards.items()):
        info = catalog.get(cid) or {}
        zh = str(info.get("effect") or "")
        if "【速攻：角色】" not in zh and "【速攻:角色】" not in zh:
            continue
        abs_out = []
        changed = False
        for ab in entry.get("abilities") or []:
            ab = dict(ab)
            if ab.get("timing") in {"your_turn", "opponent_turn"}:
                ops = [
                    o
                    for o in (ab.get("ops") or [])
                    if not (
                        o.get("op") == "grant_keyword"
                        and o.get("keyword") == "rush_character"
                        and o.get("duration") == "permanent"
                    )
                ]
                if len(ops) != len(ab.get("ops") or []):
                    changed = True
                if not ops:
                    continue
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
    print(f"batch_bb updated {n} card entries")


if __name__ == "__main__":
    main()
