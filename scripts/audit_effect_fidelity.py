#!/usr/bin/env python3
"""Full-library paper-signal fidelity audit (read-only).

Usage:
  python3 scripts/audit_effect_fidelity.py
  python3 scripts/audit_effect_fidelity.py --all-variants
  python3 scripts/audit_effect_fidelity.py --severity high
  python3 scripts/audit_effect_fidelity.py --limit 200

Writes:
  meta/effect_fidelity_full_report.json
  meta/effect_fidelity_full_report.md
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_fidelity import report_to_markdown, run_fidelity_audit  # noqa: E402
from battle.effect_library import get_abilities, reload_effect_library  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Full-library effect fidelity audit")
    parser.add_argument(
        "--all-variants",
        action="store_true",
        help="Scan every card id (default: one per base)",
    )
    parser.add_argument(
        "--severity",
        default="medium",
        choices=["low", "medium", "high", "critical"],
        help="Minimum severity to include (default medium)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Scan at most N meaningful cards")
    args = parser.parse_args(argv)

    reload_effect_library(force=True)
    catalog = json.loads((ROOT / "index" / "cards_by_id.json").read_text(encoding="utf-8"))

    report = run_fidelity_audit(
        catalog,
        get_abilities=get_abilities,
        base_only=not args.all_variants,
        limit=args.limit,
        severity_min=args.severity,
    )
    report["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    meta = ROOT / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    json_path = meta / "effect_fidelity_full_report.json"
    md_path = meta / "effect_fidelity_full_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(report_to_markdown(report), encoding="utf-8")

    totals = report["totals"]
    print(
        json.dumps(
            {
                "scanned": totals["cards_scanned"],
                "pass": totals["pass_bases"],
                "fail": totals["fail_bases"],
                "findings": totals["findings"],
                "by_category": report.get("by_category"),
                "json": str(json_path),
                "md": str(md_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
