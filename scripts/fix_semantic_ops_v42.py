#!/usr/bin/env python3
"""Deterministic semantic fixes v42: exact-ID rebuilds only (OP14/OP15 critical cluster).

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

OUT_IDS = ROOT / "meta" / "logs" / "ops_v42_fixed_ids.txt"


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
    "OP14-094": [
        {
            "timing": "on_play",
            "summary": "If field has Character cost 0 or ≥8: draw 2, trash 1",
            "ops": [
                {"op": "draw", "count": 2},
                {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_field_char_cost_0_or_gte": 8,
        },
        {
            "timing": "on_block",
            "summary": "Blocker",
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
        },
    ],
    "OP14-098": [
        {
            "timing": "main_start",
            "summary": "If field has Character cost 0 or ≥8: all own Baroque Works / B・W +3 cost until opp end",
            "ops": [
                {
                    "op": "grant_cost",
                    "amount": 3,
                    "all": True,
                    "trait_includes": "B・W|Baroque Works|巴洛克工作社",
                    "duration": "until_opp_turn_end",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_field_char_cost_0_or_gte": 8,
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
    "OP14-103": [
        {
            "timing": "on_play",
            "summary": "May life_to_hand top/bottom: hand_to_life top up to 1",
            "ops": [
                {
                    "op": "life_to_hand",
                    "count": 1,
                    "position": "top_or_bottom",
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {"op": "hand_to_life", "count": 1, "optional": True, "position": "top"},
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
    "OP14-112": [
        {
            "timing": "on_play",
            "summary": "If Seven Warlords Leader: add_life from deck; then opp life top to hand",
            "ops": [
                {"op": "add_life", "count": 1, "optional": True},
                {
                    "op": "life_to_hand",
                    "count": 1,
                    "position": "top",
                    "optional": True,
                    "owner": "opponent",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_leader_trait": "The Seven Warlords of the Sea|王下七武海",
        },
        {
            "timing": "trigger",
            "summary": "Play up to 1 hand Character power≤6000 with Trigger",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                    "power_lte": 6000,
                    "require_trigger": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP14-113": [
        {
            "timing": "on_play",
            "summary": "Search top 5 for Amazon Lily or Kuja; trash 1 hand",
            "ops": [
                {
                    "op": "search_deck",
                    "name_contains": "",
                    "trait_contains": "Amazon Lily|Kuja Pirates|亞馬遜百合|九蛇海賊團",
                    "top_n": 5,
                    "max_add": 1,
                    "order_bottom": True,
                    "destination": "hand",
                },
                {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "If Kuja Leader: play this card",
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
            "require_leader_trait": "Kuja Pirates|九蛇海賊團",
        },
    ],
    "OP14-115": [
        {
            "timing": "on_ko",
            "summary": "Opponent's turn: add_life up to 1; then take 1 damage",
            "ops": [
                {"op": "add_life", "count": 1, "optional": True},
                {"op": "deal_life_damage", "count": 1, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_opponent_turn": True,
        },
        {
            "timing": "trigger",
            "summary": "If Kuja Leader: play this card",
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
            "require_leader_trait": "Kuja Pirates|九蛇海賊團",
        },
    ],
    "OP14-118": [
        {
            "timing": "counter_event",
            "summary": "If Life≤2: deny_attack up to 1 opp active Character this turn",
            "ops": [
                {
                    "op": "deny_attack",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "duration": "turn",
                    "active_only": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_life_lte": 2,
        },
        {
            "timing": "trigger",
            "summary": "Play up to 1 hand Character power≤6000 with Trigger",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                    "power_lte": 6000,
                    "require_trigger": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP14-119": [
        {
            "timing": "your_turn",
            "summary": "When this becomes rested: deny_rest up to 1 opp cost≤9 until opp end",
            "ops": [
                {
                    "op": "deny_rest",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "cost_lte": 9,
                    "duration": "until_opp_turn_end",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "trigger_on": "self_rested",
        },
        {
            "timing": "on_opponent_attack",
            "summary": "Once: may trash 1: buff Leader or Character +2000 this battle",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
        },
    ],
    "OP15-001": [
        {
            "timing": "opponent_turn",
            "summary": "DON!!×1: if all own Characters East Blue, all opp Characters −2000",
            "ops": [
                {
                    "op": "buff",
                    "amount": -2000,
                    "target_kind": "opponent_character",
                    "optional": False,
                    "all": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_attached_gte": 1,
            "require_all_chars_trait": "East Blue|東方藍",
        },
        {
            "timing": "activate_main",
            "summary": "Once: rest up to 1 opp Character with ≥2 DON!! attached",
            "ops": [
                {
                    "op": "rest_opponent_character",
                    "count": 1,
                    "optional": True,
                    "don_attached_gte": 2,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
            "cost_don": 0,
            "rest_self": False,
        },
    ],
    "OP15-002": [
        {
            "timing": "when_attacking",
            "summary": "May trash any Event/Stage from hand: +1000 per trashed this battle",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 10,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                    "card_type": "event_or_stage",
                    "summary": "Trash any number of Event/Stage from hand",
                },
                {
                    "op": "buff",
                    "amount": 1000,
                    "target_kind": "leader",
                    "optional": True,
                    "duration": "battle",
                    "per_trash_cards": 1,
                    "summary": "+1000 per trashed Event/Stage",
                },
            ],
            "status": "compiled",
            "confidence": 0.85,
        },
        {
            "timing": "on_opponent_attack",
            "summary": "May trash any Event/Stage from hand: +1000 per trashed this battle",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 10,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                    "card_type": "event_or_stage",
                    "summary": "Trash any number of Event/Stage from hand",
                },
                {
                    "op": "buff",
                    "amount": 1000,
                    "target_kind": "leader",
                    "optional": True,
                    "duration": "battle",
                    "per_trash_cards": 1,
                    "summary": "+1000 per trashed Event/Stage",
                },
            ],
            "status": "compiled",
            "confidence": 0.85,
        },
        {
            "timing": "activate_main",
            "summary": "Once: if activated base-cost≥3 Event this turn, draw 1",
            "ops": [{"op": "draw", "count": 1}],
            "status": "compiled",
            "confidence": 0.8,
            "once": True,
            "cost_don": 0,
            "rest_self": False,
            "summary": "Draw if Event base cost≥3 activated this turn",
        },
    ],
    "OP15-005": [
        {
            "timing": "when_attacking",
            "summary": "If opp has any given DON!!: this +2000 this turn",
            "ops": [{"op": "buff_self", "amount": 2000}],
            "status": "compiled",
            "confidence": 0.95,
            "require_opp_given_don_gte": 1,
        }
    ],
    "OP15-008": [
        {
            "timing": "on_play",
            "summary": "Attach up to 3 opp rested DON!! to 1 opp Character; gain Rush this turn",
            "ops": [
                {
                    "op": "attach_don",
                    "count": 3,
                    "as_rested": True,
                    "target_kind": "opponent_character",
                    "owner": "opponent",
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
            "confidence": 0.9,
        },
        {
            "timing": "activate_main",
            "summary": "Once if played this turn: all opp Characters −1000 per DON!! on this",
            "ops": [
                {
                    "op": "buff",
                    "amount": -1000,
                    "target_kind": "opponent_character",
                    "optional": False,
                    "all": True,
                    "duration": "turn",
                    "per_rested_don": 1,
                    "summary": "−1000 per DON!! attached to this Character",
                }
            ],
            "status": "compiled",
            "confidence": 0.75,
            "once": True,
            "cost_don": 0,
            "rest_self": False,
        },
    ],
    "OP15-039": [
        {
            "timing": "your_turn",
            "summary": "This Leader cannot attack",
            "ops": [
                {
                    "op": "deny_attack",
                    "count": 1,
                    "target_kind": "leader",
                    "optional": False,
                    "duration": "permanent",
                    "summary": "This Leader cannot attack",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
        {
            "timing": "opponent_turn",
            "summary": "This Leader cannot attack",
            "ops": [
                {
                    "op": "deny_attack",
                    "count": 1,
                    "target_kind": "leader",
                    "optional": False,
                    "duration": "permanent",
                    "summary": "This Leader cannot attack",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
        {
            "timing": "activate_main",
            "summary": "Rest Leader + return 1 own Dressrosa: play cost 3 Dressrosa from hand",
            "ops": [
                {
                    "op": "return_to_hand",
                    "target_kind": "own_character",
                    "optional": False,
                    "as_cost": True,
                    "trait_contains": "Dressrosa|多雷斯羅薩",
                },
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_eq": 3,
                    "trait_contains": "Dressrosa|多雷斯羅薩",
                    "from_zone": "hand",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "rest_self": True,
            "cost_don": 0,
        },
    ],
    "OP15-047": [
        {
            "timing": "on_play",
            "summary": "Up to 1 own Character gains blockerless this turn",
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
        {
            "timing": "on_block",
            "summary": "Blocker",
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
        },
    ],
    "OP15-048": [
        {
            "timing": "on_play",
            "summary": "May trash 1 Event from hand: draw 2",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                    "card_type": "event",
                },
                {"op": "draw", "count": 2},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "on_ko",
            "summary": "Opponent's turn: opponent places 1 hand at deck bottom",
            "ops": [{"op": "opponent_hand_to_bottom", "count": 1, "optional": False}],
            "status": "compiled",
            "confidence": 0.9,
            "require_opponent_turn": True,
        },
    ],
    "OP15-054": [
        {
            "timing": "main_start",
            "summary": "If Leader is Lucy: choose draw2/trash1 then play Dressrosa≤4 OR return Stage",
            "ops": [
                {
                    "op": "choose_one",
                    "chooser": "self",
                    "options": [
                        {
                            "id": "opt0",
                            "label": "Draw 2, trash 1, play Dressrosa cost≤4",
                            "ops": [
                                {"op": "draw", "count": 2},
                                {
                                    "op": "trash_hand",
                                    "count": 1,
                                    "optional": False,
                                    "owner": "self",
                                },
                                {
                                    "op": "play_from_hand",
                                    "count": 1,
                                    "card_type": "character",
                                    "optional": True,
                                    "cost_lte": 4,
                                    "trait_contains": "Dressrosa|多雷斯羅薩",
                                    "from_zone": "hand",
                                },
                            ],
                        },
                        {
                            "id": "opt1",
                            "label": "Return up to 1 Stage to owner's hand",
                            "ops": [
                                {
                                    "op": "return_to_hand",
                                    "target_kind": "any_character",
                                    "optional": True,
                                    "card_type": "stage",
                                    "summary": "Return Stage to hand",
                                }
                            ],
                        },
                    ],
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_leader_name": "Lucy|魯西|鲁西",
        }
    ],
    "OP15-063": [
        {
            "timing": "on_play",
            "summary": "DON!! −1: draw 1",
            "ops": [
                {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                {"op": "draw", "count": 1},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "on_ko",
            "summary": "If DON!! field ≤6: KO up to 1 opp power≤2000",
            "ops": [
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "power_lte": 2000,
                    "count": 1,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_field_lte": 6,
        },
    ],
    "OP15-067": [
        *_shield_both_turns(
            {
                "summary": "If DON!! field ≤6: gain Rush",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "rush",
                        "target_kind": "self",
                        "duration": "permanent",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_field_lte": 6,
            }
        ),
        {
            "timing": "on_play",
            "summary": "DON!! −1: draw 1",
            "ops": [
                {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                {"op": "draw", "count": 1},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP15-071": [
        *_shield_both_turns(
            {
                "summary": "All own Ohm and this gain Double Attack",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "keyword": "double_attack",
                        "target_kind": "self",
                        "duration": "permanent",
                    },
                    {
                        "op": "grant_keyword",
                        "keyword": "double_attack",
                        "target_kind": "own_character",
                        "name_contains": "Ohm|歐姆|欧姆",
                        "duration": "permanent",
                        "optional": True,
                        "all": True,
                    },
                ],
                "status": "compiled",
                "confidence": 0.9,
            }
        ),
        {
            "timing": "opponent_turn",
            "summary": "All own Ohm and this base power become 6000",
            "ops": [
                {
                    "op": "set_base_power",
                    "amount": 6000,
                    "target_kind": "self",
                    "optional": False,
                },
                {
                    "op": "set_base_power",
                    "amount": 6000,
                    "target_kind": "own_character",
                    "name_contains": "Ohm|歐姆|欧姆",
                    "optional": False,
                    "all": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "OP15-076": [
        {
            "timing": "main_start",
            "summary": "DON!! −1: if Leader Enel, draw 1; opp Character −1000",
            "ops": [
                {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                {"op": "draw", "count": 1},
                {
                    "op": "buff",
                    "amount": -1000,
                    "target_kind": "opponent_character",
                    "optional": True,
                    "count": 1,
                    "duration": "turn",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_name": "Enel|艾涅爾|艾尼尔",
        },
        {
            "timing": "counter_event",
            "summary": "Up to 1 own Enel +2000 this battle",
            "ops": [
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "count": 1,
                    "name_contains": "Enel|艾涅爾|艾尼尔",
                    "duration": "battle",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP15-090": _shield_both_turns(
        {
            "summary": "Own Character base power≤7000 leaving by opp effect: may trash 1 instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "own_character",
                    "cost": "trash_hand",
                    "optional": True,
                    "base_power_lte": 7000,
                    "summary": "Trash 1 instead of leave",
                }
            ],
            "status": "compiled",
            "confidence": 0.85,
            "once": True,
        }
    ),
    "OP15-092": [
        {
            "timing": "your_turn",
            "summary": "Trash≥10: base power 9000 and +10 cost; trash≥30: +1000",
            "ops": [
                {
                    "op": "set_base_power",
                    "amount": 9000,
                    "target_kind": "self",
                    "optional": False,
                },
                {"op": "grant_cost", "amount": 10, "target_kind": "self"},
            ],
            "status": "compiled",
            "confidence": 0.85,
            "require_trash_gte": 10,
        },
        {
            "timing": "opponent_turn",
            "summary": "Trash≥20: Leader base power becomes 7000",
            "ops": [
                {
                    "op": "set_base_power",
                    "amount": 7000,
                    "target_kind": "leader",
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_trash_gte": 20,
        },
        {
            "timing": "your_turn",
            "summary": "Trash≥30: this +1000",
            "ops": [{"op": "buff_self", "amount": 1000}],
            "status": "compiled",
            "confidence": 0.9,
            "require_trash_gte": 30,
        },
        {
            "timing": "opponent_turn",
            "summary": "Trash≥30: this +1000",
            "ops": [{"op": "buff_self", "amount": 1000}],
            "status": "compiled",
            "confidence": 0.9,
            "require_trash_gte": 30,
        },
    ],
    "OP15-104": [
        {
            "timing": "on_play",
            "summary": "If Life < opp: draw 2 trash 2",
            "ops": [
                {"op": "draw", "count": 2},
                {"op": "trash_hand", "count": 2, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_life_less_than_opponent": True,
        },
        {
            "timing": "trigger",
            "summary": "Draw 2 trash 1",
            "ops": [
                {"op": "draw", "count": 2},
                {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP15-111": [
        {
            "timing": "when_attacking",
            "summary": "DON!!×1: up to 1 own Kalgara gains Rush this turn",
            "ops": [
                {
                    "op": "grant_keyword",
                    "keyword": "rush",
                    "target_kind": "own_character",
                    "name_contains": "Kalgara|卡爾葛拉|卡尔葛拉",
                    "duration": "turn",
                    "optional": True,
                    "count": 1,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_attached_gte": 1,
        }
    ],
    "OP15-118": _shield_both_turns(
        {
            "summary": "DON!! field ≤6: cannot be removed +2000",
            "ops": [
                {
                    "op": "cannot_be_removed",
                    "target_kind": "self",
                    "any_leave": True,
                    "optional": False,
                },
                {"op": "buff_self", "amount": 2000},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_field_lte": 6,
        }
    )
    + [
        {
            "timing": "on_play",
            "summary": "DON!! −1: look top 5 add 1; rest bottom; trash 1 hand",
            "ops": [
                {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                {
                    "op": "search_deck",
                    "name_contains": "",
                    "trait_contains": "",
                    "top_n": 5,
                    "max_add": 1,
                    "order_bottom": True,
                    "destination": "hand",
                },
                {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "OP13-114": [
        {
            "timing": "on_play",
            "summary": "May flip life top face-up: opp Character −2000 this turn",
            "ops": [
                {
                    "op": "flip_life",
                    "face": "up",
                    "position": "top",
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
            "confidence": 0.95,
        },
        {
            "timing": "when_attacking",
            "summary": "May flip life top face-up: opp Character −2000 this turn",
            "ops": [
                {
                    "op": "flip_life",
                    "face": "up",
                    "position": "top",
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
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "May trash 1: play this card",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
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
        },
    ],
    "OP16-011": [
        {
            "timing": "on_play",
            "summary": "May reveal hand Character power 8000: draw 1",
            "ops": [
                {
                    "op": "reveal_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "power_eq": 8000,
                    "card_type": "character",
                    "summary": "Reveal Character with 8000 power",
                },
                {"op": "draw", "count": 1},
            ],
            "status": "compiled",
            "confidence": 0.8,
        },
        {
            "timing": "when_attacking",
            "summary": "DON!!×1: KO up to 2 opp base power≤2000",
            "ops": [
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "count": 2,
                    "base_power_lte": 2000,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_attached_gte": 1,
        },
    ],
    "OP16-015": [
        {
            "timing": "hand_cost",
            "summary": "If Leader name has Ace and DON!! field ≥6: hand cost −2",
            "ops": [{"op": "hand_cost_reduce", "amount": -2}],
            "status": "compiled",
            "confidence": 0.9,
            "require_don_field_gte": 6,
            "require_leader_name": "Ace|艾斯",
        },
        {
            "timing": "on_opponent_attack",
            "summary": "May trash hand Character power 8000: Leader and this base power 7000 this turn",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                    "card_type": "character",
                    "power_eq": 8000,
                },
                {
                    "op": "set_base_power",
                    "amount": 7000,
                    "target_kind": "leader",
                    "optional": False,
                },
                {
                    "op": "set_base_power",
                    "amount": 7000,
                    "target_kind": "self",
                    "optional": False,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
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
