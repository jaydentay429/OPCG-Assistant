#!/usr/bin/env python3
"""Deterministic semantic fixes v57: remaining medium open-queue batch.

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

OUT_IDS = ROOT / "meta" / "logs" / "ops_v57_fixed_ids.txt"
REBUILDS_PATH = ROOT / "meta" / "logs" / "ops_v57_rebuilds.json"

REBUILDS: dict[str, list[dict[str, Any]]] = {
    # Colon-cost life→hand; if Straw Hat add deck-top to life top; then play Skypiea.
    "OP15-109": [
        {
            "timing": "on_play",
            "summary": "【登場時】可將1張自己生命值區上面的卡片加入手牌：若自己的領航卡擁有《草帽一行人》特徵時，將最多1張自己卡組上面的卡片加入生命值區上面。之後，使最多1張自己手牌中費用5以下擁有《空島》特徵的角色卡登場。",
            "ops": [
                {
                    "op": "life_to_hand",
                    "count": 1,
                    "position": "top",
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {
                    "op": "add_life",
                    "count": 1,
                    "position": "top",
                    "optional": True,
                    "require_leader_trait": "Straw Hat Crew",
                },
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 5,
                    "trait_contains": "Sky Island",
                    "from_zone": "hand",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        }
    ],
    "OP09-100": [
        {
            "timing": "trigger",
            "summary": "【觸發器】若自己的領航卡擁有《革命軍》特徵、雙方的生命值卡合計張數在5張以下時，使這張卡片登場。",
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
            "confidence": 0.95,
            "require_total_life_lte": 5,
            "require_leader_trait": "Revolutionary Army",
        }
    ],
    "OP09-112": [
        {
            "timing": "on_play",
            "summary": "【登場時】若自己的生命值卡在2張以下時，抽1張卡片。",
            "ops": [{"op": "draw", "count": 1}],
            "status": "compiled",
            "confidence": 0.95,
            "require_life_lte": 2,
        },
        {
            "timing": "trigger",
            "summary": "【觸發器】若自己的領航卡擁有《革命軍》特徵、雙方的生命值卡合計張數在5張以下時，使這張卡片登場。",
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
            "confidence": 0.95,
            "require_total_life_lte": 5,
            "require_leader_trait": "Revolutionary Army",
        },
    ],
    "OP16-111": [
        {
            "timing": "trigger",
            "summary": "【觸發器】若自己的生命值卡在2張以下時，使這張卡片登場。",
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
            "require_life_lte": 2,
        }
    ],
    "ST20-002": [
        {
            "timing": "your_turn",
            "summary": "【每回合1次】若這張角色卡因為效果即將遭到KO時，可以替換成將1張自己生命值區上面的卡片放置在廢棄區。",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "ko",
                    "target": "self",
                    "cost": "trash_life",
                    "life_position": "top",
                    "once": True,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
        },
        {
            "timing": "opponent_turn",
            "summary": "【每回合1次】若這張角色卡因為效果即將遭到KO時，可以替換成將1張自己生命值區上面的卡片放置在廢棄區。",
            "ops": [
                {
                    "op": "replace_leave",
                    "trigger": "ko",
                    "target": "self",
                    "cost": "trash_life",
                    "life_position": "top",
                    "once": True,
                    "optional": True,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "once": True,
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
                    "optional": False,
                    "from_zone": "hand",
                    "self_card": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "ST13-010": [
        {
            "timing": "activate_main",
            "summary": "【啟動主要】可將這張角色卡放置在廢棄區：公開1張自己生命值區上面的卡片，若該張卡片是費用5的「波特卡斯・D・艾斯」時，也可登場。若登場時，最多1張自己的領航卡，在下一個對手回合結束前，力量值+2000。",
            "ops": [
                {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                {"op": "reveal_life", "count": 1, "position": "top", "optional": False, "owner": "self"},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_eq": 5,
                    "name_contains": "Portgas.D.Ace",
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
            "confidence": 0.95,
        }
    ],
    "ST13-014": [
        {
            "timing": "activate_main",
            "summary": "【啟動主要】可將這張角色卡放置在廢棄區：公開1張自己生命值區上面的卡片，若該張卡片是費用5的「蒙其・D・魯夫」時，也可登場。若登場時，最多1張自己的領航卡，在下一個對手回合結束前，力量值+2000。",
            "ops": [
                {"op": "trash", "target_kind": "self", "optional": True, "as_cost": True},
                {"op": "reveal_life", "count": 1, "position": "top", "optional": False, "owner": "self"},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_eq": 5,
                    "name_contains": "Monkey.D.Luffy",
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
            "confidence": 0.95,
        }
    ],
    "ST22-015": [
        {
            "timing": "main_start",
            "summary": "【主要】若自己的領航卡擁有包含『白鬍子海賊團』特徵時，使最多1張自己手牌中的「艾德華・紐蓋特」登場。之後，可將1張自己生命值區上面或下面的卡片加入手牌。若有執行此動作時，最多1張自己的領航卡，在下一個對手回合結束前，力量值+2000。",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "name_contains": "Edward.Newgate",
                    "from_zone": "hand",
                },
                {
                    "op": "life_to_hand",
                    "count": 1,
                    "position": "top_or_bottom",
                    "optional": True,
                    "owner": "self",
                },
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "leader",
                    "optional": True,
                    "duration": "until_opp_turn_end",
                    "if_life_to_hand": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_trait": "Whitebeard Pirates",
        }
    ],
    "ST32-003": [
        {
            "timing": "your_turn",
            "summary": "【我方回合中】這張角色卡置為休息狀態時，抽1張卡片，並廢棄1張自己的手牌。",
            "ops": [
                {"op": "draw", "count": 1, "on_self_rest": True},
                {"op": "trash_hand", "count": 1, "optional": False, "owner": "self", "on_self_rest": True},
            ],
            "status": "compiled",
            "confidence": 0.9,
        },
        {
            "timing": "on_play",
            "summary": "【登場時】若自己的領航卡擁有(斬)屬性時，使最多1張自己手牌中費用5以下、擁有(斬)屬性的角色卡或「培羅娜」登場。",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 5,
                    "attribute": "Slash",
                    "name_contains": "Perona",
                    "name_or_attribute": True,
                    "from_zone": "hand",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_attribute": "Slash",
        },
    ],
    "EB01-028": [
        {
            "timing": "counter_event",
            "summary": "【反擊】若自己的領航卡擁有《推進城》特徵時，最多1張自己的領航卡或角色卡，在這場對戰中，力量值+2000。之後，對手將1張自身活動狀態的角色卡放回持有者的手牌。",
            "ops": [
                {
                    "op": "buff",
                    "amount": 2000,
                    "target_kind": "own_leader_or_character",
                    "optional": True,
                    "duration": "battle",
                },
                {
                    "op": "return_to_hand",
                    "target_kind": "opponent_character_active",
                    "optional": False,
                    "chooser": "opponent",
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_leader_trait": "Impel Down",
        },
        {
            "timing": "trigger",
            "summary": "【觸發器】將最多1張費用3以下的角色卡放回持有者的卡組下面。",
            "ops": [
                {
                    "op": "return_to_bottom",
                    "count": 1,
                    "optional": True,
                    "target_kind": "any_character",
                    "cost_lte": 3,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
    ],
    "OP11-092": [
        {
            "timing": "on_play",
            "summary": "【登場時】可以廢棄1張自己的手牌：抽1張卡片，並使最多1張自己廢棄區中除了「貝魯梅柏」以外費用8以下擁有《SWORD》特徵的角色卡登場。之後，這回合結束時，將1張以此效果登場的角色卡放置在持有者的卡組下面。",
            "ops": [
                {
                    "op": "trash_hand",
                    "count": 1,
                    "optional": True,
                    "as_cost": True,
                    "owner": "self",
                },
                {"op": "draw", "count": 1},
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "cost_lte": 8,
                    "exclude_name": "Bellemere",
                    "trait_contains": "SWORD",
                    "from_zone": "trash",
                    "mark_effect_played": True,
                },
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "end_of_your_turn",
            "summary": "這回合結束時，將1張以此效果登場的角色卡放置在持有者的卡組下面。",
            "ops": [
                {
                    "op": "return_to_bottom",
                    "count": 1,
                    "optional": False,
                    "effect_played_only": True,
                    "target_kind": "own_character",
                }
            ],
            "status": "compiled",
            "confidence": 0.9,
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
