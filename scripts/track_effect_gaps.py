#!/usr/bin/env python3
"""Regenerate effect gap tracker from the current card_effects library.

Usage:
  .venv/bin/python scripts/track_effect_gaps.py

Writes:
  meta/effect_gap_tracker.json
  meta/effect_gap_tracker.md
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_schema import ability_is_runnable  # noqa: E402
from battle.effects import effect_blob, has_meaningful_effect_text  # noqa: E402
from battle.effect_library import library_paths, reload_effect_library  # noqa: E402


def _base_card_id(cid: str) -> str:
    return re.sub(r"-(?:P|R)\d+$", "", cid)


def main() -> int:
    reload_effect_library(force=True)
    catalog_path = ROOT / "index" / "cards_by_id.json"
    cards = json.loads(catalog_path.read_text(encoding="utf-8"))
    lib_path, _ = library_paths()
    raw = json.loads(lib_path.read_text(encoding="utf-8"))
    lib = raw["cards"] if isinstance(raw.get("cards"), dict) else raw
    report_path = ROOT / "meta" / "effect_compile_report.json"
    generated = None
    runnable = None
    if report_path.is_file():
        rep = json.loads(report_path.read_text(encoding="utf-8"))
        generated = rep.get("generated_at")
        runnable = (rep.get("totals") or {}).get("runnable")

    gaps: list[dict] = []
    empty: list[dict] = []
    by_reason: Counter[str] = Counter()
    by_timing: Counter[str] = Counter()

    for cid, info in cards.items():
        blob = effect_blob(info).strip()
        abs_ = (lib.get(cid) or {}).get("abilities") or []
        name = info.get("name") or info.get("name_en") or cid
        if has_meaningful_effect_text(info) and not abs_:
            empty.append({"id": cid, "name": name, "effect": blob[:160]})
        for a in abs_:
            if ability_is_runnable(a):
                continue
            timing = str(a.get("timing") or "?")
            reason = "unsupported"
            for o in a.get("ops") or []:
                if o.get("op") == "unsupported":
                    reason = str(o.get("reason") or "unsupported")
                    break
            by_reason[reason] += 1
            by_timing[timing] += 1
            gaps.append(
                {
                    "id": cid,
                    "name": name,
                    "timing": timing,
                    "status": a.get("status") or "unsupported",
                    "reason": reason,
                    "summary": str(a.get("summary") or "")[:120],
                    "effect": blob[:140],
                }
            )

    out = {
        "generated_from_report": generated,
        "totals": {
            "unsupported_or_nonrunnable_abilities": len(gaps),
            "unique_gap_bases": len({_base_card_id(g["id"]) for g in gaps}),
            "empty_with_text": len(empty),
            "unique_empty_bases": len({_base_card_id(e["id"]) for e in empty}),
            "runnable_from_report": runnable,
        },
        "by_reason": dict(by_reason.most_common()),
        "by_timing": dict(by_timing.most_common()),
        "top_gaps": gaps,
        "empty_samples": empty,
    }

    meta = ROOT / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "effect_gap_tracker.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# Effect gap tracker\n\n",
        f"Source compile: `{generated}`\n\n",
        f"- Non-runnable abilities: **{len(gaps)}** "
        f"({out['totals']['unique_gap_bases']} unique bases)\n",
        f"- Empty with text: **{len(empty)}** "
        f"({out['totals']['unique_empty_bases']} unique bases)\n",
        f"- Runnable abilities (report): **{runnable}**\n\n",
        "## By reason\n\n",
    ]
    for r, c in by_reason.most_common():
        lines.append(f"- `{r}`: {c}\n")
    lines.append("\n## By timing\n\n")
    for t, c in by_timing.most_common():
        lines.append(f"- `{t}`: {c}\n")
    lines.append("\n## Gaps (all)\n\n")
    lines.append("| ID | Name | Timing | Reason |\n|----|------|--------|--------|\n")
    for g in gaps:
        lines.append(
            f"| {g['id']} | {g['name']} | {g['timing']} | `{g['reason']}` |\n"
        )
    (meta / "effect_gap_tracker.md").write_text("".join(lines), encoding="utf-8")
    print(json.dumps(out["totals"], ensure_ascii=False))
    print(f"Wrote {meta / 'effect_gap_tracker.json'}")
    print(f"Wrote {meta / 'effect_gap_tracker.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
