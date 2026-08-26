#!/usr/bin/env python3
"""Deterministic semantic fixes v54: bilateral ownership for unqualified 費用/咚/生命.

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

OUT_IDS = ROOT / "meta" / "logs" / "ops_v54_fixed_ids.txt"
REBUILDS_PATH = ROOT / "meta" / "logs" / "ops_v54_rebuilds.json"

REBUILDS: dict[str, list[dict[str, Any]]] = {
    # 「自己或對手的場上有10張咚‼」→ either-side DON gate; cannot leave by opp effect.
    "P-104": [
        {
            "timing": "your_turn",
            "summary": "若自己或對手的場上有10張咚‼卡時，這張角色卡不會因對手的效果而離開場上。",
            "ops": [
                {
                    "op": "cannot_be_removed",
                    "target_kind": "self",
                    "any_leave": True,
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_either_don_field_gte": 10,
        },
        {
            "timing": "opponent_turn",
            "summary": "若自己或對手的場上有10張咚‼卡時，這張角色卡不會因對手的效果而離開場上。",
            "ops": [
                {
                    "op": "cannot_be_removed",
                    "target_kind": "self",
                    "any_leave": True,
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_either_don_field_gte": 10,
        },
    ],
    # 「自己或對手的場上有10張咚‼」on play → leader buff.
    "P-107": [
        {
            "timing": "on_play",
            "summary": "【登場時】若自己或對手的場上有10張咚‼卡時，自己的領航卡，在下一個對手結束階段結束前，力量值+2000。",
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
            "require_either_don_field_gte": 10,
        }
    ],
    # 「雙方的生命值卡合計」→ total life only (not own life_lte).
    "OP09-114": [
        {
            "timing": "on_play",
            "summary": "【登場時】若雙方的生命值卡合計張數在5張以下時，KO最多1張對手力量值2000以下的角色卡。",
            "ops": [
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "power_lte": 2000,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_total_life_lte": 5,
        },
        {
            "timing": "trigger",
            "summary": "【觸發器】若雙方的生命值卡合計張數在5張以下時，使這張卡片登場。",
            "ops": [
                {
                    "op": "play_from_hand",
                    "count": 1,
                    "card_type": "character",
                    "optional": True,
                    "from_zone": "hand",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_total_life_lte": 5,
        },
    ],
    # Permanent cannot_be_ko; DON×1 + unqualified 「場上有費用0」→ bilateral field cost.
    "ST06-004": [
        {
            "timing": "your_turn",
            "summary": "這張角色卡不會因效果而遭到KO。",
            "ops": [
                {
                    "op": "cannot_be_ko",
                    "target_kind": "self",
                    "optional": False,
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
        },
        {
            "timing": "your_turn",
            "summary": "【咚‼×1】若場上有費用0的角色卡時，這張角色卡獲得【雙重攻擊】。",
            "ops": [
                {
                    "op": "grant_keyword",
                    "keyword": "double_attack",
                    "target_kind": "self",
                    "duration": "permanent",
                }
            ],
            "status": "compiled",
            "confidence": 0.95,
            "require_don_attached_gte": 1,
            "require_field_char_cost_eq": 0,
        },
    ],
    # 「若場上有費用9以上」→ field cost gte (either side), not eq; gate only the KO clause.
    "OP11-095": [
        {
            "timing": "on_play",
            "summary": "【登場時】可將3張自己廢棄區中擁有《海軍》特徵的卡片依任意順序放置在卡組下面：附加最多1張休息狀態的咚‼卡在1張自己的領航卡。之後，若場上有費用9以上的角色卡時，KO最多1張對手費用7以下的角色卡。",
            "ops": [
                {
                    "op": "trash_to_bottom",
                    "count": 3,
                    "optional": True,
                    "owner": "self",
                    "card_type": "any",
                    "order_any": True,
                    "as_cost": True,
                    "trait_contains": "海軍",
                },
                {
                    "op": "attach_don",
                    "count": 1,
                    "as_rested": True,
                    "target_kind": "leader",
                    "optional": True,
                },
                {
                    "op": "ko",
                    "target_kind": "opponent_character",
                    "optional": True,
                    "cost_lte": 7,
                    "require_field_char_cost_gte": 9,
                },
            ],
            "status": "compiled",
            "confidence": 0.9,
        }
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
