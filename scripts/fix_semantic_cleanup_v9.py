#!/usr/bin/env python3
"""Drop bogus on_play, force trash_hand, inject deny_attack/trash_life, fix base_cost KO.

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
    _enrich_ops_with_target_filters,
    _parse_deny_attack_ops,
    _parse_ko_op,
    _parse_trash_life_ops,
    effect_blob,
)
from fix_semantic_gates_v2 import _timing_chunk, _trim_cross_timing  # noqa: E402

SEM = ROOT / "meta" / "effect_semantic_review.json"
OUT_IDS = ROOT / "meta" / "logs" / "cleanup_v9_fixed_ids.txt"

ON_PLAY_MARK = re.compile(r"\[On Play\]|【登場時】|【登场时】", re.I)
MAIN_MARK = re.compile(r"\[Main\]|【主要】", re.I)
COUNTER_MARK = re.compile(r"\[Counter\]|【反擊】|【反击】", re.I)
TRIGGER_MARK = re.compile(r"\[Trigger\]|【觸發器】|【触发器】", re.I)


def _looks_like_main_summary(sm: str) -> bool:
    return bool(MAIN_MARK.search(sm)) and not bool(ON_PLAY_MARK.search(sm))


def _looks_like_counter_summary(sm: str) -> bool:
    return bool(COUNTER_MARK.search(sm)) and not bool(ON_PLAY_MARK.search(sm))


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
        "drop_on_play": 0,
        "convert_main": 0,
        "trash_force": 0,
        "deny_attack": 0,
        "trash_life": 0,
        "base_cost": 0,
        "dedupe_trash_life": 0,
        "cards_touched": 0,
    }
    touched: list[str] = []
    reload_effect_library(force=True)

    for cid, rev in (semantic.get("cards") or {}).items():
        if rev.get("verdict") != "issue":
            continue
        merged = get_card_entry(cid)
        abilities = [dict(a) for a in (merged.get("abilities") or []) if isinstance(a, dict)]
        if not abilities:
            continue
        blob = effect_blob(catalog.get(cid) or {})
        has_real_on_play = bool(ON_PLAY_MARK.search(blob))
        timings = {str(a.get("timing") or "") for a in abilities}
        changed = False
        new_abs: list[dict] = []

        # First pass: drop/convert bogus on_play
        filtered: list[dict] = []
        for ability in abilities:
            timing = str(ability.get("timing") or "")
            summary = str(ability.get("summary") or "")
            if timing != "on_play":
                filtered.append(ability)
                continue

            if has_real_on_play and ON_PLAY_MARK.search(summary):
                filtered.append(ability)
                continue

            # Counter text wrongly stored as on_play while counter_event exists
            if _looks_like_counter_summary(summary) and "counter_event" in timings:
                stats["drop_on_play"] += 1
                changed = True
                continue

            # Main text wrongly stored as on_play while main_start exists
            if _looks_like_main_summary(summary) and ("main_start" in timings or "activate_main" in timings):
                stats["drop_on_play"] += 1
                changed = True
                continue

            # Main text as sole/extra on_play with no real On Play in card
            if not has_real_on_play and (_looks_like_main_summary(summary) or MAIN_MARK.search(blob)):
                if "main_start" not in timings and "activate_main" not in timings:
                    ability = dict(ability)
                    ability["timing"] = "main_start"
                    # prefer English Main chunk for summary
                    chunk = _trim_cross_timing(_timing_chunk(blob, "main_start"), "main_start")
                    if chunk and chunk != blob and len(chunk) >= 12:
                        ability["summary"] = chunk[:240]
                    stats["convert_main"] += 1
                    changed = True
                    filtered.append(ability)
                    timings.add("main_start")
                    continue
                else:
                    stats["drop_on_play"] += 1
                    changed = True
                    continue

            # on_play with no On Play marker in card text at all
            if not has_real_on_play:
                stats["drop_on_play"] += 1
                changed = True
                continue

            filtered.append(ability)

        for ability in filtered:
            timing = str(ability.get("timing") or "")
            chunk = _trim_cross_timing(_timing_chunk(blob, timing), timing)
            summary = _trim_cross_timing(str(ability.get("summary") or "").strip(), timing)
            scope = summary if len(summary) >= 12 else (chunk if chunk != blob else summary)
            text = f"{scope}\n{chunk}" if chunk and chunk != blob else scope
            ops = [dict(o) for o in (ability.get("ops") or [])]

            # Force trash_hand when paper is mandatory (draw then trash pattern)
            if re.search(
                r"(?:draw.{0,20})?(?:and )?trash\s*1\s*card from your hand|"
                r"抽\d+[張张].{0,12}並廢棄\s*1\s*[張张]自己的手牌|"
                r"抽\d+[张张].{0,12}并废弃\s*1\s*[张张]自己的手牌|"
                r"並廢棄1張自己的手牌|并废弃1张自己的手牌",
                text,
                re.I,
            ) and not re.search(r"you may trash|可以廢棄|可以废弃", text, re.I):
                for i, o in enumerate(ops):
                    if o.get("op") == "trash_hand" and o.get("optional"):
                        o = dict(o)
                        o["optional"] = False
                        o.pop("as_cost", None)
                        ops[i] = o
                        stats["trash_force"] += 1
                        changed = True

            # deny_attack
            if not any(o.get("op") in {"deny_attack", "cannot_attack"} for o in ops):
                for dop in _parse_deny_attack_ops(text) or []:
                    ops.append(dop)
                    stats["deny_attack"] += 1
                    changed = True

            # trash_life
            if re.search(r"trash.{0,40}Life|生命值區.{0,24}廢棄|生命值区.{0,24}废弃", text, re.I):
                parsed = _parse_trash_life_ops(text)
                if parsed and not any(o.get("op") == "trash_life" for o in ops):
                    ops.extend(parsed)
                    stats["trash_life"] += 1
                    changed = True
                elif parsed:
                    # dedupe identical trash_life
                    seen = set()
                    deduped = []
                    for o in ops:
                        if o.get("op") == "trash_life":
                            key = (o.get("count"), o.get("owner"), o.get("position"), o.get("as_cost"), o.get("optional"))
                            if key in seen:
                                stats["dedupe_trash_life"] += 1
                                changed = True
                                continue
                            seen.add(key)
                        deduped.append(o)
                    ops = deduped

            # base_cost on KO
            if re.search(r"base cost|原本費用|原本费用", text, re.I):
                for i, o in enumerate(ops):
                    if o.get("op") != "ko":
                        continue
                    if o.get("base_cost_lte") is not None:
                        continue
                    m = re.search(
                        r"base cost of\s*(\d+)\s*or less|原本費用\s*(\d+)\s*以下|原本费用\s*(\d+)\s*以下",
                        text,
                        re.I,
                    )
                    if not m:
                        ko = _parse_ko_op(text)
                        if ko and ko.get("base_cost_lte") is not None:
                            o = dict(o)
                            o["base_cost_lte"] = ko["base_cost_lte"]
                            o.pop("cost_lte", None)
                            ops[i] = o
                            stats["base_cost"] += 1
                            changed = True
                        continue
                    n = int(next(g for g in m.groups() if g))
                    o = dict(o)
                    o["base_cost_lte"] = n
                    o.pop("cost_lte", None)
                    ops[i] = o
                    stats["base_cost"] += 1
                    changed = True

            ops = _enrich_ops_with_target_filters(ops, text)
            ability = dict(ability)
            ability["ops"] = ops
            if summary and len(summary) >= 12:
                ability["summary"] = summary[:240]
            na = normalize_ability(ability)
            if na:
                new_abs.append(na)

        if not changed:
            continue
        fixed = normalize_card_entry(cid, {"version": 1, "abilities": new_abs})
        cards[cid] = fixed
        overrides[cid] = fixed
        stats["cards_touched"] += 1
        touched.append(cid)

    print(json.dumps(stats, ensure_ascii=False), flush=True)
    OUT_IDS.parent.mkdir(parents=True, exist_ok=True)
    OUT_IDS.write_text("\n".join(touched) + ("\n" if touched else ""), encoding="utf-8")
    print(f"Wrote ids {OUT_IDS} ({len(touched)})", flush=True)
    if args.dry_run:
        return 0

    payload = {"version": 1, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "cards": cards}
    tmp = lib_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(lib_path)

    ovr_payload = dict(ovr_raw) if isinstance(ovr_raw, dict) else {}
    ovr_payload["cards"] = overrides
    ovr_payload["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    tmp_o = ovr_path.with_suffix(".json.tmp")
    tmp_o.write_text(json.dumps(ovr_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp_o.replace(ovr_path)
    reload_effect_library(force=True)
    print(f"Wrote {lib_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
