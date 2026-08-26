#!/usr/bin/env python3
"""Deterministic semantic fixes v35: exact-ID rebuilds only.

replace_leave upgrades, gates, choose_one fills, clear KO/cost fixes.
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

OUT_IDS = ROOT / "meta" / "logs" / "ops_v35_fixed_ids.txt"


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
    "EB02-030": [
        {
            "timing": "counter_event",
            "summary": "This turn: if own Character would be K.O.'d in battle, trash 1 hand instead",
            "ops": [{"op": "replace_battle_ko", "optional": True}],
            "status": "compiled",
            "confidence": 0.9,
        },
        {
            "timing": "trigger",
            "summary": "Draw 1",
            "ops": [{"op": "draw", "count": 1}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP07-042": _shield_both_turns(
        {
            "summary": "Once: if this would leave by opp effect and Leader is Seven Warlords, put another non-Moria Character on bottom instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "self",
                    "cost": "return_other_to_bottom",
                    "exclude_name": "Gecko Moria|月光・摩利亞|月光・莫利亚",
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
            "require_leader_trait": "The Seven Warlords of the Sea|王下七武海",
        }
    ),
    "OP08-045": _shield_both_turns(
        {
            "summary": "If this would be K.O.'d or leave by opp effect, trash this and draw 1 instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "self",
                    "cost": "trash_self",
                    "then_draw": 1,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ),
    "OP10-049": _shield_both_turns(
        {
            "summary": "If other own base-cost≤7 would leave by opp effect, return this to hand instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "own_filtered",
                    "cost": "return_self_to_hand",
                    "base_cost_lte": 7,
                    "exclude_name": "Sabo|薩波|萨波",
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ),
    "OP12-070": [
        *_shield_both_turns(
            {
                "summary": "If this would leave by opp effect, return 1 DON!! instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "self",
                        "cost": "return_don",
                        "don_count": 1,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.9,
            }
        ),
        {
            "timing": "your_turn",
            "summary": "+1000 per 5 Events in trash",
            "ops": [{"op": "buff_self", "amount": 1000, "per_trash_events": 5}],
            "status": "compiled",
            "confidence": 0.85,
        },
        {
            "timing": "opponent_turn",
            "summary": "+1000 per 5 Events in trash",
            "ops": [{"op": "buff_self", "amount": 1000, "per_trash_events": 5}],
            "status": "compiled",
            "confidence": 0.85,
        },
    ],
    "OP13-017": _shield_both_turns(
        {
            "summary": "Once: if Revolutionary Army would leave by opp effect, this Character −2000 instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "own_filtered",
                    "cost": "self_power_minus",
                    "amount": -2000,
                    "trait_contains": "Revolutionary Army",
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
        }
    ),
    "OP13-046": [
        {
            "timing": "your_turn",
            "summary": "Double Attack",
            "ops": [
                {
                    "op": "grant_keyword",
                    "keyword": "double_attack",
                    "target_kind": "self",
                    "duration": "permanent",
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        *_shield_both_turns(
            {
                "summary": "Once: if this would be K.O.'d or leave by opp effect, trash 1 Whitebeard Pirates hand instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "self",
                        "cost": "trash_hand",
                        "hand_trait_contains": "Whitebeard Pirates",
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.9,
                "once": True,
            }
        ),
    ],
    "OP09-022": [
        *_shield_both_turns(
            {
                "summary": "Your Characters are played rested",
                "ops": [{"op": "play_characters_rested"}],
                "status": "compiled",
                "confidence": 0.9,
                "characters_enter_rested": True,
            }
        ),
        {
            "timing": "activate_main",
            "summary": "Once: rest 3 DON: add 1 rested DON and play ODYSSEY cost≤5 from hand",
            "ops": [
                {"op": "rest_don", "count": 3, "as_cost": True, "optional": True},
                {"op": "gain_don", "count": 1, "as_rested": True, "optional": True},
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
    "OP02-094": [
        {
            "timing": "on_ko",
            "summary": "Once DON!!×1: when this Character KOs via battle, set this active",
            "ops": [{"op": "set_character_active", "target_kind": "self", "optional": False}],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
            "require_don_attached_gte": 1,
            "on_ko_caused_by_battle": True,
        }
    ],
    "OP05-017": [
        {
            "timing": "when_attacking",
            "summary": "If this power≥7000: KO up to 1 opp power≤3000",
            "ops": [
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "power_lte": 3000,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_source_power_gte": 7000,
        },
        {
            "timing": "trigger",
            "summary": "Trash up to 1 hand: if Leader multicolor, play this",
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
            "require_leader_multicolor": True,
        },
    ],
    "OP06-012": _shield_both_turns(
        {
            "summary": "If opp has base power≥6000 Leader/Character: cannot be K.O.'d in battle",
            "ops": [{"op": "cannot_be_ko", "target_kind": "self", "optional": False}],
            "status": "compiled",
            "confidence": 0.9,
            "require_opp_char_base_power_gte": 6000,
        }
    ),
    "OP06-030": [
        {
            "timing": "when_attacking",
            "summary": "If Leader is New Fish-Man Pirates: cannot be battle-KO +2000 until next turn start; Life to hand",
            "ops": [
                {"op": "cannot_be_ko", "target_kind": "self", "optional": False},
                {"op": "buff_self", "amount": 2000, "duration": "next_turn"},
                {"op": "life_to_hand", "count": 1, "position": "top"},
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_leader_trait": "New Fish-Man Pirates|新魚人海賊團",
        }
    ],
    "OP07-098": [
        *_shield_both_turns(
            {
                "summary": "If your Life < opponent Life: cannot be K.O.'d in battle",
                "ops": [{"op": "cannot_be_ko", "target_kind": "self", "optional": False}],
                "status": "compiled",
                "confidence": 0.9,
                "require_life_less_than_opponent": True,
            }
        ),
        {
            "timing": "trigger",
            "summary": "If Leader is Vegapunk, play this",
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
            "require_leader_name": "Vegapunk|貝卡帕庫|贝卡帕库",
        },
    ],
    "EB01-045": [
        {
            "timing": "on_play",
            "summary": "If opp has cost 0 Character: gain Rush this turn",
            "ops": [
                {
                    "op": "grant_keyword",
                    "keyword": "rush",
                    "target_kind": "self",
                    "duration": "turn",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_opp_char_cost_eq": 0,
        }
    ],
    "EB02-018": [
        {
            "timing": "on_play",
            "summary": "If no other Buggy: up to 1 own Leader gains Double Attack this turn",
            "ops": [
                {
                    "op": "grant_keyword",
                    "keyword": "double_attack",
                    "target_kind": "leader",
                    "duration": "turn",
                    "optional": True,
                    "count": 1,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_no_other_name": "Buggy|巴其",
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
    "OP03-028": [
        {
            "timing": "on_play",
            "summary": "Choose one: set East Blue Leader/Character cost≤6 active; OR rest this and up to 1 opp Character",
            "ops": [
                {
                    "op": "choose_one",
                    "options": [
                        {
                            "id": "opt0",
                            "label": "Set East Blue Leader or Character cost≤6 active",
                            "ops": [
                                {
                                    "op": "set_character_active",
                                    "target_kind": "own_leader_or_character",
                                    "trait_contains": "East Blue",
                                    "cost_lte": 6,
                                    "include_leader": True,
                                    "optional": True,
                                    "count": 1,
                                }
                            ],
                        },
                        {
                            "id": "opt1",
                            "label": "Rest this Character and up to 1 opp Character",
                            "ops": [
                                {"op": "rest_character", "target_kind": "self", "optional": False},
                                {
                                    "op": "rest_opponent_character",
                                    "count": 1,
                                    "optional": True,
                                },
                            ],
                        },
                    ],
                }
            ],
            "status": "compiled",
            "confidence": 0.85,
        }
    ],
    "OP10-041": [
        {
            "timing": "main_start",
            "summary": "Rest up to 1 opp cost≤6; then KO up to 1 rested opp cost≤5",
            "ops": [
                {
                    "op": "rest_opponent_character",
                    "count": 1,
                    "cost_lte": 6,
                    "optional": True,
                },
                {
                    "op": "ko",
                    "target_kind": "opponent_character_rested",
                    "cost_lte": 5,
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "Rest up to 1 opp cost≤4",
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
    "OP02-118": [
        {
            "timing": "counter_event",
            "summary": "Trash up to 1 hand: up to 1 own Character cannot be K.O.'d this battle",
            "ops": [
                {"op": "trash_hand", "count": 1, "as_cost": True, "optional": True},
                {
                    "op": "cannot_be_ko",
                    "target_kind": "own_character",
                    "count": 1,
                    "optional": True,
                    "duration": "battle",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
        {
            "timing": "trigger",
            "summary": "KO up to 1 opp Stage cost≤3",
            "ops": [
                {
                    "op": "ko",
                    "target_kind": "opponent_stage",
                    "cost_lte": 3,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "OP06-026": [
        {
            "timing": "on_play",
            "summary": "Set up to 1 own Slash cost≤4 active; this turn cannot attack Leader",
            "ops": [
                {
                    "op": "set_character_active",
                    "target_kind": "own_character",
                    "cost_lte": 4,
                    "optional": True,
                    "count": 1,
                },
                {"op": "cannot_attack_leader", "duration": "turn"},
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "OP11-005": [
        {
            "timing": "your_turn",
            "summary": "DON!!×1: cannot be K.O.'d by non-Special Character effects",
            "ops": [{"op": "cannot_be_ko", "target_kind": "self", "optional": False}],
            "status": "compiled",
            "confidence": 0.85,
            "require_don_attached_gte": 1,
        },
        {
            "timing": "opponent_turn",
            "summary": "DON!!×1: cannot be K.O.'d by non-Special Character effects",
            "ops": [{"op": "cannot_be_ko", "target_kind": "self", "optional": False}],
            "status": "compiled",
            "confidence": 0.85,
            "require_don_attached_gte": 1,
        },
    ],
    "P-007": _shield_both_turns(
        {
            "summary": "DON!!×1: cannot be K.O.'d in battle vs Strike attribute",
            "ops": [
                {
                    "op": "cannot_be_ko",
                    "target_kind": "self",
                    "attribute": "Strike",
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.85,
            "require_don_attached_gte": 1,
        }
    ),
    "P-052": _shield_both_turns(
        {
            "summary": "DON!!×1: cannot be K.O.'d in battle vs Slash attribute",
            "ops": [
                {
                    "op": "cannot_be_ko",
                    "target_kind": "self",
                    "attribute": "Slash",
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.85,
            "require_don_attached_gte": 1,
        }
    ),
    "P-054": _shield_both_turns(
        {
            "summary": "DON!!×1: cannot be K.O.'d in battle vs Strike attribute",
            "ops": [
                {
                    "op": "cannot_be_ko",
                    "target_kind": "self",
                    "attribute": "Strike",
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.85,
            "require_don_attached_gte": 1,
        }
    ),
    "OP12-096": [
        {
            "timing": "main_start",
            "summary": "KO up to 1 opp cost≤4; if you have cost≥8 Character, may choose cost≤6 instead",
            "ops": [
                {
                    "op": "choose_one",
                    "options": [
                        {
                            "id": "opt0",
                            "label": "KO cost≤4",
                            "ops": [
                                {
                                    "op": "ko",
                                    "target_kind": "opponent_character",
                                    "cost_lte": 4,
                                    "optional": True,
                                }
                            ],
                        },
                        {
                            "id": "opt1",
                            "label": "If own cost≥8 Character: KO cost≤6",
                            "ops": [
                                {
                                    "op": "ko",
                                    "target_kind": "opponent_character",
                                    "cost_lte": 6,
                                    "optional": True,
                                }
                            ],
                        },
                    ],
                }
            ],
            "status": "compiled",
            "confidence": 0.8,
        },
        {
            "timing": "trigger",
            "summary": "Draw 1 and trash deck top 1",
            "ops": [
                {"op": "draw", "count": 1},
                {"op": "trash_deck_top", "count": 1},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "EB03-001": [
        *_shield_both_turns(
            {
                "summary": "Once: if own base-cost≥4 would be K.O.'d, trash 1 hand instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "ko",
                        "target": "own_filtered",
                        "cost": "trash_hand",
                        "base_cost_gte": 4,
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.85,
                "once": True,
            }
        ),
        {
            "timing": "activate_main",
            "summary": "Rest this Leader: opp Character −2000 this turn; grant Rush to own Character without When Attacking",
            "ops": [
                {
                    "op": "buff",
                    "amount": -2000,
                    "target_kind": "opponent_character",
                    "duration": "turn",
                    "optional": True,
                    "count": 1,
                },
                {
                    "op": "grant_keyword",
                    "keyword": "rush",
                    "target_kind": "own_character",
                    "duration": "turn",
                    "optional": True,
                    "count": 1,
                    "require_no_when_attacking": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.85,
            "rest_self": True,
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
