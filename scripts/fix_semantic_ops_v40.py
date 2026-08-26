#!/usr/bin/env python3
"""Deterministic semantic fixes v40: exact-ID rebuilds only.

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

OUT_IDS = ROOT / "meta" / "logs" / "ops_v40_fixed_ids.txt"


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
    "OP10-097": [
        {
            "timing": "main_start",
            "summary": "Up to 1 Dressrosa Character +2000 this turn",
            "ops": [
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "own_character",
                    "optional": True,
                    "trait_contains": "Dressrosa",
                    "duration": "turn",
                    "summary": "Same target may then gain Banish if trash≥10",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "main_start",
            "summary": "If trash≥10: that Dressrosa Character gains Banish this turn",
            "ops": [
                {
                    "op": "grant_keyword",
                    "keyword": "banish",
                    "target_kind": "own_character",
                    "optional": True,
                    "trait_contains": "Dressrosa",
                    "duration": "turn",
                    "summary": "Same Dressrosa target as the +2000",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_trash_gte": 10,
        },
        {
            "timing": "trigger",
            "summary": "Draw 2 and trash 1 hand",
            "ops": [
                {"op": "draw", "count": 2},
                {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP11-022": [
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
            "summary": "Rest 1 DON!! and flip Life top face-up: play Sea Creature or [Megalodon] cost≤ own field DON!!",
            "ops": [
                {"op": "rest_don", "count": 1, "owner": "self", "as_cost": True},
                {"op": "flip_life", "face": "up", "position": "top", "optional": False, "as_cost": True},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                    "cost_lte_own_don_field": True,
                    "name_or_trait": True,
                    "trait_contains": "Sea Creature|Neptunian|海王類",
                    "name_contains": "Megalodon|Megalo|梅卡洛",
                    "summary": "Play Sea Creature/Neptunian or Megalo with cost ≤ own field DON!!",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
        },
    ],
    "OP11-025": [
        {
            "timing": "on_opponent_attack",
            "summary": "May rest 1 DON!! and this Character: own Leader/Character +1000 this battle",
            "ops": [
                {"op": "rest_don", "count": 1, "owner": "self", "as_cost": True},
                {"op": "rest_character", "target_kind": "self", "optional": True, "as_cost": True, "count": 1},
                {
                    "op": "buff",
                    "amount": 1000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
        }
    ],
    "OP11-035": [
        {
            "timing": "on_ko",
            "summary": "When K.O.'d by opponent effect: may rest 1 DON!!; if you do, play Fish-Man/Merfolk cost≤4 from hand",
            "ops": [
                {"op": "rest_don", "count": 1, "owner": "self", "as_cost": True, "optional": True},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 4,
                    "trait_any": ["Fish-Man", "Merfolk", "魚人族", "人魚族"],
                    "from_zone": "hand",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
        {
            "timing": "on_play",
            "summary": "Rest up to 1 opponent Character",
            "ops": [{"op": "rest_opponent_character", "count": 1, "optional": True}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP11-043": [
        {
            "timing": "on_opponent_attack",
            "summary": "If all own Characters are GERMA: +1000 this battle; then trash 2 deck top",
            "ops": [
                {
                    "op": "buff",
                    "amount": 1000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                },
                {"op": "trash_deck_top", "count": 2, "optional": False},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
            "require_all_chars_trait": "GERMA|杰爾馬|杰尔马",
        }
    ],
    "OP11-051": [
        {
            "timing": "on_ko",
            "summary": "When K.O.'d by opponent effect: look top 5; play Straw Hat cost≤5; rest bottom",
            "ops": [
                {
                    "op": "search_deck",
                    "top_n": 5,
                    "max_add": 1,
                    "destination": "play",
                    "card_type": "character",
                    "trait_contains": "Straw Hat Crew|草帽一行人",
                    "cost_lte": 5,
                    "order_bottom": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
        {
            "timing": "on_play",
            "summary": "Return up to 1 Character with base power≤5000 to hand",
            "ops": [
                {
                    "op": "return_to_hand",
                    "target_kind": "any_character",
                    "optional": True,
                    "base_power_lte": 5000,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP11-054": [
        {
            "timing": "on_play",
            "summary": "If Leader multicolored: draw 3; place 2 hand on deck top or bottom in any order",
            "ops": [
                {"op": "draw", "count": 3},
                {
                    "op": "hand_to_deck",
                    "count": 2,
                    "position": "top_or_bottom",
                    "optional": False,
                    "summary": "Place 2 hand cards on deck top or bottom",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_multicolor": True,
        }
    ],
    "OP11-067": [
        {
            "timing": "end_of_your_turn",
            "summary": "Set up to 2 Big Mom Pirates cost≥3 active; add up to 1 rested DON!!",
            "ops": [
                {
                    "op": "set_character_active",
                    "count": 2,
                    "target_kind": "own_character",
                    "optional": True,
                    "trait_contains": "Big Mom Pirates",
                    "cost_gte": 3,
                },
                {"op": "gain_don", "count": 1, "as_rested": True},
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP11-082": [
        {
            "timing": "activate_main",
            "summary": "Trash this: if Navy Leader, up to 1 Navy Character may attack active Characters; trash 2 deck top",
            "ops": [
                {"op": "trash", "target_kind": "self", "optional": False, "as_cost": True},
                {
                    "op": "allow_attack_active",
                    "count": 1,
                    "target_kind": "own_character",
                    "trait_contains": "Navy",
                    "optional": True,
                    "duration": "turn",
                },
                {"op": "trash_deck_top", "count": 2, "optional": False},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_trait": "Navy",
        }
    ],
    "OP11-083": [
        {
            "timing": "on_play",
            "summary": "Trash 2 cards from your hand",
            "ops": [{"op": "trash_hand", "count": 2, "optional": False, "owner": "self"}],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP11-107": [
        {
            "timing": "activate_main",
            "summary": "If Leader [Shirahoshi]: may flip Life top face-down; at end of turn set this active",
            "ops": [
                {"op": "flip_life", "face": "down", "position": "top", "optional": True, "as_cost": True},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
            "require_leader_name": "Shirahoshi|白星",
        },
        {
            "timing": "end_of_your_turn",
            "summary": "If activate paid this turn: set this Character active",
            "ops": [{"op": "set_character_active", "count": 1, "target_kind": "self", "optional": False}],
            "status": "compiled",
            "confidence": 0.85,
            "require_leader_name": "Shirahoshi|白星",
        },
    ],
    "OP11-109": [
        {
            "timing": "on_play",
            "summary": "If you have [Camie]: draw 2 and trash 2 hand",
            "ops": [
                {"op": "draw", "count": 2},
                {"op": "trash_hand", "count": 2, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_own_name_on_field": "Camie|海咪",
        }
    ],
    "OP12-016": [
        {
            "timing": "main_start",
            "summary": "May give 2 active DON!! to [Silvers Rayleigh]: when that card attacks this turn, opponent cannot Blocker",
            "ops": [
                {
                    "op": "attach_don",
                    "count": 2,
                    "as_rested": False,
                    "target_kind": "own_character",
                    "optional": True,
                    "as_cost": True,
                    "name_contains": "Silvers Rayleigh|席爾巴斯・雷利|希尔巴斯・雷利",
                    "summary": "Attach 2 active DON!! to Rayleigh as cost",
                },
                {
                    "op": "deny_blocker",
                    "duration": "turn",
                    "summary": "When that Rayleigh attacks this turn, opponent cannot activate Blocker",
                },
            ],
            "status": "compiled",
            "confidence": 0.85,
        },
        {
            "timing": "counter_event",
            "summary": "Up to 1 own Character or [Silvers Rayleigh] +2000 this battle",
            "ops": [
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                    "summary": "Character or Silvers Rayleigh +2000",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "OP12-018": [
        {
            "timing": "counter_event",
            "summary": "+2000 this battle; may rest 1 DON!!: if you do, all opp Leader/Characters −1000 this turn",
            "ops": [
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "own_character",
                    "optional": True,
                    "duration": "battle",
                    "summary": "Own Character or Silvers Rayleigh +2000",
                },
                {"op": "rest_don", "count": 1, "owner": "self", "as_cost": True, "optional": True},
                {
                    "op": "buff",
                    "amount": -1000,
                    "target_kind": "opponent_leader_or_character",
                    "all": True,
                    "optional": False,
                    "duration": "turn",
                    "summary": "If DON!! rested: all opp Leader and Characters −1000",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "OP12-021": _shield_both_turns(
        {
            "summary": "If Leader has Slash and ≥6 rested cards: this cannot be rested by opponent effects",
            "ops": [{"op": "cannot_be_rested", "target_kind": "self", "optional": False}],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_attribute": "Slash|斬|斩",
            "require_rested_cards_gte": 6,
        }
    )
    + [
        {
            "timing": "on_block",
            "summary": "Blocker",
            "ops": [{"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"}],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP12-027": _shield_both_turns(
        {
            "summary": "If other own Slash cost≤5 would be K.O.'d by opp effect, may rest this instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "own_filtered",
                    "cost": "rest_self",
                    "attr_contains": "Slash",
                    "cost_lte": 5,
                    "exclude_self": True,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ),
    "OP12-040": [
        {
            "timing": "on_event",
            "summary": "When hand trashed by own Navy effect: draw equal to trashed count",
            "ops": [
                {
                    "op": "draw",
                    "count": 1,
                    "equal_trashed": True,
                    "summary": "Draw equal to number of cards trashed",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_chars_trait": "Navy",
        }
    ],
    "OP12-046": [
        {
            "timing": "on_play",
            "summary": "Trash 2 cards from your hand",
            "ops": [{"op": "trash_hand", "count": 2, "optional": False, "owner": "self"}],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "activate_main",
            "summary": "Trash this: return up to 1 Character cost≤5 to hand",
            "ops": [
                {"op": "trash", "target_kind": "self", "optional": False, "as_cost": True},
                {
                    "op": "return_to_hand",
                    "target_kind": "any_character",
                    "optional": True,
                    "cost_lte": 5,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP12-051": [
        {
            "timing": "activate_main",
            "summary": "May rest this and trash 1 hand: up to 1 opp base cost≤4 cannot Blocker this turn",
            "ops": [
                {"op": "rest_character", "target_kind": "self", "optional": True, "as_cost": True, "count": 1},
                {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                {
                    "op": "deny_blocker",
                    "count": 1,
                    "target_kind": "opponent_character",
                    "optional": True,
                    "base_cost_lte": 4,
                    "duration": "turn",
                    "summary": "Up to 1 opp base cost≤4 cannot Blocker",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP12-058": [
        {
            "timing": "main_start",
            "summary": "If Whitebeard Leader: reveal top; may play Whitebeard cost≤9; if played, gains Rush",
            "ops": [
                {
                    "op": "search_deck",
                    "top_n": 1,
                    "max_add": 1,
                    "destination": "play",
                    "card_type": "character",
                    "trait_contains": "Whitebeard Pirates",
                    "cost_lte": 9,
                    "summary": "Reveal top; play Whitebeard Pirates cost≤9",
                },
                {
                    "op": "grant_keyword",
                    "keyword": "rush",
                    "target_kind": "own_character",
                    "optional": True,
                    "duration": "turn",
                    "summary": "If played, that Character gains Rush this turn",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_leader_trait": "Whitebeard Pirates",
        },
        {
            "timing": "trigger",
            "summary": "Draw 1",
            "ops": [{"op": "draw", "count": 1}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP12-059": [
        {
            "timing": "main_start",
            "summary": "If Leader is [Sanji]: draw 1",
            "ops": [{"op": "draw", "count": 1}],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_name": "Sanji|香吉士",
        },
        {
            "timing": "counter_event",
            "summary": "If trash has ≥4 Events: Leader +4000 this battle",
            "ops": [
                {
                    "op": "buff",
                    "amount": 4000,
                    "target_kind": "leader",
                    "optional": True,
                    "duration": "battle",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_trash_events_gte": 4,
        },
    ],
    "OP12-060": [
        {
            "timing": "main_start",
            "summary": "If Leader multicolored, choose one: return opp cost≤4 OR if hand≤6 draw 2",
            "ops": [
                {
                    "op": "choose_one",
                    "chooser": "self",
                    "options": [
                        {
                            "id": "opt0",
                            "label": "Return up to 1 opponent Character cost≤4 to hand",
                            "ops": [
                                {
                                    "op": "return_to_hand",
                                    "target_kind": "opponent_character",
                                    "optional": True,
                                    "cost_lte": 4,
                                }
                            ],
                        },
                        {
                            "id": "opt1",
                            "label": "If hand≤6: draw 2",
                            "ops": [{"op": "draw", "count": 2}],
                            "require_hand_lte": 6,
                        },
                    ],
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_multicolor": True,
        }
    ],
    "OP12-085": _shield_both_turns(
        {
            "summary": "If Revolutionary Army Leader: this Character gains +3 cost",
            "ops": [{"op": "grant_cost", "amount": 3, "target_kind": "self"}],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_trait": "Revolutionary Army",
        }
    )
    + [
        {
            "timing": "when_attacking",
            "summary": "If Revolutionary Leader and opp hand≥5: opponent trashes 1 hand",
            "ops": [{"op": "trash_hand", "count": 1, "optional": False, "owner": "opponent"}],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_trait": "Revolutionary Army",
            "require_opp_hand_gte": 5,
        }
    ],
    "OP12-089": _shield_both_turns(
        {
            "summary": "If Revolutionary Army Leader: gain Blocker and +4 cost",
            "ops": [
                {"op": "grant_keyword", "keyword": "blocker", "target_kind": "self", "duration": "permanent"},
                {"op": "grant_cost", "amount": 4, "target_kind": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_trait": "Revolutionary Army",
        }
    )
    + [
        {
            "timing": "on_ko",
            "summary": "If Revolutionary Leader: KO up to 1 opp base cost≤4",
            "ops": [
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "base_cost_lte": 4,
                    "count": 1,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_trait": "Revolutionary Army",
        }
    ],
    "OP12-097": [
        {
            "timing": "main_start",
            "summary": "Look top 3; reveal up to 1 Revolutionary other than Captains Assembled to hand; trash rest",
            "ops": [
                {
                    "op": "search_deck",
                    "top_n": 3,
                    "max_add": 1,
                    "destination": "hand",
                    "trait_contains": "Revolutionary Army",
                    "exclude_name": "Captains Assembled|軍隊長集結|军队长集结",
                    "trash_rest": True,
                    "order_bottom": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "Activate this card's [Main] effect",
            "ops": [{"op": "activate_timing", "timing": "main_start"}],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "OP12-098": [
        {
            "timing": "counter_event",
            "summary": "+2000 this battle; if own Revolutionary cost≥8 on field, that card +2000 more",
            "ops": [
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                },
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "trait_contains": "Revolutionary Army",
                    "cost_gte": 8,
                    "duration": "battle",
                    "summary": "Same chosen card +2000 more if Revolutionary cost≥8 on field",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
        {
            "timing": "trigger",
            "summary": "Draw 1 and trash deck top 1",
            "ops": [
                {"op": "draw", "count": 1},
                {"op": "trash_deck_top", "count": 1, "optional": False},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP12-102": _shield_both_turns(
        {
            "summary": "If own base cost≤6 would leave by opp effect: may flip Life top face-up instead",
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
        }
    )
    + [
        {
            "timing": "opponent_turn",
            "summary": "If no other base-cost-2 [Shirahoshi]: all Sea Creature Characters +2000",
            "ops": [
                {
                    "op": "buff_all_own",
                    "amount": 2000,
                    "include_leader": False,
                    "trait_contains": "Sea Creature|海王類",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_no_other_name": "Shirahoshi|白星公主|白星",
        }
    ],
    "OP12-113": [
        {
            "timing": "on_ko",
            "summary": "If Supernovas Leader: play up to 1 Supernovas cost≤4 from hand rested",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 4,
                    "trait_contains": "Supernovas",
                    "as_rested": True,
                    "from_zone": "hand",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_trait": "Supernovas",
        },
        {
            "timing": "trigger",
            "summary": "KO up to 1 opp cost≤1; add this card to hand",
            "ops": [
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "cost_lte": 1,
                    "count": 1,
                },
                {
                    "op": "add_from_trash",
                    "count": 1,
                    "optional": False,
                    "self_card": True,
                    "summary": "Add this Trigger card to hand",
                },
            ],
            "status": "compiled",
            "confidence": 0.85,
        },
    ],
    "OP12-119": [
        {
            "timing": "on_play",
            "summary": "May trash 1 hand: add up to 1 deck top to Life top; then this +2 cost until opp end",
            "ops": [
                {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True, "owner": "self"},
                {"op": "add_life", "count": 1, "optional": True},
                {
                    "op": "grant_cost",
                    "amount": 2,
                    "target_kind": "self",
                    "duration": "until_opp_turn_end",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "on_ko",
            "summary": "Add up to 1 deck top to Life top",
            "ops": [{"op": "add_life", "count": 1, "optional": True}],
            "status": "compiled",
            "confidence": 0.95,
            "require_opponent_turn": True,
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
        for base in bases:
            if cid == base or cid.startswith(base + "-"):
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

    ovr = json.loads(ovr_path.read_text()) if ovr_path.exists() else {"cards": {}}
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
