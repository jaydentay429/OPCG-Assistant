#!/usr/bin/env python3
"""Deterministic semantic fixes v43: OP15/OP16/P/ST10 critical cluster.

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

OUT_IDS = ROOT / "meta" / "logs" / "ops_v43_fixed_ids.txt"


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
    "OP13-002": [
        {
            "timing": "on_opponent_attack",
            "summary": "Once: may trash 1: opp Leader/Character −2000 this battle",
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
                    "amount": -2000,
                    "target_kind": "opponent_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
        },
        {
            "timing": "on_life_damage",
            "summary": "DON!!×1 once: when you take damage, draw 1",
            "ops": [{"op": "draw", "count": 1}],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
            "require_don_attached_gte": 1,
            "on_life_damage": True,
        },
        {
            "timing": "on_ko",
            "summary": "DON!!×1 once: when own Character base power≥6000 is KO'd, draw 1",
            "ops": [{"op": "draw", "count": 1}],
            "status": "compiled",
            "confidence": 0.85,
            "once": True,
            "require_don_attached_gte": 1,
            "require_own_char_power_gte": 6000,
        },
    ],
    "OP15-009": _shield_both_turns(
        {
            "summary": "Own Character base≤7000 leaving by opp effect: may Leader −2000 this turn instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "own_character",
                    "base_power_lte": 7000,
                    "cost": "leader_debuff",
                    "optional": True,
                    "summary": "Instead: Leader −2000 this turn",
                },
                {
                    "op": "buff",
                    "amount": -2000,
                    "target_kind": "leader",
                    "optional": True,
                    "duration": "turn",
                },
            ],
            "status": "compiled",
            "confidence": 0.85,
            "once": True,
        }
    ),
    "OP15-014": [
        {
            "timing": "your_turn",
            "summary": "When this would be KO'd: may trash 1 Event from hand instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "ko",
                    "target": "self",
                    "cost": "trash_hand",
                    "optional": True,
                    "card_type": "event",
                    "summary": "Trash Event instead of KO",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
        },
        {
            "timing": "opponent_turn",
            "summary": "When this would be KO'd: may trash 1 Event from hand instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "ko",
                    "target": "self",
                    "cost": "trash_hand",
                    "optional": True,
                    "card_type": "event",
                    "summary": "Trash Event instead of KO",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
        },
        {
            "timing": "on_play",
            "summary": "Play up to 1 hand Event base cost≤3 Dressrosa",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "event",
                    "optional": True,
                    "cost_lte": 3,
                    "trait_contains": "Dressrosa|多雷斯羅薩",
                    "from_zone": "hand",
                    "summary": "Activate/play Dressrosa Event cost≤3",
                }
            ],
            "status": "compiled",
            "confidence": 0.85,
        },
    ],
    "OP15-065": [
        {
            "timing": "on_play",
            "summary": "Reveal deck top 1; if cost≤2, gain up to 1 rested DON!!",
            "ops": [
                {"op": "look_deck", "count": 1, "position": "top", "optional": False},
                {
                    "op": "gain_don",
                    "count": 1,
                    "as_rested": True,
                    "optional": True,
                    "if_revealed_cost_lte": 2,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "OP15-080": _shield_both_turns(
        {
            "summary": "If own Moria power≥10000 and no other Oars: this +7000",
            "ops": [{"op": "buff_self", "amount": 7000}],
            "status": "compiled",
            "confidence": 0.9,
            "require_own_name_contains": "Gecko Moria|月光・摩利亞|摩利亞",
            "require_own_char_power_gte": 10000,
            "require_no_other_name": "Oars|歐斯",
        }
    )
    + [
        {
            "timing": "on_ko",
            "summary": "May trash_to_bottom 3: play this from trash",
            "ops": [
                {
                    "op": "trash_to_bottom",
                    "count": 3,
                    "optional": True,
                    "owner": "self",
                    "card_type": "any",
                    "order_any": True,
                    "as_cost": True,
                },
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": False,
                    "from_zone": "trash",
                    "self_card": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "OP15-103": [
        {
            "timing": "trigger",
            "summary": "Draw 1; if Life≤2, play this card",
            "ops": [
                {"op": "draw", "count": 1},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                    "self_card": True,
                    "summary": "If Life≤2: play this",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_life_lte": 2,
        }
    ],
    "OP16-019": [
        {
            "timing": "main_start",
            "summary": "Play up to 2 Whitebeard Pirates Characters with power 8000",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 2,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                    "power_eq": 8000,
                    "trait_includes": "Whitebeard Pirates|白鬍子海賊團|白胡子海贼团",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "Leader +1000 this turn",
            "ops": [
                {
                    "op": "buff",
                    "amount": 1000,
                    "target_kind": "leader",
                    "optional": False,
                    "duration": "turn",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP16-030": [
        {
            "timing": "on_play",
            "summary": "Up to 1 opp rested Character skips untap next refresh",
            "ops": [
                {
                    "op": "skip_untap",
                    "count": 1,
                    "target_kind": "opponent_character_rested",
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "end_of_your_turn",
            "summary": "Set all own green Characters cost≤5 as active",
            "ops": [
                {
                    "op": "set_character_active",
                    "count": 5,
                    "target_kind": "own_character",
                    "optional": False,
                    "all": True,
                    "cost_lte": 5,
                    "color": "green",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "OP16-057": [
        {
            "timing": "counter_event",
            "summary": "If ≥2 Prisoner of Impel Down: buff Leader or Character +4000 this battle",
            "ops": [
                {
                    "op": "buff",
                    "amount": 4000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "count": 1,
                    "duration": "battle",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_own_name_contains": "Prisoner of Impel Down|推進城的囚犯",
            "require_own_name_gte": 2,
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
    "OP16-058": [
        {
            "timing": "main_start",
            "summary": "If DON!! field=10: all Prisoner of Impel Down base power 7000 this turn",
            "ops": [
                {
                    "op": "set_base_power",
                    "amount": 7000,
                    "target_kind": "own_character",
                    "name_contains": "Prisoner of Impel Down|推進城的囚犯",
                    "all": True,
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_field_gte": 10,
        },
        {
            "timing": "counter_event",
            "summary": "Up to 1 own Buggy +4000 this battle",
            "ops": [
                {
                    "op": "buff",
                    "amount": 4000,
                    "target_kind": "own_character",
                    "optional": True,
                    "count": 1,
                    "name_contains": "Buggy|巴其",
                    "duration": "battle",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP16-060": [
        {
            "timing": "activate_main",
            "summary": "Return 8 active DON!!: play up to 3 different-name Admiral Characters",
            "ops": [
                {
                    "op": "return_don",
                    "count": 8,
                    "owner": "self",
                    "as_cost": True,
                },
                {
                    "op": "play_from_hand",
                    "count": 3,
                    "card_type": "character",
                    "optional": True,
                    "trait_contains": "Admiral|上將|上将",
                    "from_zone": "hand",
                    "different_names": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "cost_don": 0,
            "rest_self": False,
            "once": False,
        }
    ],
    "OP16-083": [
        {
            "timing": "on_play",
            "summary": "May trash hand Character cost≥8: draw 2",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                    "card_type": "character",
                    "cost_gte": 8,
                },
                {"op": "draw", "count": 2},
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
    "OP16-092": [
        {
            "timing": "on_play",
            "summary": "May trash hand Character cost≥8: draw 2",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                    "card_type": "character",
                    "cost_gte": 8,
                },
                {"op": "draw", "count": 2},
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP16-094": [
        {
            "timing": "on_ko",
            "summary": "Opponent trashes 2 from their hand",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 2,
                    "optional": False,
                    "owner": "opponent",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "activate_main",
            "summary": "Once: attach up to 1 rested DON!! to own Land of Wano Leader/Character",
            "ops": [
                {
                    "op": "attach_don",
                    "count": 1,
                    "as_rested": True,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "trait_contains": "Land of Wano|和之國|和之国",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
            "cost_don": 0,
            "rest_self": False,
        },
    ],
    "OP16-095": [
        {
            "timing": "on_play",
            "summary": "Up to 1 own black Land of Wano Character gains blockerless this turn",
            "ops": [
                {
                    "op": "grant_keyword",
                    "keyword": "blockerless",
                    "target_kind": "own_character",
                    "duration": "turn",
                    "optional": True,
                    "count": 1,
                    "trait_contains": "Land of Wano|和之國|和之国",
                    "color": "black",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "OP16-100": [
        {
            "timing": "main_start",
            "summary": "May rest 2 DON!!: if opp Character KO'd this turn, set Leader Yamato active",
            "ops": [
                {"op": "rest_don", "count": 2, "owner": "self", "as_cost": True},
                {
                    "op": "set_character_active",
                    "count": 1,
                    "target_kind": "leader",
                    "optional": True,
                    "name_contains": "Yamato|大和",
                    "summary": "If opp Character KO'd this turn: set Yamato active",
                },
            ],
            "status": "compiled",
            "confidence": 0.85,
            "cost_don": 2,
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
    "OP16-106": [
        {
            "timing": "on_ko",
            "summary": "If Blackbeard Leader: draw 1; set up to 1 Leader/Character base power 7000",
            "ops": [
                {"op": "draw", "count": 1},
                {
                    "op": "set_base_power",
                    "amount": 7000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "count": 1,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_trait": "Blackbeard Pirates|黑鬍子海賊團|黑胡子海贼团",
        },
        {
            "timing": "trigger",
            "summary": "Activate this card's On K.O. effect",
            "ops": [
                {
                    "op": "activate_timing",
                    "timing": "on_ko",
                    "summary": "Activate On K.O. effect",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "P-024": [
        {
            "timing": "main_start",
            "summary": "Leader +1000 per own Character this turn",
            "ops": [
                {
                    "op": "buff",
                    "amount": 1000,
                    "target_kind": "leader",
                    "optional": False,
                    "duration": "turn",
                    "per_own_chars": 1,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "Up to 1 Leader or Character +1000 this turn",
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
        },
    ],
    "P-025": _shield_both_turns(
        {
            "summary": "DON!!×1: cannot be KO'd in battle vs non-Special attribute",
            "ops": [
                {
                    "op": "cannot_be_ko",
                    "target_kind": "self",
                    "optional": False,
                    "summary": "Cannot be KO'd by non-Special attribute Characters in battle",
                }
            ],
            "status": "compiled",
            "confidence": 0.85,
            "require_don_attached_gte": 1,
        }
    ),
    "P-033": [
        {
            "timing": "activate_main",
            "summary": "May place this at deck bottom: draw 1",
            "ops": [
                {
                    "op": "return_to_bottom",
                    "count": 1,
                    "target_kind": "self",
                    "optional": True,
                    "as_cost": True,
                },
                {"op": "draw", "count": 1},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "cost_don": 0,
            "rest_self": False,
            "once": False,
        }
    ],
    "P-038": [
        {
            "timing": "on_play",
            "summary": "May rest own Leader: KO up to 1 opp cost≤1",
            "ops": [
                {
                    "op": "rest_character",
                    "target_kind": "leader",
                    "optional": True,
                    "as_cost": True,
                    "count": 1,
                    "include_leader": True,
                },
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "cost_lte": 1,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "P-060": [
        {
            "timing": "main_start",
            "summary": "May rest 1 own Uta: rest up to 2 opp DON!!",
            "ops": [
                {
                    "op": "rest_character",
                    "target_kind": "own_character",
                    "optional": True,
                    "as_cost": True,
                    "count": 1,
                    "name_contains": "Uta|美音",
                },
                {
                    "op": "rest_don",
                    "count": 2,
                    "owner": "opponent",
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "P-065": [
        {
            "timing": "when_attacking",
            "summary": "If opp has cost-0 Character: this +2000 until next your turn start",
            "ops": [{"op": "buff_self", "amount": 2000}],
            "status": "compiled",
            "confidence": 0.95,
            "require_opp_char_cost_eq": 0,
        }
    ],
    "P-071": [
        {
            "timing": "on_ko",
            "summary": "May return this to hand",
            "ops": [
                {
                    "op": "return_to_hand",
                    "target_kind": "self",
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "P-075": [
        {
            "timing": "on_play",
            "summary": "Attach up to 1 rested DON!! to Leader or Character",
            "ops": [
                {
                    "op": "attach_don",
                    "count": 1,
                    "as_rested": True,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "when_attacking",
            "summary": "If own Character cost≥8: draw 1 trash 1",
            "ops": [
                {"op": "draw", "count": 1},
                {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_chars_base_cost_gte": 8,
            "require_chars_base_cost_count_gte": 1,
        },
    ],
    "P-115": [
        {
            "timing": "on_play",
            "summary": "Attach up to 1 rested DON!! to Leader or Character",
            "ops": [
                {
                    "op": "attach_don",
                    "count": 1,
                    "as_rested": True,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "Play up to 1 yellow Character power≤5000 with Trigger",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                    "power_lte": 5000,
                    "color": "yellow",
                    "require_trigger": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "ST10-002": [
        {
            "timing": "activate_main",
            "summary": "Once: if DON!! field is 0 or ≥8, gain up to 1 active DON!!",
            "ops": [{"op": "gain_don", "count": 1, "optional": True}],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
            "cost_don": 0,
            "rest_self": False,
            "require_don_field_0_or_gte": 8,
        }
    ],
    "ST10-004": [
        {
            "timing": "on_play",
            "summary": "If opp Character power≥5000: gain Rush this turn",
            "ops": [
                {
                    "op": "grant_keyword",
                    "keyword": "rush",
                    "target_kind": "self",
                    "duration": "turn",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_opp_char_power_gte": 5000,
        }
    ],
    "ST10-008": [
        {
            "timing": "on_play",
            "summary": "If DON!! field ≤3: gain up to 2 rested DON!!",
            "ops": [
                {
                    "op": "gain_don",
                    "count": 2,
                    "as_rested": True,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_field_lte": 3,
        }
    ],
    "ST10-010": [
        {
            "timing": "on_play",
            "summary": "DON!! −1: if opp hand≥7, trash 2 from opp hand",
            "ops": [
                {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                {
                    "op": "trash_hand",
                    "count": 2,
                    "optional": False,
                    "owner": "opponent",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_opp_hand_gte": 7,
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
    "ST10-013": [
        {
            "timing": "on_play",
            "summary": "DON!! −1: up to 1 Leader +1000 until next your turn start",
            "ops": [
                {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                {
                    "op": "buff",
                    "amount": 1000,
                    "target_kind": "leader",
                    "optional": True,
                    "duration": "next_turn",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "when_attacking",
            "summary": "DON!! −1: up to 1 Leader +1000 until next your turn start",
            "ops": [
                {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                {
                    "op": "buff",
                    "amount": 1000,
                    "target_kind": "leader",
                    "optional": True,
                    "duration": "next_turn",
                },
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
