#!/usr/bin/env python3
"""Inject board gates: DON compare, trash_gte, played_this_turn; fix rested KO targets.

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
from battle.effects import _text_requires_don_field_lte_opponent, effect_blob  # noqa: E402
from fix_semantic_gates_v2 import _timing_chunk, _trim_cross_timing  # noqa: E402

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "gates_v18_fixed_ids.txt"

TRASH_GTE_RE = re.compile(
    r"(?:if you have|have)\s*(\d+)\s*or more cards? in your trash|"
    r"(?:廢棄區|废弃区).{0,8}有\s*(\d+)\s*[張张]以上|"
    r"(?:廢棄區|废弃区).{0,8}[≥≧]\s*(\d+)",
    re.I,
)
DON_FIELD_GTE_RE = re.compile(
    r"(?:if you have|have)\s*(\d+)\s*or more DON!! cards? on your field|"
    r"場上的咚‼?卡有\s*(\d+)\s*[張张]以上|场上的咚‼?卡有\s*(\d+)\s*[张張]以上|"
    r"自己場上的咚‼?有\s*(\d+)\s*[張张]以上|自己场上的咚‼?有\s*(\d+)\s*[张張]以上",
    re.I,
)
PLAYED_THIS_TURN_RE = re.compile(
    r"if this Character was played (?:during |on )?this turn|"
    r"若這張角色卡在這個回合登場|若这张角色卡在这个回合登场|"
    r"若此角色卡於本回合登場|若此角色卡于本回合登场",
    re.I,
)
RESTED_KO_RE = re.compile(
    r"K\.?O\.?.{0,40}rested Characters?|"
    r"KO.{0,40}休息狀態.{0,20}角色|KO.{0,40}休息状态.{0,20}角色|"
    r"休息狀態的角色卡|休息状态的角色卡",
    re.I,
)
ONCE_RE = re.compile(r"\[Once Per Turn\]|【每回合1次】", re.I)


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
        "don_deficit": 0,
        "don_field_gte": 0,
        "trash_gte": 0,
        "played_this_turn": 0,
        "rested_ko": 0,
        "once": 0,
        "drop_spurious_rest": 0,
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
        multi = len(abilities) > 1

        for a in abilities:
            a = dict(a)
            timing = str(a.get("timing") or "")
            chunk = _trim_cross_timing(_timing_chunk(blob, timing), timing) or ""
            if multi and (not chunk or chunk == blob):
                chunk = _trim_cross_timing(str(a.get("summary") or ""), timing) or chunk
            ops = [dict(o) for o in (a.get("ops") or []) if isinstance(o, dict)]

            if _text_requires_don_field_lte_opponent(chunk):
                if a.get("require_don_field_deficit_gte") is None:
                    a["require_don_field_deficit_gte"] = 0
                    stats["don_deficit"] += 1
                    changed = True

            m_don = DON_FIELD_GTE_RE.search(chunk)
            if m_don:
                n = int(next(g for g in m_don.groups() if g))
                if int(a.get("require_don_field_gte") or 0) != n:
                    a["require_don_field_gte"] = n
                    stats["don_field_gte"] += 1
                    changed = True

            m_tr = TRASH_GTE_RE.search(chunk)
            if m_tr:
                n = int(next(g for g in m_tr.groups() if g))
                if int(a.get("require_trash_gte") or 0) != n:
                    a["require_trash_gte"] = n
                    stats["trash_gte"] += 1
                    changed = True

            if PLAYED_THIS_TURN_RE.search(chunk):
                if not a.get("require_played_this_turn"):
                    a["require_played_this_turn"] = True
                    stats["played_this_turn"] += 1
                    changed = True

            if ONCE_RE.search(chunk) and timing in {"activate_main", "when_attacking", "on_block", "main_start"}:
                if not a.get("once"):
                    a["once"] = True
                    stats["once"] += 1
                    changed = True

            if RESTED_KO_RE.search(chunk):
                for o in ops:
                    if o.get("op") == "ko" and o.get("target_kind") in {
                        "opponent_character",
                        "any_character",
                        None,
                        "",
                    }:
                        o["target_kind"] = "opponent_character_rested"
                        stats["rested_ko"] += 1
                        changed = True

            # Rest only DON as cost: drop spurious character rests when paper is rest DON only
            if re.search(
                r"(?:you may )?rest\s*(\d+)\s*of your DON!! cards?\s*:|"
                r"可?[將将]\s*(\d+)\s*[張张]自己的咚‼?卡置[為为]休息狀態\s*[：:]",
                chunk,
                re.I,
            ) and not re.search(
                r"rest (?:up to )?\d+ of your (?:opponent'?s )?Characters?|將最多.{0,30}角色|将最多.{0,30}角色|"
                r"rest 1 of your (?:\{|Characters?|cards?|Leader)|可[將将]1[張张]自己的(?:角色|卡片|領航)",
                chunk,
                re.I,
            ):
                before = len(ops)
                ops = [
                    o
                    for o in ops
                    if o.get("op")
                    not in {"rest_character", "rest_opponent_character"}
                    or o.get("op") == "rest_don"
                ]
                # keep rest_don
                if len(ops) < before:
                    stats["drop_spurious_rest"] += 1
                    changed = True
                if not any(o.get("op") == "rest_don" for o in ops):
                    m = re.search(
                        r"rest\s*(\d+)\s*of your DON|可?[將将]\s*(\d+)\s*[張张]自己的咚",
                        chunk,
                        re.I,
                    )
                    n = int(next(g for g in m.groups() if g)) if m else 1
                    ops = [{"op": "rest_don", "count": n, "as_cost": True, "optional": True}] + ops
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
