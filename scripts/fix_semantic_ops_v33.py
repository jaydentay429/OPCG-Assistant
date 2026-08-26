#!/usr/bin/env python3
"""Deterministic semantic fixes v33: narrow ID-targeted rebuilds only.

Dual-writes library + overrides. Writes ONLY changed IDs to the ids file.
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

OUT_IDS = ROOT / "meta" / "logs" / "ops_v33_fixed_ids.txt"


def _rebuild(cid: str, abilities: list[dict[str, Any]]) -> dict[str, Any]:
    cleaned = [a for a in (normalize_ability(x) for x in abilities) if a]
    return normalize_card_entry(cid, {"version": 1, "abilities": cleaned})


# Exact-ID rebuilds only (no broad text matching that can bleed).
REBUILDS: dict[str, list[dict[str, Any]]] = {
    "OP10-118": [
        {
            "timing": "your_turn",
            "summary": "Once per turn: cannot be K.O.'d by opponent's effects",
            "ops": [{"op": "cannot_be_ko", "target_kind": "self", "optional": False}],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
        },
        {
            "timing": "opponent_turn",
            "summary": "Once per turn: cannot be K.O.'d by opponent's effects",
            "ops": [{"op": "cannot_be_ko", "target_kind": "self", "optional": False}],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
        },
        {
            "timing": "when_attacking",
            "summary": "Place 3 own trash bottom (any order): if opp hand≥5, trash 1 opp hand",
            "ops": [
                {
                    "op": "trash_to_bottom",
                    "count": 3,
                    "owner": "self",
                    "order_any": True,
                    "as_cost": True,
                    "optional": True,
                },
                {"op": "trash_hand", "count": 1, "owner": "opponent", "optional": False},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_opp_hand_gte": 5,
        },
    ],
    "OP03-092": [
        {
            "timing": "on_play",
            "summary": "Place 2 CP trash bottom: gain Rush this turn",
            "ops": [
                {
                    "op": "trash_to_bottom",
                    "count": 2,
                    "owner": "self",
                    "trait_includes": "CP",
                    "order_any": True,
                    "as_cost": True,
                    "optional": True,
                },
                {
                    "op": "grant_keyword",
                    "keyword": "rush",
                    "target_kind": "self",
                    "duration": "turn",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP03-032": [
        {
            "timing": "your_turn",
            "summary": "Cannot be K.O.'d in battle by Slash attribute",
            "ops": [
                {
                    "op": "cannot_be_ko",
                    "target_kind": "self",
                    "attribute": "Slash",
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
        {
            "timing": "opponent_turn",
            "summary": "Cannot be K.O.'d in battle by Slash attribute",
            "ops": [
                {
                    "op": "cannot_be_ko",
                    "target_kind": "self",
                    "attribute": "Slash",
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "OP13-064": [
        {
            "timing": "your_turn",
            "summary": "Own Leader + non-Roger-Pirates Characters have effects negated",
            "ops": [
                {
                    "op": "negate_effects",
                    "target_kind": "own_character",
                    "all": True,
                    "exclude_trait": "Roger Pirates",
                    "include_leader": True,
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.85,
        },
        {
            "timing": "opponent_turn",
            "summary": "Own Leader + non-Roger-Pirates Characters have effects negated",
            "ops": [
                {
                    "op": "negate_effects",
                    "target_kind": "own_character",
                    "all": True,
                    "exclude_trait": "Roger Pirates",
                    "include_leader": True,
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.85,
        },
        {
            "timing": "on_play",
            "summary": "DON!!−3: Leader +2000 until opp turn end; all opp Characters −2000 until opp turn end",
            "ops": [
                {"op": "return_don", "count": 3, "as_cost": True, "optional": True},
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "leader",
                    "duration": "until_opp_turn_end",
                },
                {
                    "op": "buff",
                    "amount": -2000,
                    "target_kind": "opponent_character",
                    "all": True,
                    "duration": "until_opp_turn_end",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "OP04-083": [
        {
            "timing": "on_play",
            "summary": "Own Characters cannot be K.O.'d by effects until next turn start; draw 2 trash 1",
            "ops": [
                {
                    "op": "cannot_be_ko",
                    "target_kind": "own_character",
                    "all": True,
                    "optional": False,
                },
                {"op": "draw", "count": 2},
                {"op": "trash_hand", "count": 1, "optional": False},
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "OP04-119": [
        {
            "timing": "opponent_turn",
            "summary": "While this rested: own active base-cost-5 Characters cannot be K.O.'d by effects",
            "ops": [
                {
                    "op": "cannot_be_ko",
                    "target_kind": "own_character",
                    "all": True,
                    "cost_eq": 5,
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.85,
            "require_source_active": False,
            # Gate approximated: source rested checked via require_source_active inverted not available;
            # keep continuous on opponent_turn; engine may refine later.
        },
        {
            "timing": "on_play",
            "summary": "Rest this Character: play green cost 5 from hand",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "from_zone": "hand",
                    "color": "green",
                    "cost_eq": 5,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "rest_self": True,
        },
    ],
    "OP12-061": [
        {
            "timing": "your_turn",
            "summary": "Once: if Trafalgar Law would be K.O.'d, add top Life to hand instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "ko",
                    "target": "own_filtered",
                    "cost": "life_to_hand",
                    "name_contains": "Trafalgar Law",
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.85,
            "once": True,
        },
        {
            "timing": "opponent_turn",
            "summary": "Once: if Trafalgar Law would be K.O.'d, add top Life to hand instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "ko",
                    "target": "own_filtered",
                    "cost": "life_to_hand",
                    "name_contains": "Trafalgar Law",
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.85,
            "once": True,
        },
        {
            "timing": "activate_main",
            "summary": "Once: DON!!−1: next Law cost 4 play cost reduce (approx gain_don path kept minimal)",
            "ops": [{"op": "return_don", "count": 1, "as_cost": True, "optional": True}],
            "status": "compiled",
            "confidence": 0.7,
            "once": True,
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
            "confidence": 0.85,
        },
        {
            "timing": "your_turn",
            "summary": "Once: if Straw Hat Crew would be K.O.'d by opp effect, rest 1 DON instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "ko",
                    "target": "own_filtered",
                    "cost": "rest_don",
                    "trait_contains": "Straw Hat Crew",
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.8,
            "once": True,
        },
        {
            "timing": "opponent_turn",
            "summary": "Once: if Straw Hat Crew would be K.O.'d by opp effect, rest 1 DON instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "ko",
                    "target": "own_filtered",
                    "cost": "rest_don",
                    "trait_contains": "Straw Hat Crew",
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.8,
            "once": True,
        },
    ],
    "OP14-057": [
        {
            "timing": "main_start",
            "summary": "All own Fish-Man/Merfolk Leader+Characters +1000 this turn",
            "ops": [
                {
                    "op": "buff",
                    "amount": 1000,
                    "target_kind": "own_leader_or_character",
                    "all": True,
                    "trait_contains": "Fish-Man",
                    "optional": False,
                    "duration": "turn",
                },
                {
                    "op": "buff",
                    "amount": 1000,
                    "target_kind": "own_leader_or_character",
                    "all": True,
                    "trait_contains": "Merfolk",
                    "optional": False,
                    "duration": "turn",
                },
            ],
            "status": "compiled",
            "confidence": 0.85,
        },
        {
            "timing": "trigger",
            "summary": "Draw 2",
            "ops": [{"op": "draw", "count": 2}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP16-107": [
        {
            "timing": "on_ko",
            "summary": "Add up to 1 card from top of opp Life to owner's hand",
            "ops": [
                {
                    "op": "life_to_hand",
                    "count": 1,
                    "owner": "opponent",
                    "position": "top",
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
        {
            "timing": "trigger",
            "summary": "Trash 1 hand: play this card",
            "ops": [
                {"op": "trash_hand", "count": 1, "as_cost": True, "optional": True},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "self_card": True,
                    "from_zone": "hand",
                    "optional": False,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "OP11-110": [
        {
            "timing": "your_turn",
            "summary": "If this would be K.O.'d, rest Fish-Man Island or Shirahoshi Leader instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "ko",
                    "target": "self",
                    "cost": "rest_own",
                    "name_contains": "Fish-Man Island|Shirahoshi",
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.8,
        },
        {
            "timing": "opponent_turn",
            "summary": "If this would be K.O.'d, rest Fish-Man Island or Shirahoshi Leader instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "ko",
                    "target": "self",
                    "cost": "rest_own",
                    "name_contains": "Fish-Man Island|Shirahoshi",
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.8,
        },
        {
            "timing": "on_play",
            "summary": "Life to hand: KO opp Character cost≤5",
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
                    "cost_lte": 5,
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "OP09-022": [
        {
            "timing": "your_turn",
            "summary": "Your Characters are played rested",
            "ops": [{"op": "unsupported", "reason": "play_characters_rested_aura"}],
            "status": "compiled",
            "confidence": 0.7,
        },
        {
            "timing": "opponent_turn",
            "summary": "Your Characters are played rested",
            "ops": [{"op": "unsupported", "reason": "play_characters_rested_aura"}],
            "status": "compiled",
            "confidence": 0.7,
        },
        {
            "timing": "activate_main",
            "summary": "Once: rest 3 DON: add 1 rested DON and play ODYSSEY cost≤5 from hand",
            "ops": [
                {"op": "rest_don", "count": 3, "as_cost": True, "optional": True},
                {"op": "gain_don", "count": 1, "as_rested": True},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "from_zone": "hand",
                    "trait_contains": "ODYSSEY",
                    "cost_lte": 5,
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
        },
    ],
    "OP05-109": [
        {
            "timing": "on_event",
            "summary": "Once per turn: when a Trigger activates, draw 2 trash 2",
            "ops": [
                {"op": "draw", "count": 2},
                {"op": "trash_hand", "count": 2, "optional": False},
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
            "on_trigger_activate": True,
        }
    ],
    "P-045": [
        {
            "timing": "your_turn",
            "summary": "This Character has Banish",
            "ops": [
                {
                    "op": "grant_keyword",
                    "keyword": "banish",
                    "target_kind": "self",
                    "duration": "permanent",
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "opponent_turn",
            "summary": "This Character has Banish",
            "ops": [
                {
                    "op": "grant_keyword",
                    "keyword": "banish",
                    "target_kind": "self",
                    "duration": "permanent",
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "ST05-010": [
        {
            "timing": "your_turn",
            "summary": "When battling Strike attribute Characters: +3000 this turn",
            "ops": [
                {
                    "op": "buff_self",
                    "amount": 3000,
                    "duration": "turn",
                    "require_battle_attr": "Strike",
                }
            ],
            "status": "compiled",
            "confidence": 0.75,
        },
        {
            "timing": "activate_main",
            "summary": "Once: DON!!−1: +2000 this turn (existing activate kept if present)",
            "ops": [
                {"op": "return_don", "count": 1, "as_cost": True, "optional": True},
                {"op": "buff_self", "amount": 2000, "duration": "turn"},
            ],
            "status": "compiled",
            "confidence": 0.85,
            "once": True,
        },
    ],
    "OP06-104": [
        {
            "timing": "on_ko",
            "summary": "If opp Life≤3: add up to 1 deck top to Life top",
            "ops": [{"op": "add_life", "count": 1, "optional": True}],
            "status": "compiled",
            "confidence": 0.95,
            "require_opp_life_lte": 3,
        },
        {
            "timing": "trigger",
            "summary": "If opp Life≤3: play this card",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "self_card": True,
                    "from_zone": "hand",
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_opp_life_lte": 3,
        },
    ],
    "OP12-040": [
        {
            "timing": "on_event",
            "summary": "When hand trashed by own Navy effect: draw equal to trashed count",
            "ops": [{"op": "draw", "count": 1, "then_draw_equal": True}],
            "status": "compiled",
            "confidence": 0.7,
            "require_chars_trait": "Navy",
            "on_hand_trashed_by_own_effect": True,
        }
    ],
}


# Also fix P-variants of exact bases when present in catalog.
PARALLEL_BASES = {
    "OP10-118",
    "OP03-092",
    "OP03-032",
    "OP13-064",
    "OP04-083",
    "OP04-119",
    "OP12-061",
    "OP14-034",
    "OP14-057",
    "OP16-107",
    "OP11-110",
    "OP09-022",
    "OP05-109",
    "P-045",
    "ST05-010",
    "OP06-104",
    "OP12-040",
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    args = ap.parse_args(argv)

    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    targets: list[str] = []
    for base, abs_ in REBUILDS.items():
        for cid in catalog:
            if cid == base or (base in PARALLEL_BASES and cid.startswith(base + "-")):
                targets.append(cid)

    # de-dupe preserve order
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
        base = cid.split("-P")[0].split("-R")[0]
        # map ST/P carefully
        if cid.startswith("ST") or cid.startswith("P-") or cid.startswith("EB") or cid.startswith("OP"):
            for b in REBUILDS:
                if cid == b or cid.startswith(b + "-"):
                    base = b
                    break
        abilities = REBUILDS.get(base)
        if not abilities:
            continue
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
    OUT_IDS.write_text("\n".join(fixed) + ("\n" if fixed else ""))
    print(json.dumps({"fixed": len(fixed), "ids_file": str(OUT_IDS), "ids": fixed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
