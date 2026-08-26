#!/usr/bin/env python3
"""Deterministic semantic fixes v36: exact-ID rebuilds only.

replace_leave leftovers, clear cost/count/gate fixes, search play destination.
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

OUT_IDS = ROOT / "meta" / "logs" / "ops_v36_fixed_ids.txt"


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
    "OP13-060": _shield_both_turns(
        {
            "summary": "If own Roger Pirates would be K.O.'d by opp effect, trash this instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "own_filtered",
                    "cost": "trash_self",
                    "trait_contains": "Roger Pirates",
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ),
    "OP13-109": [
        *_shield_both_turns(
            {
                "summary": "If this would leave by opp effect, flip top Life face-up instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "self",
                        "cost": "flip_life",
                        "face": "up",
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.9,
            }
        ),
        {
            "timing": "trigger",
            "summary": "Draw 2 trash 1 hand",
            "ops": [
                {"op": "draw", "count": 2},
                {"op": "trash_hand", "count": 1, "optional": False},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP15-052": _shield_both_turns(
        {
            "summary": "If own base power≤7000 would leave by opp effect, put 1 own Character on bottom instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "own_filtered",
                    "cost": "return_other_to_bottom",
                    "base_power_lte": 7000,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ),
    "OP15-069": _shield_both_turns(
        {
            "summary": "If own base power≤7000 would leave by opp effect, return 1 DON!! instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "own_filtered",
                    "cost": "return_don",
                    "don_count": 1,
                    "base_power_lte": 7000,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ),
    "OP13-051": [
        {
            "timing": "on_ko",
            "summary": "If Leader is Boa Hancock or multicolor: draw 2",
            "ops": [{"op": "draw", "count": 2}],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_name": "Boa Hancock|波雅・漢考克|波雅・汉考克",
            "require_leader_name_or_multicolor": True,
        }
    ],
    "OP03-049": [
        {
            "timing": "on_play",
            "summary": "If deck ≤20: return up to 1 Character cost≤3 to owner's hand",
            "ops": [
                {
                    "op": "return_to_hand",
                    "target_kind": "opponent_character",
                    "cost_lte": 3,
                    "optional": True,
                    "count": 1,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_deck_lte": 20,
        }
    ],
    "OP03-051": [
        {
            "timing": "when_attacking",
            "summary": "DON!!×1: when this attack deals Life damage, may trash top 7",
            "ops": [{"op": "trash_deck_top", "count": 7, "optional": True}],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_attached_gte": 1,
            "on_life_damage": True,
        },
        {
            "timing": "on_ko",
            "summary": "May trash top 3",
            "ops": [{"op": "trash_deck_top", "count": 3, "optional": True}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP03-094": [
        {
            "timing": "main_start",
            "summary": "If Leader has CP: look top 5, play up to 1 CP cost≤5, trash rest",
            "ops": [
                {
                    "op": "search_deck",
                    "top_n": 5,
                    "max_add": 1,
                    "trait_contains": "CP",
                    "cost_lte": 5,
                    "card_type": "character",
                    "destination": "play",
                    "trash_rest": True,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_leader_trait": "CP",
        },
        {
            "timing": "trigger",
            "summary": "Play up to 1 black Character cost≤3 from trash",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "from_zone": "trash",
                    "card_type": "character",
                    "color": "black",
                    "cost_lte": 3,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP03-099": [
        {
            "timing": "when_attacking",
            "summary": "DON!!×1: look top Life (self or opp) and reorder; Leader +1000 this battle",
            "ops": [
                {"op": "reorder_life", "owner": "self_or_opponent"},
                {
                    "op": "buff",
                    "amount": 1000,
                    "target_kind": "leader",
                    "duration": "battle",
                    "optional": False,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_don_attached_gte": 1,
        }
    ],
    "OP03-021": [
        {
            "timing": "activate_main",
            "summary": "Rest 3 DON and 2 East Blue Characters: set this Leader active; rest up to 1 opp cost≤5",
            "ops": [
                {"op": "rest_don", "count": 3, "as_cost": True, "optional": True},
                {
                    "op": "rest_character",
                    "target_kind": "own_character",
                    "trait_contains": "East Blue",
                    "count": 2,
                    "as_cost": True,
                    "optional": True,
                },
                {"op": "set_character_active", "target_kind": "leader", "optional": False},
                {
                    "op": "rest_opponent_character",
                    "count": 1,
                    "cost_lte": 5,
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "OP03-036": [
        {
            "timing": "main_start",
            "summary": "Rest 1 own East Blue: set up to 1 Kuro active",
            "ops": [
                {
                    "op": "rest_character",
                    "target_kind": "own_character",
                    "trait_contains": "East Blue",
                    "count": 1,
                    "as_cost": True,
                    "optional": True,
                },
                {
                    "op": "set_character_active",
                    "target_kind": "own_character",
                    "name_contains": "Kuro|克洛",
                    "count": 1,
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
        {
            "timing": "trigger",
            "summary": "KO up to 1 rested opp cost≤3",
            "ops": [
                {
                    "op": "ko",
                    "target_kind": "opponent_character_rested",
                    "cost_lte": 3,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP04-021": [
        {
            "timing": "on_opponent_attack",
            "summary": "Rest 2 DON: rest up to 1 opp DON!!",
            "ops": [
                {"op": "rest_don", "count": 2, "as_cost": True, "optional": True},
                {"op": "rest_don", "count": 1, "owner": "opponent", "optional": True},
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "OP04-053": [
        {
            "timing": "on_event",
            "summary": "DON!!×1 once: when you play an Event, draw 1 then hand to bottom 1",
            "ops": [
                {"op": "draw", "count": 1},
                {"op": "hand_to_deck", "count": 1, "position": "bottom", "optional": False},
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
            "require_don_attached_gte": 1,
        }
    ],
    "OP04-024": [
        {
            "timing": "on_play",
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
        {
            "timing": "opponent_turn",
            "summary": "Once: when opp plays a Character, if Leader is Donquixote Pirates: rest up to 1 opp Character, then rest this",
            "ops": [
                {
                    "op": "rest_opponent_character",
                    "count": 1,
                    "optional": True,
                },
                {"op": "rest_character", "target_kind": "self", "optional": False},
            ],
            "status": "compiled",
            "confidence": 0.85,
            "once": True,
            "require_leader_trait": "Donquixote Pirates|唐吉訶德海賊團",
            "on_opp_play_character": True,
        },
    ],
    "OP04-011": [
        {
            "timing": "when_attacking",
            "summary": "Reveal deck top: if Character power≥6000, +3000 this turn; put revealed on bottom",
            "ops": [
                {"op": "look_deck", "count": 1, "position": "bottom"},
                {
                    "op": "buff_self",
                    "amount": 3000,
                    "duration": "turn",
                    "if_revealed_power_gte": 6000,
                },
            ],
            "status": "compiled",
            "confidence": 0.85,
        }
    ],
    "EB03-055": [
        {
            "timing": "on_play",
            "summary": "Trash top Life: if Leader is Straw Hat Crew, add up to 2 deck top to Life",
            "ops": [
                {
                    "op": "trash_life",
                    "count": 1,
                    "position": "top",
                    "as_cost": True,
                    "optional": True,
                },
                {"op": "add_life", "count": 2, "optional": True},
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_leader_trait": "Straw Hat Crew|草帽一行人",
        },
        {
            "timing": "on_ko",
            "summary": "Opp turn: deal 1 Life damage",
            "ops": [{"op": "deal_life_damage", "count": 1, "optional": True}],
            "status": "compiled",
            "confidence": 0.9,
            "require_opponent_turn": True,
        },
    ],
    "EB03-042": [
        *_shield_both_turns(
            {
                "summary": "If Leader is Revolutionary Army: this Character cost +4",
                "ops": [{"op": "grant_cost", "amount": 4, "target_kind": "self"}],
                "status": "compiled",
                "confidence": 0.9,
                "require_leader_trait": "Revolutionary Army|革命軍",
            }
        ),
        {
            "timing": "on_ko",
            "summary": "Opp turn: play up to 1 Revolutionary Army cost≤6 (not Koala) or Nico Robin from hand/trash",
            "ops": [
                {
                    "op": "choose_one",
                    "options": [
                        {
                            "id": "opt0",
                            "label": "Play Revolutionary Army cost≤6 except Koala",
                            "ops": [
                                {
                                    "op": "play_from_hand",
                                    "count": 1,
                                    "from_zone": "hand_or_trash",
                                    "trait_contains": "Revolutionary Army",
                                    "cost_lte": 6,
                                    "exclude_name": "Koala|可亞拉|可亚拉",
                                    "optional": True,
                                }
                            ],
                        },
                        {
                            "id": "opt1",
                            "label": "Play Nico Robin cost≤6",
                            "ops": [
                                {
                                    "op": "play_from_hand",
                                    "count": 1,
                                    "from_zone": "hand_or_trash",
                                    "name_contains": "Nico Robin|妮可・羅賓|妮可・罗宾",
                                    "cost_lte": 6,
                                    "optional": True,
                                }
                            ],
                        },
                    ],
                }
            ],
            "status": "compiled",
            "confidence": 0.85,
            "require_opponent_turn": True,
        },
    ],
    "OP03-113": [
        {
            "timing": "on_ko",
            "summary": "Look top 3: add up to 1 Big Mom Pirates to hand, rest any order bottom",
            "ops": [
                {
                    "op": "search_deck",
                    "top_n": 3,
                    "max_add": 1,
                    "trait_contains": "Big Mom Pirates",
                    "destination": "hand",
                    "order_bottom": True,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
        {
            "timing": "trigger",
            "summary": "May trash 1 hand: play this",
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
            "confidence": 0.95,
        },
    ],
    "OP03-074": [
        {
            "timing": "main_start",
            "summary": "DON!!−2: put up to 1 opp cost≤4 on bottom",
            "ops": [
                {"op": "return_don", "count": 2, "as_cost": True, "optional": True},
                {
                    "op": "return_to_bottom",
                    "target_kind": "opponent_character",
                    "cost_lte": 4,
                    "count": 1,
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "Activate this card's Main effect",
            "ops": [
                {"op": "return_don", "count": 2, "as_cost": True, "optional": True},
                {
                    "op": "return_to_bottom",
                    "target_kind": "opponent_character",
                    "cost_lte": 4,
                    "count": 1,
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "OP08-038": [
        {
            "timing": "main_start",
            "summary": "Rest 2 own Characters: all own Characters cannot be K.O.'d by opp effects until opp turn end",
            "ops": [
                {
                    "op": "rest_character",
                    "target_kind": "own_character",
                    "count": 2,
                    "as_cost": True,
                    "optional": True,
                },
                {
                    "op": "cannot_be_ko",
                    "target_kind": "own_character",
                    "all": True,
                    "optional": False,
                    "duration": "until_opp_turn_end",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
        {
            "timing": "trigger",
            "summary": "Rest up to 1 opp cost≤3",
            "ops": [
                {
                    "op": "rest_opponent_character",
                    "count": 1,
                    "cost_lte": 3,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "ST06-016": [
        {
            "timing": "counter_event",
            "summary": "Up to 1 own Leader/Character +2000 this battle",
            "ops": [
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "own_leader_or_character",
                    "duration": "battle",
                    "optional": True,
                    "count": 1,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "Draw 1; own Characters cannot be K.O.'d this turn",
            "ops": [
                {"op": "draw", "count": 1},
                {
                    "op": "cannot_be_ko",
                    "target_kind": "own_character",
                    "all": True,
                    "optional": False,
                    "duration": "turn",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "OP12-036": _shield_both_turns(
        {
            "summary": "If Leader has Slash: cannot be K.O.'d in battle vs Slash; +1000",
            "ops": [
                {
                    "op": "cannot_be_ko",
                    "target_kind": "self",
                    "attribute": "Slash",
                    "optional": False,
                },
                {"op": "buff_self", "amount": 1000},
            ],
            "status": "compiled",
            "confidence": 0.85,
            "require_leader_attribute": "Slash",
            "cannot_play_by_effect_from_hand": True,
        }
    ),
    "EB02-039": [
        {
            "timing": "main_start",
            "summary": "Trash 1 Germa66 hand power≤4000: if your DON!! ≤ opp, play same-name trash Character power 5000–7000",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 1,
                    "as_cost": True,
                    "optional": True,
                    "trait_contains": "GERMA 66",
                    "power_lte": 4000,
                },
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "from_zone": "trash",
                    "base_power_gte": 5000,
                    "base_power_lte": 7000,
                    "same_name_as_trashed": True,
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.8,
            "require_don_field_deficit_gte": 0,
        }
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
