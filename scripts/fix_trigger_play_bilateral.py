#!/usr/bin/env python3
"""Dual-write encoding fixes: trigger watchers, play watchers, either-life, bilateral gates."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_schema import normalize_card_entry  # noqa: E402

FIXES: dict[str, list[dict[str, Any]]] = {
    "OP05-109": [
        {
            "timing": "on_trigger",
            "summary": "Once per turn: when a Trigger activates, draw 2 and trash 2 hand",
            "ops": [
                {"op": "draw", "count": 2},
                {"op": "trash_hand", "count": 2, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
        }
    ],
    "OP13-106": [
        {
            "timing": "on_trigger",
            "summary": "When a Trigger activates on opponent's turn: this Character gains Blocker this turn",
            "ops": [
                {
                    "op": "grant_keyword",
                    "keyword": "blocker",
                    "target_kind": "self",
                    "duration": "turn",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_opponent_turn": True,
        },
        {
            "timing": "trigger",
            "summary": "Play this card from hand when its [Trigger] activates",
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
            "confidence": 1.0,
        },
    ],
    "OP13-100": [
        {
            "timing": "your_turn",
            "summary": "Once: when you play a Character with Trigger, attach up to 2 rested DON!! to own Leader/Character",
            "ops": [
                {
                    "op": "attach_don",
                    "count": 2,
                    "as_rested": True,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
            "on_own_play_character": True,
            "require_played_has_trigger": True,
        }
    ],
    "OP03-104": [
        {
            "timing": "on_play",
            "summary": "Look at up to 1 top Life (self or opp) and place top or bottom",
            "ops": [{"op": "reorder_life", "owner": "self_or_opponent"}],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "EB02-053": [
        {
            "timing": "on_play",
            "summary": "Look at up to 1 top Life (self or opp) and place top or bottom",
            "ops": [{"op": "reorder_life", "owner": "self_or_opponent"}],
            "status": "compiled",
            "confidence": 0.9,
        },
        {
            "timing": "on_ko",
            "summary": "Look at up to 1 top Life (self or opp) and place top or bottom",
            "ops": [{"op": "reorder_life", "owner": "self_or_opponent"}],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "ST07-008": [
        {
            "timing": "on_play",
            "summary": "Look at up to 1 top Life (self or opp) and place top or bottom",
            "ops": [{"op": "reorder_life", "owner": "self_or_opponent"}],
            "status": "compiled",
            "confidence": 0.9,
        }
    ],
    "OP10-116": [
        {
            "timing": "on_play",
            "summary": "Look up to 1 Life top (self or opp) reorder; then KO up to 1 opp cost≤5",
            "ops": [
                {"op": "reorder_life", "owner": "self_or_opponent"},
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "cost_lte": 5,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
        {
            "timing": "trigger",
            "summary": "Draw 2, trash 1 hand",
            "ops": [
                {"op": "draw", "count": 2},
                {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
    "OP16-081": [
        {
            "timing": "activate_main",
            "summary": "Rest this: if field has Character cost≥8, up to 1 opp Character −2000 this turn",
            "ops": [
                {
                    "op": "buff",
                    "amount": -2000,
                    "target_kind": "opponent_character",
                    "optional": True,
                    "count": 1,
                    "duration": "turn",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "cost_don": 0,
            "rest_self": True,
            "once": False,
            "require_field_char_cost_gte": 8,
        }
    ],
    "OP05-100": [
        {
            "timing": "your_turn",
            "summary": "Rush",
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
        },
        {
            "timing": "your_turn",
            "summary": "Once: if this would leave, may trash Life top instead; null if Luffy on either field",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "ko",
                    "target": "self",
                    "cost": "trash_life",
                    "life_position": "top",
                    "any_leave": True,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
            "require_no_name_on_field": "Monkey.D.Luffy|蒙其・D・魯夫|蒙其·D·鲁夫",
        },
        {
            "timing": "opponent_turn",
            "summary": "Once: if this would leave, may trash Life top instead; null if Luffy on either field",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "ko",
                    "target": "self",
                    "cost": "trash_life",
                    "life_position": "top",
                    "any_leave": True,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
            "require_no_name_on_field": "Monkey.D.Luffy|蒙其・D・魯夫|蒙其·D·鲁夫",
        },
    ],
    "OP12-040": [
        {
            "timing": "your_turn",
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
            "on_hand_trash_by_own_effect": True,
        }
    ],
    "OP16-079": [
        {
            "timing": "your_turn",
            "summary": "When Land of Wano Character is played from trash: that Character gains Rush this turn",
            "ops": [
                {
                    "op": "grant_keyword",
                    "keyword": "rush",
                    "target_kind": "own_character",
                    "trait_contains": "Land of Wano",
                    "duration": "turn",
                    "optional": False,
                    "count": 1,
                }
            ],
            "status": "compiled",
            "confidence": 0.85,
            "on_own_play_character": True,
            "require_played_from_trash": True,
            "require_played_trait": "Land of Wano|和之國|和之国",
        }
    ],
}

VARIANT_ONLY_BASES = ()


def _put(store: dict, cid: str, abilities: list[dict]) -> None:
    store[cid] = normalize_card_entry(cid, {"version": 1, "abilities": abilities})


def _variants(catalog: dict, base: str) -> list[str]:
    return [base] + sorted(k for k in catalog if k.startswith(base + "-"))


def main() -> int:
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))
    lib_path = ROOT / "index" / "card_effects.json"
    ov_path = ROOT / "index" / "card_effect_overrides.json"
    lib = json.loads(lib_path.read_text(encoding="utf-8"))
    ov = json.loads(ov_path.read_text(encoding="utf-8"))
    cards = lib.setdefault("cards", {})
    ov_cards = ov.setdefault("cards", {})

    touched = 0
    for base, abilities in FIXES.items():
        abs_ = [dict(a) for a in abilities]
        for cid in _variants(catalog, base):
            for store in (cards, ov_cards):
                _put(store, cid, abs_)
                touched += 1

    lib_path.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ov_path.write_text(json.dumps(ov, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"touched": touched, "bases": list(FIXES)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
