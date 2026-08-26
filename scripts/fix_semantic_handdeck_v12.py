#!/usr/bin/env python3
"""Inject hand_to_deck / grant_cost; drop bogus buff_self on opponent-only effects.

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
    _parse_grant_cost_ops,
    _parse_hand_to_deck_ops,
    effect_blob,
)
from fix_semantic_gates_v2 import _timing_chunk, _trim_cross_timing  # noqa: E402

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "handdeck_v12_fixed_ids.txt"

OPP_ONLY_BUFF = re.compile(
    r"give up to\s*\d+\s*of your opponent'?s|對手的角色|对手的角色|"
    r"up to\s*\d+\s*of your opponent'?s Characters?\s*(?:gains?|gets?)?\s*[−\-－+]?\d+",
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

    stats = {"hand_to_deck": 0, "grant_cost": 0, "drop_buff_self": 0, "cards_touched": 0}
    touched: list[str] = []
    reload_effect_library(force=True)

    targets = [
        cid
        for cid, rev in (semantic.get("cards") or {}).items()
        if rev.get("verdict") == "issue"
    ]
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
            continue
        changed = False
        new_abs: list[dict] = []
        for a in abilities:
            a = dict(a)
            timing = str(a.get("timing") or "")
            chunk = _trim_cross_timing(_timing_chunk(blob, timing), timing) or blob
            ops = [dict(o) for o in (a.get("ops") or []) if isinstance(o, dict)]

            # hand_to_deck
            hd = _parse_hand_to_deck_ops(chunk)
            if hd and not any(o.get("op") == "hand_to_deck" for o in ops):
                # Prefer as cost at front.
                if hd[0].get("as_cost"):
                    ops = hd + ops
                else:
                    ops.extend(hd)
                stats["hand_to_deck"] += 1
                changed = True

            # grant_cost replacing buff amount 0 / missing
            gc = _parse_grant_cost_ops(chunk)
            if gc:
                if any(o.get("op") == "buff" and int(o.get("amount") or 0) == 0 for o in ops):
                    ops = [o for o in ops if not (o.get("op") == "buff" and int(o.get("amount") or 0) == 0)]
                    ops.extend(gc)
                    stats["grant_cost"] += 1
                    changed = True
                elif not any(o.get("op") == "grant_cost" for o in ops) and re.search(
                    r"cost|費用|费用", chunk, re.I
                ):
                    ops.extend(gc)
                    stats["grant_cost"] += 1
                    changed = True

            # Drop buff_self when chunk only buffs opponent
            if any(o.get("op") == "buff_self" for o in ops) and OPP_ONLY_BUFF.search(chunk):
                if not re.search(r"this Character gains|這張角色卡.*力量|这张角色卡.*力量|自身", chunk, re.I):
                    before = len(ops)
                    ops = [o for o in ops if o.get("op") != "buff_self"]
                    if len(ops) < before:
                        stats["drop_buff_self"] += 1
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
