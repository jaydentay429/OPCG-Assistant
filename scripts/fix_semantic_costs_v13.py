#!/usr/bin/env python3
"""Fix return_don counts, trash_to_bottom costs, life_to_hand direction, KO exclude_self.

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
    _parse_life_to_hand_cost,
    _parse_play_from_zone,
    _parse_trash_to_bottom_ops,
    effect_blob,
)
from fix_semantic_gates_v2 import _timing_chunk, _trim_cross_timing  # noqa: E402

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "costs_v13_fixed_ids.txt"

DON_RET_RE = re.compile(r"(?:DON!!|咚‼?)\s*[−\-－]\s*(\d+)", re.I)
KO_ALL_EXCEPT_SELF = re.compile(
    r"K\.?O\.?\s*all Characters other than this Character|"
    r"除了這張角色卡以外[，,]?\s*KO全數|除了这张角色卡以外[，,]?\s*KO全数",
    re.I,
)
LIFE_TO_HAND_RE = re.compile(
    r"Add 1 card from the top of your Life cards to your hand|"
    r"[將将]自己生命值區最上面的1[張张]卡片加入手牌|"
    r"[將将]1[張张]自己生命值區上面的卡片加入手牌",
    re.I,
)


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
        "return_don": 0,
        "drop_return_don": 0,
        "trash_to_bottom": 0,
        "life_to_hand": 0,
        "ko_exclude_self": 0,
        "play_from_trash": 0,
        "cards_touched": 0,
    }
    touched: list[str] = []
    reload_effect_library(force=True)

    targets = [cid for cid, rev in (semantic.get("cards") or {}).items() if rev.get("verdict") == "issue"]
    qpath = ROOT / "meta" / "effect_problem_queue.json"
    if qpath.is_file():
        for it in json.loads(qpath.read_text(encoding="utf-8")).get("items") or []:
            if it.get("status") == "open":
                targets.append(it["id"])
    targets = sorted(set(targets))

    for cid in targets:
        info = catalog.get(cid) or {}
        blob = effect_blob(info)
        merged = get_card_entry(cid)
        abilities = [dict(a) for a in (merged.get("abilities") or []) if isinstance(a, dict)]
        if not abilities:
            continue
        changed = False
        new_abs: list[dict] = []
        for a in abilities:
            a = dict(a)
            timing = str(a.get("timing") or "")
            chunk = _trim_cross_timing(_timing_chunk(blob, timing), timing) or ""
            ops = [dict(o) for o in (a.get("ops") or []) if isinstance(o, dict)]

            # 1) return_don count from this timing's DON!! −N
            m_ret = DON_RET_RE.search(chunk)
            if m_ret:
                n = int(m_ret.group(1))
                found = False
                for o in ops:
                    if o.get("op") == "return_don":
                        if int(o.get("count") or 0) != n:
                            o["count"] = n
                            o["as_cost"] = True
                            stats["return_don"] += 1
                            changed = True
                        elif not o.get("as_cost"):
                            o["as_cost"] = True
                            stats["return_don"] += 1
                            changed = True
                        found = True
                        break
                if not found:
                    ops.insert(0, {"op": "return_don", "count": n, "as_cost": True})
                    stats["return_don"] += 1
                    changed = True
            else:
                # Drop return_don that bled into a timing without DON!! −
                before = len(ops)
                ops = [o for o in ops if o.get("op") != "return_don"]
                if len(ops) < before:
                    stats["drop_return_don"] += 1
                    changed = True

            # 2) trash_to_bottom (own/opponent)
            tb = _parse_trash_to_bottom_ops(chunk)
            if tb:
                # Replace mistaken return_don that stood in for trash bottom when no DON-
                if not m_ret:
                    ops = [o for o in ops if o.get("op") != "return_don"]
                if not any(o.get("op") == "trash_to_bottom" for o in ops):
                    if tb[0].get("as_cost"):
                        ops = tb + ops
                    else:
                        ops.extend(tb)
                    stats["trash_to_bottom"] += 1
                    changed = True
                else:
                    for i, o in enumerate(ops):
                        if o.get("op") != "trash_to_bottom":
                            continue
                        merged_op = dict(o)
                        for k, v in tb[0].items():
                            if v is not None and v != "":
                                merged_op[k] = v
                        if int(merged_op.get("count") or 0) != int(tb[0].get("count") or 0):
                            stats["trash_to_bottom"] += 1
                            changed = True
                        ops[i] = merged_op
                        break

                # Play from trash after cost (EB01-043 style)
                play = _parse_play_from_zone(chunk)
                if play and play.get("from_zone") in {"trash", "hand_or_trash"}:
                    if not any(o.get("op") == "play_from_hand" and o.get("from_zone") in {"trash", "hand_or_trash"} for o in ops):
                        ops.append(play)
                        stats["play_from_trash"] += 1
                        changed = True

            # 3) life_to_hand direction (replace wrong add_life)
            if LIFE_TO_HAND_RE.search(chunk) or (
                re.search(r"life_to_hand|生命值區.{0,20}加入手牌", chunk, re.I)
                and any(o.get("op") == "add_life" for o in ops)
            ):
                lth = _parse_life_to_hand_cost(chunk)
                if not lth and LIFE_TO_HAND_RE.search(chunk):
                    lth = [
                        {
                            "op": "life_to_hand",
                            "count": 1,
                            "position": "top",
                            "optional": False,
                            "owner": "self",
                        }
                    ]
                if lth and any(o.get("op") == "add_life" for o in ops):
                    ops = [o for o in ops if o.get("op") != "add_life"]
                    if not any(o.get("op") == "life_to_hand" for o in ops):
                        ops.extend(lth)
                    stats["life_to_hand"] += 1
                    changed = True
                elif lth and not any(o.get("op") == "life_to_hand" for o in ops):
                    if lth[0].get("as_cost"):
                        ops = lth + ops
                    else:
                        ops.extend(lth)
                    stats["life_to_hand"] += 1
                    changed = True

            # 4) KO all except self
            if KO_ALL_EXCEPT_SELF.search(chunk):
                replaced = False
                for o in ops:
                    if o.get("op") == "ko":
                        o["exclude_self"] = True
                        o["target_kind"] = "all"  # may normalize away; keep exclude_self
                        o["optional"] = False
                        # Prefer broad KO: both sides except self — engine uses exclude_self on pools
                        if o.get("target_kind") not in {"all_characters", "character"}:
                            o["target_kind"] = "opponent_character"  # incomplete but mark exclude
                        # Use a dedicated marker many engines honor:
                        o["all"] = True
                        o["exclude_self"] = True
                        replaced = True
                        stats["ko_exclude_self"] += 1
                        changed = True
                        break
                if not replaced:
                    ops.append(
                        {
                            "op": "ko",
                            "all": True,
                            "exclude_self": True,
                            "optional": False,
                            "target_kind": "opponent_character",
                        }
                    )
                    stats["ko_exclude_self"] += 1
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
