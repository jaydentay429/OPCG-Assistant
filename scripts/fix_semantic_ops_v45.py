#!/usr/bin/env python3
"""Deterministic semantic fixes v45: declare-cost reveal + high missing-gate batch.

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

OUT_IDS = ROOT / "meta" / "logs" / "ops_v45_fixed_ids.txt"


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
    "OP11-071": [
        {
            "timing": "activate_main",
            "summary": "Once: may trash 1 hand: declare a cost, reveal opp deck top; if cost matches, draw 1 and gain up to 1 active DON!!",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {
                    "op": "look_opp_deck",
                    "count": 1,
                    "position": "top",
                    "declare_cost": True,
                    "optional": False,
                    "summary": "Declare a cost; reveal opp deck top; continue only if costs match",
                },
                {"op": "draw", "count": 1, "if_declared_cost_match": True},
                {
                    "op": "gain_don",
                    "count": 1,
                    "optional": True,
                    "if_declared_cost_match": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
        }
    ],
    "OP11-079": [
        {
            "timing": "counter_event",
            "summary": "Declare a cost, reveal opp deck top; if match, up to 1 own Leader/Character +5000 this battle",
            "ops": [
                {
                    "op": "look_opp_deck",
                    "count": 1,
                    "position": "top",
                    "declare_cost": True,
                    "optional": False,
                    "summary": "Declare a cost; reveal opp deck top; continue only if costs match",
                },
                {
                    "op": "buff",
                    "amount": 5000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                    "if_declared_cost_match": True,
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
    "EB02-022": [
        {
            "timing": "on_play",
            "summary": "If own Characters with power≥5000 are ≤2: play up to 1 hand Character power≤6000 with no base effect",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "power_lte": 6000,
                    "no_base_effect": True,
                    "from_zone": "hand",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_chars_lte": 2,
            "require_own_char_power_gte": 5000,
        }
    ],
    "EB02-024": [
        {
            "timing": "on_play",
            "summary": "Draw 2; hand_to_deck bottom 2; return up to 1 Character cost≤1 to hand",
            "ops": [
                {"op": "draw", "count": 2},
                {
                    "op": "hand_to_deck",
                    "count": 2,
                    "position": "bottom",
                    "optional": False,
                    "owner": "self",
                },
                {
                    "op": "return_to_hand",
                    "target_kind": "own_character",
                    "optional": True,
                    "cost_lte": 1,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "EB02-045": [
        {
            "timing": "on_play",
            "summary": "May trash_to_bottom 2: choose draw 1 OR if opp hand≥5 opp trash 1 hand",
            "ops": [
                {
                    "op": "trash_to_bottom",
                    "count": 2,
                    "optional": True,
                    "as_cost": True,
                },
                {
                    "op": "choose_one",
                    "options": [
                        {
                            "id": "draw",
                            "label": "Draw 1",
                            "ops": [{"op": "draw", "count": 1}],
                        },
                        {
                            "id": "opp_trash",
                            "label": "If opp hand≥5: opp trash 1",
                            "require_opp_hand_gte": 5,
                            "ops": [
                                {
                                    "op": "trash_hand",
                                    "count": 1,
                                    "optional": False,
                                    "owner": "opponent",
                                }
                            ],
                        },
                    ],
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "EB03-009": [
        {
            "timing": "activate_main",
            "summary": "Rest self: up to 1 own Character with no base effect +2000 this turn",
            "ops": [
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "own_character",
                    "optional": True,
                    "duration": "turn",
                    "no_base_effect": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "rest_self": True,
        }
    ],
    "EB03-020": [
        {
            "timing": "counter_event",
            "summary": "Up to 1 own Leader/Character +2000 this battle",
            "ops": [
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "counter_event",
            "summary": "If ≥2 own FILM Characters: that card +2000 more this battle",
            "ops": [
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                    "summary": "Additional +2000 if ≥2 FILM",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_chars_trait": "FILM",
            "require_chars_trait_gte": 2,
        },
        {
            "timing": "trigger",
            "summary": "Set up to 1 own Character active",
            "ops": [
                {
                    "op": "set_character_active",
                    "count": 1,
                    "target_kind": "own_character",
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "EB03-021": [
        {
            "timing": "on_play",
            "summary": "May trash 1 hand: return to bottom up to 1 opp base power≤4000 Character and up to 1 opp cost≤3 Character",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {
                    "op": "return_to_bottom",
                    "count": 1,
                    "target_kind": "opponent_character",
                    "optional": True,
                    "base_power_lte": 4000,
                },
                {
                    "op": "return_to_bottom",
                    "count": 1,
                    "target_kind": "opponent_character",
                    "optional": True,
                    "cost_lte": 3,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "EB03-024": [
        {
            "timing": "on_play",
            "summary": "Play up to 1 hand cost≤5 Alabasta|Straw Hat Character; then cannot play Characters this turn",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 5,
                    "trait_any": ["Alabasta", "Straw Hat Crew"],
                    "from_zone": "hand",
                },
                {
                    "op": "cannot_play_from_hand",
                    "card_type": "character",
                    "duration": "turn",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "EB03-062": [
        {
            "timing": "activate_main",
            "summary": "May trash 1 hand and this: add up to 1 deck top to Life; play up to 1 hand Trafalgar Law cost≤7",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                {"op": "add_life", "count": 1, "optional": True},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 7,
                    "name_contains": "Trafalgar Law",
                    "from_zone": "hand",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "your_turn",
            "summary": "Rush",
            "ops": [
                {
                    "op": "grant_keyword",
                    "target_kind": "self",
                    "keyword": "rush",
                    "duration": "permanent",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "EB04-007": [
        {
            "timing": "on_play",
            "summary": "Leader +2000 until end of opp next End Phase",
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
            "confidence": 0.9,
        },
        {
            "timing": "activate_main",
            "summary": "Once: if opp has Character power≥8000, this gains Rush: Character this turn",
            "ops": [
                {
                    "op": "grant_keyword",
                    "target_kind": "self",
                    "keyword": "rush_character",
                    "duration": "turn",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
            "require_opp_char_power_gte": 8000,
        },
    ],
    "EB04-041": [
        {
            "timing": "main_start",
            "summary": "If Leader is Sanji and DON!! field≥4: play up to 1 Sanji power≤6000 from hand or trash",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "power_lte": 6000,
                    "name_contains": "Sanji",
                    "from_zone": "hand_or_trash",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_name": "Sanji",
            "require_don_field_gte": 4,
        },
        {
            "timing": "trigger",
            "summary": "Draw 2 then trash 1 hand",
            "ops": [
                {"op": "draw", "count": 2},
                {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "EB04-043": [
        {
            "timing": "on_play",
            "summary": "Trash 2 deck top",
            "ops": [{"op": "trash_deck_top", "count": 2, "optional": False}],
            "status": "compiled",
            "confidence": 0.95,
        },
        *_shield_both_turns(
            {
                "summary": "Once: when own black Character base cost≤5 would be KO'd by opp effect, may trash_to_bottom 3 instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "own_filtered",
                        "base_cost_lte": 5,
                        "color": "black",
                        "cost": "trash_to_bottom",
                        "trash_count": 3,
                        "optional": True,
                        "summary": "Trash_to_bottom 3 instead of KO by opp effect",
                    }
                ],
                "status": "compiled",
                "confidence": 0.85,
                "once": True,
            }
        ),
    ],
    "EB04-044": [
        *_shield_both_turns(
            {
                "summary": "Once: if Leader trait includes Navy and this would leave, may trash 1 hand instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "ko",
                        "target": "self",
                        "cost": "trash_hand",
                        "optional": True,
                        "any_leave": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.85,
                "once": True,
                "require_leader_trait": "Navy",
            }
        ),
        {
            "timing": "your_turn",
            "summary": "Once: when opp Character is KO'd, draw 1",
            "ops": [{"op": "draw", "count": 1, "on_opp_ko": True}],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
        },
    ],
    "EB04-051": [
        {
            "timing": "your_turn",
            "summary": "Cannot attack unless a Character with base power≥12000 is on field",
            "ops": [
                {
                    "op": "cannot_attack",
                    "target_kind": "self",
                    "unless_field_char_base_power_gte": 12000,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
        {
            "timing": "trigger",
            "summary": "All opp Characters −3000 this turn; then if Life=0 play this",
            "ops": [
                {
                    "op": "buff",
                    "amount": -3000,
                    "target_kind": "opponent_character",
                    "all": True,
                    "optional": False,
                    "duration": "turn",
                },
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "self_card": True,
                    "from_zone": "hand",
                    "summary": "If Life=0: play this",
                },
            ],
            "status": "compiled",
            "confidence": 0.85,
        },
    ],
    "EB04-060": [
        {
            "timing": "main_start",
            "summary": "May life_to_hand top/bottom: hand_to_life face-up up to 1 Egghead Character; then opp Character −1000",
            "ops": [
                {
                    "op": "life_to_hand",
                    "count": 1,
                    "position": "top_or_bottom",
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {
                    "op": "hand_to_life",
                    "count": 1,
                    "optional": True,
                    "face": "up",
                    "position": "top",
                    "card_type": "character",
                    "trait_contains": "Egghead",
                },
                {
                    "op": "buff",
                    "amount": -1000,
                    "target_kind": "opponent_character",
                    "optional": True,
                    "duration": "turn",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "Draw 2 then trash 1 hand",
            "ops": [
                {"op": "draw", "count": 2},
                {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP01-011": [
        {
            "timing": "on_play",
            "summary": "May hand_to_deck bottom 1: draw 1",
            "ops": [
                {
                    "op": "hand_to_deck",
                    "count": 1,
                    "position": "bottom",
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {"op": "draw", "count": 1},
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP01-059": [
        {
            "timing": "main_start",
            "summary": "May trash 1 Land of Wano hand: set active up to 1 own Land of Wano Character cost≤3",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                    "trait_contains": "Land of Wano",
                },
                {
                    "op": "set_character_active",
                    "count": 1,
                    "target_kind": "own_character",
                    "optional": True,
                    "cost_lte": 3,
                    "trait_contains": "Land of Wano",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP01-090": [
        {
            "timing": "main_start",
            "summary": "Look 5: add up to 1 Baroque Works excluding Baroque Works name to hand; rest bottom",
            "ops": [
                {
                    "op": "search_deck",
                    "top_n": 5,
                    "max_add": 1,
                    "trait_contains": "Baroque Works",
                    "exclude_name": "Baroque Works",
                    "destination": "hand",
                    "order_bottom": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "OP02-026": [
        {
            "timing": "your_turn",
            "summary": "Once: when you play a no-base-effect Character from hand, if chars≤3, active up to 2 DON!!",
            "ops": [{"op": "active_don", "count": 2}],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
            "require_chars_lte": 3,
            "require_play_no_base_effect_from_hand": True,
        }
    ],
    "OP02-046": [
        {
            "timing": "main_start",
            "summary": "KO up to 1 opp rested Character cost≤4",
            "ops": [
                {
                    "op": "ko",
                    "target_kind": "opponent_character_rested",
                    "optional": True,
                    "cost_lte": 4,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "Play up to 1 Character cost≤4 with no base effect from hand",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 4,
                    "no_base_effect": True,
                    "from_zone": "hand",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP02-102": [
        {
            "timing": "your_turn",
            "summary": "Cannot be K.O.'d by effects",
            "ops": [{"op": "cannot_be_ko", "target_kind": "self", "optional": False}],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "opponent_turn",
            "summary": "Cannot be K.O.'d by effects",
            "ops": [{"op": "cannot_be_ko", "target_kind": "self", "optional": False}],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "when_attacking",
            "summary": "If a Character with cost 0 is on field, this +2000",
            "ops": [{"op": "buff_self", "amount": 2000}],
            "status": "compiled",
            "confidence": 0.9,
            "require_field_char_cost_eq": 0,
        },
    ],
    "OP03-037": [
        {
            "timing": "main_start",
            "summary": "May rest 1 East Blue Character: KO up to 1 opp rested Character cost≤3",
            "ops": [
                {
                    "op": "rest_character",
                    "count": 1,
                    "target_kind": "own_character",
                    "optional": True,
                    "as_cost": True,
                    "trait_contains": "East Blue",
                },
                {
                    "op": "ko",
                    "target_kind": "opponent_character_rested",
                    "optional": True,
                    "cost_lte": 3,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP04-082": [
        *_shield_both_turns(
            {
                "summary": "If this would be KO'd: may rest Leader or [Corrida Colosseum] instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "ko",
                        "target": "self",
                        "cost": "rest_own",
                        "optional": True,
                        "name_contains": "Corrida Colosseum",
                        "summary": "Rest Leader or Corrida Colosseum instead",
                    }
                ],
                "status": "compiled",
                "confidence": 0.8,
            }
        ),
        {
            "timing": "on_play",
            "summary": "If Leader is Rebecca: KO up to 1 opp Character cost≤1",
            "ops": [
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "cost_lte": 1,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_name": "Rebecca",
        },
    ],
    "OP07-051": [
        {
            "timing": "on_play",
            "summary": "Deny attack up to 1 opp Character except Monkey.D.Luffy until opp turn end; then return to bottom up to 1 Character cost≤1",
            "ops": [
                {
                    "op": "deny_attack",
                    "count": 1,
                    "target_kind": "opponent_character",
                    "optional": True,
                    "exclude_name": "Monkey.D.Luffy",
                    "duration": "until_opp_turn_end",
                },
                {
                    "op": "return_to_bottom",
                    "count": 1,
                    "target_kind": "any_character",
                    "optional": True,
                    "cost_lte": 1,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "OP08-005": [
        {
            "timing": "on_play",
            "summary": "Opp Character −2000 this turn; if no own Kuromarimo, play up to 1 Kuromarimo from hand",
            "ops": [
                {
                    "op": "buff",
                    "amount": -2000,
                    "target_kind": "opponent_character",
                    "optional": True,
                    "duration": "turn",
                },
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "name_contains": "Kuromarimo",
                    "from_zone": "hand",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_no_own_name_on_field": "Kuromarimo",
        }
    ],
    "OP08-055": [
        {
            "timing": "main_start",
            "summary": "May reveal 2 Whitebeard Pirates from hand as cost: return to bottom up to 1 Character cost≤6",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 2,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                    "trait_contains": "Whitebeard Pirates",
                    "summary": "Reveal 2 Whitebeard Pirates from hand (as cost)",
                },
                {
                    "op": "return_to_bottom",
                    "count": 1,
                    "target_kind": "any_character",
                    "optional": True,
                    "cost_lte": 6,
                },
            ],
            "status": "compiled",
            "confidence": 0.8,
        }
    ],
    "OP09-070": [
        {
            "timing": "on_play",
            "summary": "May return 1+ DON!! from field: attach up to 2 rested DON!! to Leader or Character",
            "ops": [
                {
                    "op": "return_don",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                },
                {
                    "op": "attach_don",
                    "count": 2,
                    "as_rested": True,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "OP09-073": [
        {
            "timing": "when_attacking",
            "summary": "May return 1+ DON!! from field: opp Character −2000 this turn",
            "ops": [
                {
                    "op": "return_don",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                },
                {
                    "op": "buff",
                    "amount": -2000,
                    "target_kind": "opponent_character",
                    "optional": True,
                    "duration": "turn",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "OP09-104": [
        {
            "timing": "on_play",
            "summary": "Hand_to_life face-up up to 1 Revolutionary Army Character; if Life≥2, may life_to_hand top/bottom",
            "ops": [
                {
                    "op": "hand_to_life",
                    "count": 1,
                    "optional": True,
                    "face": "up",
                    "position": "top",
                    "card_type": "character",
                    "trait_contains": "Revolutionary Army",
                },
                {
                    "op": "life_to_hand",
                    "count": 1,
                    "position": "top_or_bottom",
                    "optional": True,
                    "owner": "self",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_life_gte": 2,
        },
        {
            "timing": "trigger",
            "summary": "If Leader is multicolor: draw 2",
            "ops": [{"op": "draw", "count": 2}],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_multicolor": True,
        },
    ],
    "ST13-007": [
        {
            "timing": "activate_main",
            "summary": "Trash self: reveal Life top; if cost5 [Sabo] may play it; if played, Leader +2000 until opp turn end",
            "ops": [
                {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_eq": 5,
                    "name_contains": "Sabo",
                    "from_zone": "life",
                    "summary": "Play if revealed matches",
                },
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "leader",
                    "optional": True,
                    "duration": "until_opp_turn_end",
                    "summary": "Only if Life Character was played",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "ST13-010": [
        {
            "timing": "activate_main",
            "summary": "Trash self: reveal Life top; if cost5 [Portgas.D.Ace] may play it; if played, Leader +2000 until opp turn end",
            "ops": [
                {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_eq": 5,
                    "name_contains": "Portgas.D.Ace",
                    "from_zone": "life",
                    "summary": "Play if revealed matches",
                },
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "leader",
                    "optional": True,
                    "duration": "until_opp_turn_end",
                    "summary": "Only if Life Character was played",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "ST13-014": [
        {
            "timing": "activate_main",
            "summary": "Trash self: reveal Life top; if cost5 [Monkey.D.Luffy] may play it; if played, Leader +2000 until opp turn end",
            "ops": [
                {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_eq": 5,
                    "name_contains": "Monkey.D.Luffy",
                    "from_zone": "life",
                    "summary": "Play if revealed matches",
                },
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "leader",
                    "optional": True,
                    "duration": "until_opp_turn_end",
                    "summary": "Only if Life Character was played",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    lib_path, ovr_path = library_paths()
    raw = json.loads(lib_path.read_text())
    cards = raw.get("cards") or {}
    idx = json.loads((ROOT / "index" / "cards_by_id.json").read_text())

    bases = list(REBUILDS.keys())
    targets: list[str] = []
    for cid in list(cards.keys()) + list(idx.keys()):
        for base in sorted(bases, key=len, reverse=True):
            if cid == base or cid.startswith(base + "-"):
                targets.append(cid)
                break
    for base in bases:
        if base not in targets:
            targets.append(base)

    seen: set[str] = set()
    ordered: list[str] = []
    for cid in targets:
        if cid not in seen:
            seen.add(cid)
            ordered.append(cid)

    ovr = json.loads(ovr_path.read_text()) if ovr_path.exists() else {"cards": {}}
    overrides = ovr.get("cards") or {}

    fixed: list[str] = []
    for cid in ordered:
        base = None
        for b in sorted(REBUILDS, key=len, reverse=True):
            if cid == b or cid.startswith(b + "-"):
                base = b
                break
        if not base:
            continue
        out = _rebuild(cid, [dict(a) for a in REBUILDS[base]])
        prev = cards.get(cid) or get_card_entry(cid) or {"abilities": []}
        if json.dumps(prev.get("abilities"), sort_keys=True, ensure_ascii=False) == json.dumps(
            out.get("abilities"), sort_keys=True, ensure_ascii=False
        ):
            continue
        if args.dry_run:
            fixed.append(cid)
            continue
        cards[cid] = out
        overrides[cid] = out
        fixed.append(cid)

    if args.dry_run:
        print(json.dumps({"dry_run": True, "would_fix": len(fixed), "ids": fixed}, ensure_ascii=False))
        return 0

    raw["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    lib_path.write_text(json.dumps(raw, ensure_ascii=False, separators=(",", ":")))
    ovr["cards"] = overrides
    ovr["generated_at"] = raw["generated_at"]
    ovr_path.write_text(json.dumps(ovr, ensure_ascii=False, separators=(",", ":")))
    reload_effect_library(force=True)

    OUT_IDS.parent.mkdir(parents=True, exist_ok=True)
    prev_ids = (
        [ln.strip() for ln in OUT_IDS.read_text().splitlines() if ln.strip()] if OUT_IDS.exists() else []
    )
    merged: list[str] = []
    seen_ids: set[str] = set()
    for cid in prev_ids + fixed:
        if cid not in seen_ids:
            seen_ids.add(cid)
            merged.append(cid)
    OUT_IDS.write_text("\n".join(merged) + ("\n" if merged else ""))
    print(
        json.dumps(
            {"fixed": len(fixed), "merged": len(merged), "ids_file": str(OUT_IDS), "ids": fixed},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
