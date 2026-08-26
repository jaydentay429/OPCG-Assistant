#!/usr/bin/env python3
"""Targeted recompile for cards still listed in the effect gap tracker.

Uses DeepSeek on unique base IDs only (alt-arts share results), then merges
back into index/card_effects.json and refreshes the gap tracker.

Usage:
  # All unique gap bases (non-runnable abilities)
  .venv/bin/python scripts/compile_gap_cards.py --llm

  # Only one reason / timing bucket
  .venv/bin/python scripts/compile_gap_cards.py --llm --reason complex_when_attacking
  .venv/bin/python scripts/compile_gap_cards.py --llm --timing when_attacking

  # Explicit IDs (comma or file)
  .venv/bin/python scripts/compile_gap_cards.py --llm --ids OP14-017,OP04-085
  .venv/bin/python scripts/compile_gap_cards.py --llm --ids-file /tmp/ids.txt

  # Dry run: print which IDs would be sent
  .venv/bin/python scripts/compile_gap_cards.py --dry-run --reason complex_trigger

  # Also include empty-with-text cards
  .venv/bin/python scripts/compile_gap_cards.py --llm --include-empty
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

from battle.effect_library import (  # noqa: E402
    compile_card_from_templates,
    detect_timings_in_text,
    library_paths,
    reload_effect_library,
)
from battle.effect_schema import (  # noqa: E402
    ability_is_runnable,
    normalize_ability,
    normalize_card_entry,
    sanitize_ops_list,
)
from battle.effects import effect_blob, get_deepseek_asker  # noqa: E402

# Reuse merge / LLM helpers from the main compiler.
from scripts.compile_card_effects import (  # noqa: E402
    _base_card_id,
    _meaningful_effect,
    llm_compile_ability,
    load_catalog,
    load_existing,
    merge_abilities,
)


def _load_tracker() -> dict:
    path = ROOT / "meta" / "effect_gap_tracker.json"
    if not path.is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "track_effect_gaps.py")], cwd=str(ROOT), check=False)
    if not path.is_file():
        return {"top_gaps": [], "empty_samples": [], "totals": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_ids(raw: str | None, file_path: str | None) -> set[str]:
    out: set[str] = set()
    if raw:
        for part in re.split(r"[\s,;]+", raw.strip()):
            if part:
                out.add(part.strip())
    if file_path:
        text = Path(file_path).read_text(encoding="utf-8")
        for part in re.split(r"[\s,;]+", text.strip()):
            if part and not part.startswith("#"):
                out.add(part.strip())
    return out


def _select_targets(
    tracker: dict,
    *,
    reason: str | None,
    timing: str | None,
    explicit_ids: set[str],
    include_empty: bool,
) -> list[str]:
    """Return sorted unique base IDs to recompile."""
    bases: set[str] = set()
    if explicit_ids:
        for cid in explicit_ids:
            bases.add(_base_card_id(cid))
        return sorted(bases)

    for g in tracker.get("top_gaps") or []:
        r = str(g.get("reason") or "")
        if reason:
            aliases = {reason, reason.replace("complex_", ""), f"complex_{reason.replace('complex_', '')}"}
            if r not in aliases:
                continue
        if timing and str(g.get("timing") or "") != timing:
            continue
        cid = str(g.get("id") or "")
        if cid:
            bases.add(_base_card_id(cid))

    if include_empty:
        from battle.effects import has_meaningful_effect_text

        for e in tracker.get("empty_samples") or []:
            cid = str(e.get("id") or "")
            if not cid:
                continue
            # Skip dash / keyword-only unless explicitly requested via --ids
            eff = str(e.get("effect") or "").strip()
            if not has_meaningful_effect_text(eff):
                continue
            bases.add(_base_card_id(cid))

    return sorted(bases)


def _focused_llm(card_id: str, info: dict, ask, focus_timings: set[str]) -> list[dict]:
    """LLM compile with an extra hint about which timings still fail."""
    blob = effect_blob(info)
    if not blob.strip():
        return []
    focus = ", ".join(sorted(focus_timings)) if focus_timings else "all marked timings"
    prompt = (
        "Compile OPTCG card effects into JSON ONLY.\n"
        "Focus especially on these still-missing/broken timings: "
        f"{focus}.\n"
        "Timing mapping rules:\n"
        "- Event [Main]/【主要】 → timing on_play (effect resolves when the Event is played).\n"
        "- Character [Activate: Main]/【啟動主要】 → timing activate_main.\n"
        "- Continuous power with no turn tag → timing your_turn (buff_self).\n"
        "- When this Leader/Character attacks or is attacked → when_attacking and/or on_opponent_attack.\n"
        "- When your opponent activates [Blocker] → on_block if expressible, else unsupported.\n"
        "Prefer real runnable ops over unsupported when the text can be expressed with:\n"
        "draw, gain_don, attach_don, set_don, rest_opponent_character, rest_character, buff, buff_self, "
        "ko, ko_lowest_opponent, search_deck, play_from_hand, trash, trash_hand, return_to_hand, "
        "return_to_bottom, add_life, deal_life_damage, rest_don, active_don, return_don, "
        "set_character_active, grant_keyword, cannot_be_ko, set_base_power*, "
        "set_power_equal_opponent_leader, choose_target, deny_blocker, allow_attack_active, "
        "replace_battle_ko, cannot_take_life, skip_untap, reorder_life.\n"
        "Play from trash / hand or trash → play_from_hand with from_zone=trash|hand_or_trash.\n"
        "Trash hand cost with [Trigger] → trash_hand require_trigger=true.\n"
        "Look-at-top / reveal-from-deck / add-to-hand MUST use search_deck.\n"
        "If truly impossible, status=unsupported with op=unsupported and a short reason.\n"
        'Return: {"abilities":[{"timing":"...","summary":"...","ops":[...],'
        '"status":"compiled|needs_review|unsupported","confidence":0.0,"once":false}]}\n'
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
        # Fall back to shared prompt
        return llm_compile_ability(card_id, info, ask)


def main() -> int:
    ap = argparse.ArgumentParser(description="Recompile only cards from the effect gap tracker")
    ap.add_argument("--llm", action="store_true", help="Use DeepSeek (recommended)")
    ap.add_argument("--reason", type=str, default="", help="Filter gap reason, e.g. complex_trigger")
    ap.add_argument("--timing", type=str, default="", help="Filter timing, e.g. when_attacking")
    ap.add_argument("--ids", type=str, default="", help="Comma-separated card IDs")
    ap.add_argument("--ids-file", type=str, default="", help="File with card IDs")
    ap.add_argument("--include-empty", action="store_true", help="Also include empty-with-text cards")
    ap.add_argument("--limit", type=int, default=0, help="Max unique bases to process")
    ap.add_argument("--sleep", type=float, default=0.08)
    ap.add_argument("--dry-run", action="store_true", help="List targets only")
    ap.add_argument("--force-llm", action="store_true", help="Always call LLM even if templates fill gaps")
    ap.add_argument(
        "--checkpoint-every",
        type=int,
        default=10,
        help="Flush library to disk every N cards (0=only at end)",
    )
    args = ap.parse_args()

    catalog = load_catalog()
    tracker = _load_tracker()
    explicit = _parse_ids(args.ids or None, args.ids_file or None)
    targets = _select_targets(
        tracker,
        reason=args.reason or None,
        timing=args.timing or None,
        explicit_ids=explicit,
        include_empty=bool(args.include_empty),
    )
    # Keep only IDs that exist in catalog
    targets = [cid for cid in targets if cid in catalog or any(k.startswith(cid + "-") for k in catalog)]
    # Expand: prefer exact base id present in catalog; else first matching variant
    resolved: list[str] = []
    for base in targets:
        if base in catalog:
            resolved.append(base)
        else:
            alts = sorted(k for k in catalog if _base_card_id(k) == base)
            if alts:
                resolved.append(alts[0])
    targets = resolved
    if args.limit > 0:
        targets = targets[: args.limit]

    print(f"Selected {len(targets)} unique bases", flush=True)
    if args.dry_run:
        for cid in targets:
            info = catalog.get(cid) or {}
            print(f"  {cid}\t{info.get('name') or info.get('name_en') or ''}")
        return 0

    if not targets:
        print("No matching gap cards.")
        return 0

    ask = get_deepseek_asker() if args.llm else None
    if args.llm and ask is None:
        print("ERROR: --llm set but DeepSeek asker unavailable (check DEEPSEEK_API_KEY).", file=sys.stderr)
        return 2

    lib_path, _ = library_paths()
    existing = load_existing(lib_path)
    cards_out = dict(existing)

    # Map base -> focus timings from tracker
    focus_by_base: dict[str, set[str]] = {}
    for g in tracker.get("top_gaps") or []:
        base = _base_card_id(str(g.get("id") or ""))
        t = str(g.get("timing") or "")
        if base and t:
            focus_by_base.setdefault(base, set()).add(t)

    improved = 0
    llm_calls = 0
    llm_errors = 0

    def _flush_library() -> None:
        payload = {
            "version": 1,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "cards": cards_out,
        }
        lib_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = lib_path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=None, separators=(",", ":"))
        tmp.replace(lib_path)

    for i, cid in enumerate(targets):
        info = catalog.get(cid) or {}
        base = _base_card_id(cid)
        # Prefer a printing that actually has effect text (promo bases are often blank).
        if not _meaningful_effect(info):
            alts = sorted(k for k in catalog if _base_card_id(k) == base)
            for alt in alts:
                if _meaningful_effect(catalog.get(alt) or {}):
                    cid = alt
                    info = catalog[alt]
                    break
        if not _meaningful_effect(info) and not explicit:
            print(f"skip blank {cid}", flush=True)
            continue
        prev = list((existing.get(cid) or {}).get("abilities") or [])
        entry = compile_card_from_templates(cid, info)
        # Template wins for timings it can compile; keep prior only for leftover timings.
        by_t = {a["timing"]: a for a in prev}
        for a in entry.get("abilities") or []:
            if ability_is_runnable(a):
                by_t[a["timing"]] = a
            elif a["timing"] not in by_t:
                by_t[a["timing"]] = a
        abilities = list(by_t.values())

        still_gap = any(not ability_is_runnable(a) for a in abilities) or not abilities
        if ask is not None and (still_gap or args.force_llm):
            focus = focus_by_base.get(base) or detect_timings_in_text(effect_blob(info))
            if args.timing:
                focus = {args.timing}
            try:
                llm_abs = _focused_llm(cid, info, ask, set(focus))
            except Exception as exc:
                llm_errors += 1
                print(f"LLM error {cid}: {type(exc).__name__}: {exc}", flush=True)
                llm_abs = []
            if llm_abs:
                for a in llm_abs:
                    if ability_is_runnable(a):
                        by_t[a["timing"]] = a
                    elif a["timing"] not in by_t or not ability_is_runnable(by_t[a["timing"]]):
                        by_t[a["timing"]] = a
                abilities = list(by_t.values())
            llm_calls += 1
            time.sleep(max(0.0, args.sleep))

        # Re-stub missing timings; drop stale timings not in text and not in fresh templates.
        # Keep runnable abilities even when text has no explicit timing tag
        # (continuous effects often compile as your_turn / opponent_turn).
        detected = detect_timings_in_text(effect_blob(info))
        templ_timings = {
            str(a.get("timing"))
            for a in (entry.get("abilities") or [])
            if ability_is_runnable(a)
        }
        by_t = {a["timing"]: a for a in abilities}
        for timing in list(by_t.keys()):
            cur = by_t.get(timing)
            if ability_is_runnable(cur):
                continue
            if timing not in detected and timing not in templ_timings:
                del by_t[timing]
        for timing in detected:
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
        abilities = list(by_t.values())
        new_entry = normalize_card_entry(cid, {"version": 1, "abilities": abilities})

        before_run = sum(1 for a in prev if ability_is_runnable(a))
        after_run = sum(1 for a in abilities if ability_is_runnable(a))
        if after_run > before_run:
            improved += 1

        # Write base + all alt-arts sharing this base (per-variant template when text differs).
        for variant in sorted(k for k in catalog if _base_card_id(k) == base):
            v_info = catalog.get(variant) or {}
            if _meaningful_effect(v_info):
                v_entry = compile_card_from_templates(variant, v_info)
                v_prev = list((existing.get(variant) or {}).get("abilities") or [])
                v_by = {a["timing"]: a for a in v_prev}
                for a in v_entry.get("abilities") or []:
                    if ability_is_runnable(a):
                        v_by[a["timing"]] = a
                    elif a["timing"] not in v_by:
                        v_by[a["timing"]] = a
                v_det = detect_timings_in_text(effect_blob(v_info))
                v_templ = {
                    str(a.get("timing"))
                    for a in (v_entry.get("abilities") or [])
                    if ability_is_runnable(a)
                }
                for timing in list(v_by.keys()):
                    cur = v_by.get(timing)
                    if ability_is_runnable(cur):
                        continue
                    if timing not in v_det and timing not in v_templ:
                        del v_by[timing]
                for timing in v_det:
                    cur = v_by.get(timing)
                    if cur is None or not ability_is_runnable(cur):
                        shared = by_t.get(timing)
                        if shared and ability_is_runnable(shared):
                            v_by[timing] = shared
                        elif cur is None or cur.get("status") != "unsupported":
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
                                v_by[timing] = stub
                # Propagate runnable continuous / LLM fills from representative card.
                for t, a in by_t.items():
                    if not ability_is_runnable(a):
                        continue
                    if t not in v_by or not ability_is_runnable(v_by.get(t)):
                        v_by[t] = a
                cards_out[variant] = normalize_card_entry(variant, {"version": 1, "abilities": list(v_by.values())})
            else:
                cards_out[variant] = normalize_card_entry(variant, {"version": 1, "abilities": abilities})

        # Keep in-memory existing updated so later variants / checkpoints see new fills.
        existing[cid] = new_entry
        for variant in sorted(k for k in catalog if _base_card_id(k) == base):
            if variant in cards_out:
                existing[variant] = cards_out[variant]

        print(
            f"[{i + 1}/{len(targets)}] {cid} runnable {before_run}->{after_run} "
            f"timings={[a.get('timing') for a in abilities]}",
            flush=True,
        )

        if args.checkpoint_every and args.checkpoint_every > 0 and (i + 1) % int(args.checkpoint_every) == 0:
            _flush_library()
            print(f"checkpoint saved after {i + 1} cards", flush=True)

    _flush_library()
    reload_effect_library(force=True)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "track_effect_gaps.py")], cwd=str(ROOT), check=False)

    print(
        json.dumps(
            {
                "targets": len(targets),
                "llm_calls": llm_calls,
                "llm_errors": llm_errors,
                "improved_cards": improved,
                "library": str(lib_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
