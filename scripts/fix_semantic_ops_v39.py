#!/usr/bin/env python3
"""Deterministic semantic fixes v39: exact-ID rebuilds only.

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

OUT_IDS = ROOT / "meta" / "logs" / "ops_v39_fixed_ids.txt"


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
    "OP05-119": [
        {
            "timing": "on_play",
            "summary": "DON!! −10: place all other own Characters at deck bottom; then take an extra turn",
            "ops": [
                {"op": "return_don", "count": 10, "owner": "self", "as_cost": True},
                {
                    "op": "return_to_bottom",
                    "count": 1,
                    "optional": False,
                    "all": True,
                    "exclude_self": True,
                    "target_kind": "own_character",
                    "summary": "Place all other own Characters at deck bottom",
                },
                {"op": "extra_turn", "summary": "Gain an additional own turn after this one"},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "activate_main",
            "summary": "①: add up to 1 active DON!!",
            "ops": [{"op": "gain_don", "count": 1}],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
            "cost_don": 1,
        },
    ],
    "OP06-042": [
        {
            "timing": "on_don_returned",
            "summary": "When a DON!! on your field is returned to DON!! deck: draw 1",
            "ops": [{"op": "draw", "count": 1}],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
        }
    ],
    "OP06-086": [
        {
            "timing": "on_play",
            "summary": "From trash: up to 1 cost≤4 and up to 1 cost≤2; play one, play the other rested",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "trash",
                    "cost_lte": 4,
                    "summary": "Play up to 1 cost≤4 from trash",
                },
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "trash",
                    "cost_lte": 2,
                    "as_rested": True,
                    "summary": "Play up to 1 cost≤2 from trash rested",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "OP07-031": [
        {
            "timing": "your_turn",
            "summary": "Once/turn when a Character is rested by your effect: draw 1 and trash 1 hand",
            "ops": [
                {"op": "draw", "count": 1},
                {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
            "on_char_rested_by_own_effect": True,
        }
    ],
    "OP07-048": [
        {
            "timing": "activate_main",
            "summary": "②: reveal top deck; if Warlords cost≤4 Character, may play rested; rest to bottom",
            "ops": [
                {"op": "rest_don", "count": 2, "owner": "self", "as_cost": True},
                {
                    "op": "search_deck",
                    "top_n": 1,
                    "max_add": 1,
                    "destination": "play",
                    "card_type": "character",
                    "trait_contains": "The Seven Warlords of the Sea",
                    "cost_lte": 4,
                    "as_rested": True,
                    "order_bottom": True,
                    "summary": "Reveal top 1; play Warlords cost≤4 rested; rest bottom",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
        }
    ],
    "OP07-091": [
        {
            "timing": "when_attacking",
            "summary": "Trash up to 1 opp cost≤2; place any number cost≥4 Characters from trash bottom; +1000 per 3",
            "ops": [
                {
                    "op": "trash",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "cost_lte": 2,
                    "count": 1,
                },
                {
                    "op": "trash_to_bottom",
                    "count": 20,
                    "optional": True,
                    "card_type": "character",
                    "cost_gte": 4,
                    "order_any": True,
                    "buff_self_per_n": 3,
                    "buff_self_amount": 1000,
                    "summary": "Any number cost≥4 Characters from trash to bottom; +1000 per 3",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "OP08-050": [
        {
            "timing": "on_play",
            "summary": "Draw 2; place 2 hand cards on deck top or bottom in any order",
            "ops": [
                {"op": "draw", "count": 2},
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
        }
    ],
    "OP08-054": [
        {
            "timing": "counter_event",
            "summary": "Own Leader/Character +3000 this battle; reveal top; play Whitebeard Pirates cost≤3; rest top/bottom",
            "ops": [
                {
                    "op": "buff",
                    "amount": 3000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                },
                {
                    "op": "search_deck",
                    "top_n": 1,
                    "max_add": 1,
                    "destination": "play",
                    "card_type": "character",
                    "trait_contains": "Whitebeard Pirates",
                    "cost_lte": 3,
                    "order_bottom": False,
                    "summary": "Reveal top 1; play Whitebeard Pirates cost≤3; rest top or bottom",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP08-067": [
        {
            "timing": "on_don_returned",
            "summary": "When DON!! returned: add up to 1 rested DON!!",
            "ops": [{"op": "gain_don", "count": 1, "as_rested": True}],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
        }
    ],
    "OP08-071": [
        {
            "timing": "on_ko",
            "summary": "DON!! −1: play up to 1 [Baron Tamago] cost≤4 from deck; shuffle",
            "ops": [
                {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                {
                    "op": "search_deck",
                    "top_n": 8,
                    "max_add": 1,
                    "destination": "play",
                    "card_type": "character",
                    "name_contains": "Baron Tamago|塔馬哥男爵|塔马哥男爵",
                    "cost_lte": 4,
                    "summary": "Play Baron Tamago cost≤4 from deck then shuffle",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_opponent_turn": True,
        }
    ],
    "OP08-073": [
        {
            "timing": "on_ko",
            "summary": "DON!! −1: play up to 1 [Count Niwatori] cost≤6 from deck; shuffle",
            "ops": [
                {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                {
                    "op": "search_deck",
                    "top_n": 8,
                    "max_add": 1,
                    "destination": "play",
                    "card_type": "character",
                    "name_contains": "Count Niwatori|公雞伯爵|公鸡伯爵",
                    "cost_lte": 6,
                    "summary": "Play Count Niwatori cost≤6 from deck then shuffle",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_opponent_turn": True,
        }
    ],
    "OP08-074": [
        {
            "timing": "activate_main",
            "summary": "If no other [Black Maria]: add up to 5 rested DON!!; end of turn equalize DON!! to opponent",
            "ops": [
                {"op": "gain_don", "count": 5, "as_rested": True},
                {
                    "op": "equalize_don_to_opponent",
                    "summary": "At end of this turn, return DON!! until equal to opponent field DON!!",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
            "require_no_other_name": "Black Maria|黑瑪麗亞|黑玛丽亚",
        }
    ],
    "OP08-085": [
        {
            "timing": "when_attacking",
            "summary": "If you have a Character cost≥8: KO up to 1 opp cost≤4",
            "ops": [
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "cost_lte": 4,
                    "count": 1,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_attached_gte": 1,
            "require_chars_base_cost_gte": 8,
            "require_chars_base_cost_count_gte": 1,
        }
    ],
    "OP08-086": [
        {
            "timing": "on_play",
            "summary": "If opponent has a cost-0 Character: draw 2 and trash 2 hand",
            "ops": [
                {"op": "draw", "count": 2},
                {"op": "trash_hand", "count": 2, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_opp_char_cost_eq": 0,
        }
    ],
    "OP08-096": [
        {
            "timing": "counter_event",
            "summary": "Trash deck top 1; if cost≥6, own Leader/Character +5000 this battle",
            "ops": [
                {"op": "trash_deck_top", "count": 1},
                {
                    "op": "buff",
                    "amount": 5000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                    "summary": "If trashed card cost≥6: +5000 this battle",
                },
            ],
            "status": "compiled",
            "confidence": 0.85,
        },
        {
            "timing": "trigger",
            "summary": "Play up to 1 black Character cost≤3 from trash",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "trash",
                    "color": "black",
                    "cost_lte": 3,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP09-005": [
        {
            "timing": "on_play",
            "summary": "If opponent has ≥2 Characters with base power≥5000: draw 2 and trash 1 hand",
            "ops": [
                {"op": "draw", "count": 2},
                {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_opp_chars_count_gte": 2,
            "require_opp_chars_base_power_gte": 5000,
        }
    ],
    "OP09-045": _shield_both_turns(
        {
            "summary": "If you have [Buggy] or [Mohji]: this Character cannot be K.O.'d in battle",
            "ops": [{"op": "cannot_be_ko", "target_kind": "self", "optional": False}],
            "status": "compiled",
            "confidence": 0.95,
            "require_own_name_contains": "Buggy|巴其|Mohji|摩奇",
        }
    ),
    "OP09-051": [
        {
            "timing": "on_play",
            "summary": "Place up to 1 opponent Character at owner's deck bottom",
            "ops": [
                {
                    "op": "return_to_bottom",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_character",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "on_play",
            "summary": "If you have fewer than 5 Characters with cost≥5: place this at deck bottom",
            "ops": [
                {
                    "op": "return_to_bottom",
                    "count": 1,
                    "optional": False,
                    "target_kind": "self",
                    "summary": "Place this Character at deck bottom",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_chars_base_cost_gte": 5,
            "require_chars_base_cost_count_lte": 4,
        },
    ],
    "OP09-059": [
        {
            "timing": "counter_event",
            "summary": "+3000 this battle; trash up to 2 hand; trash equal count from deck top",
            "ops": [
                {
                    "op": "buff",
                    "amount": 3000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                },
                {
                    "op": "trash_hand",
                    "count": 2,
                    "optional": True,
                    "owner": "self",
                    "then_trash_equal": True,
                    "summary": "Trash up to 2 hand; trash same number from deck top",
                },
                {"op": "trash_deck_top", "count": 2, "optional": True, "summary": "Equal count from deck top"},
            ],
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
    "OP09-093": [
        {
            "timing": "activate_main",
            "summary": "If Blackbeard Leader and played this turn: negate opp Leader; then negate+deny opp Character until opp turn end",
            "ops": [
                {
                    "op": "negate_effects",
                    "count": 1,
                    "optional": True,
                    "target_kind": "leader",
                    "include_leader": True,
                    "include_characters": False,
                    "summary": "Negate up to 1 opponent Leader this turn",
                },
                {
                    "op": "negate_effects",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "include_leader": False,
                    "include_characters": True,
                    "duration": "until_opp_turn_end",
                    "summary": "Negate up to 1 opp Character until opp turn end",
                },
                {
                    "op": "deny_attack",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "duration": "until_opp_turn_end",
                    "summary": "That Character cannot attack until opp turn end",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
            "require_leader_trait": "Blackbeard Pirates",
            "require_played_this_turn": True,
        }
    ],
    "OP09-097": [
        {
            "timing": "counter_event",
            "summary": "Negate up to 1 opp Leader/Character and give −4000 this turn",
            "ops": [
                {
                    "op": "negate_effects",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_leader_or_character",
                    "include_leader": True,
                    "include_characters": True,
                },
                {
                    "op": "buff",
                    "amount": -4000,
                    "target_kind": "opponent_leader_or_character",
                    "optional": True,
                    "duration": "turn",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "Negate up to 1 opp Leader/Character this turn",
            "ops": [
                {
                    "op": "negate_effects",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_leader_or_character",
                    "include_leader": True,
                    "include_characters": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP09-098": [
        {
            "timing": "main_start",
            "summary": "If Blackbeard Leader: negate up to 1 opp Character; if cost≤4, KO it",
            "ops": [
                {
                    "op": "negate_effects",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "include_leader": False,
                    "include_characters": True,
                },
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "cost_lte": 4,
                    "count": 1,
                    "summary": "If that Character cost≤4: KO it",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_leader_trait": "Blackbeard Pirates",
        },
        {
            "timing": "trigger",
            "summary": "Negate up to 1 opp Leader/Character",
            "ops": [
                {
                    "op": "negate_effects",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_leader_or_character",
                    "include_leader": True,
                    "include_characters": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP09-105": [
        {
            "timing": "trigger",
            "summary": "If Egghead Leader: add up to 1 deck top to Life top; then trash 2 hand",
            "ops": [
                {"op": "add_life", "count": 1},
                {"op": "trash_hand", "count": 2, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_trait": "Egghead",
        }
    ],
    "OP09-111": [
        {
            "timing": "trigger",
            "summary": "If Egghead Leader and opp hand≥6: opponent trashes 2 hand",
            "ops": [
                {"op": "trash_hand", "count": 2, "optional": False, "owner": "opponent"},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_trait": "Egghead",
            "require_opp_hand_gte": 6,
        }
    ],
    "OP09-119": [
        {
            "timing": "on_play",
            "summary": "May return 1+ DON!!: draw 1; this gains Rush this turn",
            "ops": [
                {"op": "return_don", "count": 1, "owner": "self", "as_cost": True, "optional": True},
                {"op": "draw", "count": 1},
                {"op": "grant_keyword", "keyword": "rush", "target_kind": "self", "duration": "turn"},
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP10-008": [
        {
            "timing": "on_play",
            "summary": "If you have no [Rock]: play up to 1 [Rock] from hand",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "name_contains": "Rock|洛克",
                    "from_zone": "hand",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_no_own_name_on_field": "Rock|洛克",
        }
    ],
    "OP10-020": [
        {
            "timing": "main_start",
            "summary": "Give up to 1 opponent Character −4000 this turn",
            "ops": [
                {
                    "op": "buff",
                    "amount": -4000,
                    "target_kind": "opponent_character",
                    "optional": True,
                    "duration": "turn",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "main_start",
            "summary": "If Life≤2: up to 1 own Leader/Character +1000 this turn",
            "ops": [
                {
                    "op": "buff",
                    "amount": 1000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "turn",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_life_lte": 2,
        },
        {
            "timing": "trigger",
            "summary": "KO up to 1 opp Character power≤3000",
            "ops": [
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "power_lte": 3000,
                    "count": 1,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP10-022": [
        {
            "timing": "activate_main",
            "summary": "If own Characters total cost≥5: return 1 Character; reveal Life top; if Supernovas cost≤5 may play",
            "ops": [
                {
                    "op": "return_to_hand",
                    "target_kind": "own_character",
                    "optional": True,
                    "as_cost": True,
                    "count": 1,
                },
                {
                    "op": "look_deck",
                    "count": 1,
                    "position": "top",
                    "optional": False,
                    "summary": "Reveal top Life; if Supernovas cost≤5 Character, may play it",
                },
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                    "trait_contains": "Supernovas",
                    "cost_lte": 5,
                    "summary": "Play revealed Supernovas cost≤5 from Life (approx via hand filter)",
                },
            ],
            "status": "compiled",
            "confidence": 0.75,
            "once": True,
            "require_don_attached_gte": 1,
            "require_chars_cost_sum_gte": 5,
        }
    ],
    "OP10-026": [
        {
            "timing": "activate_main",
            "summary": "Place this and 1 power-0 [Kin'emon] from trash at deck bottom: play cost-6 Kin'emon from hand",
            "ops": [
                {
                    "op": "return_to_bottom",
                    "count": 1,
                    "optional": False,
                    "target_kind": "self",
                    "as_cost": True,
                    "summary": "Place this Character at deck bottom",
                },
                {
                    "op": "trash_to_bottom",
                    "count": 1,
                    "optional": False,
                    "as_cost": True,
                    "card_type": "character",
                    "name_contains": "Kin'emon|錦右衛門|锦右卫门",
                    "summary": "Place power-0 Kin'emon from trash at deck bottom",
                },
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                    "name_contains": "Kin'emon|錦右衛門|锦右卫门",
                    "cost_eq": 6,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "OP10-043": [
        {
            "timing": "on_play",
            "summary": "May rest own Dressrosa Leader or Stage: up to 1 [Monkey.D.Luffy] gains Banish this turn",
            "ops": [
                {
                    "op": "rest_character",
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "as_cost": True,
                    "count": 1,
                    "trait_contains": "Dressrosa",
                    "include_leader": True,
                    "summary": "Rest own Dressrosa Leader or Stage (not Character)",
                },
                {
                    "op": "grant_keyword",
                    "keyword": "banish",
                    "target_kind": "own_character",
                    "optional": True,
                    "name_contains": "Monkey.D.Luffy|蒙其・D・魯夫|蒙其·D·鲁夫",
                    "duration": "turn",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "OP10-047": [
        {
            "timing": "when_attacking",
            "summary": "May return 1 own Revolutionary Army cost≥3 to hand: this +3000 this turn",
            "ops": [
                {
                    "op": "return_to_hand",
                    "target_kind": "own_character",
                    "optional": True,
                    "as_cost": True,
                    "cost_gte": 3,
                    "trait_contains": "Revolutionary Army",
                    "count": 1,
                },
                {"op": "buff_self", "amount": 3000},
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP10-058": [
        {
            "timing": "on_play",
            "summary": "If field has Character cost≥8: draw 1; reveal up to 2 Dressrosa cost≤7 except Rebecca; play 1, other cost≤4 rested",
            "ops": [
                {"op": "draw", "count": 1},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                    "trait_contains": "Dressrosa",
                    "cost_lte": 7,
                    "exclude_name": "Rebecca|蕾貝卡|蕾贝卡",
                    "summary": "Play 1 revealed Dressrosa cost≤7 except Rebecca",
                },
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                    "trait_contains": "Dressrosa",
                    "cost_lte": 4,
                    "exclude_name": "Rebecca|蕾貝卡|蕾贝卡",
                    "as_rested": True,
                    "summary": "If other revealed is cost≤4, play rested",
                },
            ],
            "status": "compiled",
            "confidence": 0.85,
            "require_field_char_cost_gte": 8,
        }
    ],
    "OP10-092": [
        {
            "timing": "activate_main",
            "summary": "May place 2 Thriller Bark Pirates from trash bottom: up to 1 own Character other than Perona +2000",
            "ops": [
                {
                    "op": "trash_to_bottom",
                    "count": 2,
                    "optional": True,
                    "as_cost": True,
                    "trait_contains": "Thriller Bark Pirates",
                    "order_any": True,
                },
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "own_character",
                    "optional": True,
                    "exclude_name": "Perona|培羅娜|培罗娜",
                    "duration": "turn",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
        }
    ],
    "OP10-098": [
        {
            "timing": "main_start",
            "summary": "If your Characters ≤ opp−2: KO up to 1 base cost≤6 and up to 1 base cost≤4",
            "ops": [
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "base_cost_lte": 6,
                    "count": 1,
                },
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "base_cost_lte": 4,
                    "count": 1,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_chars_deficit_gte": 2,
        },
        {
            "timing": "trigger",
            "summary": "Negate up to 1 opp Leader and up to 1 opp Character",
            "ops": [
                {
                    "op": "negate_effects",
                    "count": 1,
                    "optional": True,
                    "target_kind": "leader",
                    "include_leader": True,
                    "include_characters": False,
                },
                {
                    "op": "negate_effects",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "include_leader": False,
                    "include_characters": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "OP10-107": [
        {
            "timing": "on_play",
            "summary": "May add 1 Life top/bottom to hand: add up to 1 hand Supernovas cost-5 face-up to Life top",
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
                    "card_type": "character",
                    "trait_contains": "Supernovas",
                    "cost_eq": 5,
                    "face": "up",
                    "position": "top",
                    "summary": "Add Supernovas cost-5 from hand face-up to Life top",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP10-112": [
        {
            "timing": "on_play",
            "summary": "May rest this: trash up to 1 card from top of opponent Life",
            "ops": [
                {"op": "rest_character", "target_kind": "self", "optional": True, "as_cost": True, "count": 1},
                {
                    "op": "trash_life",
                    "count": 1,
                    "optional": True,
                    "owner": "opponent",
                    "position": "top",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "end_of_your_turn",
            "summary": "If opponent Life≤2: draw 1 and trash 1 hand",
            "ops": [
                {"op": "draw", "count": 1},
                {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_opp_life_lte": 2,
        },
    ],
    "OP10-119": [
        {
            "timing": "on_play",
            "summary": "Reveal up to 1 Supernovas from hand face-down to Life top; attach up to 1 rested DON!! to Supernovas Leader",
            "ops": [
                {
                    "op": "hand_to_life",
                    "count": 1,
                    "optional": True,
                    "card_type": "character",
                    "trait_contains": "Supernovas",
                    "face": "down",
                    "position": "top",
                },
                {
                    "op": "attach_don",
                    "count": 1,
                    "as_rested": True,
                    "target_kind": "leader",
                    "optional": True,
                    "summary": "Attach rested DON!! to own Supernovas Leader",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
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
    PARALLEL_BASES = set(bases)

    targets: list[str] = []
    for cid in list(cards.keys()) + list(idx.keys()):
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
        abilities = REBUILDS[base]
        out = _rebuild(cid, [dict(a) for a in abilities])
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
