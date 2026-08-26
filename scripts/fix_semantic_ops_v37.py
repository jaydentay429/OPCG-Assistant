#!/usr/bin/env python3
"""Deterministic semantic fixes v37: exact-ID rebuilds only.

Life-damage / KO gates, grant/trash targets, stage costs, replace_leave leftovers.
Dual-writes library + overrides. Merges ids file across re-runs.
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

OUT_IDS = ROOT / "meta" / "logs" / "ops_v37_fixed_ids.txt"


def _rebuild(cid: str, abilities: list[dict[str, Any]]) -> dict[str, Any]:
    cleaned = [a for a in (normalize_ability(x) for x in abilities) if a]
    return normalize_card_entry(cid, {"version": 1, "abilities": cleaned})


def _shield_both_turns(body: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for timing in ("your_turn", "opponent_turn"):
        ab = dict(body)
        ab["timing"] = timing
        out.append(ab)
    return out


REBUILDS: dict[str, list[dict[str, Any]]] = {
    "OP03-043": [
        {
            "timing": "when_attacking",
            "summary": "When this attack deals Life damage: may trash top 3, then trash this",
            "ops": [
                {"op": "trash_deck_top", "count": 3, "optional": True, "as_cost": True},
                {"op": "trash", "target_kind": "self", "optional": False},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "on_life_damage": True,
        }
    ],
    "OP04-073": [
        {
            "timing": "activate_main",
            "summary": "Trash this and 1 own Baroque Works Character: gain up to 1 active DON!!",
            "ops": [
                {"op": "trash", "target_kind": "self", "as_cost": True, "optional": False},
                {
                    "op": "trash",
                    "target_kind": "own_character",
                    "trait_contains": "Baroque Works",
                    "exclude_self": True,
                    "as_cost": True,
                    "optional": False,
                },
                {"op": "gain_don", "count": 1, "optional": True},
            ],
            "status": "compiled",
            "confidence": 0.9,
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
    "OP04-086": [
        {
            "timing": "on_ko",
            "summary": "DON!!×1: when this battles and KOs opp Character, draw 2 trash 2",
            "ops": [
                {"op": "draw", "count": 2},
                {"op": "trash_hand", "count": 2, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_attached_gte": 1,
            "on_ko_caused_by_battle": True,
        }
    ],
    "OP04-090": [
        {
            "timing": "your_turn",
            "summary": "This Character can attack active Characters",
            "ops": [{"op": "allow_attack_active", "target_kind": "self", "optional": False}],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "activate_main",
            "summary": "Once: may return 7 trash to bottom as cost: set this active; skip next own refresh",
            "ops": [
                {
                    "op": "trash_to_bottom",
                    "count": 7,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {"op": "set_character_active", "target_kind": "self", "optional": False},
                {"op": "skip_untap", "target_kind": "self", "optional": False},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
        },
    ],
    "OP04-093": [
        {
            "timing": "main_start",
            "summary": "Up to 1 own Dressrosa gains +6000 this turn",
            "ops": [
                {
                    "op": "buff",
                    "amount": 6000,
                    "target_kind": "own_character",
                    "trait_contains": "Dressrosa",
                    "optional": True,
                    "count": 1,
                    "duration": "turn",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "main_start",
            "summary": "If trash≥15: that Dressrosa also gains Double Attack this turn",
            "ops": [
                {
                    "op": "grant_keyword",
                    "keyword": "double_attack",
                    "target_kind": "own_character",
                    "trait_contains": "Dressrosa",
                    "optional": True,
                    "count": 1,
                    "duration": "turn",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_trash_gte": 15,
        },
        {
            "timing": "trigger",
            "summary": "Draw 3 trash 2",
            "ops": [
                {"op": "draw", "count": 3},
                {"op": "trash_hand", "count": 2, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP04-111": [
        {
            "timing": "activate_main",
            "summary": "Trash 1 other own Homies and rest this: set up to 1 Charlotte Lily active",
            "ops": [
                {
                    "op": "trash",
                    "target_kind": "own_character",
                    "trait_contains": "Homies",
                    "exclude_self": True,
                    "as_cost": True,
                    "optional": False,
                },
                {"op": "rest_character", "target_kind": "self", "as_cost": True, "optional": False},
                {
                    "op": "set_character_active",
                    "target_kind": "own_character",
                    "name_contains": "Charlotte Lily|夏洛特・莉莉|夏洛特・莉莉",
                    "optional": True,
                    "count": 1,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "rest_self": True,
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
    "OP04-118": [
        {
            "timing": "your_turn",
            "summary": "All other own red Characters cost≥3 gain Rush",
            "ops": [
                {
                    "op": "grant_keyword",
                    "keyword": "rush",
                    "target_kind": "own_character",
                    "color": "red",
                    "cost_gte": 3,
                    "exclude_self": True,
                    "all": True,
                    "duration": "permanent",
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP05-003": [
        {
            "timing": "your_turn",
            "summary": "If another own Character has power≥7000, this gains Rush",
            "ops": [{"op": "grant_keyword", "keyword": "rush", "target_kind": "self", "duration": "permanent"}],
            "status": "compiled",
            "confidence": 0.95,
            "require_other_own_char_power_gte": 7000,
        }
    ],
    "OP05-009": [
        {
            "timing": "on_play",
            "summary": "If Leader power≤0: draw 1",
            "ops": [{"op": "draw", "count": 1}],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_power_lte": 0,
        }
    ],
    "OP05-016": [
        {
            "timing": "when_attacking",
            "summary": "If this power≥7000: opponent cannot activate Blocker this battle",
            "ops": [{"op": "deny_blocker", "duration": "battle"}],
            "status": "compiled",
            "confidence": 0.95,
            "require_source_power_gte": 7000,
        },
        {
            "timing": "trigger",
            "summary": "May trash 1 hand: if Leader multicolor, play this",
            "ops": [
                {"op": "trash_hand", "count": 1, "as_cost": True, "optional": True, "owner": "self"},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": False,
                    "from_zone": "hand",
                    "self_card": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_multicolor": True,
        },
    ],
    "OP05-031": [
        {
            "timing": "when_attacking",
            "summary": "Once: if ≥2 rested own Characters, set up to 1 rested cost=1 active",
            "ops": [
                {
                    "op": "set_character_active",
                    "target_kind": "own_character",
                    "cost_eq": 1,
                    "optional": True,
                    "count": 1,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
            "require_rested_own_chars_gte": 2,
        }
    ],
    "OP05-056": [
        {
            "timing": "on_play",
            "summary": "May put 1 other own Character on bottom: draw 1",
            "ops": [
                {
                    "op": "return_to_bottom",
                    "target_kind": "own_character",
                    "exclude_self": True,
                    "as_cost": True,
                    "optional": True,
                    "count": 1,
                },
                {"op": "draw", "count": 1},
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP05-058": [
        {
            "timing": "main_start",
            "summary": "All Characters cost≤3 to owner's bottom; both trash hand down to 5",
            "ops": [
                {
                    "op": "return_to_bottom",
                    "target_kind": "any_character",
                    "cost_lte": 3,
                    "all": True,
                    "optional": False,
                },
                {"op": "trash_hand_down_to", "hand_size": 5, "side": "both"},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "All Characters cost≤2 to owner's bottom",
            "ops": [
                {
                    "op": "return_to_bottom",
                    "target_kind": "any_character",
                    "cost_lte": 2,
                    "all": True,
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP05-059": [
        {
            "timing": "main_start",
            "summary": "If Leader multicolor: draw 1, then return up to 1 Character cost≤5 to hand",
            "ops": [
                {"op": "draw", "count": 1},
                {
                    "op": "return_to_hand",
                    "target_kind": "any_character",
                    "cost_lte": 5,
                    "optional": True,
                    "count": 1,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_multicolor": True,
        },
        {
            "timing": "trigger",
            "summary": "If Leader multicolor: draw 2",
            "ops": [{"op": "draw", "count": 2}],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_multicolor": True,
        },
    ],
    "OP05-078": [
        {
            "timing": "main_start",
            "summary": "DON!!−1: up to 1 own Kid Pirates Leader/Character +5000 this turn",
            "ops": [
                {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                {
                    "op": "buff",
                    "amount": 5000,
                    "target_kind": "own_leader_or_character",
                    "trait_contains": "Kid Pirates",
                    "optional": True,
                    "count": 1,
                    "duration": "turn",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "Add up to 1 active DON!! from your DON!! deck",
            "ops": [{"op": "gain_don", "count": 1, "optional": True}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP05-104": [
        {
            "timing": "on_play",
            "summary": "May put 1 own Stage on bottom: draw 1 and trash 1 hand",
            "ops": [
                {
                    "op": "return_to_bottom",
                    "target_kind": "own_stage",
                    "as_cost": True,
                    "optional": True,
                    "count": 1,
                },
                {"op": "draw", "count": 1},
                {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP06-102": [
        {
            "timing": "activate_main",
            "summary": "Once: put Stage cost=1 on bottom: KO up to 1 opp Character cost≤2",
            "ops": [
                {
                    "op": "return_to_bottom",
                    "target_kind": "own_stage",
                    "cost_eq": 1,
                    "as_cost": True,
                    "optional": True,
                    "count": 1,
                },
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "cost_lte": 2,
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
        },
        {
            "timing": "trigger",
            "summary": "If Life≤2: play this",
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
            "require_life_lte": 2,
        },
    ],
    "OP06-112": [
        {
            "timing": "when_attacking",
            "summary": "May trash 1 hand: rest up to 1 opp DON!!",
            "ops": [
                {"op": "trash_hand", "count": 1, "as_cost": True, "optional": True, "owner": "self"},
                {"op": "rest_don", "count": 1, "owner": "opponent", "optional": True},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "If opp Life≤3: play this",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                    "self_card": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_opp_life_lte": 3,
        },
    ],
    "OP06-114": [
        {
            "timing": "on_play",
            "summary": "May put Stage cost=1 on bottom: look 5, add Upper Yard or Shandian Warrior",
            "ops": [
                {
                    "op": "return_to_bottom",
                    "target_kind": "own_stage",
                    "cost_eq": 1,
                    "as_cost": True,
                    "optional": True,
                    "count": 1,
                },
                {
                    "op": "search_deck",
                    "top_n": 5,
                    "max_add": 1,
                    "name_contains": "Upper Yard|神之島",
                    "trait_contains": "Shandian Warrior",
                    "name_or_trait": True,
                    "order_bottom": True,
                    "destination": "hand",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP16-033": _shield_both_turns(
        {
            "summary": "If this would be K.O.'d, may rest 2 own cards instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "ko",
                    "target": "self",
                    "cost": "rest_own",
                    "rest_count": 2,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ),
    "P-111": _shield_both_turns(
        {
            "summary": "Once: if own Straw Hat would leave by opp effect, rest 1 DON!! instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "own_filtered",
                    "cost": "rest_don",
                    "don_count": 1,
                    "trait_contains": "Straw Hat Crew",
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
        }
    ),
    "ST22-012": [
        *_shield_both_turns(
            {
                "summary": "Once: if this would be K.O.'d by opp effect, trash 1 hand instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "self",
                        "cost": "trash_hand",
                        "trash_count": 1,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "once": True,
            }
        ),
        {
            "timing": "when_attacking",
            "summary": "Reveal top; if Whitebeard Pirates, +1000 until opp next end",
            "ops": [
                {"op": "look_deck", "count": 1, "position": "top"},
                {
                    "op": "buff_self",
                    "amount": 1000,
                    "duration": "until_opp_turn_end",
                    "trait_contains": "Whitebeard Pirates",
                },
            ],
            "status": "compiled",
            "confidence": 0.85,
        },
    ],
    "ST23-002": [
        {
            "timing": "hand_cost",
            "summary": "If opp has Character base power≥8000, this card in hand −3 cost",
            "ops": [{"op": "hand_cost_reduce", "amount": -3}],
            "status": "compiled",
            "confidence": 0.95,
            "require_opp_char_base_power_gte": 8000,
        },
        {
            "timing": "on_play",
            "summary": "If Leader is Red-Haired or Uta: Leader +2000 until opp next end",
            "ops": [
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "leader",
                    "optional": False,
                    "duration": "until_opp_turn_end",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_name": "Uta|美音",
            "require_leader_trait": "Red-Haired Pirates",
            "require_leader_name_or_trait": True,
        },
    ],
    "EB02-056": [
        {
            "timing": "on_play",
            "summary": "Look 5: play up to 1 Scientist cost≤5 other than Vegapunk; if opp≤2 chars trash 1",
            "ops": [
                {
                    "op": "search_deck",
                    "top_n": 5,
                    "max_add": 1,
                    "trait_contains": "Scientist",
                    "cost_lte": 5,
                    "exclude_name": "Vegapunk|貝卡帕庫",
                    "destination": "play",
                    "card_type": "character",
                    "order_bottom": True,
                },
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": False,
                    "owner": "self",
                    "require_opp_chars_count_lte": 2,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "Draw 1",
            "ops": [{"op": "draw", "count": 1}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "EB03-061": [
        {
            "timing": "activate_main",
            "summary": "Once: active 1 DON!!; then rest opp DON!! or Character cost≤4",
            "ops": [
                {"op": "active_don", "count": 1, "optional": True},
                {
                    "op": "choose_one",
                    "options": [
                        {
                            "id": "rest_char",
                            "label": "Rest up to 1 opp Character cost≤4",
                            "ops": [
                                {
                                    "op": "rest_character",
                                    "target_kind": "opponent_character",
                                    "cost_lte": 4,
                                    "optional": True,
                                    "count": 1,
                                }
                            ],
                        },
                        {
                            "id": "rest_don",
                            "label": "Rest up to 1 opp DON!!",
                            "ops": [{"op": "rest_don", "count": 1, "owner": "opponent", "optional": True}],
                        },
                    ],
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
        },
        {
            "timing": "end_of_your_turn",
            "summary": "May rest 1 DON!!: set up to 1 own FILM Character active",
            "ops": [
                {"op": "rest_don", "count": 1, "owner": "self", "as_cost": True, "optional": True},
                {
                    "op": "set_character_active",
                    "target_kind": "own_character",
                    "trait_contains": "FILM",
                    "optional": True,
                    "count": 1,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*", default=None, help="Optional subset of base IDs")
    args = ap.parse_args()

    bases = list(REBUILDS.keys())
    if args.ids:
        want = set(args.ids)
        bases = [b for b in bases if b in want]

    # Include exact + parallel suffixes present in library.
    lib_path, ovr_path = library_paths()
    raw = json.loads(lib_path.read_text())
    cards = raw["cards"]
    PARALLEL_BASES = set(bases)

    targets: list[str] = []
    for cid in list(cards.keys()):
        for base in bases:
            if cid == base or (base in PARALLEL_BASES and cid.startswith(base + "-")):
                targets.append(cid)

    # Always include bases even if missing from library keys (will create).
    for base in bases:
        if base not in targets:
            targets.append(base)

    seen: set[str] = set()
    ordered: list[str] = []
    for cid in targets:
        if cid not in seen:
            seen.add(cid)
            ordered.append(cid)

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
    prev_ids = [ln.strip() for ln in OUT_IDS.read_text().splitlines() if ln.strip()] if OUT_IDS.exists() else []
    merged: list[str] = []
    seen_ids: set[str] = set()
    for cid in prev_ids + fixed:
        if cid not in seen_ids:
            seen_ids.add(cid)
            merged.append(cid)
    OUT_IDS.write_text("\n".join(merged) + ("\n" if merged else ""))
    print(json.dumps({"fixed": len(fixed), "merged": len(merged), "ids_file": str(OUT_IDS), "ids": fixed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
