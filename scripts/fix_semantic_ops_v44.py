#!/usr/bin/env python3
"""Deterministic semantic fixes v44: ST13/ST22/ST25 + P/PRB/ST life & reveal cluster.

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

OUT_IDS = ROOT / "meta" / "logs" / "ops_v44_fixed_ids.txt"


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


def _life_play_activate(name: str) -> list[dict[str, Any]]:
    return [
        {
            "timing": "activate_main",
            "summary": f"Trash self: reveal Life top; if cost5 [{name}], may play it; then Leader +2000 until opp turn end",
            "ops": [
                {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_eq": 5,
                    "name_contains": name,
                    "from_zone": "life",
                },
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "leader",
                    "optional": True,
                    "duration": "until_opp_turn_end",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ]


def _reveal_trait_draw(trait: str, draw: int = 2, trash_after: bool = False) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = [
        {"op": "look_deck", "count": 1, "position": "top", "optional": False},
        {"op": "draw", "count": draw, "if_revealed_trait_includes": trait},
    ]
    if trash_after:
        ops.append({"op": "trash_hand", "count": 1, "optional": False, "owner": "self"})
    return [
        {
            "timing": "on_play",
            "summary": f"Reveal deck top: if trait includes {trait}, draw {draw}"
            + (" then trash 1" if trash_after else ""),
            "ops": ops,
            "status": "compiled",
            "confidence": 0.9,
        }
    ]


REBUILDS: dict[str, list[dict[str, Any]]] = {
    "OP01-062": [
        {
            "timing": "on_event",
            "summary": "DON!!×1 once/turn: when activate Event, if hand≤4 and not drawn via this effect this turn, draw 1",
            "ops": [{"op": "draw", "count": 1}],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
            "require_don_attached_gte": 1,
            "require_hand_lte": 4,
        }
    ],
    "OP12-081": [
        {
            "timing": "when_attacking",
            "summary": "When this Leader attacks opp Leader: if ≥2 own Characters cost≥8, draw 1",
            "ops": [{"op": "draw", "count": 1}],
            "status": "compiled",
            "confidence": 0.9,
            "require_chars_base_cost_gte": 8,
            "require_chars_base_cost_count_gte": 2,
        },
        {
            "timing": "on_opponent_play",
            "summary": "Once: when opp plays base-cost≥8 Character or plays Character by Character effect: opp adds top Life to hand",
            "ops": [
                {
                    "op": "life_to_hand",
                    "count": 1,
                    "position": "top",
                    "optional": True,
                    "owner": "opponent",
                    "hand_owner": "life_owner",
                }
            ],
            "status": "compiled",
            "confidence": 0.85,
            "once": True,
        },
    ],
    "OP13-079": [
        {
            "timing": "on_game_start",
            "summary": "Game start: play up to 1 {Mary Geoise} Stage from deck",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "stage",
                    "optional": True,
                    "trait_contains": "Mary Geoise",
                    "from_zone": "deck",
                }
            ],
            "status": "compiled",
            "confidence": 0.85,
        },
        {
            "timing": "activate_main",
            "summary": "Once: trash 1 Celestial Dragon Character or 1 hand: draw 1",
            "ops": [
                {
                    "op": "choose_one",
                    "options": [
                        {
                            "id": "trash_celestial",
                            "label": "Trash Celestial Dragon Character",
                            "ops": [
                                {
                                    "op": "trash",
                                    "target_kind": "own_character",
                                    "optional": True,
                                    "as_cost": True,
                                    "trait_contains": "Celestial Dragons",
                                }
                            ],
                        },
                        {
                            "id": "trash_hand",
                            "label": "Trash 1 hand",
                            "ops": [
                                {
                                    "op": "trash_hand",
                                    "count": 1,
                                    "optional": True,
                                    "as_cost": True,
                                    "owner": "self",
                                }
                            ],
                        },
                    ],
                },
                {"op": "draw", "count": 1},
            ],
            "status": "compiled",
            "confidence": 0.85,
            "once": True,
        },
    ],
    "P-046": [
        {
            "timing": "on_play",
            "summary": "May place all hand to bottom in any order; if you do, draw equal",
            "ops": [
                {
                    "op": "return_to_bottom",
                    "all": True,
                    "from_zone": "hand",
                    "optional": True,
                    "then_draw_equal": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "P-058": [
        {
            "timing": "end_of_your_turn",
            "summary": "[Main delayed] If Leader is Uta: set all own {FILM} Characters active at end of turn",
            "ops": [
                {
                    "op": "set_character_active",
                    "all": True,
                    "target_kind": "own_character",
                    "optional": False,
                    "trait_contains": "FILM",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_leader_name": "Uta",
        },
        {
            "timing": "trigger",
            "summary": "Set all own {FILM} Characters active",
            "ops": [
                {
                    "op": "set_character_active",
                    "all": True,
                    "target_kind": "own_character",
                    "optional": False,
                    "trait_contains": "FILM",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "P-059": [
        {
            "timing": "counter_event",
            "summary": "If Leader is Uta: may return any number of Characters to hand; +2000 per returned this battle",
            "ops": [
                {
                    "op": "return_to_hand",
                    "target_kind": "own_character",
                    "optional": True,
                    "all": True,
                },
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                    "per_returned_chars": 1,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_leader_name": "Uta",
        }
    ],
    "P-084": [
        {
            "timing": "on_play",
            "summary": "Play up to 1 hand Cross Guild Character cost≤6",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 6,
                    "trait_contains": "Cross Guild",
                    "from_zone": "hand",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        *_shield_both_turns(
            {
                "summary": "This Character cannot attack",
                "ops": [{"op": "cannot_attack", "target_kind": "self"}],
                "status": "compiled",
                "confidence": 0.95,
            }
        ),
        *_shield_both_turns(
            {
                "summary": "If Leader is Buggy: all Characters with cost 3 or 4 cannot attack",
                "ops": [
                    {
                        "op": "cannot_attack",
                        "target_kind": "own_character",
                        "all": True,
                        "cost_in": [3, 4],
                    }
                ],
                "status": "compiled",
                "confidence": 0.9,
                "require_leader_name": "Buggy",
            }
        ),
    ],
    "P-098": [
        {
            "timing": "on_play",
            "summary": "If you do not have 5 Characters with cost≥5, place this at bottom of deck",
            "ops": [{"op": "return_to_bottom", "target_kind": "self", "optional": False}],
            "status": "compiled",
            "confidence": 0.95,
            "require_chars_base_cost_gte": 5,
            "require_chars_base_cost_count_lte": 4,
        }
    ],
    "PRB02-003": [
        {
            "timing": "on_play",
            "summary": "May trash 1 hand Character power≥6000: draw 2",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                    "card_type": "character",
                    "power_gte": 6000,
                },
                {"op": "draw", "count": 2},
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "PRB02-016": [
        {
            "timing": "activate_main",
            "summary": "Rest self + life_to_hand top/bottom: up to 1 Leader/Character +3000 this turn",
            "ops": [
                {"op": "rest_character", "target_kind": "self", "optional": False, "as_cost": True},
                {
                    "op": "life_to_hand",
                    "count": 1,
                    "position": "top_or_bottom",
                    "optional": False,
                    "as_cost": True,
                    "owner": "self",
                },
                {
                    "op": "buff",
                    "amount": 3000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "turn",
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
    "ST02-014": [
        {
            "timing": "your_turn",
            "summary": "DON!!×1: if this is rested, own Supernovas|Navy Leaders and Characters +1000",
            "ops": [
                {
                    "op": "buff_all_own",
                    "amount": 1000,
                    "include_leader": True,
                    "trait_any": ["Supernovas", "Navy"],
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_don_attached_gte": 1,
        }
    ],
    "ST07-003": [
        {
            "timing": "on_play",
            "summary": "Look up to 1 Life top (self or opp) and place top or bottom",
            "ops": [
                {
                    "op": "reorder_life",
                    "owner": "self_or_opponent",
                    "summary": "Look up to 1 top Life; place top or bottom",
                }
            ],
            "status": "compiled",
            "confidence": 0.85,
        },
        {
            "timing": "on_play",
            "summary": "If own Life < opp Life: gain Rush this turn",
            "ops": [
                {
                    "op": "grant_keyword",
                    "target_kind": "self",
                    "keyword": "Rush",
                    "duration": "turn",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_life_less_than_opponent": True,
        },
    ],
    "ST08-005": [
        {
            "timing": "on_play",
            "summary": "May trash 1 hand: KO all Characters cost≤1",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {
                    "op": "ko",
                    "target_kind": "any_character",
                    "all": True,
                    "cost_lte": 1,
                    "optional": False,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "ST08-013": [
        {
            "timing": "end_of_battle",
            "summary": "DON!!×1: end of battle vs Character — may KO battle opponent Character; if you do, KO self",
            "ops": [
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "summary": "KO the Character this battled",
                },
                {"op": "ko", "target_kind": "self", "optional": False},
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_don_attached_gte": 1,
        }
    ],
    "ST09-010": [
        {
            "timing": "on_ko",
            "summary": "Once: if this would be K.O.'d, may trash 1 Life top/bottom instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "ko",
                    "target": "self",
                    "cost": "trash_life",
                    "optional": True,
                    "summary": "Trash Life top/bottom instead of KO",
                },
                {
                    "op": "trash_life",
                    "count": 1,
                    "position": "top_or_bottom",
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
        }
    ],
    "ST09-014": [
        {
            "timing": "counter_event",
            "summary": "If Life≤2: up to 1 opp Leader/Character −3000 this turn",
            "ops": [
                {
                    "op": "buff",
                    "amount": -3000,
                    "target_kind": "opponent_leader_or_character",
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
            "summary": "May trash 2 hand: add up to 1 deck top to Life top",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 2,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {
                    "op": "search_deck",
                    "top_n": 1,
                    "max_add": 1,
                    "destination": "life",
                    "face": "down",
                    "order_bottom": False,
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "ST12-010": [
        {
            "timing": "on_play",
            "summary": "Reveal deck top: play up to 1 cost-2 Character; place rest top or bottom",
            "ops": [
                {
                    "op": "search_deck",
                    "top_n": 1,
                    "max_add": 1,
                    "cost_eq": 2,
                    "destination": "play",
                    "card_type": "character",
                    "order_bottom": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
        {
            "timing": "when_attacking",
            "summary": "Once: if hand≤6, draw 1",
            "ops": [{"op": "draw", "count": 1}],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
            "require_hand_lte": 6,
        },
    ],
    "ST12-017": [
        {
            "timing": "counter_event",
            "summary": "+2000 this battle; reveal deck top play up to 1 cost-2 Character; rest top/bottom",
            "ops": [
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                },
                {
                    "op": "search_deck",
                    "top_n": 1,
                    "max_add": 1,
                    "cost_eq": 2,
                    "destination": "play",
                    "card_type": "character",
                    "order_bottom": False,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "ST13-002": [
        {
            "timing": "activate_main",
            "summary": "DON!!×2 once: look 5; add up to 1 cost-5 Character face-up to Life top; rest bottom any order",
            "ops": [
                {
                    "op": "search_deck",
                    "top_n": 5,
                    "max_add": 1,
                    "cost_eq": 5,
                    "destination": "life",
                    "face": "up",
                    "order_bottom": True,
                    "card_type": "character",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
            "require_don_attached_gte": 2,
        },
        {
            "timing": "end_of_your_turn",
            "summary": "Trash all own face-up Life cards",
            "ops": [
                {
                    "op": "trash_life",
                    "position": "all_face_up",
                    "all": True,
                    "face_up": True,
                    "optional": False,
                    "owner": "self",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "ST13-005": [
        {
            "timing": "on_play",
            "summary": "May trash Life top/bottom: reveal up to 1 hand cost-5 Character and add face-down to Life top",
            "ops": [
                {
                    "op": "trash_life",
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
                    "face": "down",
                    "position": "top",
                    "card_type": "character",
                    "cost_eq": 5,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "ST13-007": _life_play_activate("Sabo"),
    "ST13-010": _life_play_activate("Portgas.D.Ace"),
    "ST13-014": _life_play_activate("Monkey.D.Luffy"),
    "ST13-015": [
        {
            "timing": "activate_main",
            "summary": "Once: this +2000 until next your turn start; if Life≥1 draw 1 then trash Life top",
            "ops": [
                {"op": "buff_self", "amount": 2000, "duration": "next_turn"},
                {"op": "draw", "count": 1},
                {
                    "op": "trash_life",
                    "count": 1,
                    "position": "top",
                    "optional": False,
                    "owner": "self",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
        }
    ],
    "ST13-016": [
        {
            "timing": "on_play",
            "summary": "Look all Life; place 1 on deck top; reorder remaining Life",
            "ops": [
                {
                    "op": "reorder_life",
                    "owner": "self",
                    "to_deck_top": True,
                    "summary": "Look all Life; 1 to deck top; reorder rest",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "ST14-009": [
        {
            "timing": "opponent_turn",
            "summary": "DON!!×1: if own Character cost≥6 on field, cannot be KO'd by opp effects and +2000",
            "ops": [
                {"op": "buff_self", "amount": 2000},
                {"op": "cannot_be_ko", "target_kind": "self", "optional": False},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_attached_gte": 1,
            "require_field_char_cost_gte": 6,
        }
    ],
    "ST14-012": [
        {
            "timing": "your_turn",
            "summary": "If own Character cost≥10 on field, gain Rush",
            "ops": [
                {
                    "op": "grant_keyword",
                    "target_kind": "self",
                    "keyword": "Rush",
                    "duration": "permanent",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_field_char_cost_gte": 10,
        }
    ],
    "ST17-001": [
        {
            "timing": "on_play",
            "summary": "Reveal deck top: if {The Seven Warlords of the Sea}, draw 2 then hand_to_deck top 1",
            "ops": [
                {"op": "look_deck", "count": 1, "position": "top", "optional": False},
                {
                    "op": "draw",
                    "count": 2,
                    "if_revealed_trait_includes": "The Seven Warlords of the Sea",
                },
                {
                    "op": "hand_to_deck",
                    "count": 1,
                    "position": "top",
                    "optional": False,
                    "owner": "self",
                    "if_revealed_trait_includes": "The Seven Warlords of the Sea",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "ST17-005": [
        {
            "timing": "activate_main",
            "summary": "Once: hand_to_deck top 1: attach up to 2 rested DON!! to Leader or Character",
            "ops": [
                {
                    "op": "hand_to_deck",
                    "count": 1,
                    "position": "top",
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
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
            "confidence": 0.95,
            "once": True,
        }
    ],
    "ST20-004": [
        {
            "timing": "on_play",
            "summary": "May life_to_hand top: set active up to 1 own Big Mom Pirates cost≤3",
            "ops": [
                {
                    "op": "life_to_hand",
                    "count": 1,
                    "position": "top",
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {
                    "op": "set_character_active",
                    "count": 1,
                    "target_kind": "own_character",
                    "optional": True,
                    "cost_lte": 3,
                    "trait_contains": "Big Mom Pirates",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "Rest up to 1 opp Character cost≤3",
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
    "ST21-011": [
        {
            "timing": "opponent_turn",
            "summary": "DON!!×2: all own Straw Hat Crew base power≤4000 Characters +1000",
            "ops": [
                {
                    "op": "buff_all_own",
                    "amount": 1000,
                    "include_leader": False,
                    "trait_contains": "Straw Hat Crew",
                    "base_power_lte": 4000,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_attached_gte": 2,
        }
    ],
    "ST22-003": _reveal_trait_draw("Whitebeard Pirates", 2, False)
    + [
        {
            "timing": "your_turn",
            "summary": "Double Attack",
            "ops": [
                {
                    "op": "grant_keyword",
                    "target_kind": "self",
                    "keyword": "double_attack",
                    "duration": "permanent",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "ST22-006": _reveal_trait_draw("Whitebeard Pirates", 2, True),
    "ST22-015": [
        {
            "timing": "main_start",
            "summary": "If Leader trait includes Whitebeard Pirates: play up to 1 Edward.Newgate from hand; may life_to_hand top/bottom; if you do Leader +2000",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "name_contains": "Edward.Newgate",
                    "from_zone": "hand",
                },
                {
                    "op": "life_to_hand",
                    "count": 1,
                    "position": "top_or_bottom",
                    "optional": True,
                    "owner": "self",
                },
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "leader",
                    "optional": True,
                    "duration": "turn",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_leader_trait": "Whitebeard Pirates",
        }
    ],
    "ST22-016": [
        {
            "timing": "counter_event",
            "summary": "Reveal deck top: if Whitebeard Pirates, up to 1 own Leader/Character +4000 this battle",
            "ops": [
                {"op": "look_deck", "count": 1, "position": "top", "optional": False},
                {
                    "op": "buff",
                    "amount": 4000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                    "if_revealed_trait_includes": "Whitebeard Pirates",
                },
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
    "ST24-001": [
        {
            "timing": "on_play",
            "summary": "If rested cards≥6: draw 1 then trash 1 hand",
            "ops": [
                {"op": "draw", "count": 1},
                {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_rested_cards_gte": 6,
        }
    ],
    "ST25-001": [
        *_shield_both_turns(
            {
                "summary": "If ≥2 own base-cost≥5 Characters: this +1 cost",
                "ops": [{"op": "grant_cost", "amount": 1, "target_kind": "self"}],
                "status": "compiled",
                "confidence": 0.95,
                "require_chars_base_cost_gte": 5,
                "require_chars_base_cost_count_gte": 2,
            }
        ),
        {
            "timing": "on_play",
            "summary": "If Leader is Buggy: draw 3 then trash 2 hand",
            "ops": [
                {"op": "draw", "count": 3},
                {"op": "trash_hand", "count": 2, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_name": "Buggy",
        },
    ],
    "ST25-002": [
        *_shield_both_turns(
            {
                "summary": "If ≥2 own base-cost≥5 Characters: gain Blocker and +1 cost",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "target_kind": "self",
                        "keyword": "Blocker",
                        "duration": "permanent",
                    },
                    {"op": "grant_cost", "amount": 1, "target_kind": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_chars_base_cost_gte": 5,
                "require_chars_base_cost_count_gte": 2,
            }
        ),
        {
            "timing": "opponent_turn",
            "summary": "This Character +5000",
            "ops": [{"op": "buff_self", "amount": 5000}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "ST25-003": [
        {
            "timing": "on_play",
            "summary": "Draw 2, trash 1, play up to 1 Cross Guild cost≤4 from hand",
            "ops": [
                {"op": "draw", "count": 2},
                {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 4,
                    "trait_contains": "Cross Guild",
                    "from_zone": "hand",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        *_shield_both_turns(
            {
                "summary": "Once: when own Cross Guild would leave by opp effect, may trash 1 hand instead",
                "ops": [
                    {
                        "op": "replace_leave",
                        "trigger": "opp_remove",
                        "target": "own_character",
                        "trait_contains": "Cross Guild",
                        "cost": "trash_hand",
                        "optional": True,
                    }
                ],
                "status": "compiled",
                "confidence": 0.85,
                "once": True,
            }
        ),
    ],
    "ST25-004": [
        {
            "timing": "activate_main",
            "summary": "May trash 1 hand and trash self: if Leader is Buggy, play up to 1 Cross Guild cost≤6 from hand",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 6,
                    "trait_contains": "Cross Guild",
                    "from_zone": "hand",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_name": "Buggy",
        }
    ],
    "ST25-005": [
        *_shield_both_turns(
            {
                "summary": "If ≥2 own base-cost≥5 Characters: gain Blocker and +1 cost",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "target_kind": "self",
                        "keyword": "Blocker",
                        "duration": "permanent",
                    },
                    {"op": "grant_cost", "amount": 1, "target_kind": "self"},
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_chars_base_cost_gte": 5,
                "require_chars_base_cost_count_gte": 2,
            }
        ),
        {
            "timing": "on_ko",
            "summary": "If Leader is Buggy and hand≤3: draw 1",
            "ops": [{"op": "draw", "count": 1}],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_name": "Buggy",
            "require_hand_lte": 3,
        },
    ],
    "ST26-001": [
        {
            "timing": "hand_cost",
            "summary": "If own San-Gorou|Sanji base power≥7000 on field: this hand cost −5",
            "ops": [{"op": "hand_cost_reduce", "amount": -5}],
            "status": "compiled",
            "confidence": 0.9,
            "require_own_char_power_gte": 7000,
            "require_own_name_contains": "San-Gorou|Sanji",
        },
        {
            "timing": "on_play",
            "summary": "Return all own San-Gorou and Sanji Characters to hand",
            "ops": [
                {
                    "op": "return_to_hand",
                    "target_kind": "own_character",
                    "all": True,
                    "name_contains": "San-Gorou|Sanji",
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "ST28-002": [
        *_shield_both_turns(
            {
                "summary": "DON!!×2: this gains Blocker",
                "ops": [
                    {
                        "op": "grant_keyword",
                        "target_kind": "self",
                        "keyword": "Blocker",
                        "duration": "permanent",
                    }
                ],
                "status": "compiled",
                "confidence": 0.95,
                "require_don_attached_gte": 2,
            }
        ),
        {
            "timing": "on_play",
            "summary": "Own Land of Wano Leader gains Banish this turn",
            "ops": [
                {
                    "op": "grant_keyword",
                    "target_kind": "leader",
                    "keyword": "Banish",
                    "duration": "turn",
                    "trait_contains": "Land of Wano",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "ST30-003": [
        {
            "timing": "your_turn",
            "summary": "All own Characters with base power 6000 gain +1000",
            "ops": [
                {
                    "op": "buff_all_own",
                    "amount": 1000,
                    "include_leader": False,
                    "base_power_eq": 6000,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "ST30-006": [
        {
            "timing": "on_play",
            "summary": "May trash 1 hand Character power_eq 6000: draw 2",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                    "card_type": "character",
                    "power_eq": 6000,
                },
                {"op": "draw", "count": 2},
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "ST31-004": [
        {
            "timing": "your_turn",
            "summary": "If attached DON!!≥3: gain Rush",
            "ops": [
                {
                    "op": "grant_keyword",
                    "target_kind": "self",
                    "keyword": "Rush",
                    "duration": "permanent",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_attached_gte": 3,
        },
        {
            "timing": "on_play",
            "summary": "Per own Straw Hat Crew card on field: up to 1 opp Character −1000 this turn",
            "ops": [
                {
                    "op": "buff",
                    "amount": -1000,
                    "target_kind": "opponent_character",
                    "optional": True,
                    "duration": "turn",
                    "per_own_chars": 1,
                    "per_own_trait": "Straw Hat Crew",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "ST32-003": [
        {
            "timing": "your_turn",
            "summary": "When this becomes rested: draw 1 then trash 1 hand",
            "ops": [
                {"op": "draw", "count": 1},
                {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.9,
            "on_char_rested_by_own_effect": True,
        },
        {
            "timing": "on_play",
            "summary": "If Leader has Slash: play up to 1 hand cost≤5 with Slash or [Perona]",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 5,
                    "name_contains": "Perona",
                    "attribute": "Slash",
                    "name_or_trait": True,
                    "from_zone": "hand",
                }
            ],
            "status": "compiled",
            "confidence": 0.85,
            "require_leader_attribute": "Slash",
        },
    ],
    "ST32-005": [
        {
            "timing": "on_play",
            "summary": "If Leader has Slash: rest up to 1 opp Character cost≤2",
            "ops": [
                {
                    "op": "rest_opponent_character",
                    "count": 1,
                    "cost_lte": 2,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_attribute": "Slash",
        },
        {
            "timing": "your_turn",
            "summary": "Rush: Character",
            "ops": [
                {
                    "op": "grant_keyword",
                    "target_kind": "self",
                    "keyword": "Rush",
                    "duration": "permanent",
                    "summary": "Rush: Character",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "ST36-002": [
        {
            "timing": "on_play",
            "summary": "If Leader has Kid Pirates: add up to 1 deck top to Life top",
            "ops": [
                {
                    "op": "search_deck",
                    "top_n": 1,
                    "max_add": 1,
                    "destination": "life",
                    "face": "down",
                    "order_bottom": False,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_leader_trait": "Kid Pirates",
        },
        {
            "timing": "trigger",
            "summary": "If opp Life≤3: play this card",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "self_card": True,
                    "from_zone": "hand",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_opp_life_lte": 3,
        },
    ],
    "ST36-003": [
        {
            "timing": "trigger",
            "summary": "Draw 1; own Supernovas Leader base power becomes 7000 this turn",
            "ops": [
                {"op": "draw", "count": 1},
                {
                    "op": "set_base_power",
                    "amount": 7000,
                    "target_kind": "leader",
                    "optional": False,
                    "trait_contains": "Supernovas",
                    "duration": "turn",
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
