#!/usr/bin/env python3
"""Fix trash→hand, look→play search, and draw+trash gaps.

Writes library + overrides.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from battle.effect_library import get_card_entry, library_paths, reload_effect_library  # noqa: E402
from battle.effect_schema import normalize_ability, normalize_card_entry  # noqa: E402
from battle.effects import (  # noqa: E402
    _parse_add_from_trash,
    _parse_look_top_search,
    effect_blob,
)
from fix_semantic_gates_v2 import _timing_chunk, _trim_cross_timing  # noqa: E402

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "search_v11_fixed_ids.txt"

DRAW_TRASH_RE = re.compile(
    r"draw\s*(\d+)\s*cards?\s*and\s*trash\s*(\d+)\s*card.{0,24}hand|"
    r"抽\s*(\d+)\s*[張张]卡片?[，,、]?\s*並?廢棄\s*(\d+)\s*[張张]|"
    r"抽\s*(\d+)\s*[张張]卡片?[，,、]?\s*并?废弃\s*(\d+)\s*[张張]|"
    r"draw\s*1\s*card\s*and\s*trash\s*1|"
    r"抽1[張张].{0,8}廢棄1|抽1[张張].{0,8}废弃1",
    re.I,
)


def _draw_trash_counts(text: str) -> tuple[int, int] | None:
    m = DRAW_TRASH_RE.search(text)
    if not m:
        return None
    nums = [int(g) for g in m.groups() if g]
    if len(nums) >= 2:
        return nums[0], nums[1]
    if re.search(r"draw\s*1|抽1", m.group(0), re.I):
        return 1, 1
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))
    semantic = json.loads(SEM.read_text(encoding="utf-8")) if SEM.exists() else {"cards": {}}
    lib_path, ovr_path = library_paths()
    raw = json.loads(lib_path.read_text(encoding="utf-8"))
    cards = raw.get("cards") or raw
    ovr_raw = json.loads(ovr_path.read_text(encoding="utf-8")) if ovr_path.is_file() else {"cards": {}}
    overrides = ovr_raw.get("cards") if isinstance(ovr_raw.get("cards"), dict) else {}

    stats = {
        "add_from_trash": 0,
        "look_play": 0,
        "draw_trash": 0,
        "cards_touched": 0,
    }
    touched: list[str] = []
    reload_effect_library(force=True)

    targets = [
        cid
        for cid, rev in (semantic.get("cards") or {}).items()
        if rev.get("verdict") == "issue" or rev.get("status") == "issue"
    ]
    # Also include open queue ids in case verdict key differs.
    qpath = ROOT / "meta" / "effect_problem_queue.json"
    if qpath.is_file():
        q = json.loads(qpath.read_text(encoding="utf-8"))
        for it in q.get("items") or []:
            if it.get("status") == "open":
                targets.append(it["id"])
    targets = sorted(set(targets))

    for cid in targets:
        info = catalog.get(cid) or {}
        blob = effect_blob(info)
        merged = get_card_entry(cid)
        abilities = [dict(a) for a in (merged.get("abilities") or []) if isinstance(a, dict)]
        if not abilities:
            # synthesize from common timings if we can parse something useful
            continue
        changed = False
        new_abs: list[dict] = []
        for a in abilities:
            a = dict(a)
            timing = str(a.get("timing") or "")
            chunk = _trim_cross_timing(_timing_chunk(blob, timing), timing) or blob
            ops = [dict(o) for o in (a.get("ops") or []) if isinstance(o, dict)]
            kinds = [o.get("op") for o in ops]

            # 1) Trash → hand wrongly encoded as search_deck
            add_op = _parse_add_from_trash(chunk) or (
                _parse_add_from_trash(blob) if "trash" in chunk.lower() or "廢棄" in chunk or "废弃" in chunk else None
            )
            if add_op and (
                "search_deck" in kinds
                or "add_from_trash" not in kinds
                and re.search(r"from your trash to your hand|廢棄區.{0,40}加入手牌|废弃区.{0,40}加入手牌", chunk, re.I)
            ):
                ops = [o for o in ops if o.get("op") != "search_deck"]
                if not any(o.get("op") == "add_from_trash" for o in ops):
                    ops.append(add_op)
                    stats["add_from_trash"] += 1
                    changed = True
                else:
                    # replace filters on existing
                    for i, o in enumerate(ops):
                        if o.get("op") == "add_from_trash":
                            merged_op = dict(o)
                            for k, v in add_op.items():
                                if k == "op":
                                    continue
                                if v is not None and v != "" and (merged_op.get(k) in (None, "", False) or k in {"cost_lte", "cost_eq", "color", "card_type", "name_contains", "name_exclude", "trait_contains"}):
                                    merged_op[k] = v
                            ops[i] = merged_op
                            stats["add_from_trash"] += 1
                            changed = True
                            break

            # 2) Look-top then play
            search = _parse_look_top_search(chunk)
            if search and search.get("destination") == "play":
                if "search_deck" in kinds:
                    for i, o in enumerate(ops):
                        if o.get("op") != "search_deck":
                            continue
                        merged_op = dict(o)
                        for k, v in search.items():
                            if v is not None and v != "":
                                merged_op[k] = v
                        ops[i] = merged_op
                        # Drop redundant play_from_hand that tried to stand in for look-play.
                        ops = [
                            x
                            for x in ops
                            if not (
                                x.get("op") == "play_from_hand"
                                and str(x.get("from_zone") or "hand") == "hand"
                                and x.get("cost_lte") == search.get("cost_lte")
                            )
                        ]
                        stats["look_play"] += 1
                        changed = True
                        break
                else:
                    ops = [
                        x
                        for x in ops
                        if not (
                            x.get("op") == "play_from_hand"
                            and str(x.get("from_zone") or "hand") == "hand"
                        )
                    ]
                    ops.append(search)
                    stats["look_play"] += 1
                    changed = True

            # 3) Draw + trash_hand
            dt = _draw_trash_counts(chunk)
            if dt and "draw" in kinds and "trash_hand" not in kinds:
                draw_n, trash_n = dt
                # Ensure draw count matches; inject trash after draw.
                for o in ops:
                    if o.get("op") == "draw" and int(o.get("count") or 0) != draw_n:
                        o["count"] = draw_n
                insert_at = next((i + 1 for i, o in enumerate(ops) if o.get("op") == "draw"), len(ops))
                ops.insert(insert_at, {"op": "trash_hand", "count": trash_n, "optional": False})
                stats["draw_trash"] += 1
                changed = True

            a["ops"] = ops
            na = normalize_ability(a)
            if na:
                new_abs.append(na)

        if not changed:
            continue
        fixed = normalize_card_entry(cid, {"version": 1, "abilities": new_abs})
        cards[cid] = fixed
        overrides[cid] = fixed
        stats["cards_touched"] += 1
        touched.append(cid)

    print(json.dumps({"stats": stats, "touched": len(touched)}, ensure_ascii=False))
    OUT_IDS.parent.mkdir(parents=True, exist_ok=True)
    OUT_IDS.write_text("\n".join(touched) + ("\n" if touched else ""), encoding="utf-8")
    if args.dry_run:
        return 0
    raw["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    if "cards" in raw:
        raw["cards"] = cards
    lib_path.write_text(json.dumps(raw, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    ovr_raw["cards"] = overrides
    ovr_raw["generated_at"] = raw["generated_at"]
    ovr_path.write_text(json.dumps(ovr_raw, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    reload_effect_library(force=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
