#!/usr/bin/env python3
"""Runtime smoke: resolve_ability for runnable timings; catch exceptions.

Usage:
  .venv/bin/python scripts/smoke_effect_runtime.py
  .venv/bin/python scripts/smoke_effect_runtime.py --base-only --limit 500

Writes:
  meta/effect_runtime_smoke.json
  meta/effect_runtime_smoke.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_library import get_abilities, reload_effect_library, resolve_ability  # noqa: E402
from battle.effect_schema import ability_is_runnable  # noqa: E402
from battle.effects import has_meaningful_effect_text  # noqa: E402
from battle.state import MatchState, PlayerState  # noqa: E402


def _base_card_id(cid: str) -> str:
    return re.sub(r"-(?:P|R)\d+$", "", cid)


def _minimal_state() -> MatchState:
    p0 = PlayerState(
        seat=0,
        user_id="u0",
        username="P1",
        is_ai=False,
        leader_card_id="ST01-001",
        deck=["ST01-002"] * 20,
        hand=["ST01-003", "ST01-004"],
        life=["ST01-005"] * 5,
    )
    p1 = PlayerState(
        seat=1,
        user_id="u1",
        username="AI",
        is_ai=True,
        leader_card_id="ST01-001",
        deck=["ST01-002"] * 20,
        hand=["ST01-003"],
        life=["ST01-005"] * 5,
    )
    return MatchState(
        room_code="SMOKE",
        status="playing",
        phase="main",
        turn_seat=0,
        first_seat=0,
        turn_number=1,
        players=[p0, p1],
        rng_seed=1,
    )


def iter_ids(catalog: dict[str, Any], *, base_only: bool) -> list[str]:
    if not base_only:
        return sorted(catalog.keys())
    seen: set[str] = set()
    out: list[str] = []
    for cid in sorted(catalog.keys()):
        base = _base_card_id(cid)
        if base in seen:
            continue
        if base in catalog:
            seen.add(base)
            out.append(base)
        else:
            seen.add(base)
            out.append(cid)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Runtime smoke for compiled effects")
    parser.add_argument("--base-only", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)

    reload_effect_library(force=True)
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))
    ids = iter_ids(catalog, base_only=args.base_only)
    if args.limit and args.limit > 0:
        ids = ids[: int(args.limit)]

    errors: list[dict[str, Any]] = []
    scanned = 0
    runnable_checks = 0
    for cid in ids:
        info = catalog.get(cid)
        if not isinstance(info, dict):
            continue
        if not has_meaningful_effect_text(info):
            continue
        scanned += 1
        abilities = get_abilities(cid)
        for a in abilities:
            if not ability_is_runnable(a):
                continue
            timing = str(a.get("timing") or "")
            if not timing:
                continue
            runnable_checks += 1
            state = _minimal_state()
            try:
                resolve_ability(
                    state, 0, cid, "smoke1", timing, info, None, allow_llm=False, catalog=catalog
                )
            except Exception as exc:
                errors.append(
                    {
                        "card_id": cid,
                        "base_id": _base_card_id(cid),
                        "name": info.get("name") or info.get("name_en") or cid,
                        "timing": timing,
                        "error": f"{type(exc).__name__}: {exc}",
                        "trace": traceback.format_exc(limit=4)[-500:],
                    }
                )

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "totals": {
            "cards_scanned": scanned,
            "runnable_checks": runnable_checks,
            "errors": len(errors),
            "unique_bases": len({e["base_id"] for e in errors}),
        },
        "errors": errors,
    }
    meta = ROOT / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    json_path = meta / "effect_runtime_smoke.json"
    md_path = meta / "effect_runtime_smoke.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Effect runtime smoke\n\n",
        f"Generated: `{report['generated_at']}`\n\n",
        f"- Cards scanned: **{report['totals']['cards_scanned']}**\n",
        f"- Runnable checks: **{report['totals']['runnable_checks']}**\n",
        f"- Errors: **{report['totals']['errors']}**\n\n",
    ]
    if errors:
        lines.append("| ID | Timing | Error |\n|----|--------|-------|\n")
        for e in errors[:200]:
            err = str(e.get("error") or "").replace("|", "/")[:120]
            lines.append(f"| {e.get('card_id')} | {e.get('timing')} | {err} |\n")
    md_path.write_text("".join(lines), encoding="utf-8")
    print(json.dumps({"totals": report["totals"], "json": str(json_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
