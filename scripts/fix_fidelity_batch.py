#!/usr/bin/env python3
"""Batch-fix high-confidence full-library fidelity gaps.

Actions:
  1) Attach missing require_* / leader gates from text onto primary abilities
  2) Attach exclude_name onto deny_attack ops
  3) Fix attack_tax miscompiled as deny_rest-all
  4) Demote compiled choose-one misses / dangling choose_target to needs_review
  5) Prefer template abilities when library is choose_target-only stub

Usage:
  python3 scripts/fix_fidelity_batch.py --dry-run
  python3 scripts/fix_fidelity_batch.py
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

from battle.effect_fidelity import base_card_id, extract_expected_signals  # noqa: E402
from battle.effect_library import (  # noqa: E402
    compile_card_from_templates,
    library_paths,
    reload_effect_library,
)
from battle.effect_schema import ability_is_runnable, normalize_ability, normalize_card_entry  # noqa: E402
from battle.effects import has_meaningful_effect_text  # noqa: E402


def _primary_timing(abilities: list[dict]) -> str | None:
    order = (
        "on_play",
        "counter_event",
        "when_attacking",
        "on_ko",
        "on_block",
        "on_opponent_attack",
        "activate_main",
        "trigger",
        "your_turn",
        "opponent_turn",
        "end_of_your_turn",
    )
    by = {a.get("timing"): a for a in abilities}
    for t in order:
        if t in by and ability_is_runnable(by[t]):
            return t
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))
    lib_path, _ = library_paths()
    raw = json.loads(lib_path.read_text(encoding="utf-8"))
    cards = raw.get("cards") or raw

    stats = {
        "gates_attached": 0,
        "exclude_name": 0,
        "attack_tax": 0,
        "demoted_choose_one": 0,
        "demoted_stub": 0,
        "template_promoted": 0,
        "cards_touched": 0,
    }

    for cid, info in catalog.items():
        if not has_meaningful_effect_text(info):
            continue
        entry = cards.get(cid) or {"abilities": []}
        abilities = list(entry.get("abilities") or [])
        if not abilities:
            continue
        expected = extract_expected_signals(info)
        by_t = {a.get("timing"): dict(a) for a in abilities if a.get("timing")}
        changed = False

        # 1) Attach gates onto primary ability
        pt = _primary_timing(list(by_t.values()))
        if pt:
            a = by_t[pt]
            if a.get("status") in {"compiled", "verified", "needs_review"}:
                for g, val in (expected.get("gates") or {}).items():
                    if a.get(g) is None:
                        a[g] = val
                        changed = True
                        stats["gates_attached"] += 1
                if expected.get("leader_trait") and not a.get("require_leader_trait"):
                    a["require_leader_trait"] = expected["leader_trait"][:40]
                    changed = True
                    stats["gates_attached"] += 1
                if expected.get("leader_name") and not a.get("require_leader_name"):
                    a["require_leader_name"] = expected["leader_name"][:60]
                    changed = True
                    stats["gates_attached"] += 1
            by_t[pt] = a

        # 2) exclude_name on deny_attack
        excl = expected.get("exclude_name") or ""
        if excl:
            for t, a in list(by_t.items()):
                ops = []
                op_ch = False
                for o in a.get("ops") or []:
                    if o.get("op") == "deny_attack" and not o.get("exclude_name"):
                        o = dict(o)
                        o["exclude_name"] = excl
                        op_ch = True
                        stats["exclude_name"] += 1
                    ops.append(o)
                if op_ch:
                    a = dict(a)
                    a["ops"] = ops
                    by_t[t] = a
                    changed = True

        # 3) attack_tax fix when deny_rest-all stands in for tax text
        if "attack_tax" in (expected.get("op_hints") or []):
            for t, a in list(by_t.items()):
                ops = a.get("ops") or []
                if any(o.get("op") == "attack_tax" for o in ops):
                    continue
                if any(o.get("op") == "deny_rest" and o.get("all") for o in ops) or (
                    t == "on_play"
                    and a.get("status") == "compiled"
                    and any(o.get("op") in {"deny_rest", "deny_attack", "choose_target"} for o in ops)
                ):
                    blob = f"{info.get('effect_en') or ''}\n{info.get('effect') or ''}"
                    m = re.search(r"trash\s*(\d+)|廢棄\s*(\d+)\s*張|废弃\s*(\d+)\s*张", blob, re.I)
                    n = int(next(g for g in m.groups() if g)) if m else 2
                    a = dict(a)
                    a["ops"] = [
                        {
                            "op": "attack_tax",
                            "trash_hand": max(1, min(5, n)),
                            "all": True,
                            "duration": "until_opp_turn_end",
                        }
                    ]
                    a["status"] = "compiled"
                    a["confidence"] = max(float(a.get("confidence") or 0.6), 0.85)
                    by_t[t] = a
                    changed = True
                    stats["attack_tax"] += 1
                    break

        # 4) demote choose-one misses
        if "choose_one" in (expected.get("op_hints") or []):
            has_choose = any(
                any(o.get("op") == "choose_one" for o in (a.get("ops") or [])) for a in by_t.values()
            )
            if not has_choose:
                for t, a in list(by_t.items()):
                    if t in {"on_play", "counter_event", "activate_main"} and a.get("status") == "compiled":
                        ops = {o.get("op") for o in (a.get("ops") or [])}
                        if "activate_timing" not in ops and "choose_one" not in ops:
                            a = dict(a)
                            a["status"] = "needs_review"
                            a["confidence"] = min(float(a.get("confidence") or 0.5), 0.45)
                            by_t[t] = a
                            changed = True
                            stats["demoted_choose_one"] += 1

        # 5) demote dangling choose_target compiled
        for t, a in list(by_t.items()):
            ops = a.get("ops") or []
            if (
                a.get("status") == "compiled"
                and ops
                and all(o.get("op") == "choose_target" and not o.get("then_op") for o in ops)
            ):
                a = dict(a)
                a["status"] = "needs_review"
                a["confidence"] = 0.35
                by_t[t] = a
                changed = True
                stats["demoted_stub"] += 1

        # 6) template promote when library stub
        fresh = compile_card_from_templates(cid, info)
        for a in fresh.get("abilities") or []:
            t = a.get("timing")
            if not t or not ability_is_runnable(a):
                continue
            lib = by_t.get(t)
            fresh_ops = [o.get("op") for o in (a.get("ops") or [])]
            if not fresh_ops or set(fresh_ops) <= {"unsupported", "choose_target"}:
                continue
            if lib is None or not ability_is_runnable(lib):
                by_t[t] = a
                changed = True
                stats["template_promoted"] += 1
                continue
            lib_ops = [o.get("op") for o in (lib.get("ops") or [])]
            if set(lib_ops) <= {"choose_target", "unsupported"} and set(fresh_ops) - {"unsupported", "choose_target"}:
                na = normalize_ability(a) or a
                by_t[t] = na
                changed = True
                stats["template_promoted"] += 1

        if changed:
            normalized = []
            for a in by_t.values():
                na = normalize_ability(a)
                if na:
                    normalized.append(na)
            cards[cid] = normalize_card_entry(cid, {"version": 1, "abilities": normalized})
            stats["cards_touched"] += 1

    print(json.dumps(stats, ensure_ascii=False))
    if args.dry_run:
        print("dry-run: no write")
        return 0

    lib_path.write_text(
        json.dumps(
            {"version": 1, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "cards": cards},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    reload_effect_library(force=True)
    print(f"wrote {lib_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
