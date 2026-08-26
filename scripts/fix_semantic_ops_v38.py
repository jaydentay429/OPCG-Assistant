#!/usr/bin/env python3
"""Deterministic semantic fixes v38: exact-ID rebuilds only.

Gates, wrong targets, missing costs/ops. Dual-writes library + overrides.
Merges ids file across re-runs.
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

OUT_IDS = ROOT / "meta" / "logs" / "ops_v38_fixed_ids.txt"


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
    "OP02-018": [
        {
            "timing": "on_ko",
            "summary": "May trash 1 Whitebeard hand: if Life≤2 play this from trash rested",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 1,
                    "as_cost": True,
                    "optional": True,
                    "trait_contains": "Whitebeard Pirates",
                    "owner": "self",
                },
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "from_zone": "trash",
                    "self_card": True,
                    "as_rested": True,
                    "optional": False,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_life_lte": 2,
        }
    ],
    "OP05-091": [
        {
            "timing": "on_play",
            "summary": "Add up to 1 black Character cost 3–7 other than Rebecca from trash; play up to 1 black cost≤3 from hand rested",
            "ops": [
                {
                    "op": "add_from_trash",
                    "count": 1,
                    "optional": True,
                    "card_type": "character",
                    "color": "black",
                    "cost_gte": 3,
                    "cost_lte": 7,
                    "name_exclude": "Rebecca|蕾貝卡|蕾贝卡",
                },
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 3,
                    "color": "black",
                    "as_rested": True,
                    "from_zone": "hand",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP05-115": [
        {
            "timing": "main_start",
            "summary": "Up to 1 own Leader/Character +3000 this turn",
            "ops": [
                {
                    "op": "buff",
                    "amount": 3000,
                    "target_kind": "own_leader_or_character",
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
            "summary": "If Life≤1: rest up to 1 opp Character cost≤4",
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
            "require_life_lte": 1,
        },
        {
            "timing": "trigger",
            "summary": "May trash 2 hand: add up to 1 deck top to Life top",
            "ops": [
                {"op": "trash_hand", "count": 2, "as_cost": True, "optional": True, "owner": "self"},
                {"op": "add_life", "count": 1, "optional": True},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP06-023": [
        {
            "timing": "on_play",
            "summary": "May trash 1 hand: opp rested Leader cannot attack until opp next end",
            "ops": [
                {"op": "trash_hand", "count": 1, "as_cost": True, "optional": True, "owner": "self"},
                {
                    "op": "deny_attack",
                    "target_kind": "leader",
                    "include_leader": True,
                    "optional": True,
                    "duration": "until_opp_turn_end",
                    "rested_only": True,
                    "summary": "Opponent rested Leader cannot attack",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
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
    "OP06-083": [
        {
            "timing": "your_turn",
            "summary": "This Character cannot attack",
            "ops": [{"op": "cannot_attack", "target_kind": "self"}],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "opponent_turn",
            "summary": "This Character cannot attack",
            "ops": [{"op": "cannot_attack", "target_kind": "self"}],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "activate_main",
            "summary": "May KO 1 own Thriller Bark: this Character's effects are negated this turn",
            "ops": [
                {
                    "op": "ko",
                    "target_kind": "own_character",
                    "trait_contains": "Thriller Bark Pirates",
                    "as_cost": True,
                    "optional": True,
                },
                {"op": "negate_effects", "target_kind": "self", "optional": False},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP06-103": [
        {
            "timing": "when_attacking",
            "summary": "May trash 2 hand: place up to 1 own power-0 Character on Life top/bottom face-up",
            "ops": [
                {"op": "trash_hand", "count": 2, "as_cost": True, "optional": True, "owner": "self"},
                {
                    "op": "place_on_life",
                    "target_kind": "own_character",
                    "owner": "self",
                    "power_lte": 0,
                    "optional": True,
                    "face": "up",
                    "position": "top_or_bottom",
                },
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
                    "from_zone": "hand",
                    "self_card": True,
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_opp_life_lte": 3,
        },
    ],
    "OP06-115": [
        {
            "timing": "counter_event",
            "summary": "May trash 1 hand: up to 1 own Leader/Character +3000 this battle",
            "ops": [
                {"op": "trash_hand", "count": 1, "as_cost": True, "optional": True, "owner": "self"},
                {
                    "op": "buff",
                    "amount": 3000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "count": 1,
                    "duration": "battle",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "If Life=0: add up to 1 deck top to Life top, then trash 1 hand",
            "ops": [
                {"op": "add_life", "count": 1, "optional": True},
                {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_life_lte": 0,
        },
    ],
    "OP07-033": [
        *_shield_both_turns(
            {
                "summary": "If ≥3 own Characters: own cost≤3 other than Luffy cannot be KO'd by opp effects",
                "ops": [
                    {
                        "op": "cannot_be_ko",
                        "target_kind": "own_character",
                        "all": True,
                        "cost_lte": 3,
                        "exclude_name": "Monkey.D.Luffy|蒙其・D・魯夫|蒙其・D・路飞",
                        "optional": False,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_chars_gte": 3,
            }
        )
    ],
    "OP07-036": [
        {
            "timing": "main_start",
            "summary": "+3000; may rest own cost≥3: if you do, rest up to 1 opp cost≤5",
            "ops": [
                {
                    "op": "buff",
                    "amount": 3000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "count": 1,
                    "duration": "turn",
                },
                {
                    "op": "rest_character",
                    "target_kind": "own_character",
                    "cost_gte": 3,
                    "as_cost": True,
                    "optional": True,
                    "count": 1,
                },
                {
                    "op": "rest_opponent_character",
                    "count": 1,
                    "cost_lte": 5,
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
        {
            "timing": "trigger",
            "summary": "Rest up to 1 opp cost≤4",
            "ops": [{"op": "rest_opponent_character", "count": 1, "cost_lte": 4, "optional": True}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP07-050": [
        {
            "timing": "on_play",
            "summary": "If ≥2 Amazon Lily or Kuja Characters: return up to 1 opp cost≤3 to hand",
            "ops": [
                {
                    "op": "return_to_hand",
                    "target_kind": "opponent_character",
                    "cost_lte": 3,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_chars_trait": "Amazon Lily|Kuja Pirates",
            "require_chars_trait_gte": 2,
        }
    ],
    "OP07-052": [
        {
            "timing": "on_play",
            "summary": "If ≥2 Amazon Lily or Kuja Characters: put up to 1 cost≤2 Character on bottom",
            "ops": [
                {
                    "op": "return_to_bottom",
                    "target_kind": "any_character",
                    "cost_lte": 2,
                    "optional": True,
                    "count": 1,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_chars_trait": "Amazon Lily|Kuja Pirates",
            "require_chars_trait_gte": 2,
        }
    ],
    "OP07-053": [
        {
            "timing": "on_play",
            "summary": "Draw 2; place 2 hand cards on top or bottom in any order",
            "ops": [
                {"op": "draw", "count": 2},
                {"op": "hand_to_deck", "count": 2, "position": "top_or_bottom", "optional": False},
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP07-056": [
        {
            "timing": "counter_event",
            "summary": "May return own cost≥2 Character to hand: up to 1 Leader/Character +4000 this battle",
            "ops": [
                {
                    "op": "return_to_hand",
                    "target_kind": "own_character",
                    "cost_gte": 2,
                    "as_cost": True,
                    "optional": True,
                },
                {
                    "op": "buff",
                    "amount": 4000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "count": 1,
                    "duration": "battle",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "Draw 2; place 2 hand on bottom",
            "ops": [
                {"op": "draw", "count": 2},
                {"op": "hand_to_deck", "count": 2, "position": "bottom", "optional": False},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP07-069": [
        *_shield_both_turns(
            {
                "summary": "If own DON!! ≤ opp: own Foxy Pirates other than Pickles cannot be KO'd by opp effects",
                "ops": [
                    {
                        "op": "cannot_be_ko",
                        "target_kind": "own_character",
                        "all": True,
                        "trait_contains": "Foxy Pirates",
                        "exclude_name": "Pickles|皮克魯斯|皮克鲁斯",
                        "optional": False,
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_field_deficit_gte": 0,
            }
        )
    ],
    "OP07-078": [
        {
            "timing": "main_start",
            "summary": "If own DON!! ≤ opp: set up to 1 own Foxy active",
            "ops": [
                {
                    "op": "set_character_active",
                    "target_kind": "own_character",
                    "name_contains": "Foxy|弗克西",
                    "optional": True,
                    "count": 1,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_field_deficit_gte": 0,
        },
        {
            "timing": "trigger",
            "summary": "Gain up to 1 active DON!!",
            "ops": [{"op": "gain_don", "count": 1, "optional": True}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP07-087": [
        {
            "timing": "your_turn",
            "summary": "If opp has a cost-0 Character: this gains +3000",
            "ops": [{"op": "buff_self", "amount": 3000}],
            "status": "compiled",
            "confidence": 0.95,
            "require_opp_char_cost_eq": 0,
        }
    ],
    "OP07-107": [
        {
            "timing": "trigger",
            "summary": "Draw 1; if Life≤1 play this",
            "ops": [
                {"op": "draw", "count": 1},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "from_zone": "hand",
                    "self_card": True,
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_life_lte": 1,
        }
    ],
    "OP08-006": [
        {
            "timing": "your_turn",
            "summary": "If trash has Kuromarimo and Chess: this gains +2000",
            "ops": [{"op": "buff_self", "amount": 2000}],
            "status": "compiled",
            "confidence": 0.95,
            "require_trash_names_all": "Kuromarimo|克羅馬利蒙|克罗马利蒙&Chess|傑斯|杰斯",
        }
    ],
    "OP08-010": [
        {
            "timing": "activate_main",
            "summary": "DON!!×1 once: up to 1 other own Animal +1000 this turn",
            "ops": [
                {
                    "op": "buff",
                    "amount": 1000,
                    "target_kind": "own_character",
                    "trait_contains": "Animal",
                    "exclude_self": True,
                    "optional": True,
                    "count": 1,
                    "duration": "turn",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
            "require_don_attached_gte": 1,
        }
    ],
    "OP08-018": [
        {
            "timing": "main_start",
            "summary": "Up to 3 own Characters +1000; up to 1 opp Character −2000",
            "ops": [
                {
                    "op": "buff",
                    "amount": 1000,
                    "target_kind": "own_character",
                    "optional": True,
                    "count": 3,
                    "duration": "turn",
                },
                {
                    "op": "buff",
                    "amount": -2000,
                    "target_kind": "opponent_character",
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
            "summary": "Up to 1 opp Leader/Character −3000 this turn",
            "ops": [
                {
                    "op": "buff",
                    "amount": -3000,
                    "target_kind": "opponent_leader_or_character",
                    "optional": True,
                    "count": 1,
                    "duration": "turn",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP08-028": [
        {
            "timing": "on_play",
            "summary": "If opp has ≥7 rested cards: this gains Rush this turn",
            "ops": [{"op": "grant_keyword", "keyword": "rush", "target_kind": "self", "duration": "turn"}],
            "status": "compiled",
            "confidence": 0.95,
            "require_opp_rested_chars_gte": 7,
        }
    ],
    "OP07-019": [
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
        }
    ],
    "OP07-059": [
        {
            "timing": "when_attacking",
            "summary": "DON!!−3: if ≥3 Foxy Characters, skip untap on opp rested Leader and up to 1 Character",
            "ops": [
                {"op": "return_don", "count": 3, "owner": "self", "as_cost": True},
                {
                    "op": "skip_untap",
                    "target_kind": "leader",
                    "include_leader": True,
                    "optional": False,
                },
                {
                    "op": "skip_untap",
                    "target_kind": "opponent_character_rested",
                    "optional": True,
                    "count": 1,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_chars_trait": "Foxy Pirates",
            "require_chars_trait_gte": 3,
        }
    ],
    "OP07-097": [
        {
            "timing": "your_turn",
            "summary": "This Leader cannot attack",
            "ops": [{"op": "cannot_attack", "target_kind": "leader"}],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "activate_main",
            "summary": "Once: rest 1 DON!!: play or add-to-Life up to 1 Egghead cost≤5 from hand face-up",
            "ops": [
                {"op": "rest_don", "count": 1, "owner": "self", "as_cost": True},
                {
                    "op": "choose_one",
                    "options": [
                        {
                            "id": "play",
                            "label": "Play Egghead cost≤5 from hand",
                            "ops": [
                                {
                                    "op": "play_from_hand",
                                    "count": 1,
                                    "card_type": "character",
                                    "trait_contains": "Egghead",
                                    "cost_lte": 5,
                                    "optional": True,
                                    "from_zone": "hand",
                                }
                            ],
                        },
                        {
                            "id": "life",
                            "label": "Add Egghead cost≤5 from hand to Life top face-up",
                            "ops": [
                                {
                                    "op": "hand_to_life",
                                    "count": 1,
                                    "optional": True,
                                    "face": "up",
                                    "position": "top",
                                    "trait_contains": "Egghead",
                                    "card_type": "character",
                                }
                            ],
                        },
                    ],
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
        },
    ],
    "OP05-040": [
        {
            "timing": "your_turn",
            "summary": "If Leader is Doflamingo: all Characters cost≤5 skip refresh",
            "ops": [
                {
                    "op": "skip_untap",
                    "target_kind": "any_character",
                    "cost_lte": 5,
                    "all": True,
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_leader_name": "Donquixote Doflamingo|唐吉訶德・多佛朗明哥|唐吉诃德・多弗拉门戈",
        },
        {
            "timing": "opponent_turn",
            "summary": "If Leader is Doflamingo: all Characters cost≤5 skip refresh",
            "ops": [
                {
                    "op": "skip_untap",
                    "target_kind": "any_character",
                    "cost_lte": 5,
                    "all": True,
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_leader_name": "Donquixote Doflamingo|唐吉訶德・多佛朗明哥|唐吉诃德・多弗拉门戈",
        },
        {
            "timing": "end_of_your_turn",
            "summary": "If ≥10 DON!!: KO all rested Characters cost≤5; trash this Stage",
            "ops": [
                {
                    "op": "ko",
                    "target_kind": "any_character",
                    "all": True,
                    "cost_lte": 5,
                    "rested_only": True,
                    "optional": False,
                },
                {"op": "trash", "target_kind": "own_stage", "optional": False},
            ],
            "status": "compiled",
            "confidence": 0.85,
            "require_don_field_gte": 10,
        },
    ],
    "OP06-035": [
        {
            "timing": "on_play",
            "summary": "Rest up to total 2 opp Characters or DON!!; then take top Life to hand",
            "ops": [
                {
                    "op": "choose_one",
                    "options": [
                        {
                            "id": "c2",
                            "label": "Rest up to 2 opp Characters",
                            "ops": [
                                {
                                    "op": "rest_opponent_character",
                                    "count": 2,
                                    "optional": True,
                                }
                            ],
                        },
                        {
                            "id": "c1d1",
                            "label": "Rest 1 opp Character and 1 opp DON!!",
                            "ops": [
                                {"op": "rest_opponent_character", "count": 1, "optional": True},
                                {"op": "rest_don", "count": 1, "owner": "opponent", "optional": True},
                            ],
                        },
                        {
                            "id": "d2",
                            "label": "Rest up to 2 opp DON!!",
                            "ops": [{"op": "rest_don", "count": 2, "owner": "opponent", "optional": True}],
                        },
                    ],
                },
                {"op": "life_to_hand", "count": 1, "position": "top", "owner": "self", "optional": False},
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "OP08-049": [
        {
            "timing": "on_play",
            "summary": "Reveal top; place top or bottom; if Whitebeard Pirates, gain Rush this turn",
            "ops": [
                {"op": "look_deck", "count": 1, "position": "top"},
                {
                    "op": "grant_keyword",
                    "keyword": "rush",
                    "target_kind": "self",
                    "duration": "turn",
                    "trait_contains": "Whitebeard Pirates",
                },
            ],
            "status": "compiled",
            "confidence": 0.8,
        }
    ],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*", default=None)
    args = ap.parse_args()

    bases = list(REBUILDS.keys())
    if args.ids:
        want = set(args.ids)
        bases = [b for b in bases if b in want]

    lib_path, ovr_path = library_paths()
    raw = json.loads(lib_path.read_text())
    cards = raw["cards"]
    PARALLEL_BASES = set(bases)

    targets: list[str] = []
    for cid in list(cards.keys()):
        for base in bases:
            if cid == base or (base in PARALLEL_BASES and cid.startswith(base + "-")):
                targets.append(cid)
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
