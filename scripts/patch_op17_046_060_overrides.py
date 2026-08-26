#!/usr/bin/env python3
"""Write battle encodings for OP17-046..060 into card_effect_overrides.json."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

ROCKS = "Rocks Pirates|洛克斯海賊團|洛克斯海贼团"
XEBEC = "Rocks.D.Xebec|洛克斯・D・吉貝克|洛克斯·D·吉贝克"
AKP = "Animal Kingdom Pirates|百獸海賊團|百兽海贼团"


def ab(**kwargs):
    kwargs.setdefault("status", "compiled")
    kwargs.setdefault("confidence", 0.9)
    return kwargs


def _blocker() -> dict:
    return ab(
        timing="your_turn",
        summary="Blocker",
        ops=[
            {
                "op": "grant_keyword",
                "keyword": "blocker",
                "target_kind": "self",
                "duration": "permanent",
            }
        ],
        confidence=0.95,
    )


def _kaido058_debuff(timing: str) -> dict:
    return ab(
        timing=timing,
        summary="Once: DON!! −1: up to 1 opp Character −2000 this turn",
        ops=[
            {
                "op": "return_don",
                "count": 1,
                "owner": "self",
                "as_cost": True,
                "optional": True,
            },
            {
                "op": "buff",
                "amount": -2000,
                "target_kind": "opponent_character",
                "optional": True,
                "duration": "turn",
            },
        ],
        once=True,
        optional=True,
        may_activate=True,
    )


def _shiki048_debuff(timing: str) -> dict:
    return ab(
        timing=timing,
        summary="Once: may trash 1 Rocks from hand: up to 1 opp Character −3000 this turn",
        ops=[
            {
                "op": "trash_hand",
                "count": 1,
                "optional": True,
                "as_cost": True,
                "owner": "self",
                "trait_contains": ROCKS,
            },
            {
                "op": "buff",
                "amount": -3000,
                "target_kind": "opponent_character",
                "optional": True,
                "duration": "turn",
            },
        ],
        once=True,
    )


def _rocks_counter_buff() -> dict:
    return ab(
        timing="counter_event",
        summary="Up to 1 own Rocks Pirates Leader or Character +2000 this battle",
        ops=[
            {
                "op": "buff",
                "amount": 2000,
                "target_kind": "own_leader_or_character",
                "trait_contains": ROCKS,
                "optional": True,
                "duration": "battle",
            }
        ],
    )


ENTRIES: dict[str, list[dict]] = {
    "OP17-046": [
        _blocker(),
        ab(
            timing="on_play",
            summary="Up to 1 Character cost≤5 to bottom",
            ops=[
                {
                    "op": "return_to_bottom",
                    "count": 1,
                    "optional": True,
                    "target_kind": "any_character",
                    "cost_lte": 5,
                }
            ],
        ),
    ],
    "OP17-047": [
        ab(
            timing="end_of_your_turn",
            summary="If hand ≤2: opponent puts 1 hand card on bottom",
            ops=[
                {
                    "op": "opponent_hand_to_bottom",
                    "count": 1,
                    "optional": False,
                }
            ],
            require_hand_lte=2,
        )
    ],
    "OP17-048": [
        ab(
            timing="your_turn",
            summary="Rush: Character",
            ops=[
                {
                    "op": "grant_keyword",
                    "keyword": "rush_character",
                    "target_kind": "self",
                    "duration": "permanent",
                }
            ],
            confidence=0.95,
        ),
        _shiki048_debuff("when_attacking"),
        _shiki048_debuff("on_opponent_attack"),
    ],
    "OP17-049": [
        ab(
            timing="on_play",
            summary="Opponent chooses: you draw 2, or they trash 2 hand",
            ops=[
                {
                    "op": "choose_one",
                    "chooser": "opponent",
                    "options": [
                        {
                            "id": "draw",
                            "label": "Draw 2 cards",
                            "ops": [{"op": "draw", "count": 2}],
                        },
                        {
                            "id": "trash",
                            "label": "Trash 2 from opponent hand",
                            "ops": [
                                {
                                    "op": "trash_hand",
                                    "count": 2,
                                    "optional": False,
                                    "owner": "opponent",
                                }
                            ],
                        },
                    ],
                }
            ],
        ),
        ab(
            timing="on_opponent_attack",
            summary="Once: may trash 1 hand: up to 1 own Leader or Character +1000 this battle",
            ops=[
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {
                    "op": "buff",
                    "amount": 1000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                },
            ],
            once=True,
        ),
    ],
    "OP17-050": [
        ab(
            timing="on_play",
            summary="Look top 2, reorder to top or bottom, then draw 1",
            ops=[
                {
                    "op": "look_deck",
                    "count": 2,
                    "position": "top_or_bottom",
                    "optional": False,
                },
                {"op": "draw", "count": 1},
            ],
        )
    ],
    "OP17-051": [],
    "OP17-052": [
        ab(
            timing="on_play",
            summary="Add up to 1 blue cost-0 Event from trash to hand",
            ops=[
                {
                    "op": "add_from_trash",
                    "count": 1,
                    "optional": True,
                    "card_type": "event",
                    "color": "blue",
                    "cost_eq": 0,
                }
            ],
        )
    ],
    "OP17-053": [
        ab(
            timing="on_ko",
            summary="Opponent puts 2 hand cards on bottom",
            ops=[
                {
                    "op": "opponent_hand_to_bottom",
                    "count": 2,
                    "optional": False,
                }
            ],
        ),
        ab(
            timing="activate_main",
            summary="Once: may trash 1 hand: this Character +3000 this turn",
            ops=[
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {
                    "op": "buff",
                    "amount": 3000,
                    "target_kind": "self",
                    "duration": "turn",
                },
            ],
            once=True,
            cost_don=0,
            rest_self=False,
        ),
    ],
    "OP17-054": [
        ab(
            timing="on_play",
            summary="Up to 1 opp Character base cost≤6 cannot attack until opp next End",
            ops=[
                {
                    "op": "deny_attack",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "base_cost_lte": 6,
                    "duration": "until_opp_turn_end",
                }
            ],
        ),
        ab(
            timing="activate_main",
            summary="May rest 3 DON!! and this: up to 1 opp Character cannot attack until opp next End",
            ops=[
                {
                    "op": "rest_don",
                    "count": 3,
                    "owner": "self",
                    "as_cost": True,
                    "optional": True,
                },
                {
                    "op": "deny_attack",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "duration": "until_opp_turn_end",
                },
            ],
            cost_don=0,
            rest_self=True,
            once=False,
        ),
    ],
    "OP17-055": [
        ab(
            timing="on_play",
            summary="May rest 1 DON!!: up to 1 Rocks.D.Xebec gains Unblockable this turn",
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
                    "keyword": "blockerless",
                    "target_kind": "own_leader_or_character",
                    "name_contains": XEBEC,
                    "optional": True,
                    "duration": "turn",
                    "count": 1,
                },
            ],
        ),
        _rocks_counter_buff(),
    ],
    "OP17-056": [
        ab(
            timing="on_play",
            summary="May rest 5 DON!!: return up to 1 Character cost≤6 to hand",
            ops=[
                {
                    "op": "rest_don",
                    "count": 5,
                    "owner": "self",
                    "as_cost": True,
                    "optional": True,
                },
                {
                    "op": "return_to_hand",
                    "target_kind": "any_character",
                    "optional": True,
                    "cost_lte": 6,
                },
            ],
        ),
        _rocks_counter_buff(),
    ],
    "OP17-057": [
        ab(
            timing="on_opponent_attack",
            summary="May rest this Stage and trash 1 hand: up to 1 Rocks Leader or Character +1000 this battle",
            ops=[
                {
                    "op": "rest_character",
                    "target_kind": "self",
                    "optional": True,
                    "as_cost": True,
                    "count": 1,
                },
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {
                    "op": "buff",
                    "amount": 1000,
                    "target_kind": "own_leader_or_character",
                    "trait_contains": ROCKS,
                    "optional": True,
                    "duration": "battle",
                },
            ],
        )
    ],
    "OP17-058": [
        _kaido058_debuff("when_attacking"),
        _kaido058_debuff("on_opponent_attack"),
    ],
    "OP17-059": [
        _blocker(),
        ab(
            timing="on_play",
            summary="May DON!! −1: draw 1 and KO up to 2 opp Characters cost≤2",
            ops=[
                {
                    "op": "return_don",
                    "count": 1,
                    "owner": "self",
                    "as_cost": True,
                    "optional": True,
                },
                {"op": "draw", "count": 1},
                {
                    "op": "ko",
                    "count": 2,
                    "target_kind": "opponent_character",
                    "cost_lte": 2,
                    "optional": True,
                },
            ],
        ),
    ],
    "OP17-060": [
        ab(
            timing="on_play",
            summary="If Leader Animal Kingdom Pirates: gain 1 active DON; then KO up to 1 opp Character power≤3000",
            ops=[
                {"op": "gain_don", "count": 1, "optional": True},
                {
                    "op": "ko",
                    "count": 1,
                    "target_kind": "opponent_character",
                    "power_lte": 3000,
                    "optional": True,
                },
            ],
            require_leader_trait=AKP,
        )
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
