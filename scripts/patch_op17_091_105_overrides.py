#!/usr/bin/env python3
"""Write battle encodings for OP17-091..105 (and Elbaph both-turn auras) into overrides."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

ELBAPH = "Elbaph|艾爾巴夫|艾尔巴夫"
BMP = "Big Mom Pirates|BIG MOM海賊團|BIG MOM海贼团"
DORRY = "Dorry|多利"
OVEN = "Charlotte Oven|夏洛特・歐文|夏洛特·欧文"
COST12 = 12


def ab(**kwargs):
    kwargs.setdefault("status", "compiled")
    kwargs.setdefault("confidence", 0.9)
    return kwargs


def _both_turns(**kwargs) -> list[dict]:
    return [
        ab(timing="your_turn", **kwargs),
        ab(timing="opponent_turn", **kwargs),
    ]


def _cost12_buff() -> list[dict]:
    return _both_turns(
        summary=f"If field Character cost≥{COST12}, this Character +3000",
        ops=[{"op": "buff_self", "amount": 3000}],
        require_field_char_cost_gte=COST12,
    )


def _grant_cost12() -> list[dict]:
    return _both_turns(
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


def _elbaph_cost12() -> list[dict]:
    return _both_turns(
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


def _trigger_play_this() -> dict:
    return ab(
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
    )


def _leader_counter(amount: int) -> dict:
    return ab(
        timing="counter_event",
        summary=f"Leader +{amount} this battle",
        ops=[
            {
                "op": "buff",
                "amount": amount,
                "target_kind": "leader",
                "optional": True,
                "duration": "battle",
            }
        ],
    )


# Also refresh Elbaph cost/power/Blocker auras so they apply on both turns.
ENTRIES: dict[str, list[dict]] = {
    "OP17-079": _both_turns(
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
    ),
    "OP17-080": [
        *_cost12_buff(),
        _elbaph_search_on_play(),
    ],
    "OP17-081": [
        *_elbaph_cost12(),
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
                    "name_exclude": "Gerd|葛兒德|葛尔德",
                },
            ],
        ),
    ],
    "OP17-082": [
        *_cost12_buff(),
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
    "OP17-083": _both_turns(
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
    ),
    "OP17-085": [
        *_grant_cost12(),
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
                    "name_contains": "Brogy|布洛基|布罗基",
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
    "OP17-087": [
        *_cost12_buff(),
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
    "OP17-089": [
        *_grant_cost12(),
        _elbaph_search_on_play(),
    ],
    "OP17-090": [
        *_cost12_buff(),
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
    "OP17-091": [
        *_cost12_buff(),
        ab(
            timing="on_play",
            summary=f"If field Character cost≥{COST12}, opponent trashes 1 hand",
            ops=[
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": False,
                    "owner": "opponent",
                }
            ],
            require_field_char_cost_gte=COST12,
        ),
    ],
    "OP17-092": [
        *_grant_cost12(),
        ab(
            timing="on_play",
            summary="If Elbaph Leader: play up to 1 Dorry cost≤5 from hand/trash; cannot play Characters this turn",
            ops=[
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 5,
                    "name_contains": DORRY,
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
    "OP17-093": [
        *_both_turns(
            summary=f"If field Character cost≥{COST12}, this Character gains Rush",
            ops=[
                {
                    "op": "grant_keyword",
                    "keyword": "rush",
                    "target_kind": "self",
                    "duration": "permanent",
                }
            ],
            require_field_char_cost_gte=COST12,
        ),
        ab(
            timing="on_play",
            summary="Draw 1 and play up to 1 Character cost≤2 from trash",
            ops=[
                {"op": "draw", "count": 1},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 2,
                    "from_zone": "trash",
                },
            ],
        ),
    ],
    "OP17-094": _elbaph_cost12(),
    "OP17-095": [
        *_cost12_buff(),
        *_both_turns(
            summary="When own Character would be removed by opp effect, may place 3 trash to deck bottom instead",
            ops=[
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "own_filtered",
                    "cost": "trash_to_bottom",
                    "trash_count": 3,
                    "optional": True,
                }
            ],
        ),
    ],
    "OP17-096": [
        ab(
            timing="counter_event",
            summary=f"If field Character cost≥{COST12}, up to 1 own Leader or Character +4000 this battle",
            ops=[
                {
                    "op": "buff",
                    "amount": 4000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                }
            ],
            require_field_char_cost_gte=COST12,
        ),
        ab(
            timing="trigger",
            summary="Add up to 1 Elbaph card from trash to hand",
            ops=[
                {
                    "op": "add_from_trash",
                    "count": 1,
                    "optional": True,
                    "trait_contains": ELBAPH,
                }
            ],
        ),
    ],
    "OP17-097": [
        ab(
            timing="on_play",
            summary="All opp Characters −1 cost this turn",
            ops=[
                {
                    "op": "grant_cost",
                    "amount": -1,
                    "target_kind": "opponent_character",
                    "all": True,
                    "optional": False,
                    "duration": "turn",
                }
            ],
        ),
        _leader_counter(3000),
    ],
    "OP17-098": [
        ab(
            timing="on_play",
            summary=f"May rest 6 DON!!: if field Character cost≥{COST12}, KO up to 2 opp Characters cost≤6",
            ops=[
                {
                    "op": "rest_don",
                    "count": 6,
                    "owner": "self",
                    "as_cost": True,
                    "optional": True,
                },
                {
                    "op": "ko",
                    "count": 2,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "cost_lte": 6,
                },
            ],
            require_field_char_cost_gte=COST12,
        ),
        _leader_counter(3000),
    ],
    "OP17-099": [
        ab(
            timing="when_attacking",
            summary="May trash 1: opponent chooses — you trash 1 then add 1 life, or they trash 1 hand",
            ops=[
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {
                    "op": "choose_one",
                    "chooser": "opponent",
                    "options": [
                        {
                            "id": "tax_life",
                            "label": "廢棄發動者1張手牌，發動者加1點生命",
                            "ops": [
                                {
                                    "op": "trash_hand",
                                    "count": 1,
                                    "optional": False,
                                    "owner": "self",
                                },
                                {
                                    "op": "add_life",
                                    "count": 1,
                                    "optional": True,
                                    "position": "top",
                                },
                            ],
                        },
                        {
                            "id": "opp_trash",
                            "label": "廢棄選擇者1張手牌",
                            "ops": [
                                {
                                    "op": "trash_hand",
                                    "count": 1,
                                    "optional": False,
                                    "owner": "opponent",
                                }
                            ],
                        },
                    ],
                },
            ],
        )
    ],
    "OP17-100": [],
    "OP17-101": [
        ab(
            timing="activate_main",
            summary="Once: may life-to-hand top 1: up to 1 opp Character −3000 this turn",
            ops=[
                {
                    "op": "life_to_hand",
                    "count": 1,
                    "position": "top",
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
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
            cost_don=0,
            rest_self=False,
        ),
        ab(
            timing="trigger",
            summary="May trash 1 hand: KO up to 1 opp Character cost≤5",
            ops=[
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {
                    "op": "ko",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "cost_lte": 5,
                },
            ],
        ),
    ],
    "OP17-102": [
        ab(
            timing="on_ko",
            summary="Play up to 1 Character power≤4000 other than Charlotte Oven from trash",
            ops=[
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "power_lte": 4000,
                    "exclude_name": OVEN,
                    "from_zone": "trash",
                }
            ],
        ),
        _trigger_play_this(),
    ],
    "OP17-103": [
        ab(
            timing="on_play",
            summary="Your Turn + BMP Leader: add 1 deck top to life top; then up to 1 opp Character −3000 this turn",
            ops=[
                {
                    "op": "add_life",
                    "count": 1,
                    "optional": True,
                    "position": "top",
                },
                {
                    "op": "buff",
                    "amount": -3000,
                    "target_kind": "opponent_character",
                    "optional": True,
                    "duration": "turn",
                },
            ],
            require_leader_trait=BMP,
            require_your_turn=True,
        ),
        _trigger_play_this(),
    ],
    "OP17-104": [
        ab(
            timing="on_play",
            summary="Your Turn: may rest 2 DON!!; if BMP Leader, add 1 deck top to life top",
            ops=[
                {
                    "op": "rest_don",
                    "count": 2,
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
            require_leader_trait=BMP,
            require_your_turn=True,
        ),
        _trigger_play_this(),
    ],
    "OP17-105": [
        ab(
            timing="on_play",
            summary="May trash 1 Trigger from hand: return up to 1 opp Character with Trigger to hand",
            ops=[
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                    "require_trigger": True,
                },
                {
                    "op": "return_to_hand",
                    "count": 1,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "require_trigger": True,
                },
            ],
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
