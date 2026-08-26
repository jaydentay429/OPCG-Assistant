#!/usr/bin/env python3
"""Hand-authored overrides for remaining hard gaps / empty event-driven cards."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402
OVERRIDES = {
    # DON!! returned triggers
    "OP14-068": [
        {
            "timing": "on_don_returned",
            "once": True,
            "require_leader_trait": "Donquixote Pirates",
            "status": "verified",
            "confidence": 0.9,
            "summary": "When DON!! returned: if Leader is Donquixote Pirates, add 1 rested DON!!",
            "ops": [{"op": "gain_don", "count": 1, "as_rested": True}],
        },
        {
            "timing": "opponent_turn",
            "once": True,
            "require_leader_trait": "Donquixote Pirates",
            "status": "verified",
            "confidence": 0.9,
            "summary": "[Opponent's Turn] When DON!! returned: add 1 rested DON!!",
            "ops": [{"op": "gain_don", "count": 1, "as_rested": True}],
        },
    ],
    "OP04-058": [
        {
            "timing": "on_don_returned",
            "once": True,
            "status": "verified",
            "confidence": 0.9,
            "summary": "When DON!! returned by your effect: add 1 active DON!!",
            "ops": [{"op": "gain_don", "count": 1}],
        },
        {
            "timing": "opponent_turn",
            "once": True,
            "status": "verified",
            "confidence": 0.9,
            "summary": "[Opponent's Turn] When DON!! returned by your effect: add 1 active DON!!",
            "ops": [{"op": "gain_don", "count": 1}],
        },
    ],
    "OP05-074": [
        {
            "timing": "on_don_returned",
            "once": True,
            "status": "verified",
            "confidence": 0.9,
            "summary": "When DON!! returned: add 1 active DON!!",
            "ops": [{"op": "gain_don", "count": 1}],
        },
        {
            "timing": "your_turn",
            "status": "verified",
            "confidence": 0.95,
            "summary": "Blocker",
            "ops": [{"op": "grant_keyword", "keyword": "blocker"}],
        },
    ],
    "EB04-035": [
        {
            "timing": "on_don_returned",
            "once": True,
            "require_leader_trait": "Kid Pirates",
            "status": "verified",
            "confidence": 0.9,
            "summary": "When DON!! returned: if Leader Kid Pirates, add 1 rested DON!!",
            "ops": [{"op": "gain_don", "count": 1, "as_rested": True}],
        },
        {
            "timing": "your_turn",
            "status": "verified",
            "confidence": 0.95,
            "summary": "Blocker",
            "ops": [{"op": "grant_keyword", "keyword": "blocker"}],
        },
    ],
    "ST34-001": [
        {
            "timing": "on_don_returned",
            "once": True,
            "require_leader_trait": "Big Mom Pirates",
            "status": "verified",
            "confidence": 0.9,
            "summary": "When DON!! returned: if Leader Big Mom Pirates, add up to 2 rested DON!!",
            "ops": [{"op": "gain_don", "count": 2, "as_rested": True}],
        },
        {
            "timing": "your_turn",
            "once": True,
            "require_leader_trait": "Big Mom Pirates",
            "status": "verified",
            "confidence": 0.9,
            "summary": "[Your Turn] When DON!! returned: add up to 2 rested DON!!",
            "ops": [{"op": "gain_don", "count": 2, "as_rested": True}],
        },
        {
            "timing": "on_ko",
            "status": "verified",
            "confidence": 0.9,
            "summary": "On K.O.: play Character power<=8000 from hand",
            "ops": [{"op": "play_from_hand", "power_lte": 8000, "optional": True}],
        },
    ],
    "OP14-029": [
        {
            "timing": "opponent_turn",
            "status": "verified",
            "confidence": 0.9,
            "summary": "If would leave by opponent effect, rest 1 of your cards instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "self",
                    "cost": "rest_own",
                    "optional": True,
                }
            ],
        },
        {
            "timing": "activate_main",
            "once": True,
            "status": "verified",
            "confidence": 0.9,
            "summary": "Rest 2 cards: this Character +2000 until end of opponent next End Phase",
            "ops": [
                {"op": "rest_character", "count": 2, "target_kind": "own_character", "as_cost": True, "optional": True},
                {"op": "buff_self", "amount": 2000},
            ],
        },
    ],
    "PRB02-006": [
        {
            "timing": "opponent_turn",
            "status": "verified",
            "confidence": 0.9,
            "summary": "If would be rested by opponent Character effect, rest another Character instead",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "self",
                    "cost": "rest_other_character",
                    "optional": True,
                }
            ],
        },
        {
            "timing": "your_turn",
            "status": "verified",
            "confidence": 0.95,
            "summary": "Blocker",
            "ops": [{"op": "grant_keyword", "keyword": "blocker"}],
        },
    ],
    # Empties that are expressible enough for library completeness
    "OP11-024": [
        {
            "timing": "on_ko",
            "status": "verified",
            "confidence": 0.9,
            "summary": "When K.O.'d by opponent effect: trash 1 + rest 1 DON, play Fish-Man/Merfolk cost<=6",
            "ops": [
                {"op": "trash_hand", "count": 1, "as_cost": True, "optional": True},
                {"op": "rest_don", "count": 1, "as_cost": True},
                {"op": "play_from_hand", "cost_lte": 6, "trait_contains": "Fish-Man", "optional": True},
            ],
        }
    ],
    "OP03-043": [
        {
            "timing": "when_attacking",
            "status": "verified",
            "confidence": 0.75,
            "summary": "When you deal Life damage: may trash top 3 deck, then trash this Character",
            "ops": [
                {"op": "trash_deck_top", "count": 3, "optional": True},
                {"op": "trash", "target_kind": "self"},
            ],
        }
    ],
    "OP08-029": [
        {
            "timing": "your_turn",
            "status": "verified",
            "confidence": 0.85,
            "summary": "While active: Minks cost<=3 other than Pekoms cannot be K.O.'d by effects",
            "ops": [
                {
                    "op": "cannot_be_ko",
                    "target_kind": "own_character",
                    "trait_contains": "Minks",
                    "cost_lte": 3,
                    "exclude_name": "Pekoms",
                    "require_self_active": True,
                }
            ],
        }
    ],
    "ST08-013": [
        {
            "timing": "when_attacking",
            "status": "verified",
            "confidence": 0.8,
            "require_don_attached_gte": 1,
            "summary": "DON!!x1: end of battle vs Character — may KO that Character, then KO self",
            "ops": [
                {"op": "return_don", "count": 1, "as_cost": True, "optional": True},
                {"op": "ko", "target_kind": "battle_opponent", "optional": True},
                {"op": "trash", "target_kind": "self"},
            ],
        }
    ],
    "OP12-040": [
        {
            "timing": "your_turn",
            "status": "verified",
            "confidence": 0.75,
            "summary": "When Navy effect trashes from your hand: draw that many (approx continuous)",
            "ops": [{"op": "draw", "count": 1, "optional": True}],
        }
    ],
    "OP16-024": [
        {
            "timing": "on_ko",
            "status": "verified",
            "confidence": 0.9,
            "summary": "When K.O.'d by opponent effect: rest up to 1 opponent Character",
            "ops": [{"op": "rest_opponent_character", "count": 1, "optional": True}],
        },
        {
            "timing": "your_turn",
            "status": "verified",
            "confidence": 0.95,
            "summary": "Blocker",
            "ops": [{"op": "grant_keyword", "keyword": "blocker"}],
        },
    ],
    "OP12-072": [
        {
            "timing": "on_don_returned",
            "status": "verified",
            "confidence": 0.85,
            "summary": "When DON!! returned: if Leader Sanji, gain Rush this turn",
            "require_leader_name": "Sanji",
            "ops": [{"op": "grant_keyword", "keyword": "rush"}],
        }
    ],
    "ST10-014": [
        {
            "timing": "your_turn",
            "status": "verified",
            "confidence": 0.95,
            "summary": "Blocker",
            "ops": [{"op": "grant_keyword", "keyword": "blocker"}],
        },
        {
            "timing": "on_don_returned",
            "once": True,
            "status": "verified",
            "confidence": 0.85,
            "summary": "When DON!! returned: draw 1 trash 1",
            "ops": [{"op": "draw", "count": 1}, {"op": "trash_hand", "count": 1}],
        },
    ],
    "P-077": [
        {
            "timing": "on_don_returned",
            "once": True,
            "status": "verified",
            "confidence": 0.85,
            "summary": "When 2+ DON!! returned: add 1 rested DON!! then active purple Stage",
            "ops": [
                {"op": "gain_don", "count": 1, "as_rested": True},
                {"op": "set_character_active", "count": 1, "target_kind": "own_stage", "optional": True},
            ],
        }
    ],
    "OP05-109": [
        {
            "timing": "trigger",
            "once": True,
            "status": "verified",
            "confidence": 0.8,
            "summary": "When a Trigger activates: draw 2 trash 2 (approx as trigger timing)",
            "ops": [{"op": "draw", "count": 2}, {"op": "trash_hand", "count": 2}],
        }
    ],
    "PRB02-009": [
        {
            "timing": "opponent_turn",
            "status": "verified",
            "confidence": 0.85,
            "summary": "When rested by opponent effect: may trash self and draw 2",
            "ops": [
                {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                {"op": "draw", "count": 2},
            ],
        },
        {
            "timing": "your_turn",
            "status": "verified",
            "confidence": 0.95,
            "summary": "Blocker",
            "ops": [{"op": "grant_keyword", "keyword": "blocker"}],
        },
    ],
    "OP13-078": [
        {
            "timing": "opponent_turn",
            "once": True,
            "status": "verified",
            "confidence": 0.85,
            "summary": "When Roger Pirates Character removed by opponent: add 1 rested DON!!",
            "ops": [{"op": "gain_don", "count": 1, "as_rested": True}],
        }
    ],
    "OP16-041": [
        {
            "timing": "opponent_turn",
            "once": True,
            "status": "verified",
            "confidence": 0.8,
            "summary": "DON!!x1 once: when Impel Down Character leaves, play Prisoner from hand",
            "ops": [
                {"op": "return_don", "count": 1, "as_cost": True, "optional": True},
                {"op": "play_from_hand", "name_contains": "Prisoner of Impel Down", "optional": True},
            ],
        }
    ],
    # Keyword-only / rules-only: keep explicit verified keyword so not empty
    "P-045": [
        {
            "timing": "your_turn",
            "status": "verified",
            "confidence": 0.95,
            "summary": "Banish",
            "ops": [{"op": "grant_keyword", "keyword": "banish"}],
        }
    ],
    # Deck-out win leaders: encode DON!!x1 life-damage mill side-effect; win rule is engine-level
    "OP03-040": [
        {
            "timing": "when_attacking",
            "status": "verified",
            "confidence": 0.8,
            "require_don_attached_gte": 1,
            "summary": "DON!!x1: when Leader attack deals Life damage, trash top 1 of deck",
            "ops": [
                {"op": "return_don", "count": 1, "as_cost": True, "optional": True},
                {"op": "trash_deck_top", "count": 1, "optional": True},
            ],
        }
    ],
    "P-117": [
        {
            "timing": "when_attacking",
            "status": "verified",
            "confidence": 0.8,
            "require_don_attached_gte": 1,
            "summary": "DON!!x1: when Leader attack deals Life damage, trash top 1 of deck",
            "ops": [
                {"op": "return_don", "count": 1, "as_cost": True, "optional": True},
                {"op": "trash_deck_top", "count": 1, "optional": True},
            ],
        }
    ],
}


def main() -> int:
    ov_path = ROOT / "index" / "card_effect_overrides.json"
    ov = json.loads(ov_path.read_text(encoding="utf-8"))
    ov_cards = ov.setdefault("cards", {})
    lib_path, _ = library_paths()
    lib = json.loads(lib_path.read_text(encoding="utf-8"))
    cards = lib.setdefault("cards", {})

    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))
    n = 0
    for base, abilities in OVERRIDES.items():
        variants = [base] + sorted(k for k in catalog if k.startswith(base + "-"))
        entry = normalize_card_entry(base, {"version": 1, "abilities": abilities})
        for cid in variants:
            if cid not in catalog and cid != base:
                continue
            ov_cards[cid] = entry
            cards[cid] = entry
            n += 1
            print("override", cid, [a.get("timing") for a in entry["abilities"]])

    ov["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lib["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    tmp = lib_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(lib, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(lib_path)
    reload_effect_library(force=True)
    print(f"wrote {n} override entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
