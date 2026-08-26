#!/usr/bin/env python3
"""Offline compile of structured card effects for the battle engine.

Usage:
  .venv/bin/python scripts/compile_card_effects.py
  .venv/bin/python scripts/compile_card_effects.py --llm          # also call DeepSeek for gaps
  .venv/bin/python scripts/compile_card_effects.py --limit 200
  .venv/bin/python scripts/compile_card_effects.py --incremental  # only missing / unsupported
  .venv/bin/python scripts/compile_card_effects.py --fill-gaps    # recompile missing timings
  .venv/bin/python scripts/compile_card_effects.py --llm --fill-gaps
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

from battle.effect_library import (  # noqa: E402
    card_has_timing_gaps,
    compile_card_from_templates,
    detect_timings_in_text,
    library_paths,
)
from battle.effect_schema import (  # noqa: E402
    TIMINGS,
    ability_is_runnable,
    normalize_ability,
    normalize_card_entry,
    sanitize_ops_list,
)
from battle.effects import effect_blob, get_deepseek_asker  # noqa: E402


def load_catalog() -> dict[str, dict]:
    path = ROOT / "index" / "cards_by_id.json"
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def load_existing(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and isinstance(data.get("cards"), dict):
        return data["cards"]
    return data if isinstance(data, dict) else {}


def llm_compile_ability(card_id: str, info: dict, ask) -> list[dict]:
    blob = effect_blob(info)
    if not blob.strip():
        return []
    prompt = (
        "Compile OPTCG card effects into JSON ONLY:\n"
        '{"abilities":[{"timing":"on_play|activate_main|trigger|when_attacking|on_block|'
        "on_opponent_attack|on_ko|end_of_your_turn|turn_start|counter_event|your_turn|"
        'opponent_turn|don_attached|on_don_attached","summary":"...","ops":[{"op":"draw|gain_don|'
        "set_don|rest_opponent_character|rest_character|buff|buff_self|set_base_power_from_opponent_leader|"
        "set_base_power_from_character|set_base_power_from_attacker|set_base_power|"
        "set_power_equal_opponent_leader|ko|ko_lowest_opponent|search_deck|play_from_hand|trash|"
        "trash_hand|return_to_hand|return_to_bottom|add_life|deal_life_damage|rest_don|active_don|"
        "return_don|attach_don|set_character_active|grant_keyword|cannot_be_ko|choose_target|"
        'unsupported","count":1,"amount":1000,"top_n":3,"max_add":1,"trait_contains":"","name_contains":"",'
        '"target_kind":"opponent_character","keyword":"blocker","as_rested":false,"as_cost":false,'
        '"cost_don":0,"rest_self":false,"once":false}],'
        '"status":"compiled|needs_review|unsupported","confidence":0.0,"once":false}]}\n'
        "Rules: look-at-top / reveal-from-deck / add-to-hand MUST use search_deck (never draw). "
        "Give/attach DON!! from DON!! deck onto a Character/Leader → attach_don. "
        "Add DON!! to cost area → gain_don. Trash cards from hand as cost → trash_hand with as_cost. "
        "If the effect cannot be expressed safely, use status=unsupported with op=unsupported. "
        "Split by timing. Keep ops short.\n"
        f"Card: {card_id} {info.get('name_en') or info.get('name')}\n"
        f"Effect:\n{blob}\n"
    )
    try:
        raw = ask(prompt)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I | re.S)
        data = json.loads(cleaned)
        abilities = data.get("abilities") if isinstance(data, dict) else None
        if not isinstance(abilities, list):
            return []
        out = []
        for a in abilities:
            if not isinstance(a, dict):
                continue
            if a.get("ops"):
                a["ops"] = sanitize_ops_list(a["ops"])
            na = normalize_ability(a)
            if na:
                out.append(na)
        return out
    except Exception:
        return []


def merge_abilities(base: list[dict], extra: list[dict]) -> list[dict]:
    by_timing: dict[str, dict] = {}
    for a in base:
        by_timing[a["timing"]] = a
    for a in extra:
        t = a["timing"]
        prev = by_timing.get(t)
        if not prev:
            by_timing[t] = a
            continue
        if ability_is_runnable(a) and not ability_is_runnable(prev):
            by_timing[t] = a
        elif prev.get("status") == "unsupported" and a.get("status") != "unsupported":
            by_timing[t] = a
        elif prev.get("status") != "compiled" and a.get("status") == "compiled":
            by_timing[t] = a
        elif a.get("status") == "verified":
            by_timing[t] = a
    return list(by_timing.values())


def _should_skip_incremental(info: dict, existing_entry: dict, *, fill_gaps: bool) -> bool:
    abs_ = existing_entry.get("abilities") or []
    if not abs_:
        return False
    if fill_gaps:
        return not card_has_timing_gaps(info, abs_)
    # Legacy incremental: skip unless all unsupported
    return not all(a.get("status") == "unsupported" for a in abs_)


def _base_card_id(cid: str) -> str:
    return re.sub(r"-(?:P|R)\d+$", "", cid)


def _meaningful_effect(info: dict) -> bool:
    from battle.effects import has_meaningful_effect_text

    return has_meaningful_effect_text(info)


def _ability_has_gap_for_llm(info: dict, abilities: list[dict]) -> bool:
    """LLM when text has timing gaps or whole card is empty/unsupported."""
    if not _meaningful_effect(info):
        return False
    return card_has_timing_gaps(info, abilities)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="Fill gaps with DeepSeek")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--incremental", action="store_true")
    ap.add_argument(
        "--fill-gaps",
        action="store_true",
        help="Recompile cards that have text timings without runnable abilities",
    )
    ap.add_argument("--sleep", type=float, default=0.15, help="Delay between LLM calls")
    ap.add_argument(
        "--ids",
        type=str,
        default="",
        help="Comma-separated IDs or globs, e.g. OP17-* or OP17-001,OP17-022",
    )
    args = ap.parse_args()

    catalog = load_catalog()
    lib_path, _ovr_path = library_paths()
    existing = load_existing(lib_path)

    id_patterns = [p.strip() for p in str(args.ids or "").split(",") if p.strip()]

    use_base = args.incremental or args.fill_gaps or bool(id_patterns)
    skip_existing = args.incremental or args.fill_gaps
    cards_out: dict[str, dict] = dict(existing) if use_base else {}
    report: dict = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": (
            "fill_gaps"
            if args.fill_gaps
            else ("incremental" if args.incremental else "full")
        ),
        "used_llm": bool(args.llm),
        "totals": {
            "cards": 0,
            "with_abilities": 0,
            "runnable": 0,
            "unsupported": 0,
            "empty_with_text": 0,
            "llm_calls": 0,
            "recompiled": 0,
        },
        "by_timing": {
            t: {"compiled": 0, "needs_review": 0, "unsupported": 0, "verified": 0}
            for t in sorted(TIMINGS)
        },
        "by_reason": {},
        "timing_gaps": {},
        "needs_review_ids": [],
    }
    reason_counter: Counter[str] = Counter()
    gap_counter: Counter[str] = Counter()

    ask = get_deepseek_asker() if args.llm else None
    if args.llm and ask is None:
        print(
            "WARNING: --llm requested but DEEPSEEK_API_KEY / openai unavailable; templates only.",
            file=sys.stderr,
        )

    ids = sorted(catalog.keys())
    if id_patterns:
        ids = [
            cid
            for cid in ids
            if any(fnmatch(cid, pat) or cid == pat for pat in id_patterns)
        ]
        if not ids:
            raise SystemExit(f"No catalog cards matched --ids {id_patterns}")
    if args.limit > 0:
        ids = ids[: args.limit]

    # Cache LLM/template results by base id so alt-arts reuse one compile.
    base_cache: dict[str, list[dict]] = {}

    for i, cid in enumerate(ids):
        info = catalog[cid] or {}
        blob = effect_blob(info)
        base = _base_card_id(cid)
        if skip_existing and cid in existing:
            if _should_skip_incremental(info, existing[cid], fill_gaps=args.fill_gaps):
                cards_out[cid] = normalize_card_entry(cid, existing[cid])
                continue

        prev_abs = list((existing.get(cid) or {}).get("abilities") or []) if skip_existing else []
        if base in base_cache:
            abilities = merge_abilities(prev_abs, list(base_cache[base]))
            entry = normalize_card_entry(cid, {"version": 1, "abilities": abilities})
            cards_out[cid] = entry
            report["totals"]["recompiled"] += 1
            if (i + 1) % 500 == 0:
                print(f"... compiled {i + 1}/{len(ids)}")
            continue

        entry = compile_card_from_templates(cid, info)
        abilities = list(entry.get("abilities") or [])
        if prev_abs:
            abilities = merge_abilities(prev_abs, abilities)
        report["totals"]["recompiled"] += 1

        if ask is not None and _ability_has_gap_for_llm(info, abilities):
            llm_abs = llm_compile_ability(cid, info, ask)
            if llm_abs:
                abilities = merge_abilities(abilities, llm_abs)
            report["totals"]["llm_calls"] += 1
            if report["totals"]["llm_calls"] % 25 == 0:
                print(
                    f"... llm_calls={report['totals']['llm_calls']} last={cid} "
                    f"recompiled={report['totals']['recompiled']}",
                    flush=True,
                )
            time.sleep(max(0.0, args.sleep))

        # After LLM, re-stub any still-missing detected timings
        by_t = {a["timing"]: a for a in abilities}
        for timing in detect_timings_in_text(blob):
            cur = by_t.get(timing)
            if cur is None or not ability_is_runnable(cur):
                if cur is None or cur.get("status") != "unsupported":
                    stub = normalize_ability(
                        {
                            "timing": timing,
                            "summary": f"Needs review / unsupported (complex_{timing})",
                            "ops": [{"op": "unsupported", "reason": f"complex_{timing}"}],
                            "status": "unsupported",
                            "confidence": 0.1,
                        }
                    )
                    if stub:
                        by_t[timing] = stub
                gap_counter[timing] += 1
        abilities = list(by_t.values())
        base_cache[base] = abilities

        entry = normalize_card_entry(cid, {"version": 1, "abilities": abilities})
        cards_out[cid] = entry

        if (i + 1) % 500 == 0:
            print(f"... compiled {i + 1}/{len(ids)}")

    # Ensure every catalog card is present when fill-gaps/incremental
    if use_base:
        for cid in ids:
            cards_out.setdefault(cid, normalize_card_entry(cid, existing.get(cid) or {"abilities": []}))

    # Stats
    for cid, entry in cards_out.items():
        report["totals"]["cards"] += 1
        abs_ = entry.get("abilities") or []
        info = catalog.get(cid) or {}
        blob = effect_blob(info)
        if abs_:
            report["totals"]["with_abilities"] += 1
        elif blob.strip():
            report["totals"]["empty_with_text"] += 1
        for a in abs_:
            st = a.get("status") or "compiled"
            t = a.get("timing")
            if t in report["by_timing"] and st in report["by_timing"][t]:
                report["by_timing"][t][st] += 1
            ops = a.get("ops") or []
            runnable = ability_is_runnable(a)
            if runnable:
                report["totals"]["runnable"] += 1
            if st == "unsupported":
                report["totals"]["unsupported"] += 1
                for o in ops:
                    if o.get("op") == "unsupported":
                        reason_counter[str(o.get("reason") or "unsupported")] += 1
            if st == "needs_review":
                report["needs_review_ids"].append(cid)
            if blob and t and t in detect_timings_in_text(blob) and not runnable:
                gap_counter[str(t)] += 1

    report["needs_review_ids"] = sorted(set(report["needs_review_ids"]))[:500]
    report["by_reason"] = dict(reason_counter.most_common(50))
    report["timing_gaps"] = dict(gap_counter.most_common())

    lib_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "generated_at": report["generated_at"],
        "cards": cards_out,
    }
    with lib_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=None, separators=(",", ":"))

    report_path = ROOT / "meta" / "effect_compile_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Wrote {lib_path} ({len(cards_out)} cards)")
    print(f"Wrote {report_path}")
    print(json.dumps(report["totals"], ensure_ascii=False))
    print("timing_gaps", json.dumps(report["timing_gaps"], ensure_ascii=False))

    # Keep gap tracker in sync with the library we just wrote.
    try:
        import subprocess

        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "track_effect_gaps.py")],
            check=False,
            cwd=str(ROOT),
        )
    except Exception as exc:
        print(f"gap tracker refresh skipped: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
