#!/usr/bin/env python3
"""Audit all card effects vs text; record mismatches by category (read-only).

Usage:
  .venv/bin/python scripts/audit_card_effects.py
  .venv/bin/python scripts/audit_card_effects.py --base-only
  .venv/bin/python scripts/audit_card_effects.py --category ko_own_as_opp
  .venv/bin/python scripts/audit_card_effects.py --limit 200

Writes:
  meta/effect_audit_report.json
  meta/effect_audit_report.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from battle.effect_audit import report_to_markdown, run_audit  # noqa: E402
from battle.effect_library import reload_effect_library  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit compiled card effects vs card text")
    parser.add_argument(
        "--base-only",
        action="store_true",
        help="Deduplicate alt arts; scan one id per base card",
    )
    parser.add_argument(
        "--category",
        default=None,
        help="Only emit findings for this category (e.g. ko_own_as_opp)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Scan at most N cards (debug)",
    )
    args = parser.parse_args(argv)

    reload_effect_library(force=True)
    catalog_path = ROOT / "index" / "cards_by_id.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))

    report = run_audit(
        catalog,
        base_only=bool(args.base_only),
        category=args.category,
        limit=args.limit,
    )

    meta = ROOT / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    json_path = meta / "effect_audit_report.json"
    md_path = meta / "effect_audit_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(report_to_markdown(report), encoding="utf-8")

    print(json.dumps({"totals": report["totals"], "by_category": report["by_category"]}, ensure_ascii=False, indent=2))
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
