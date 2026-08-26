#!/usr/bin/env python3
"""Write battle encodings for OP17-016..030 into card_effect_overrides.json."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

WB = "Whitebeard Pirates"
RH = "Red-Haired Pirates"
SHANKS = "Shanks|香克斯"


def ab(**kwargs):
    kwargs.setdefault("status", "compiled")
    kwargs.setdefault("confidence", 0.9)
    return kwargs


def _replace_leave(op: dict) -> list[dict]:
    """Continuous replace_leave must sit on both turns so it can fire off-turn."""
    return [
        ab(timing="your_turn", summary=op["summary"], ops=[op]),
        ab(timing="opponent_turn", summary=op["summary"], ops=[op]),
    ]


ENTRIES: dict[str, list[dict]] = {
    "OP17-016": [
        ab(
            timing="on_play",
            summary="K.O. up to 2 opponent Characters with 2000 base power or less",
            ops=[
                {
                    "op": "ko",
                    "count": 2,
                    "target_kind": "opponent_character",
                    "base_power_lte": 2000,
                    "optional": True,
                }
            ],
        )
    ],
    "OP17-017": [
        ab(
            timing="counter_event",
            summary="Up to 1 own Whitebeard Pirates Leader or Character +2000 this battle; then up to 1 opp Leader or Character −2000 this turn",
            ops=[
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "own_leader_or_character",
                    "trait_contains": WB,
                    "optional": True,
                    "duration": "battle",
                },
                {
                    "op": "buff",
                    "amount": -2000,
                    "target_kind": "opponent_leader_or_character",
                    "optional": True,
                    "duration": "turn",
                },
            ],
        )
    ],
    "OP17-018": [
        ab(
            timing="on_play",
            summary="You may rest 2 DON!!: K.O. up to 1 opponent Stage",
            ops=[
                {
                    "op": "rest_don",
                    "count": 2,
                    "owner": "self",
                    "as_cost": True,
                    "optional": True,
                },
                {
                    "op": "ko",
                    "count": 1,
                    "target_kind": "opponent_stage",
                    "optional": True,
                },
            ],
        ),
        ab(
            timing="counter_event",
            summary="If 2+ own Characters have 8000 base power or more: up to 1 own Leader or Character +4000 this battle",
            ops=[
                {
                    "op": "buff",
                    "amount": 4000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                }
            ],
            require_chars_base_power_gte=8000,
            require_chars_base_power_count_gte=2,
        ),
    ],
    "OP17-019": [
        ab(
            timing="on_play",
            summary="Look top 5; reveal up to 1 Whitebeard Pirates to hand; rest bottom any order",
            ops=[
                {
                    "op": "search_deck",
                    "top_n": 5,
                    "max_add": 1,
                    "trait_contains": WB,
                    "order_bottom": True,
                    "destination": "hand",
                }
            ],
        ),
        ab(
            timing="trigger",
            summary="Your Leader +1000 this turn",
            ops=[{"op": "buff", "amount": 1000, "target_kind": "leader", "duration": "turn"}],
        ),
    ],
    "OP17-021": _replace_leave(
        {
            "op": "replace_leave",
            "trigger": "opp_remove",
            "target": "own_filtered",
            "cost": "rest_own",
            "rest_count": 1,
            "trait_contains": RH,
            "optional": True,
            "summary": "Rest 1 of your cards instead of a Red-Haired Pirates Character leaving by opponent's effect",
        }
    ),
    "OP17-022": [
        ab(
            timing="your_turn",
            summary="Rush",
            ops=[
                {
                    "op": "grant_keyword",
                    "keyword": "rush",
                    "target_kind": "self",
                    "duration": "permanent",
                }
            ],
            confidence=0.95,
        ),
        ab(
            timing="on_play",
            summary="Set up to 2 DON!! active; rest all opponent Characters",
            ops=[
                {"op": "active_don", "count": 2, "optional": True},
                {
                    "op": "rest_opponent_character",
                    "all": True,
                    "optional": False,
                },
            ],
        ),
    ],
    "OP17-023": _replace_leave(
        {
            "op": "replace_leave",
            "trigger": "ko",
            "target": "own_filtered",
            "cost": "rest_self",
            "trait_contains": "East Blue|Straw Hat Crew",
            "optional": True,
            "summary": "Rest this Character instead of an East Blue or Straw Hat Crew Character being K.O.'d",
        }
    ),
    "OP17-024": [
        ab(
            timing="on_play",
            summary="Rest up to 1 opponent Character",
            ops=[
                {
                    "op": "rest_opponent_character",
                    "count": 1,
                    "optional": True,
                }
            ],
        )
    ],
    "OP17-025": [
        ab(
            timing="on_ko",
            summary="K.O. up to 1 opponent rested Character with cost 6 or less",
            ops=[
                {
                    "op": "ko",
                    "count": 1,
                    "target_kind": "opponent_character_rested",
                    "cost_lte": 6,
                    "optional": True,
                }
            ],
        ),
        ab(
            timing="activate_main",
            summary="Once: give up to 1 rested DON!! to your [Shanks] Leader",
            ops=[
                {
                    "op": "attach_don",
                    "count": 1,
                    "from_rested": True,
                    "as_rested": True,
                    "target_kind": "leader",
                    "name_contains": SHANKS,
                    "optional": True,
                }
            ],
            once=True,
            cost_don=0,
            rest_self=False,
            require_leader_name=SHANKS,
        ),
    ],
    "OP17-026": [
        ab(
            timing="when_attacking",
            summary="If Leader has Red-Haired Pirates: rest up to 1 opponent Character with cost 2 or less",
            ops=[
                {
                    "op": "rest_opponent_character",
                    "count": 1,
                    "cost_lte": 2,
                    "optional": True,
                }
            ],
            require_leader_trait=RH,
        ),
        ab(
            timing="on_ko",
            summary="Draw 1",
            ops=[{"op": "draw", "count": 1}],
        ),
    ],
    "OP17-027": [
        ab(
            timing="on_play",
            summary="If Leader has Red-Haired Pirates: draw 1 and rest up to 2 opponent Characters",
            ops=[
                {"op": "draw", "count": 1},
                {
                    "op": "rest_character",
                    "target_kind": "opponent_character",
                    "count": 2,
                    "optional": True,
                },
            ],
            require_leader_trait=RH,
        )
    ],
    "OP17-028": [
        ab(
            timing="on_play",
            summary="K.O. up to 1 opponent rested Character with cost 6 or less",
            ops=[
                {
                    "op": "ko",
                    "count": 1,
                    "target_kind": "opponent_character_rested",
                    "cost_lte": 6,
                    "optional": True,
                }
            ],
        )
    ],
    "OP17-029": [
        ab(
            timing="on_play",
            summary="Set up to 1 DON!! active; rest up to 2 opponent Characters with cost 2 or less",
            ops=[
                {"op": "active_don", "count": 1, "optional": True},
                {
                    "op": "rest_character",
                    "target_kind": "opponent_character",
                    "count": 2,
                    "cost_lte": 2,
                    "optional": True,
                },
            ],
        )
    ],
    "OP17-030": [
        ab(
            timing="on_play",
            summary="You may rest 1 DON!!: this Character gains Rush this turn",
            ops=[
                {
                    "op": "rest_don",
                    "count": 1,
                    "owner": "self",
                    "as_cost": True,
                    "optional": True,
                },
                {
                    "op": "grant_keyword",
                    "keyword": "rush",
                    "target_kind": "self",
                    "duration": "turn",
                },
            ],
        ),
        ab(
            timing="activate_main",
            summary="Once: if hand ≤5, set up to 1 DON!! active",
            ops=[{"op": "active_don", "count": 1, "optional": True}],
            once=True,
            cost_don=0,
            rest_self=False,
            require_hand_lte=5,
        ),
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
    for base, abilities in ENTRIES.items():
        variants = [base] + sorted(k for k in catalog if k.startswith(base + "-"))
        entry = normalize_card_entry(base, {"version": 1, "card_id": base, "abilities": abilities})
        for cid in variants:
            if cid not in catalog and cid != base:
                continue
            packed = dict(entry)
            packed["card_id"] = cid
            ov_cards[cid] = packed
            cards[cid] = packed
            n += 1
            print("override", cid, [a.get("timing") for a in packed["abilities"]])

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
