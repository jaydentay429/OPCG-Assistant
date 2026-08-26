#!/usr/bin/env python3
"""Write battle encodings for OP17-061..075 into card_effect_overrides.json."""

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
KQJ = "King|Queen|Jack|金獸|奎因|傑克|金兽|奎因|杰克"


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


def _banish() -> dict:
    return ab(
        timing="your_turn",
        summary="Banish",
        ops=[
            {
                "op": "grant_keyword",
                "keyword": "banish",
                "target_kind": "self",
                "duration": "permanent",
            }
        ],
        confidence=0.95,
    )


def _on_opp_attack_trash_buff(*, amount: int) -> dict:
    return ab(
        timing="on_opponent_attack",
        summary=f"Once: may trash 1 hand: up to 1 own Leader or Character +{amount} this battle",
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
                "target_kind": "own_leader_or_character",
                "optional": True,
                "duration": "battle",
            },
        ],
        once=True,
    )


def _akp_on_play_debuff(amount: int) -> dict:
    return ab(
        timing="on_play",
        summary=f"DON!! −1 + AKP Leader: up to 1 opp Character {amount} this turn",
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
                "target_kind": "opponent_character",
                "optional": True,
                "duration": "turn",
            },
        ],
        require_leader_trait=AKP,
    )


ENTRIES: dict[str, list[dict]] = {
    "OP17-061": [
        ab(
            timing="on_play",
            summary="DON!! −1 + AKP Leader: add up to 1 deck top to life top",
            ops=[
                {
                    "op": "return_don",
                    "count": 1,
                    "owner": "self",
                    "as_cost": True,
                    "optional": True,
                },
                {
                    "op": "add_life",
                    "count": 1,
                    "optional": True,
                    "position": "top",
                },
            ],
            require_leader_trait=AKP,
        ),
        ab(
            timing="activate_main",
            summary="May trash this Character: play up to 1 King/Queen/Jack from hand",
            ops=[
                {
                    "op": "trash",
                    "target_kind": "self",
                    "optional": True,
                    "as_cost": True,
                },
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "name_contains": KQJ,
                    "from_zone": "hand",
                },
            ],
            cost_don=0,
            rest_self=False,
            once=False,
        ),
    ],
    "OP17-062": [
        _blocker(),
        ab(
            timing="on_don_returned",
            summary="Your Turn once: when DON!! returned, gain 1 active DON!! then set 1 DON!! active",
            ops=[
                {
                    "op": "gain_don",
                    "count": 1,
                    "optional": True,
                },
                {
                    "op": "active_don",
                    "count": 1,
                    "optional": True,
                },
            ],
            once=True,
            on_return_don_from_field_gte=1,
            require_your_turn=True,
        ),
    ],
    "OP17-063": [
        ab(
            timing="hand_cost",
            summary="Hand Characters without Counter gain +1000 Counter",
            ops=[
                {
                    "op": "hand_counter",
                    "amount": 1000,
                    "card_type": "character",
                    "all": True,
                    "add": True,
                    "require_no_counter": True,
                }
            ],
            confidence=0.95,
        ),
        ab(
            timing="activate_main",
            summary="Once: DON!! −1 if played this turn: negate then KO up to 1 opp Character cost≤6",
            ops=[
                {
                    "op": "return_don",
                    "count": 1,
                    "owner": "self",
                    "as_cost": True,
                    "optional": True,
                },
                {
                    "op": "negate_effects",
                    "count": 1,
                    "optional": True,
                    "duration": "turn",
                    "target_kind": "opponent_character",
                    "cost_lte": 6,
                },
                {
                    "op": "ko",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "cost_lte": 6,
                    "same_target_as_prior": True,
                },
            ],
            once=True,
            cost_don=0,
            rest_self=False,
            require_played_this_turn=True,
        ),
    ],
    "OP17-064": [
        _blocker(),
        _on_opp_attack_trash_buff(amount=2000),
    ],
    "OP17-065": [
        _banish(),
        ab(
            timing="on_play",
            summary="DON!! −1: draw 1; up to 2 opp Characters cost≤5 cannot attack until opp next End",
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
                    "op": "deny_attack",
                    "count": 2,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "cost_lte": 5,
                    "duration": "until_opp_turn_end",
                },
            ],
        ),
    ],
    "OP17-066": [
        ab(
            timing="on_play",
            summary="DON!! −1 if own Character cost≥10: draw 2 and trash 1 hand",
            ops=[
                {
                    "op": "return_don",
                    "count": 1,
                    "owner": "self",
                    "as_cost": True,
                    "optional": True,
                },
                {"op": "draw", "count": 2},
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": False,
                    "owner": "self",
                },
            ],
            require_own_char_cost_gte=10,
            optional=True,
            may_activate=True,
        ),
    ],
    "OP17-067": [
        ab(
            timing="on_play",
            summary="DON!! −1 if own Character cost≥10: rest up to 1 opp Character",
            ops=[
                {
                    "op": "return_don",
                    "count": 1,
                    "owner": "self",
                    "as_cost": True,
                    "optional": True,
                },
                {
                    "op": "rest_opponent_character",
                    "count": 1,
                    "optional": True,
                },
            ],
            require_own_char_cost_gte=10,
            optional=True,
            may_activate=True,
        ),
    ],
    "OP17-068": [
        ab(
            timing="when_attacking",
            summary="May trash 2 hand: if AKP Leader, gain up to 2 rested DON!!",
            ops=[
                {
                    "op": "trash_hand",
                    "count": 2,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {
                    "op": "gain_don",
                    "count": 2,
                    "optional": True,
                    "as_rested": True,
                },
            ],
            require_leader_trait=AKP,
        ),
    ],
    "OP17-069": [
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
        _akp_on_play_debuff(-2000),
    ],
    "OP17-070": [],
    "OP17-071": [
        ab(
            timing="on_play",
            summary="DON!! −1: KO up to 2 opp Characters cost≤2",
            ops=[
                {
                    "op": "return_don",
                    "count": 1,
                    "owner": "self",
                    "as_cost": True,
                    "optional": True,
                },
                {
                    "op": "ko",
                    "count": 2,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "cost_lte": 2,
                },
            ],
        ),
        ab(
            timing="trigger",
            summary="Play this card",
            ops=[
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": False,
                    "from_zone": "hand",
                    "self_card": True,
                }
            ],
            confidence=0.95,
        ),
    ],
    "OP17-072": [
        _blocker(),
        _on_opp_attack_trash_buff(amount=1000),
    ],
    "OP17-073": [
        ab(
            timing="on_play",
            summary="May trash 1 hand: if AKP Leader, gain 1 active DON!!",
            ops=[
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {
                    "op": "gain_don",
                    "count": 1,
                    "optional": True,
                },
            ],
            require_leader_trait=AKP,
        ),
    ],
    "OP17-074": [
        _blocker(),
        ab(
            timing="on_play",
            summary="Gain up to 1 rested DON!!",
            ops=[
                {
                    "op": "gain_don",
                    "count": 1,
                    "optional": True,
                    "as_rested": True,
                }
            ],
        ),
    ],
    "OP17-075": [
        ab(
            timing="on_play",
            summary="DON!! −2: trash 1 card from opponent's hand",
            ops=[
                {
                    "op": "return_don",
                    "count": 2,
                    "owner": "self",
                    "as_cost": True,
                    "optional": True,
                },
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": False,
                    "owner": "opponent",
                },
            ],
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
