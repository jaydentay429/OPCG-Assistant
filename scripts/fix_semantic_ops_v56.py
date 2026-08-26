#!/usr/bin/env python3
"""Deterministic semantic fixes v56: P-083 high cost-order + medium batch.

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

OUT_IDS = ROOT / "meta" / "logs" / "ops_v56_fixed_ids.txt"
REBUILDS_PATH = ROOT / "meta" / "logs" / "ops_v56_rebuilds.json"

# P-083: official EN + P1/R1 Chinese = trash Character as cost → −1000 → draw.
# (Base Chinese HK catalog text omits the colon-cost; encode the corrected paper.)
REBUILDS: dict[str, list[dict[str, Any]]] = {
    "P-083": [
        {
            "timing": "when_attacking",
            "summary": "【咚‼×1】【攻擊時】可以廢棄1張自己手牌中的角色卡：最多1張對手的角色卡，在這個回合，力量值-1000。之後，抽1張卡片。",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "card_type": "character",
                    "owner": "self",
                },
                {
                    "op": "buff",
                    "amount": -1000,
                    "target_kind": "opponent_character",
                    "optional": True,
                    "duration": "turn",
                },
                {"op": "draw", "count": 1},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_attached_gte": 1,
        }
    ],
    "OP10-100": [
        {
            "timing": "when_attacking",
            "summary": "【咚‼×1】【攻擊時】將最多1張對手費用數值在雙方生命值卡合計張數以下的角色卡置為休息狀態。",
            "ops": [
                {
                    "op": "rest_opponent_character",
                    "count": 1,
                    "optional": True,
                    "cost_lte_total_life": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_attached_gte": 1,
        },
        {
            "timing": "trigger",
            "summary": "【觸發器】若自己的領航卡擁有《革命軍》特徵、雙方的生命值卡合計張數在5張以下時，使這張卡片登場。",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                    "self_card": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_total_life_lte": 5,
            "require_leader_trait": "Revolutionary Army",
        },
    ],
    "OP14-033": [
        {
            "timing": "on_play",
            "summary": "【登場時】最多2張對手費用5以下的角色卡，在下一個對手結束階段結束前，無法置為休息狀態。",
            "ops": [
                {
                    "op": "deny_rest",
                    "count": 2,
                    "optional": True,
                    "target_kind": "opponent_character",
                    "cost_lte": 5,
                    "duration": "until_opp_turn_end",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "on_ko",
            "summary": "【KO時】可將1張自己的卡片置為休息狀態：使最多1張自己手牌中費用5以下綠色的角色卡登場。",
            "ops": [
                {
                    "op": "rest_character",
                    "target_kind": "own_character",
                    "optional": True,
                    "as_cost": True,
                    "count": 1,
                    "include_leader": True,
                },
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 5,
                    "color": "green",
                    "from_zone": "hand",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP06-062": [
        {
            "timing": "on_play",
            "summary": "【登場時】咚‼-1,可以廢棄2張自己的手牌：使最多4張自己廢棄區中卡片名稱不同力量值4000以下擁有《杰爾馬66》特徵的卡片登場。",
            "ops": [
                {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                {
                    "op": "trash_hand",
                    "count": 2,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {
                    "op": "play_from_hand",
                    "count": 4,
                    "card_type": "character",
                    "optional": True,
                    "power_lte": 4000,
                    "trait_contains": "GERMA 66",
                    "different_names": True,
                    "from_zone": "trash",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "activate_main",
            "summary": "【啟動主要】【每回合1次】咚‼-1：將最多1張對手的咚‼卡置為休息狀態。",
            "ops": [
                {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                {"op": "rest_don", "count": 1, "owner": "opponent", "optional": True},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
            "cost_don": 0,
            "rest_self": False,
        },
    ],
    "OP10-087": [
        {
            "timing": "activate_main",
            "summary": "【啟動主要】可將這張角色卡和1張自己擁有《多雷斯羅薩》特徵的領航卡或舞台卡置為休息狀態：若對手的手牌有5張以上時，對手廢棄1張自身的手牌。之後，將2張自己卡組上面的卡片放置在廢棄區。",
            "ops": [
                {
                    "op": "rest_character",
                    "target_kind": "self",
                    "optional": True,
                    "as_cost": True,
                },
                {
                    "op": "rest_character",
                    "target_kind": "own_character",
                    "optional": True,
                    "as_cost": True,
                    "trait_contains": "Dressrosa",
                    "include_leader": True,
                    "card_type": "leader_or_stage",
                },
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": False,
                    "owner": "opponent",
                },
                {"op": "trash_deck_top", "count": 2, "optional": False},
            ],
            "status": "compiled",
            "confidence": 0.9,
            "cost_don": 0,
            "rest_self": False,
            "once": False,
            "require_opp_hand_gte": 5,
        }
    ],
    "OP10-027": [
        {
            "timing": "activate_main",
            "summary": "【啟動主要】可將這張角色卡和1張自己廢棄區中力量值1000的「錦右衛門」依任意順序放置在卡組下面：使最多1張自己手牌中費用6的「錦右衛門」登場。",
            "ops": [
                {
                    "op": "return_to_bottom",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "target_kind": "self",
                    "order_any": True,
                },
                {
                    "op": "trash_to_bottom",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                    "card_type": "character",
                    "name_contains": "錦右衛門",
                    "power_eq": 1000,
                    "order_any": True,
                },
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_eq": 6,
                    "name_contains": "錦右衛門",
                    "from_zone": "hand",
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "cost_don": 0,
            "rest_self": False,
            "once": False,
        }
    ],
    "OP04-057": [
        {
            "timing": "counter_event",
            "summary": "【反擊】最多1張自己的領航卡或角色卡，在這場對戰中，力量值+4000。之後，將最多1張費用1以下的角色卡放置在持有者的卡組下面。",
            "ops": [
                {
                    "op": "buff",
                    "amount": 4000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                },
                {
                    "op": "return_to_bottom",
                    "count": 1,
                    "optional": True,
                    "target_kind": "any_character",
                    "cost_lte": 1,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "【觸發器】將最多1張費用6以下的角色卡放回持有者的手牌。",
            "ops": [
                {
                    "op": "return_to_hand",
                    "target_kind": "any_character",
                    "optional": True,
                    "cost_lte": 6,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "ST13-012": [
        {
            "timing": "on_play",
            "summary": "【登場時】可將1張自己生命值區上面或下面的卡片加入手牌：查看自己全數的生命值卡，並依任意順序放置。",
            "ops": [
                {
                    "op": "life_to_hand",
                    "count": 1,
                    "position": "top_or_bottom",
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {"op": "reorder_life", "owner": "self"},
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "ST19-004": [
        {
            "timing": "opponent_turn",
            "summary": "【咚‼×1】【對方回合中】這張角色卡的費用+4。",
            "ops": [{"op": "grant_cost", "amount": 4, "target_kind": "self", "duration": "permanent"}],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_attached_gte": 1,
        },
        {
            "timing": "activate_main",
            "summary": "【啟動主要】【每回合1次】可將1張自己廢棄區中的卡片放置在卡組下面：附加最多1張休息狀態的咚‼卡在1張自己的領航卡或角色卡。",
            "ops": [
                {
                    "op": "trash_to_bottom",
                    "count": 1,
                    "optional": True,
                    "owner": "self",
                    "card_type": "any",
                    "order_any": True,
                    "as_cost": True,
                },
                {
                    "op": "attach_don",
                    "count": 1,
                    "as_rested": True,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
            "cost_don": 0,
            "rest_self": False,
        },
    ],
    "ST13-003": [
        {
            "timing": "activate_main",
            "summary": "【咚‼×2】【啟動主要】【每回合1次】可以廢棄1張自己的手牌：若自己的生命值卡為0張時，將最多2張自己手牌或廢棄區中費用5的角色卡，以正面朝上加入自己的生命值區上面。",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {
                    "op": "hand_to_life",
                    "count": 2,
                    "optional": True,
                    "face": "up",
                    "position": "top",
                    "card_type": "character",
                    "cost_eq": 5,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
            "once": True,
            "cost_don": 0,
            "rest_self": False,
            "require_don_attached_gte": 2,
            "require_life_lte": 0,
        }
    ],
    "EB04-031": [
        {
            "timing": "your_turn",
            "summary": "若這張角色卡即將遭到KO時，可以替換成將1張自己場上的咚‼卡放回咚‼卡組。",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "ko",
                    "target": "self",
                    "cost": "return_don",
                    "don_count": 1,
                    "optional": True,
                    "summary": "Return 1 field DON!! instead of K.O.",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "activate_main",
            "summary": "【啟動主要】【每回合1次】若自己的領航卡擁有《百獸海賊團》特徵、場上沒有自己其他的角色卡「KING」時，從咚‼卡組追加最多1張活動狀態的咚‼卡，並再追加最多1張休息狀態的咚‼卡。",
            "ops": [
                {"op": "gain_don", "count": 1, "optional": True},
                {"op": "gain_don", "count": 1, "as_rested": True, "optional": True},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
            "cost_don": 0,
            "rest_self": False,
            "require_leader_trait": "百獸海賊團",
            "require_no_other_name": "KING",
        },
    ],
    "OP04-056": [
        {
            "timing": "activate_main",
            "summary": "【主要】將最多1張角色卡放置在持有者的卡組下面。",
            "ops": [
                {
                    "op": "return_to_bottom",
                    "count": 1,
                    "optional": True,
                    "target_kind": "any_character",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "【觸發器】將最多1張費用4以下的角色卡放置在持有者的卡組下面。",
            "ops": [
                {
                    "op": "return_to_bottom",
                    "count": 1,
                    "optional": True,
                    "target_kind": "any_character",
                    "cost_lte": 4,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "EB04-050": [
        {
            "timing": "activate_main",
            "summary": "【主要】最多1張自己擁有《SWORD》特徵的領航卡或角色卡，在這個回合，可以攻擊活動狀態的角色卡。",
            "ops": [
                {
                    "op": "allow_attack_active",
                    "count": 1,
                    "target_kind": "own_leader_or_character",
                    "trait_contains": "SWORD",
                    "optional": True,
                    "duration": "turn",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "counter_event",
            "summary": "【反擊】自己的領航卡，在這場對戰中，力量值+3000。",
            "ops": [
                {
                    "op": "buff",
                    "amount": 3000,
                    "target_kind": "leader",
                    "optional": False,
                    "duration": "battle",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "ST08-007": [
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
            "timing": "trigger",
            "summary": "【觸發器】使這張卡片登場。",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                    "self_card": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "ST03-013": [
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
            "timing": "trigger",
            "summary": "【觸發器】使這張卡片登場。",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                    "self_card": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP05-073": [
        {
            "timing": "on_play",
            "summary": "【登場時】可以廢棄1張自己的手牌：從咚‼卡組追加最多1張休息狀態的咚‼卡。",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {"op": "gain_don", "count": 1, "as_rested": True, "optional": True},
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "trigger",
            "summary": "【觸發器】咚‼-1：使這張卡片登場。",
            "ops": [
                {"op": "return_don", "count": 1, "owner": "self", "as_cost": True},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                    "self_card": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP03-108": [
        {
            "timing": "your_turn",
            "summary": "【咚‼×1】若自己的生命值卡張數比對手少時，這張角色卡獲得【雙重攻擊】，力量值+1000。",
            "ops": [
                {
                    "op": "grant_keyword",
                    "keyword": "double_attack",
                    "target_kind": "self",
                    "duration": "permanent",
                },
                {"op": "buff_self", "amount": 1000},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_attached_gte": 1,
            "require_life_less_than_opponent": True,
        },
        {
            "timing": "trigger",
            "summary": "【觸發器】可以廢棄1張自己的手牌：使這張卡片登場。",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                    "self_card": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP08-114": [
        {
            "timing": "your_turn",
            "summary": "【咚‼×1】若自己的生命值卡張數比對手少時，這張角色卡在和擁有(斬)屬性的卡片對戰中，不會遭到KO，這張角色卡的力量值+2000。",
            "ops": [
                {
                    "op": "cannot_be_ko",
                    "target_kind": "self",
                    "attribute": "Slash",
                    "optional": False,
                },
                {"op": "buff_self", "amount": 2000},
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_attached_gte": 1,
            "require_life_less_than_opponent": True,
        },
        {
            "timing": "trigger",
            "summary": "【觸發器】可以廢棄1張自己的手牌：自己的生命值卡在2張以下時，使這張卡片登場。",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                    "self_card": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_life_lte": 2,
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
