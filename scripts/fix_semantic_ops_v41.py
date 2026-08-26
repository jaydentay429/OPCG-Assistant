#!/usr/bin/env python3
"""Deterministic semantic fixes v41: exact-ID rebuilds only.

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

OUT_IDS = ROOT / "meta" / "logs" / "ops_v41_fixed_ids.txt"


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
    "OP13-001": [
        {
            "timing": "on_opponent_attack",
            "summary": "DON!!×1: if active DON!!≤5, may rest any DON!!; +2000 per rested DON!! to Leader or up to 1 Straw Hat",
            "ops": [
                {
                    "op": "rest_don",
                    "count": 10,
                    "owner": "self",
                    "optional": True,
                    "as_cost": True,
                    "summary": "Rest any number of own DON!!",
                },
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "per_rested_don": 1,
                    "duration": "battle",
                    "trait_contains": "Straw Hat Crew|草帽一行人",
                    "count": 1,
                    "summary": "+2000 per rested DON!! to Leader or Straw Hat Character",
                },
            ],
            "status": "compiled",
            "confidence": 0.85,
            "require_don_attached_gte": 1,
            "require_don_active_lte": 5,
        }
    ],
    "OP13-004": [
        {
            "timing": "your_turn",
            "summary": "If Life≥4: this Leader −1000 power",
            "ops": [{"op": "buff", "amount": -1000, "target_kind": "leader", "optional": False}],
            "status": "compiled",
            "confidence": 0.95,
            "require_life_gte": 4,
        },
        {
            "timing": "opponent_turn",
            "summary": "If Life≥4: this Leader −1000 power",
            "ops": [{"op": "buff", "amount": -1000, "target_kind": "leader", "optional": False}],
            "status": "compiled",
            "confidence": 0.95,
            "require_life_gte": 4,
        },
        {
            "timing": "your_turn",
            "summary": "DON!!×1: if own Character cost≥8, Leader and all Characters +1000",
            "ops": [{"op": "buff_all_own", "amount": 1000, "include_leader": True}],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_attached_gte": 1,
            "require_chars_base_cost_gte": 8,
            "require_chars_base_cost_count_gte": 1,
        },
        {
            "timing": "opponent_turn",
            "summary": "DON!!×1: if own Character cost≥8, Leader and all Characters +1000",
            "ops": [{"op": "buff_all_own", "amount": 1000, "include_leader": True}],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_attached_gte": 1,
            "require_chars_base_cost_gte": 8,
            "require_chars_base_cost_count_gte": 1,
        },
    ],
    "OP13-007": [
        {
            "timing": "activate_main",
            "summary": "Give 1 active DON!! to own Leader/Character and trash this: opp Character −3000",
            "ops": [
                {
                    "op": "attach_don",
                    "count": 1,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "as_cost": True,
                },
                {"op": "trash", "target_kind": "self", "optional": False, "as_cost": True},
                {
                    "op": "buff",
                    "amount": -3000,
                    "target_kind": "opponent_character",
                    "optional": True,
                    "duration": "turn",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP13-009": _shield_both_turns(
        {
            "summary": "If other Mountain Bandits Character on field: gain Double Attack",
            "ops": [
                {
                    "op": "grant_keyword",
                    "keyword": "double_attack",
                    "target_kind": "self",
                    "duration": "permanent",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_other_chars_trait": "Mountain Bandits|山賊|山贼",
        }
    ),
    "OP13-016": [
        {
            "timing": "on_play",
            "summary": "If Leader Sabo/Ace/Luffy: look top 4; reveal up to 1 cost≥3 to hand; rest bottom",
            "ops": [
                {
                    "op": "search_deck",
                    "top_n": 4,
                    "max_add": 1,
                    "destination": "hand",
                    "cost_gte": 3,
                    "order_bottom": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_name": "Sabo|薩波|萨波|Portgas.D.Ace|波特卡斯・D・艾斯|Monkey.D.Luffy|蒙其・D・魯夫|蒙其·D·鲁夫",
        }
    ],
    "OP13-038": [
        {
            "timing": "main_start",
            "summary": "Rest up to 1 opp Character cost≤5",
            "ops": [
                {
                    "op": "rest_opponent_character",
                    "count": 1,
                    "cost_lte": 5,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "end_of_your_turn",
            "summary": "Set up to 2 own DON!! as active (from Main this turn)",
            "ops": [{"op": "active_don", "count": 2, "optional": True}],
            "status": "compiled",
            "confidence": 0.9,
        },
        {
            "timing": "trigger",
            "summary": "Rest up to 1 opp Character cost≤5",
            "ops": [
                {
                    "op": "rest_opponent_character",
                    "count": 1,
                    "cost_lte": 5,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP13-040": [
        {
            "timing": "main_start",
            "summary": "May rest 2 DON!!: up to 2 opp rested cost≤7 skip untap until opp refresh",
            "ops": [
                {"op": "rest_don", "count": 2, "owner": "self", "as_cost": True},
                {
                    "op": "skip_untap",
                    "count": 2,
                    "target_kind": "opponent_character_rested",
                    "cost_lte": 7,
                    "optional": True,
                    "summary": "Up to 2 opp rested Characters cost≤7 skip next untap",
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
    "OP13-042": [
        {
            "timing": "on_play",
            "summary": "Draw 2, trash 1 hand; attach up to 2 rested DON!! to Leader and up to 2 to 1 Character",
            "ops": [
                {"op": "draw", "count": 2},
                {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                {
                    "op": "attach_don",
                    "count": 2,
                    "as_rested": True,
                    "target_kind": "leader",
                    "optional": True,
                },
                {
                    "op": "attach_don",
                    "count": 2,
                    "as_rested": True,
                    "target_kind": "own_character",
                    "optional": True,
                    "count_targets": 1,
                    "summary": "Attach up to 2 rested DON!! to 1 own Character",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP13-055": [
        {
            "timing": "when_attacking",
            "summary": "If hand≤4: all own Whitebeard Pirates Characters +1000 this turn",
            "ops": [
                {
                    "op": "buff_all_own",
                    "amount": 1000,
                    "include_leader": False,
                    "trait_contains": "Whitebeard Pirates",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_hand_lte": 4,
        }
    ],
    "OP13-068": _shield_both_turns(
        {
            "summary": "If field DON!!≥8: this Character +2000 power",
            "ops": [{"op": "buff_self", "amount": 2000}],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_field_gte": 8,
        }
    )
    + [
        {
            "timing": "on_play",
            "summary": "If Roger Pirates Leader: add up to 1 rested DON!!",
            "ops": [{"op": "gain_don", "count": 1, "as_rested": True}],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_trait": "Roger Pirates",
        }
    ],
    "OP13-081": _shield_both_turns(
        {
            "summary": "If Revolutionary Army Leader: this +3 cost",
            "ops": [{"op": "grant_cost", "amount": 3, "target_kind": "self"}],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_trait": "Revolutionary Army",
        }
    )
    + [
        {
            "timing": "activate_main",
            "summary": "May place 1 trash at deck bottom: attach up to 1 rested DON!! to Leader or Character",
            "ops": [
                {
                    "op": "trash_to_bottom",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "card_type": "any",
                    "order_any": True,
                },
                {
                    "op": "attach_don",
                    "count": 1,
                    "as_rested": True,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
        }
    ],
    "OP13-083": _shield_both_turns(
        {
            "summary": "If trash≥7: cannot be removed by opp effects",
            "ops": [
                {
                    "op": "cannot_be_removed",
                    "target_kind": "self",
                    "any_leave": True,
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_trash_gte": 7,
        }
    )
    + [
        {
            "timing": "on_play",
            "summary": "Look top 5; reveal up to 1 Five Elders to hand; rest bottom",
            "ops": [
                {
                    "op": "search_deck",
                    "top_n": 5,
                    "max_add": 1,
                    "destination": "hand",
                    "trait_contains": "Five Elders|五老星",
                    "order_bottom": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP13-089": _shield_both_turns(
        {
            "summary": "If trash≥7: cannot be removed + Blocker",
            "ops": [
                {
                    "op": "cannot_be_removed",
                    "target_kind": "self",
                    "any_leave": True,
                    "optional": False,
                },
                {
                    "op": "grant_keyword",
                    "keyword": "blocker",
                    "target_kind": "self",
                    "duration": "permanent",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_trash_gte": 7,
        }
    )
    + [
        {
            "timing": "on_ko",
            "summary": "Draw 1",
            "ops": [{"op": "draw", "count": 1}],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP13-092": [
        {
            "timing": "on_play",
            "summary": "If Life≤3: play up to 1 Mary Geoise Stage cost 1 from trash",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "stage",
                    "optional": True,
                    "cost_eq": 1,
                    "trait_contains": "Mary Geoise",
                    "from_zone": "trash",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_life_lte": 3,
        }
    ],
    "OP13-099": [
        {
            "timing": "your_turn",
            "summary": "If trash≥19: Leader +1000",
            "ops": [{"op": "buff", "amount": 1000, "target_kind": "leader", "optional": False}],
            "status": "compiled",
            "confidence": 0.95,
            "require_trash_gte": 19,
        },
        {
            "timing": "activate_main",
            "summary": "Rest this and 3 DON!!: play black Five Elders cost≤ field DON!! from hand",
            "ops": [
                {"op": "rest_character", "target_kind": "self", "as_cost": True, "count": 1},
                {"op": "rest_don", "count": 3, "owner": "self", "as_cost": True},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                    "color": "black",
                    "trait_contains": "Five Elders|五老星",
                    "cost_lte_own_don_field": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "rest_self": True,
        },
    ],
    "OP13-102": [
        {
            "timing": "activate_main",
            "summary": "Trash this: if Life≤opp Life, draw 1; then rest up to 1 opp cost≤3",
            "ops": [
                {"op": "trash", "target_kind": "self", "optional": False, "as_cost": True},
                {"op": "draw", "count": 1},
                {
                    "op": "rest_opponent_character",
                    "count": 1,
                    "cost_lte": 3,
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_life_lte_opponent": True,
        },
        {
            "timing": "trigger",
            "summary": "Draw 1; rest up to 1 opp cost≤3",
            "ops": [
                {"op": "draw", "count": 1},
                {
                    "op": "rest_opponent_character",
                    "count": 1,
                    "cost_lte": 3,
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP13-119": _shield_both_turns(
        {
            "summary": "If Life≤3: gain Rush",
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
            "require_life_lte": 3,
        }
    )
    + [
        {
            "timing": "on_play",
            "summary": "Attach up to 1 rested DON!! to Leader; may bounce opp cost≤5; if you do, opp plays cost≤4 from hand",
            "ops": [
                {
                    "op": "attach_don",
                    "count": 1,
                    "as_rested": True,
                    "target_kind": "leader",
                    "optional": True,
                },
                {
                    "op": "return_to_hand",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "cost_lte": 5,
                },
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                    "cost_lte": 4,
                    "owner": "opponent",
                    "summary": "If bounced: opponent plays up to 1 cost≤4 from their hand",
                },
            ],
            "status": "compiled",
            "confidence": 0.85,
        }
    ],
        "OP13-119-P5": _shield_both_turns(
        {
            "summary": "If Life≤3: gain Rush",
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
            "require_life_lte": 3,
        }
    )
    + [
        {
            "timing": "on_play",
            "summary": "Attach up to 1 rested DON!! to Leader; may bounce opp cost≤5; if you do, opp plays cost≤8 from hand",
            "ops": [
                {
                    "op": "attach_don",
                    "count": 1,
                    "as_rested": True,
                    "target_kind": "leader",
                    "optional": True,
                },
                {
                    "op": "return_to_hand",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "cost_lte": 5,
                },
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                    "cost_lte": 8,
                    "owner": "opponent",
                    "summary": "If bounced: opponent plays up to 1 cost≤8 from their hand",
                },
            ],
            "status": "compiled",
            "confidence": 0.85,
        }
    ],
    "OP14-003": _shield_both_turns(
        {
            "summary": "Cannot be K.O.'d by effects of opp Characters with base power≤5000",
            "ops": [
                {
                    "op": "cannot_be_ko",
                    "target_kind": "self",
                    "optional": False,
                    "opp_effect_base_power_lte": 5000,
                    "summary": "Immune to KO by opp Character effects base power≤5000",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ),
    "OP14-020": [
        {
            "timing": "your_turn",
            "summary": "If opp Leader has Slash: this Leader +1000",
            "ops": [{"op": "buff", "amount": 1000, "target_kind": "leader", "optional": False}],
            "status": "compiled",
            "confidence": 0.9,
            "require_opp_leader_attribute": "Slash|斬|斩",
        },
        {
            "timing": "opponent_turn",
            "summary": "If opp Leader has Slash: this Leader +1000",
            "ops": [{"op": "buff", "amount": 1000, "target_kind": "leader", "optional": False}],
            "status": "compiled",
            "confidence": 0.9,
            "require_opp_leader_attribute": "Slash|斬|斩",
        },
        {
            "timing": "activate_main",
            "summary": "May rest 1 own card: if field has Character cost≥5, active up to 3 DON!!; then cannot play Characters this turn",
            "ops": [
                {
                    "op": "rest_character",
                    "target_kind": "own_character",
                    "optional": True,
                    "as_cost": True,
                    "count": 1,
                    "include_leader": True,
                    "summary": "Rest 1 own card (Leader/Character/DON!!)",
                },
                {"op": "active_don", "count": 3, "optional": True},
                {
                    "op": "cannot_play_from_hand",
                    "card_type": "character",
                    "summary": "Cannot play Characters this turn",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
            "require_field_char_cost_gte": 5,
        },
    ],
    "OP14-024": [
        {
            "timing": "on_play",
            "summary": "Active up to 3 DON!!; then cannot play Characters this turn",
            "ops": [
                {"op": "active_don", "count": 3, "optional": True},
                {
                    "op": "cannot_play_from_hand",
                    "card_type": "character",
                    "summary": "Cannot play Characters this turn",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "on_ko",
            "summary": "Rest up to 1 opponent card",
            "ops": [{"op": "rest_opponent_character", "count": 1, "optional": True, "include_leader": True}],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "OP14-031": [
        {
            "timing": "on_play",
            "summary": "Rest up to 2 opp Characters cost≤8",
            "ops": [
                {
                    "op": "rest_opponent_character",
                    "count": 2,
                    "cost_lte": 8,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "end_of_your_turn",
            "summary": "Set up to 5 own DON!! as active (from On Play this turn)",
            "ops": [{"op": "active_don", "count": 5, "optional": True}],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "OP14-037": [
        {
            "timing": "main_start",
            "summary": "May rest 3 own cards: KO up to 1 opp rested base power≤7000",
            "ops": [
                {
                    "op": "rest_don",
                    "count": 3,
                    "owner": "self",
                    "as_cost": True,
                    "optional": True,
                    "summary": "Rest 3 own cards (DON!!/Characters)",
                },
                {
                    "op": "ko",
                    "target_kind": "opponent_character_rested",
                    "optional": True,
                    "base_power_lte": 7000,
                    "count": 1,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
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
    "OP14-045": [
        {
            "timing": "your_turn",
            "summary": "When a card is trashed from hand by effect: gain Rush this turn",
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
            "on_hand_trashed_by_effect": True,
        },
        {
            "timing": "opponent_turn",
            "summary": "When a card is trashed from hand by effect: gain Rush this turn",
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
            "on_hand_trashed_by_effect": True,
        },
        {
            "timing": "on_ko",
            "summary": "Draw 1",
            "ops": [{"op": "draw", "count": 1}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP14-049": [
        {
            "timing": "your_turn",
            "summary": "When a card is trashed from hand by effect: gain Rush this turn",
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
            "on_hand_trashed_by_effect": True,
        },
        {
            "timing": "opponent_turn",
            "summary": "When a card is trashed from hand by effect: gain Rush this turn",
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
            "on_hand_trashed_by_effect": True,
        },
        {
            "timing": "on_play",
            "summary": "May rest 2 DON!!: draw 2; return up to 1 Character cost≤7 to hand",
            "ops": [
                {"op": "rest_don", "count": 2, "owner": "self", "as_cost": True},
                {"op": "draw", "count": 2},
                {
                    "op": "return_to_hand",
                    "target_kind": "any_character",
                    "optional": True,
                    "cost_lte": 7,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP14-054": [
        {
            "timing": "on_play",
            "summary": "If Fish-Man Leader: draw 3",
            "ops": [{"op": "draw", "count": 3}],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_trait": "Fish-Man",
        },
        {
            "timing": "end_of_your_turn",
            "summary": "Trash hand down to 5",
            "ops": [{"op": "trash_hand_down_to", "hand_size": 5, "side": "self"}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP14-056": _shield_both_turns(
        {
            "summary": "Cannot attack; when hand trashed by effect, effects negated this turn",
            "ops": [{"op": "cannot_attack", "target_kind": "self"}],
            "status": "compiled",
            "confidence": 0.95,
            "negated_when_hand_trashed": True,
            "on_hand_trashed_by_effect": True,
        }
    ),
    "OP14-058": [
        {
            "timing": "main_start",
            "summary": "May rest 3 DON!!: play Fish-Man cost≤3 from hand; return up to 1 base power 6000 to hand",
            "ops": [
                {"op": "rest_don", "count": 3, "owner": "self", "as_cost": True},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                    "trait_contains": "Fish-Man",
                    "cost_lte": 3,
                },
                {
                    "op": "return_to_hand",
                    "target_kind": "any_character",
                    "optional": True,
                    "base_power_eq": 6000,
                    "summary": "Return Character with base power 6000",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
        {
            "timing": "counter_event",
            "summary": "Draw 1; Leader +3000 this battle",
            "ops": [
                {"op": "draw", "count": 1},
                {
                    "op": "buff",
                    "amount": 3000,
                    "target_kind": "leader",
                    "optional": False,
                    "duration": "battle",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP14-063": [
        {
            "timing": "on_play",
            "summary": "Add up to 1 active DON!!",
            "ops": [{"op": "gain_don", "count": 1}],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "on_ko",
            "summary": "If opp field DON!!≥6: play Donquixote cost≤5 from hand",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                    "trait_contains": "Donquixote Pirates",
                    "cost_lte": 5,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_opp_don_field_gte": 6,
        },
    ],
    "OP14-069": [
        {
            "timing": "on_play",
            "summary": "DON!! −3: choose KO opp cost≤8 (if Donquixote Leader) OR deny_rest up to 3 opp cost≤7 until opp end",
            "ops": [
                {"op": "return_don", "count": 3, "owner": "self", "as_cost": True},
                {
                    "op": "choose_one",
                    "chooser": "self",
                    "options": [
                        {
                            "id": "opt0",
                            "label": "If Donquixote Leader: KO up to 1 opp cost≤8",
                            "ops": [
                                {
                                    "op": "ko",
                                    "target_kind": "opponent_character",
                                    "optional": True,
                                    "cost_lte": 8,
                                    "count": 1,
                                }
                            ],
                            "require_leader_trait": "Donquixote Pirates",
                        },
                        {
                            "id": "opt1",
                            "label": "Up to 3 opp cost≤7 cannot be rested until opp turn end",
                            "ops": [
                                {
                                    "op": "deny_rest",
                                    "count": 3,
                                    "optional": True,
                                    "target_kind": "opponent_character",
                                    "cost_lte": 7,
                                    "duration": "until_opp_turn_end",
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
    "OP14-070": [
        {
            "timing": "your_turn",
            "summary": "When rested by opp effect: may return 1 DON!!; if you do, set this active",
            "ops": [
                {"op": "return_don", "count": 1, "owner": "self", "as_cost": True, "optional": True},
                {"op": "set_character_active", "count": 1, "target_kind": "self", "optional": False},
            ],
            "status": "compiled",
            "confidence": 0.9,
            "trigger_on": "self_rested",
        },
        {
            "timing": "opponent_turn",
            "summary": "When rested by opp effect: may return 1 DON!!; if you do, set this active",
            "ops": [
                {"op": "return_don", "count": 1, "owner": "self", "as_cost": True, "optional": True},
                {"op": "set_character_active", "count": 1, "target_kind": "self", "optional": False},
            ],
            "status": "compiled",
            "confidence": 0.9,
            "trigger_on": "self_rested",
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
