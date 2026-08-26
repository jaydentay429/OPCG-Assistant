#!/usr/bin/env python3
"""Write battle encodings for OP17-076..090 into card_effect_overrides.json."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

AKP = "Animal Kingdom Pirates|百獸海賊團|百兽海贼团"
ELBAPH = "Elbaph|艾爾巴夫|艾尔巴夫"
GERD_EX = "Gerd|葛兒德|葛尔德"
BROGY = "Brogy|布洛基|布罗基"
COST12 = 12


def ab(**kwargs):
    kwargs.setdefault("status", "compiled")
    kwargs.setdefault("confidence", 0.9)
    return kwargs


def _counter_trash_buff(*, amount: int, target_kind: str = "own_leader_or_character") -> dict:
    return ab(
        timing="counter_event",
        summary=f"May trash 1 hand: up to 1 own Leader or Character +{amount} this battle",
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
                "amount": amount,
                "target_kind": target_kind,
                "optional": True,
                "duration": "battle",
            },
        ],
    )


def _counter_return_don_leader_buff(*, amount: int) -> dict:
    return ab(
        timing="counter_event",
        summary=f"DON!! −1: Leader +{amount} this battle",
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
                "amount": amount,
                "target_kind": "leader",
                "optional": True,
                "duration": "battle",
            },
        ],
    )


def _akp_main_gain_rested_don(*, rest_don: int) -> dict:
    return ab(
        timing="on_play",
        summary=f"May rest {rest_don} DON!! and trash 2 hand: if AKP Leader, gain up to 3 rested DON!!",
        ops=[
            {
                "op": "rest_don",
                "count": rest_don,
                "owner": "self",
                "as_cost": True,
            },
            {
                "op": "trash_hand",
                "count": 2,
                "as_cost": True,
                "owner": "self",
            },
            {
                "op": "gain_don",
                "count": 3,
                "optional": True,
                "as_rested": True,
            },
        ],
        require_leader_trait=AKP,
    )


def _cost12_buff_self() -> dict:
    return ab(
        timing="your_turn",
        summary=f"If field Character cost≥{COST12}, this Character +3000",
        ops=[{"op": "buff_self", "amount": 3000}],
        require_field_char_cost_gte=COST12,
    )


def _grant_cost12() -> dict:
    return ab(
        timing="your_turn",
        summary="This Character +12 cost",
        ops=[
            {
                "op": "grant_cost",
                "amount": 12,
                "target_kind": "self",
                "duration": "permanent",
            }
        ],
        confidence=0.95,
    )


def _elbaph_search_on_play() -> dict:
    return ab(
        timing="on_play",
        summary="Look top 3; reveal up to 1 Elbaph to hand; trash rest",
        ops=[
            {
                "op": "search_deck",
                "trait_contains": ELBAPH,
                "top_n": 3,
                "max_add": 1,
                "trash_rest": True,
                "order_bottom": False,
                "destination": "hand",
            }
        ],
    )


ENTRIES: dict[str, list[dict]] = {
    "OP17-076": [
        _counter_trash_buff(amount=3000),
        ab(
            timing="trigger",
            summary="DON!! −1: draw 2",
            ops=[
                {
                    "op": "return_don",
                    "count": 1,
                    "owner": "self",
                    "as_cost": True,
                },
                {"op": "draw", "count": 2},
            ],
            confidence=0.95,
        ),
    ],
    "OP17-077": [
        _akp_main_gain_rested_don(rest_don=3),
        _counter_return_don_leader_buff(amount=4000),
    ],
    "OP17-078": [
        _akp_main_gain_rested_don(rest_don=2),
        ab(
            timing="counter_event",
            summary="Up to 1 own Leader or Character +4000 this battle",
            ops=[
                {
                    "op": "buff",
                    "amount": 4000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                }
            ],
        ),
    ],
    "OP17-079": [
        ab(
            timing="your_turn",
            summary="Your Characters with cost 12+ gain Blocker",
            ops=[
                {
                    "op": "grant_keyword",
                    "keyword": "blocker",
                    "target_kind": "own_character",
                    "cost_gte": COST12,
                    "duration": "permanent",
                    "all": True,
                }
            ],
            confidence=0.95,
        )
    ],
    "OP17-080": [
        _cost12_buff_self(),
        _elbaph_search_on_play(),
    ],
    "OP17-081": [
        ab(
            timing="your_turn",
            summary="If Elbaph Leader, this Character +12 cost",
            ops=[
                {
                    "op": "grant_cost",
                    "amount": 12,
                    "target_kind": "self",
                    "duration": "permanent",
                }
            ],
            require_leader_trait=ELBAPH,
            confidence=0.95,
        ),
        ab(
            timing="on_play",
            summary="May trash 1 hand: add up to 1 Character cost≤8 other than Gerd from trash",
            ops=[
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {
                    "op": "add_from_trash",
                    "count": 1,
                    "optional": True,
                    "card_type": "character",
                    "cost_lte": 8,
                    "name_exclude": GERD_EX,
                },
            ],
        ),
    ],
    "OP17-082": [
        _cost12_buff_self(),
        ab(
            timing="on_play",
            summary="Draw 2 and trash 2 hand",
            ops=[
                {"op": "draw", "count": 2},
                {
                    "op": "trash_hand",
                    "count": 2,
                    "optional": False,
                    "owner": "self",
                },
            ],
        ),
    ],
    "OP17-083": [
        ab(
            timing="your_turn",
            summary=f"If field Character cost≥{COST12}, this Character gains Blocker and +3000",
            ops=[
                {
                    "op": "grant_keyword",
                    "keyword": "blocker",
                    "target_kind": "self",
                    "duration": "permanent",
                },
                {"op": "buff_self", "amount": 3000},
            ],
            require_field_char_cost_gte=COST12,
        )
    ],
    "OP17-084": [
        ab(
            timing="on_play",
            summary=f"If field Character cost≥{COST12}, up to 1 own Character gains Unblockable this turn",
            ops=[
                {
                    "op": "grant_keyword",
                    "keyword": "blockerless",
                    "target_kind": "own_character",
                    "duration": "turn",
                    "optional": True,
                    "count": 1,
                }
            ],
            require_field_char_cost_gte=COST12,
        )
    ],
    "OP17-085": [
        _grant_cost12(),
        ab(
            timing="on_play",
            summary="If Elbaph Leader: play up to 1 Brogy cost≤5 from hand/trash; cannot play Characters this turn",
            ops=[
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 5,
                    "name_contains": BROGY,
                    "from_zone": "hand_or_trash",
                },
                {
                    "op": "cannot_play_from_hand",
                    "duration": "turn",
                    "card_type": "character",
                },
            ],
            require_leader_trait=ELBAPH,
        ),
    ],
    "OP17-086": [
        ab(
            timing="on_play",
            summary="May trash 1 Elbaph from hand: draw 2",
            ops=[
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                    "trait_contains": ELBAPH,
                },
                {"op": "draw", "count": 2},
            ],
        )
    ],
    "OP17-087": [
        _cost12_buff_self(),
        ab(
            timing="on_play",
            summary=f"If field Character cost≥{COST12}, up to 1 opp Character −3000 this turn",
            ops=[
                {
                    "op": "buff",
                    "amount": -3000,
                    "target_kind": "opponent_character",
                    "optional": True,
                    "duration": "turn",
                }
            ],
            require_field_char_cost_gte=COST12,
        ),
    ],
    "OP17-088": [],
    "OP17-089": [
        _grant_cost12(),
        _elbaph_search_on_play(),
    ],
    "OP17-090": [
        _cost12_buff_self(),
        ab(
            timing="on_play",
            summary=f"If field Character cost≥{COST12}, KO up to 1 opp Character cost≤2",
            ops=[
                {
                    "op": "ko",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "cost_lte": 2,
                }
            ],
            require_field_char_cost_gte=COST12,
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
