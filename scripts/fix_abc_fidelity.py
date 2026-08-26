#!/usr/bin/env python3
"""Force paper-accurate abilities for A/B/C focus cards into overrides."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library
from battle.effect_schema import normalize_card_entry, normalize_ability

FOCUS: dict[str, list[dict]] = {
    "OP14-118": [
        {
            "timing": "counter_event",
            "summary": "If ≤2 Life: up to 1 opponent active Character cannot attack this turn",
            "ops": [
                {
                    "op": "deny_attack",
                    "count": 1,
                    "active_only": True,
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
            "summary": "Play up to 1 Character with 6000 power or less and a Trigger from hand",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "power_lte": 6000,
                    "require_trigger": True,
                    "from_zone": "hand",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "OP14-119": [
        {
            "timing": "your_turn",
            "summary": "When this becomes rested: up to 1 opp Character cost≤9 cannot be rested until opp End Phase",
            "ops": [
                {
                    "op": "deny_rest",
                    "count": 1,
                    "cost_lte": 9,
                    "optional": True,
                    "duration": "until_opp_turn_end",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "trigger_on": "self_rested",
        },
        {
            "timing": "on_opponent_attack",
            "summary": "Once: trash 1 hand: Leader or Character +2000 this battle",
            "ops": [
                {"op": "trash_hand", "count": 1, "optional": True, "as_cost": True},
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "own_character_or_leader",
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
        },
    ],
    "OP05-072": [
        {
            "timing": "on_play",
            "summary": "If ≥8 DON on field: up to 2 opponent Characters −2000 this turn",
            "ops": [
                {"op": "buff", "amount": -2000, "target_kind": "opponent_character", "optional": True},
                {"op": "buff", "amount": -2000, "target_kind": "opponent_character", "optional": True},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_field_gte": 8,
        }
    ],
    "OP08-043": [
        {
            "timing": "on_play",
            "summary": "If Whitebeard Pirates Leader and ≤2 Life: all opp Characters must trash 2 hand to attack",
            "ops": [{"op": "attack_tax", "trash_hand": 2, "all": True, "duration": "until_opp_turn_end"}],
            "status": "compiled",
            "confidence": 0.95,
            "require_life_lte": 2,
            "require_leader_trait": "Whitebeard Pirates",
        }
    ],
    "OP09-033": [
        {
            "timing": "on_play",
            "summary": "If ≥2 rested own Characters: ODYSSEY/Straw Hat Crew cannot be KO by effects",
            "ops": [
                {
                    "op": "cannot_be_ko",
                    "target_kind": "own_character",
                    "all": True,
                    "trait_any": ["ODYSSEY", "Straw Hat Crew"],
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_rested_own_chars_gte": 2,
        }
    ],
    "OP03-091": [
        {
            "timing": "on_play",
            "summary": "Set cost of up to 1 opponent Character with no base effect to 0 this turn",
            "ops": [
                {
                    "op": "set_cost",
                    "amount": 0,
                    "optional": True,
                    "require_no_effect": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "ST36-005": [
        {
            "timing": "on_opponent_attack",
            "summary": "Once: flip Life face-down (top or bottom): redirect attack to Eustass Kid base≥5000",
            "ops": [
                {"op": "flip_life", "face": "down", "position": "top_or_bottom", "as_cost": True, "optional": False},
                {
                    "op": "redirect_attack",
                    "target_kind": "own_character",
                    "name_contains": "Eustass",
                    "base_power_gte": 5000,
                    "optional": False,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
        },
        {
            "timing": "activate_main",
            "summary": "Once: flip Life face-up (top or bottom): attach 1 rested DON!! to Leader",
            "ops": [
                {"op": "flip_life", "face": "up", "position": "top_or_bottom", "as_cost": True, "optional": False},
                {"op": "attach_don", "count": 1, "as_rested": True, "target_kind": "leader"},
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
            "cost_don": 0,
            "rest_self": False,
        },
    ],
    "EB04-054": [
        {
            "timing": "on_play",
            "summary": "If ≤2 Life: add up to 1 from deck top to Life top",
            "ops": [{"op": "add_life", "count": 1}],
            "status": "compiled",
            "confidence": 0.95,
            "require_life_lte": 2,
        },
        {
            "timing": "on_ko",
            "summary": "Add up to 1 from opponent Life top to that Life card's owner hand",
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
            "confidence": 0.95,
        },
    ],
    "EB02-003": [
        {
            "timing": "on_play",
            "summary": "If Leader has Straw Hat Crew: attach up to 1 rested DON!! to Leader or Character",
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
            "require_leader_trait": "Straw Hat Crew",
        },
        {
            "timing": "opponent_turn",
            "summary": "[DON!! x2] [Opponent's Turn] This Character gains +2000 power",
            "ops": [{"op": "buff_self", "amount": 2000}],
            "status": "verified",
            "confidence": 1.0,
            "require_don_attached_gte": 2,
        },
    ],
    "P-057": [
        {
            "timing": "on_play",
            "summary": "If Leader is Uta: up to 2 opp rested Characters cost≤4 skip next Refresh",
            "ops": [
                {
                    "op": "skip_untap",
                    "count": 2,
                    "target_kind": "opponent_character_rested",
                    "cost_lte": 4,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_name": "Uta",
        },
        {
            "timing": "trigger",
            "summary": "Activate this card's Main effect",
            "ops": [{"op": "activate_timing", "timing": "on_play"}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "ST28-003": [
        {
            "timing": "trigger",
            "summary": "If Leader has Land of Wano and opp Life ≤3: play this card",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": False,
                    "from_zone": "hand",
                    "name_contains": "Kin'emon",
                }
            ],
            "status": "compiled",
            "confidence": 0.85,
            "require_leader_trait": "Land of Wano",
            "require_opp_life_lte": 3,
        }
    ],
    "EB04-055": [
        {
            "timing": "on_ko",
            "summary": "Play up to 1 Revolutionary Army Character cost≤4 from hand",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 4,
                    "trait_contains": "Revolutionary Army",
                    "from_zone": "hand",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "If Leader has Revolutionary Army and total Life ≤5: play this card",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": False,
                    "from_zone": "hand",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_leader_trait": "Revolutionary Army",
            "require_total_life_lte": 5,
        },
    ],
    "EB03-059": [
        {
            "timing": "on_play",
            "summary": "If Egghead Leader and ≥2 Life: add Trigger Character from hand to Life face-up",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "require_trigger": True,
                    "from_zone": "hand",
                }
            ],
            "status": "needs_review",
            "confidence": 0.55,
            "require_leader_trait": "Egghead",
            "require_life_gte": 2,
        },
        {
            "timing": "trigger",
            "summary": "Up to 1 opp Character cost≤6 other than Luffy cannot attack this turn",
            "ops": [
                {
                    "op": "deny_attack",
                    "count": 1,
                    "cost_lte": 6,
                    "optional": True,
                    "duration": "turn",
                    "exclude_name": "Monkey.D.Luffy",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP01-040": [
        {
            "timing": "on_play",
            "summary": "If Leader Kouzuki Oden: play up to 1 Akazaya Nine cost≤3 from hand",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 3,
                    "trait_contains": "The Akazaya Nine",
                    "from_zone": "hand",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_leader_name": "Kouzuki Oden",
        },
        {
            "timing": "when_attacking",
            "summary": "DON!! x1 Once: set up to 1 Akazaya Nine cost≤3 as active",
            "ops": [
                {
                    "op": "set_character_active",
                    "count": 1,
                    "optional": True,
                    "trait_contains": "The Akazaya Nine",
                    "cost_lte": 3,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
            "require_don_attached_gte": 1,
        },
    ],
    "OP02-110": [
        {
            "timing": "on_block",
            "summary": "Up to 1 opp Character cost≤6 cannot attack this turn",
            "ops": [
                {
                    "op": "deny_attack",
                    "count": 1,
                    "cost_lte": 6,
                    "optional": True,
                    "duration": "turn",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP04-038": [
        {
            "timing": "on_play",
            "summary": "Rest up to 1 opp Leader or Character, then KO rested cost≤6",
            "ops": [
                {"op": "rest_opponent_character", "count": 1, "include_leader": True},
                {
                    "op": "ko",
                    "count": 1,
                    "target_kind": "opponent_character_rested",
                    "cost_lte": 6,
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "counter_event",
            "summary": "Rest up to 1 opp Leader or Character, then KO rested cost≤6",
            "ops": [
                {"op": "rest_opponent_character", "count": 1, "include_leader": True},
                {
                    "op": "ko",
                    "count": 1,
                    "target_kind": "opponent_character_rested",
                    "cost_lte": 6,
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "Set up to 5 DON!! as active",
            "ops": [{"op": "active_don", "count": 5}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP04-100": [
        {
            "timing": "trigger",
            "summary": "Up to 1 opp Leader or Character cannot attack this turn",
            "ops": [
                {
                    "op": "deny_attack",
                    "count": 1,
                    "optional": True,
                    "duration": "turn",
                    "include_leader": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP06-039": [
        {
            "timing": "on_play",
            "summary": "Choose one: rest cost≤6 OR KO rested cost≤6",
            "ops": [
                {
                    "op": "choose_one",
                    "chooser": "self",
                    "options": [
                        {
                            "id": "rest",
                            "label": "Rest up to 1 Character cost≤6",
                            "ops": [{"op": "rest_opponent_character", "count": 1, "cost_lte": 6}],
                        },
                        {
                            "id": "ko",
                            "label": "KO up to 1 rested Character cost≤6",
                            "ops": [
                                {
                                    "op": "ko",
                                    "count": 1,
                                    "target_kind": "opponent_character_rested",
                                    "cost_lte": 6,
                                    "optional": True,
                                }
                            ],
                        },
                    ],
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "Activate this card's Main effect",
            "ops": [{"op": "activate_timing", "timing": "on_play"}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP08-112": [
        {
            "timing": "on_play",
            "summary": "Up to 1 opp Character cost≤6 other than Luffy cannot attack until opp turn end",
            "ops": [
                {
                    "op": "deny_attack",
                    "count": 1,
                    "cost_lte": 6,
                    "optional": True,
                    "duration": "until_opp_turn_end",
                    "exclude_name": "Monkey.D.Luffy",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "Activate this card's On Play effect",
            "ops": [{"op": "activate_timing", "timing": "on_play"}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP08-117": [
        {
            "timing": "on_play",
            "summary": "Trash 1 from Life top: KO up to 1 opp Character cost≤7",
            "ops": [
                {"op": "trash_life", "count": 1, "position": "top", "as_cost": True, "optional": True},
                {"op": "ko", "count": 1, "target_kind": "opponent_character", "cost_lte": 7, "optional": True},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "Life top to hand, then up to 1 hand to Life top",
            "ops": [
                {"op": "life_to_hand", "count": 1, "position": "top", "optional": False, "owner": "self"},
                {"op": "hand_to_life", "count": 1, "optional": True},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP09-102": [
        {
            "timing": "on_play",
            "summary": "If Leader Nico Robin: look top 3; add up to 1 Trigger; rest bottom",
            "ops": [
                {
                    "op": "search_deck",
                    "top_n": 3,
                    "max_add": 1,
                    "order_bottom": True,
                    "require_trigger": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_name": "Nico Robin",
        },
        {
            "timing": "trigger",
            "summary": "Activate this card's On Play effect",
            "ops": [{"op": "activate_timing", "timing": "on_play"}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP14-111": [
        {
            "timing": "on_play",
            "summary": "Up to 1 opp Character cost≤6 cannot attack until opp End Phase",
            "ops": [
                {
                    "op": "deny_attack",
                    "count": 1,
                    "cost_lte": 6,
                    "optional": True,
                    "duration": "until_opp_turn_end",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "on_ko",
            "summary": "Up to 1 opp Character cost≤6 cannot attack until opp End Phase",
            "ops": [
                {
                    "op": "deny_attack",
                    "count": 1,
                    "cost_lte": 6,
                    "optional": True,
                    "duration": "until_opp_turn_end",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "Play up to 1 Thriller Bark Pirates Character cost≤4 from trash rested",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 4,
                    "trait_contains": "Thriller Bark Pirates",
                    "as_rested": True,
                    "from_zone": "trash",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP15-097": [
        {
            "timing": "on_play",
            "summary": "If trash≥10: up to 1 opp Character base cost≤5 cannot attack until opp End Phase",
            "ops": [
                {
                    "op": "deny_attack",
                    "count": 1,
                    "optional": True,
                    "duration": "until_opp_turn_end",
                    "base_cost_lte": 5,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_trash_gte": 10,
        },
        {
            "timing": "trigger",
            "summary": "Activate this card's Main effect",
            "ops": [{"op": "activate_timing", "timing": "on_play"}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "ST07-015": [
        {
            "timing": "on_play",
            "summary": "Opponent chooses: trash 1 from their Life top, OR you add 1 from deck to Life",
            "ops": [
                {
                    "op": "choose_one",
                    "chooser": "opponent",
                    "options": [
                        {
                            "id": "trash_life",
                            "label": "Trash 1 from your Life top",
                            "ops": [
                                {
                                    "op": "trash_life",
                                    "count": 1,
                                    "position": "top",
                                    "owner": "opponent",
                                    "optional": False,
                                }
                            ],
                        },
                        {
                            "id": "add_life",
                            "label": "Opponent adds 1 from deck to Life",
                            "ops": [{"op": "add_life", "count": 1}],
                        },
                    ],
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "Activate this card's Main effect",
            "ops": [{"op": "activate_timing", "timing": "on_play"}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "ST11-003": [
        {
            "timing": "on_play",
            "summary": "If Leader Uta: choose rest cost≤5 OR KO rested cost≤5",
            "ops": [
                {
                    "op": "choose_one",
                    "chooser": "self",
                    "options": [
                        {
                            "id": "rest",
                            "label": "Rest up to 1 Character cost≤5",
                            "ops": [{"op": "rest_opponent_character", "count": 1, "cost_lte": 5}],
                        },
                        {
                            "id": "ko",
                            "label": "KO up to 1 rested Character cost≤5",
                            "ops": [
                                {
                                    "op": "ko",
                                    "count": 1,
                                    "target_kind": "opponent_character_rested",
                                    "cost_lte": 5,
                                    "optional": True,
                                }
                            ],
                        },
                    ],
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_name": "Uta",
        }
    ],
}


def base_id(cid: str) -> str:
    return re.sub(r"-(?:P|R)\d+$", "", cid)


def main() -> None:
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text())
    _, ov_path = library_paths()
    ov = json.loads(ov_path.read_text())
    cards = ov.setdefault("cards", ov if "cards" not in ov else ov["cards"])
    if "cards" not in ov and any(re.match(r"^[A-Z0-9]+-\d+", k) for k in ov):
        cards = ov

    written = 0
    for cid in list(catalog):
        b = base_id(cid)
        if b not in FOCUS:
            continue
        abs_ = [normalize_ability(a) for a in FOCUS[b]]
        abs_ = [a for a in abs_ if a]
        cards[cid] = normalize_card_entry(cid, {"version": 1, "abilities": abs_})
        written += 1

    payload = {"version": 1, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "cards": cards} if "cards" in ov or True else cards
    # Keep wrapper if original had cards key
    if isinstance(ov, dict) and "cards" in ov:
        ov["cards"] = cards
        ov["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        ov_path.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")
    reload_effect_library(force=True)
    print(f"wrote overrides for {written} variants covering {len(FOCUS)} bases")


if __name__ == "__main__":
    main()
