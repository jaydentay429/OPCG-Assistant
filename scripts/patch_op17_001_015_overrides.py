#!/usr/bin/env python3
"""Write battle encodings for OP17-001..015 into card_effect_overrides.json."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_card_entry  # noqa: E402

NEWGATE = "Edward.Newgate|愛德華・紐蓋特|爱德华・纽盖特"
WB = "Whitebeard Pirates"
WANO = "Land of Wano"


def ab(**kwargs):
    kwargs.setdefault("status", "compiled")
    kwargs.setdefault("confidence", 0.9)
    return kwargs


ENTRIES: dict[str, list[dict]] = {
    "OP17-002": [
        ab(
            timing="opponent_turn",
            summary="[Opponent's Turn] This Character +3000",
            ops=[{"op": "buff_self", "amount": 3000}],
        )
    ],
    "OP17-003": [
        ab(
            timing="on_play",
            summary="If Leader is Edward.Newgate or Land of Wano: up to 1 opp rested Character −6000 this turn",
            ops=[
                {
                    "op": "buff",
                    "amount": -6000,
                    "target_kind": "opponent_character_rested",
                    "optional": True,
                    "duration": "turn",
                }
            ],
            require_leader_name=NEWGATE,
            require_leader_trait=WANO,
            require_leader_name_or_trait=True,
        )
    ],
    "OP17-004": [
        ab(
            timing="on_play",
            summary="Up to 1 own Land of Wano or Whitebeard Pirates Character gains Rush this turn",
            ops=[
                {
                    "op": "grant_keyword",
                    "keyword": "rush",
                    "target_kind": "own_character",
                    "optional": True,
                    "duration": "turn",
                    "trait_any": [WANO, WB],
                }
            ],
        )
    ],
    "OP17-005": [
        ab(
            timing="hand_cost",
            summary="If opponent has a Character with 10000 power or more, this card in hand −4 cost",
            ops=[{"op": "hand_cost_reduce", "amount": -4}],
            require_opp_char_power_gte=10000,
        ),
        ab(
            timing="on_play",
            summary="Your monocolored Leader's base power becomes 8000 until opponent's next End Phase",
            ops=[
                {
                    "op": "set_base_power",
                    "amount": 8000,
                    "target_kind": "leader",
                    "optional": False,
                    "duration": "until_opp_turn_end",
                }
            ],
            require_leader_monocolor=True,
        ),
    ],
    "OP17-007": [
        ab(
            timing="on_play",
            summary="If Leader is Edward.Newgate or Land of Wano: play up to 1 Land of Wano or Whitebeard Pirates Character power≤6000 from hand",
            ops=[
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "power_lte": 6000,
                    "trait_any": [WANO, WB],
                    "from_zone": "hand",
                }
            ],
            require_leader_name=NEWGATE,
            require_leader_trait=WANO,
            require_leader_name_or_trait=True,
        )
    ],
    "OP17-008": [
        ab(
            timing="on_play",
            summary="Your Edward.Newgate Leader's base power becomes 8000 until opponent's next End Phase",
            ops=[
                {
                    "op": "set_base_power",
                    "amount": 8000,
                    "target_kind": "leader",
                    "optional": False,
                    "duration": "until_opp_turn_end",
                }
            ],
            require_leader_name=NEWGATE,
        )
    ],
    "OP17-009": [
        ab(
            timing="opponent_turn",
            summary="[Opponent's Turn] This Character +3000",
            ops=[{"op": "buff_self", "amount": 3000}],
        ),
        ab(
            timing="on_play",
            summary="K.O. up to 1 opponent Character with 2000 base power or less",
            ops=[
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "base_power_lte": 2000,
                }
            ],
        ),
    ],
    "OP17-010": [
        ab(
            timing="activate_main",
            summary="Once: if opp Character 10000+ and no other Fossa, this gains Blocker and +2000 until opp next End Phase",
            ops=[
                {
                    "op": "grant_keyword",
                    "keyword": "blocker",
                    "target_kind": "self",
                    "duration": "until_opp_turn_end",
                },
                {"op": "buff_self", "amount": 2000, "duration": "until_opp_turn_end"},
            ],
            once=True,
            cost_don=0,
            rest_self=False,
            require_opp_char_power_gte=10000,
            require_no_other_name="Fossa",
        )
    ],
    "OP17-011": [
        ab(
            timing="when_attacking",
            summary="DON!! x2: up to 1 opp Character −4000 this turn",
            ops=[
                {
                    "op": "buff",
                    "amount": -4000,
                    "target_kind": "opponent_character",
                    "optional": True,
                    "duration": "turn",
                }
            ],
            require_don_attached_gte=2,
        )
    ],
    "OP17-012": [
        ab(
            timing="on_ko",
            summary="Play up to 1 cost-1 Whitebeard Pirates card from hand",
            ops=[
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_eq": 1,
                    "trait_contains": WB,
                    "from_zone": "hand",
                }
            ],
        )
    ],
    "OP17-013": [
        ab(
            timing="hand_cost",
            summary="If opponent has a Character with 10000 power or more, this card in hand −2 cost",
            ops=[{"op": "hand_cost_reduce", "amount": -2}],
            require_opp_char_power_gte=10000,
        ),
        ab(
            timing="on_play",
            summary="If Leader is Edward.Newgate: up to 1 opp rested Character −6000 this turn",
            ops=[
                {
                    "op": "buff",
                    "amount": -6000,
                    "target_kind": "opponent_character_rested",
                    "optional": True,
                    "duration": "turn",
                }
            ],
            require_leader_name=NEWGATE,
        ),
    ],
    "OP17-014": [
        ab(
            timing="on_play",
            summary="K.O. up to 1 opponent Character with 2000 base power or less",
            ops=[
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "base_power_lte": 2000,
                }
            ],
        ),
        ab(
            timing="on_opponent_attack",
            summary="You may trash this Character: your Leader +1000 this battle",
            ops=[
                {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                {
                    "op": "buff",
                    "amount": 1000,
                    "target_kind": "leader",
                    "optional": False,
                    "duration": "battle",
                },
            ],
        ),
    ],
    "OP17-015": [
        ab(
            timing="your_turn",
            summary="If an own Character would leave by opponent's effect, you may K.O. this Character instead",
            ops=[
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "own_filtered",
                    "cost": "ko_self",
                    "exclude_self": True,
                    "optional": True,
                    "summary": "K.O. this Character instead of allied leave",
                }
            ],
        ),
        ab(
            timing="opponent_turn",
            summary="If an own Character would leave by opponent's effect, you may K.O. this Character instead",
            ops=[
                {
                    "op": "replace_leave",
                    "trigger": "opp_remove",
                    "target": "own_filtered",
                    "cost": "ko_self",
                    "exclude_self": True,
                    "optional": True,
                    "summary": "K.O. this Character instead of allied leave",
                }
            ],
        ),
        ab(
            timing="on_ko",
            summary="You may trash 1 Whitebeard Pirates from hand: play this Character from trash",
            ops=[
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                    "trait_contains": WB,
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
