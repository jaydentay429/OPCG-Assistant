#!/usr/bin/env python3
"""Deterministic semantic fixes v34: exact-ID rebuilds only.

Focus: trash count, KO cost, replace_leave→opp_remove, hand_cost_reduce name,
grant rush filters, counter cannot_be_ko. Dual-writes library + overrides.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_ability, normalize_card_entry  # noqa: E402

OUT_IDS = ROOT / "meta" / "logs" / "ops_v34_fixed_ids.txt"


def _rebuild(cid: str, abilities: list[dict[str, Any]]) -> dict[str, Any]:
    cleaned = [a for a in (normalize_ability(x) for x in abilities) if a]
    return normalize_card_entry(cid, {"version": 1, "abilities": cleaned})


def _shield_both_turns(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Continuous leave/KO shields need both turn timings for review digest."""
    out: list[dict[str, Any]] = []
    for timing in ("your_turn", "opponent_turn"):
        ab = dict(body)
        ab["timing"] = timing
        out.append(ab)
    return out


REBUILDS: dict[str, list[dict[str, Any]]] = {
    "OP04-083": [
        {
            "timing": "on_play",
            "summary": "Own Characters cannot be K.O.'d by effects until next turn start; draw 2 trash 2",
            "ops": [
                {
                    "op": "cannot_be_ko",
                    "target_kind": "own_character",
                    "all": True,
                    "optional": False,
                },
                {"op": "draw", "count": 2},
                {"op": "trash_hand", "count": 2, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP11-110": [
        *_shield_both_turns(
            {
                "summary": "If this would be K.O.'d, rest Fish-Man Island or Shirahoshi Leader instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "ko",
                        "target": "self",
                        "cost": "rest_own",
                        "rest_name_contains": "Fish-Man Island|魚人島|鱼人岛|Shirahoshi|白星",
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.9,
            }
        ),
        {
            "timing": "on_play",
            "summary": "Life to hand: KO opp Character cost≤1",
            "ops": [
                {
                    "op": "life_to_hand",
                    "count": 1,
                    "position": "top_or_bottom",
                    "as_cost": True,
                    "optional": True,
                },
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "cost_lte": 1,
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP14-034": [
        {
            "timing": "your_turn",
            "summary": "Green Straw Hat Crew base cost≥4 gain +1000",
            "ops": [
                {
                    "op": "buff",
                    "amount": 1000,
                    "target_kind": "own_character",
                    "all": True,
                    "trait_contains": "Straw Hat Crew",
                    "color": "green",
                    "base_cost_gte": 4,
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
        *_shield_both_turns(
            {
                "summary": "Once: if Straw Hat Crew would be K.O.'d by opp effect, rest 1 own Character instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "own_filtered",
                        "cost": "rest_own",
                        "rest_count": 1,
                        "trait_contains": "Straw Hat Crew",
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.9,
                "once": True,
            }
        ),
    ],
    "OP12-061": [
        *_shield_both_turns(
            {
                "summary": "Once: if Trafalgar Law would be K.O.'d, add top Life to hand instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "ko",
                        "target": "own_filtered",
                        "cost": "life_to_hand",
                        "name_contains": "Trafalgar Law|托拉法爾加・羅|托拉法尔加・罗",
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.9,
                "once": True,
            }
        ),
        {
            "timing": "activate_main",
            "summary": "Once: DON!!−1: next Law cost≥4 play cost −2 this turn",
            "ops": [
                {"op": "return_don", "count": 1, "as_cost": True, "optional": True},
                {
                    "op": "hand_cost_reduce",
                    "amount": -2,
                    "cost_gte": 4,
                    "name_contains": "Trafalgar Law|托拉法爾加・羅|托拉法尔加・罗",
                    "next_only": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
        },
    ],
    "OP15-035": _shield_both_turns(
        {
            "summary": "If own base power≤7000 would leave by opp effect, rest 2 own cards instead",
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
            "confidence": 0.9,
        }
    ),
    "OP15-094": _shield_both_turns(
        {
            "summary": "If other Straw Hat Crew would leave by opp effect, trash this instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "own_filtered",
                    "cost": "trash_self",
                    "trait_contains": "Straw Hat Crew",
                    "exclude_self": True,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ),
    "ST30-009": _shield_both_turns(
        {
            "summary": "If own base power 6000 would leave by opp effect, trash this and draw 1 instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "own_filtered",
                    "cost": "trash_self",
                    "base_power_gte": 6000,
                    "base_power_lte": 6000,
                    "then_draw": 1,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ),
    "OP11-101": _shield_both_turns(
        {
            "summary": "Once: if other Supernovas would leave by opp effect, add them to Life face-down instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "own_filtered",
                    "cost": "to_life",
                    "trait_contains": "Supernovas",
                    "exclude_name": "Capone",
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
        }
    ),
    "OP10-037": [
        *_shield_both_turns(
            {
                "summary": "Once: if this would leave by opp effect, rest 1 ODYSSEY Character instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "self",
                        "cost": "rest_other_character",
                        "rest_trait_contains": "ODYSSEY",
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.9,
                "once": True,
            }
        ),
        {
            "timing": "end_of_your_turn",
            "summary": "Set up to 1 ODYSSEY Character active",
            "ops": [
                {
                    "op": "set_character_active",
                    "target_kind": "own_character",
                    "trait_contains": "ODYSSEY",
                    "count": 1,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "PRB01-001": [
        {
            "timing": "activate_main",
            "summary": "Once: up to 1 own cost≤8 Character with no On Play gains Rush this turn",
            "ops": [
                {
                    "op": "grant_keyword",
                    "keyword": "rush",
                    "target_kind": "own_character",
                    "cost_lte": 8,
                    "require_no_on_play": True,
                    "count": 1,
                    "duration": "turn",
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
        }
    ],
    "ST05-017": [
        {
            "timing": "counter_event",
            "summary": "Up to 1 FILM Leader/Character +4000 this battle; if Character, cannot be K.O.'d this turn",
            "ops": [
                {
                    "op": "buff",
                    "amount": 4000,
                    "target_kind": "own_leader_or_character",
                    "trait_contains": "FILM",
                    "duration": "battle",
                    "optional": True,
                    "count": 1,
                },
                {
                    "op": "cannot_be_ko",
                    "target_kind": "own_character",
                    "trait_contains": "FILM",
                    "duration": "turn",
                    "optional": True,
                    "count": 1,
                },
            ],
            "status": "compiled",
            "confidence": 0.85,
        },
        {
            "timing": "trigger",
            "summary": "Add up to 1 active DON!!",
            "ops": [{"op": "gain_don", "count": 1, "optional": True}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
}


PARALLEL_BASES = set(REBUILDS.keys())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.parse_args(argv)

    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    targets: list[str] = []
    for base in REBUILDS:
        for cid in catalog:
            if cid == base or (base in PARALLEL_BASES and cid.startswith(base + "-")):
                targets.append(cid)

    seen: set[str] = set()
    ordered: list[str] = []
    for cid in targets:
        if cid not in seen:
            seen.add(cid)
            ordered.append(cid)

    lib_path, ovr_path = library_paths()
    raw = json.loads(lib_path.read_text())
    cards = raw["cards"]
    ovr = json.loads(ovr_path.read_text())
    overrides = ovr.get("cards") or {}

    fixed: list[str] = []
    for cid in ordered:
        base = None
        for b in REBUILDS:
            if cid == b or cid.startswith(b + "-"):
                base = b
                break
        if not base:
            continue
        abilities = REBUILDS[base]
        out = _rebuild(cid, [dict(a) for a in abilities])
        prev = cards.get(cid) or get_card_entry(cid) or {"abilities": []}
        if json.dumps(prev.get("abilities"), sort_keys=True, ensure_ascii=False) == json.dumps(
            out.get("abilities"), sort_keys=True, ensure_ascii=False
        ):
            continue
        cards[cid] = out
        overrides[cid] = out
        fixed.append(cid)

    raw["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    lib_path.write_text(json.dumps(raw, ensure_ascii=False, separators=(",", ":")))
    ovr["cards"] = overrides
    ovr["generated_at"] = raw["generated_at"]
    ovr_path.write_text(json.dumps(ovr, ensure_ascii=False, separators=(",", ":")))
    reload_effect_library(force=True)

    OUT_IDS.parent.mkdir(parents=True, exist_ok=True)
    prev_ids: list[str] = []
    if OUT_IDS.exists():
        prev_ids = [ln.strip() for ln in OUT_IDS.read_text().splitlines() if ln.strip()]
    merged: list[str] = []
    seen_ids: set[str] = set()
    for cid in prev_ids + fixed:
        if cid not in seen_ids:
            seen_ids.add(cid)
            merged.append(cid)
    OUT_IDS.write_text("\n".join(merged) + ("\n" if merged else ""))
    print(json.dumps({"fixed": len(fixed), "ids_file": str(OUT_IDS), "ids": fixed, "merged": len(merged)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
