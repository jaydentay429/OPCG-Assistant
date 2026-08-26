#!/usr/bin/env python3
"""Dual-write continuous per-count power scalers (OP16-034-class siblings)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_schema import normalize_card_entry  # noqa: E402

# Base encodings (variants inherit).
FIXES: dict[str, list[dict[str, Any]]] = {
    "EB01-014": [
        {
            "timing": "your_turn",
            "summary": "DON!!×1: +1000 for every 3 rested DON!!",
            "ops": [{"op": "buff_self", "amount": 1000, "per_rested_don": 3}],
            "status": "verified",
            "confidence": 1.0,
            "require_don_attached_gte": 1,
        }
    ],
    "OP01-083": [
        {
            "timing": "your_turn",
            "summary": "DON!!×1: if Leader is Baroque Works, +1000 per 2 Events in trash",
            "ops": [{"op": "buff_self", "amount": 1000, "per_trash_events": 2}],
            "status": "verified",
            "confidence": 1.0,
            "require_don_attached_gte": 1,
            "require_leader_trait": "Baroque Works|B・W|B.W|B·W|巴洛克工作社",
        }
    ],
    "OP09-086": [
        {
            "timing": "your_turn",
            "summary": "Cannot be K.O.'d by opponent's effects",
            "ops": [{"op": "cannot_be_ko", "target_kind": "self"}],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "opponent_turn",
            "summary": "Cannot be K.O.'d by opponent's effects",
            "ops": [{"op": "cannot_be_ko", "target_kind": "self"}],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "your_turn",
            "summary": "If Leader is Blackbeard Pirates: +1000 per 4 cards in trash",
            "ops": [{"op": "buff_self", "amount": 1000, "per_trash_cards": 4}],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_trait": "Blackbeard Pirates|黑鬍子海賊團|黑胡子海贼团",
        },
        {
            "timing": "opponent_turn",
            "summary": "If Leader is Blackbeard Pirates: +1000 per 4 cards in trash",
            "ops": [{"op": "buff_self", "amount": 1000, "per_trash_cards": 4}],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_trait": "Blackbeard Pirates|黑鬍子海賊團|黑胡子海贼团",
        },
    ],
    "EB01-027": [
        {
            "timing": "your_turn",
            "summary": "If Leader includes Baroque Works: +1000 per 2 Events in trash",
            "ops": [{"op": "buff_self", "amount": 1000, "per_trash_events": 2}],
            "status": "compiled",
            "confidence": 0.9,
            "require_leader_trait": "Baroque Works|B・W|B.W|B·W|巴洛克工作社",
        },
        {
            "timing": "opponent_turn",
            "summary": "If Leader includes Baroque Works: +1000 per 2 Events in trash",
            "ops": [{"op": "buff_self", "amount": 1000, "per_trash_events": 2}],
            "status": "compiled",
            "confidence": 0.9,
            "require_leader_trait": "Baroque Works|B・W|B.W|B·W|巴洛克工作社",
        },
        {
            "timing": "on_play",
            "summary": "Draw 2, trash 1 hand",
            "ops": [
                {"op": "draw", "count": 2},
                {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "EB04-048": [
        {
            "timing": "your_turn",
            "summary": "If Leader includes CP: +1000 power and +2 cost per 5 trash cards",
            "ops": [
                {"op": "buff_self", "amount": 1000, "per_trash_cards": 5},
                {"op": "grant_cost", "amount": 2, "target_kind": "self", "per_trash_cards": 5},
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_leader_trait": "CP",
        },
        {
            "timing": "opponent_turn",
            "summary": "If Leader includes CP: +1000 power and +2 cost per 5 trash cards",
            "ops": [
                {"op": "buff_self", "amount": 1000, "per_trash_cards": 5},
                {"op": "grant_cost", "amount": 2, "target_kind": "self", "per_trash_cards": 5},
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_leader_trait": "CP",
        },
        {
            "timing": "on_play",
            "summary": "May trash 1 own Character: draw 1",
            "ops": [
                {
                    "op": "trash",
                    "target_kind": "own_character",
                    "optional": True,
                    "as_cost": True,
                },
                {"op": "draw", "count": 1},
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
    ],
}


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
