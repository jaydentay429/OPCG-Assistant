#!/usr/bin/env python3
"""Deterministic semantic fixes v55: high leave/KO watchers + medium order/optional/gate batch.

Dual-writes library + overrides. Merges ids file across re-runs.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_card_entry, library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_ability, normalize_card_entry  # noqa: E402

OUT_IDS = ROOT / "meta" / "logs" / "ops_v55_fixed_ids.txt"
REBUILDS_PATH = ROOT / "meta" / "logs" / "ops_v55_rebuilds.json"

REBUILDS: dict[str, list[dict[str, Any]]] = {
    "OP10-042": [
        {
            "timing": "your_turn",
            "summary": "自己費用2以上擁有《多雷斯羅薩》特徵的角色卡全數費用+1。",
            "ops": [
                {
                    "op": "grant_cost",
                    "amount": 1,
                    "target_kind": "all_own",
                    "trait_contains": "Dressrosa",
                    "all": True,
                    "cost_gte": 2,
                    "duration": "permanent",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "opponent_turn",
            "summary": "自己費用2以上擁有《多雷斯羅薩》特徵的角色卡全數費用+1。",
            "ops": [
                {
                    "op": "grant_cost",
                    "amount": 1,
                    "target_kind": "all_own",
                    "trait_contains": "Dressrosa",
                    "all": True,
                    "cost_gte": 2,
                    "duration": "permanent",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "opponent_turn",
            "summary": "【對方回合中】【每回合1次】自己擁有《多雷斯羅薩》特徵的角色卡遭到KO時、或因對手的效果離開場上時，若自己的手牌在5張以下時，抽1張卡片。",
            "ops": [{"op": "draw", "count": 1}],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
            "require_hand_lte": 5,
            "on_own_trait_leave_or_ko": "Dressrosa",
        },
    ],
    "ST16-002": [
        {
            "timing": "your_turn",
            "summary": "Blocker",
            "ops": [
                {
                    "op": "grant_keyword",
                    "keyword": "blocker",
                    "target_kind": "self",
                    "duration": "permanent",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "on_opponent_attack",
            "summary": "【對方攻擊時】可以廢棄自己手牌中擁有《音樂》特徵任意張數的卡片。每廢棄1張卡片，1張自己的領航卡或角色卡，在這場對戰中，力量值+1000。",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 20,
                    "optional": True,
                    "as_cost": True,
                    "any_number": True,
                    "trait_contains": "Music",
                    "owner": "self",
                },
                {
                    "op": "buff",
                    "amount": 1000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                    "per_trash_cards": 1,
                    "per_choose": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP03-122": [
        {
            "timing": "on_play",
            "summary": "【登場時】將最多1張費用6以下的角色卡放回持有者的手牌。之後，抽2張卡片，並廢棄2張自己的手牌。",
            "ops": [
                {
                    "op": "return_to_hand",
                    "target_kind": "any_character",
                    "optional": True,
                    "cost_lte": 6,
                },
                {"op": "draw", "count": 2},
                {"op": "trash_hand", "count": 2, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "EB02-007": [
        {
            "timing": "activate_main",
            "summary": "【主要】合計最多3張自己的領航卡或角色卡，在這個回合，力量值+1000。之後，KO最多1張對手力量值3000以下的角色卡。",
            "ops": [
                {
                    "op": "buff",
                    "amount": 1000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "count": 3,
                    "duration": "turn",
                },
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "power_lte": 3000,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "【觸發器】KO最多1張對手力量值4000以下的角色卡。",
            "ops": [
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "power_lte": 4000,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "EB03-053": [
        {
            "timing": "on_play",
            "summary": "【登場時】附加最多1張休息狀態的咚‼卡在自己的領航卡。",
            "ops": [
                {
                    "op": "attach_don",
                    "count": 1,
                    "as_rested": True,
                    "target_kind": "leader",
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "on_play",
            "summary": "之後，若對手的生命值卡在3張以上時，將最多1張對手生命值區上面的卡片加入持有者的手牌。",
            "ops": [
                {
                    "op": "life_to_hand",
                    "count": 1,
                    "position": "top",
                    "optional": True,
                    "owner": "opponent",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_opp_life_gte": 3,
        },
        {
            "timing": "on_ko",
            "summary": "【KO時】可將1張自己生命值區上面的卡片翻成正面朝上：使最多1張自己手牌中力量值6000以下的角色卡登場。",
            "ops": [
                {
                    "op": "flip_life",
                    "face": "up",
                    "position": "top",
                    "optional": True,
                    "as_cost": True,
                },
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "power_lte": 6000,
                    "from_zone": "hand",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "EB04-059": [
        {
            "timing": "activate_main",
            "summary": "【主要】可將1張自己生命值區上面的卡片翻成正面朝上：若自己的角色卡比對手的角色卡少時，KO最多1張對手費用6以下的角色卡和最多1張費用5以下的角色卡。",
            "ops": [
                {
                    "op": "flip_life",
                    "face": "up",
                    "position": "top",
                    "optional": True,
                    "as_cost": True,
                },
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "cost_lte": 6,
                },
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "cost_lte": 5,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_chars_deficit_gte": 1,
        },
        {
            "timing": "trigger",
            "summary": "【觸發器】抽2張卡片，並廢棄1張自己的手牌。",
            "ops": [
                {"op": "draw", "count": 2},
                {"op": "trash_hand", "count": 1, "optional": False, "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "ST24-004": [
        {
            "timing": "on_play",
            "summary": "【登場時】將最多1張對手的角色卡置為休息狀態，該張角色卡在下一個對手的重整階段無法為活動狀態。",
            "ops": [
                {
                    "op": "rest_character",
                    "count": 1,
                    "target_kind": "opponent_character",
                    "optional": True,
                },
                {
                    "op": "skip_untap",
                    "count": 1,
                    "target_kind": "opponent_character",
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
        {
            "timing": "on_play",
            "summary": "之後，若場上有2張以上對手休息狀態的角色卡時，自己的領航卡，在下一個對手結束階段結束前，力量值+2000。",
            "ops": [
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "leader",
                    "optional": False,
                    "duration": "until_opp_turn_end",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_opp_rested_chars_gte": 2,
        },
    ],
    "OP13-066": [
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
            "timing": "on_play",
            "summary": "【登場時】若有自己已附加的咚‼卡時，將最多1張對手費用5以下的角色卡置為休息狀態。之後，這回合結束時，從咚‼卡組追加最多1張活動狀態的咚‼卡。",
            "ops": [
                {
                    "op": "rest_character",
                    "count": 1,
                    "target_kind": "opponent_character",
                    "optional": True,
                    "cost_lte": 5,
                },
                {"op": "gain_don", "count": 1, "optional": True, "at_end_of_turn": True},
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_don_attached_gte": 1,
        },
    ],
    "ST13-007": [
        {
            "timing": "activate_main",
            "summary": "【啟動主要】可將這張角色卡放置在廢棄區：公開1張自己生命值區上面的卡片，若該張卡片是費用5的「薩波」時，也可登場。若登場時，最多1張自己的領航卡，在下一個對手回合結束前，力量值+2000。",
            "ops": [
                {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                {"op": "reveal_life", "count": 1, "position": "top", "optional": False},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_eq": 5,
                    "name_contains": "薩波",
                    "from_zone": "life",
                },
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "leader",
                    "optional": True,
                    "duration": "until_opp_turn_end",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "cost_don": 0,
            "rest_self": False,
            "once": False,
        }
    ],
    "ST13-017": [
        {
            "timing": "counter_event",
            "summary": "【反擊】最多1張自己的領航卡或角色卡，在這場對戰中，力量值+4000。之後，查看自己全數的生命值卡，並依任意順序放置。",
            "ops": [
                {
                    "op": "buff",
                    "amount": 4000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                },
                {"op": "reorder_life", "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "【觸發器】可將1張自己生命值區上面或下面的卡片加入手牌：將最多1張自己的手牌加入生命值區上面。",
            "ops": [
                {
                    "op": "life_to_hand",
                    "count": 1,
                    "position": "top_or_bottom",
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {"op": "hand_to_life", "count": 1, "optional": True, "position": "top"},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP04-075": [
        {
            "timing": "counter_event",
            "summary": "【反擊】最多1張自己的領航卡或角色卡，在這場對戰中，力量值+6000。",
            "ops": [
                {
                    "op": "buff",
                    "amount": 6000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "counter_event",
            "summary": "之後，若自己的生命值卡在2張以下時，從咚‼卡組追加最多1張休息狀態的咚‼卡。",
            "ops": [{"op": "gain_don", "count": 1, "as_rested": True, "optional": True}],
            "status": "compiled",
            "confidence": 0.95,
            "require_life_lte": 2,
        },
        {
            "timing": "trigger",
            "summary": "【觸發器】從咚‼卡組追加最多1張活動狀態的咚‼卡。",
            "ops": [{"op": "gain_don", "count": 1, "optional": True}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP15-056": [
        {
            "timing": "activate_main",
            "summary": "【主要】抽2張卡片。之後，自己的領航卡「魯西」，在這個回合，獲得【雙重攻擊】，力量值+3000。",
            "ops": [
                {"op": "draw", "count": 2},
                {
                    "op": "grant_keyword",
                    "keyword": "double_attack",
                    "target_kind": "leader",
                    "name_contains": "Lucy",
                    "duration": "turn",
                    "optional": False,
                },
                {
                    "op": "buff",
                    "amount": 3000,
                    "target_kind": "leader",
                    "name_contains": "Lucy",
                    "duration": "turn",
                    "optional": False,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "【觸發器】抽2張卡片。",
            "ops": [{"op": "draw", "count": 2}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP01-118": [
        {
            "timing": "counter_event",
            "summary": "【反擊】咚!!-2：最多1張自己的領航卡或角色卡，在這場對戰中，力量值+2000。之後，抽1張卡片。",
            "ops": [
                {"op": "return_don", "count": 2, "owner": "self", "as_cost": True},
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                },
                {"op": "draw", "count": 1},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "【觸發器】從咚!!卡組追加最多1張活動狀態的咚!!卡。",
            "ops": [{"op": "gain_don", "count": 1, "optional": True}],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP03-019": [
        {
            "timing": "activate_main",
            "summary": "【主要】自己的領航卡，在這個回合，力量值+4000。",
            "ops": [
                {
                    "op": "buff",
                    "amount": 4000,
                    "target_kind": "leader",
                    "optional": False,
                    "duration": "turn",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "【觸發器】最多1張對手的領航卡或角色卡，在這個回合，力量值-10000。",
            "ops": [
                {
                    "op": "buff",
                    "amount": -10000,
                    "target_kind": "opponent_leader_or_character",
                    "optional": True,
                    "duration": "turn",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "EB01-057": [
        {
            "timing": "on_ko",
            "summary": "這張角色卡因對手的效果遭到KO時，將最多1張自己卡組上面的卡片加入生命值區上面。",
            "ops": [{"op": "add_life", "count": 1, "optional": True}],
            "status": "compiled",
            "confidence": 0.95,
            "on_ko_by_opp_effect": True,
        },
        {
            "timing": "your_turn",
            "summary": "Blocker",
            "ops": [
                {
                    "op": "grant_keyword",
                    "keyword": "blocker",
                    "target_kind": "self",
                    "duration": "permanent",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "EB04-061": [
        {
            "timing": "hand_cost",
            "summary": "若自己的生命值卡在1張以下時，手牌中這張卡片的費用-1。",
            "ops": [{"op": "hand_cost_reduce", "amount": 1}],
            "status": "compiled",
            "confidence": 0.95,
            "require_life_lte": 1,
        },
        {
            "timing": "on_play",
            "summary": "【登場時】可以廢棄1張自己的手牌：自己的領航卡，在下一個對手結束階段結束前，力量值+2000。之後，這張角色卡，在下一個對手結束階段結束前，獲得【防禦】。",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "leader",
                    "optional": False,
                    "duration": "until_opp_turn_end",
                },
                {
                    "op": "grant_keyword",
                    "keyword": "blocker",
                    "target_kind": "self",
                    "duration": "until_opp_turn_end",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP13-076": [
        {
            "timing": "activate_main",
            "summary": "【主要】可將5張自己的咚‼卡置為休息狀態：若有自己已附加的咚‼卡時，最多1張對手的角色卡，在這個回合，力量值-8000。",
            "ops": [
                {"op": "rest_don", "count": 5, "owner": "self", "as_cost": True},
                {
                    "op": "buff",
                    "amount": -8000,
                    "target_kind": "opponent_character",
                    "optional": True,
                    "count": 1,
                    "duration": "turn",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_attached_gte": 1,
        },
        {
            "timing": "counter_event",
            "summary": "【反擊】可以廢棄1張自己的手牌：最多1張自己的領航卡或角色卡，在這場對戰中，力量值+3000。",
            "ops": [
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
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP13-003": [
        {
            "timing": "on_don_attached",
            "summary": "若自己場上有咚‼卡時，將1張在自己咚‼階段放置的咚‼卡附加在自己的領航卡。",
            "ops": [
                {
                    "op": "attach_don",
                    "count": 1,
                    "target_kind": "leader",
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
            "require_don_field_gte": 1,
        },
        {
            "timing": "your_turn",
            "summary": "若自己場上的咚‼卡在9張以下時，這張領航卡的力量值-2000。",
            "ops": [{"op": "buff_self", "amount": -2000}],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_field_lte": 9,
        },
        {
            "timing": "opponent_turn",
            "summary": "若自己場上的咚‼卡在9張以下時，這張領航卡的力量值-2000。",
            "ops": [{"op": "buff_self", "amount": -2000}],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_field_lte": 9,
        },
    ],
}


def _rebuild(cid: str, abilities: list[dict[str, Any]]) -> dict[str, Any]:
    cleaned = [a for a in (normalize_ability(x) for x in abilities) if a]
    return normalize_card_entry(cid, {"version": 1, "abilities": cleaned})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    REBUILDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    REBUILDS_PATH.write_text(json.dumps(REBUILDS, ensure_ascii=False, indent=2) + "\n")

    lib_path, ovr_path = library_paths()
    raw = json.loads(lib_path.read_text())
    cards = raw.get("cards") or {}
    idx = json.loads((ROOT / "index" / "cards_by_id.json").read_text())

    bases = list(REBUILDS.keys())
    targets: list[str] = []
    for cid in list(cards.keys()) + list(idx.keys()):
        for base in sorted(bases, key=len, reverse=True):
            if cid == base or cid.startswith(base + "-"):
                targets.append(cid)
                break
    for base in bases:
        if base not in targets:
            targets.append(base)

    seen: set[str] = set()
    ordered: list[str] = []
    for cid in targets:
        if cid not in seen:
            seen.add(cid)
            ordered.append(cid)

    ovr = json.loads(ovr_path.read_text()) if ovr_path.exists() else {"cards": {}}
    overrides = ovr.get("cards") or {}

    fixed: list[str] = []
    for cid in ordered:
        base = None
        for b in sorted(REBUILDS, key=len, reverse=True):
            if cid == b or cid.startswith(b + "-"):
                base = b
                break
        if not base:
            continue
        out = _rebuild(cid, [dict(a) for a in REBUILDS[base]])
        prev = cards.get(cid) or get_card_entry(cid) or {"abilities": []}
        if json.dumps(prev.get("abilities"), sort_keys=True, ensure_ascii=False) == json.dumps(
            out.get("abilities"), sort_keys=True, ensure_ascii=False
        ):
            if cid not in fixed:
                fixed.append(cid)
            continue
        if args.dry_run:
            fixed.append(cid)
            continue
        cards[cid] = out
        overrides[cid] = out
        fixed.append(cid)

    if args.dry_run:
        print(json.dumps({"dry_run": True, "would_fix": len(fixed), "ids": fixed}, ensure_ascii=False))
        return 0

    raw["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    lib_path.write_text(json.dumps(raw, ensure_ascii=False, separators=(",", ":")))
    ovr["cards"] = overrides
    ovr["generated_at"] = raw["generated_at"]
    ovr_path.write_text(json.dumps(ovr, ensure_ascii=False, separators=(",", ":")))
    reload_effect_library(force=True)

    OUT_IDS.parent.mkdir(parents=True, exist_ok=True)
    prev_ids = (
        [ln.strip() for ln in OUT_IDS.read_text().splitlines() if ln.strip()] if OUT_IDS.exists() else []
    )
    merged: list[str] = []
    seen_ids: set[str] = set()
    for cid in prev_ids + fixed:
        if cid not in seen_ids:
            seen_ids.add(cid)
            merged.append(cid)
    OUT_IDS.write_text("\n".join(merged) + ("\n" if merged else ""))
    print(
        json.dumps(
            {"fixed": len(fixed), "merged": len(merged), "ids_file": str(OUT_IDS), "ids": fixed},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
