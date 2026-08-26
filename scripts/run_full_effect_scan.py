#!/usr/bin/env python3
"""Full effect quality scan → problem queue.

Usage:
  .venv/bin/python scripts/run_full_effect_scan.py
  .venv/bin/python scripts/run_full_effect_scan.py --skip-llm
  .venv/bin/python scripts/run_full_effect_scan.py --llm-limit 50
  .venv/bin/python scripts/run_full_effect_scan.py --resume-llm

Steps:
  1) track_effect_gaps
  2) audit_card_effects
  3) audit_effect_fidelity
  4) smoke_effect_runtime
  5) review_effect_semantics (LLM, optional)
  6) build_effect_problem_queue
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def _run(label: str, args: list[str]) -> int:
    print(f"\n======== {label} ========", flush=True)
    print(" ".join(args), flush=True)
    t0 = time.time()
    proc = subprocess.run(args, cwd=str(ROOT))
    print(f"[{label}] rc={proc.returncode} elapsed={time.time() - t0:.1f}s", flush=True)
    return int(proc.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Full effect scan → problem queue")
    parser.add_argument("--skip-llm", action="store_true", help="Skip DeepSeek semantic review")
    parser.add_argument("--resume-llm", action="store_true", help="Resume semantic review file")
    parser.add_argument("--llm-limit", type=int, default=0, help="Limit new LLM reviews this run")
    parser.add_argument("--llm-sleep", type=float, default=0.2)
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument("--skip-fidelity", action="store_true")
    parser.add_argument("--skip-audit", action="store_true")
    parser.add_argument("--recompile", action="store_true", help="Recompile card_effects first")
    args = parser.parse_args(argv)

    rc_all = 0
    if args.recompile:
        rc = _run("compile", [PY, "scripts/compile_card_effects.py"])
        rc_all = rc_all or rc

    rc = _run("gaps", [PY, "scripts/track_effect_gaps.py"])
    rc_all = rc_all or rc

    if not args.skip_audit:
        rc = _run("audit", [PY, "scripts/audit_card_effects.py", "--base-only"])
        rc_all = rc_all or rc

    if not args.skip_fidelity:
        rc = _run(
            "fidelity",
            [PY, "scripts/audit_effect_fidelity.py", "--severity", "medium"],
        )
        rc_all = rc_all or rc

    if not args.skip_smoke:
        rc = _run("smoke", [PY, "scripts/smoke_effect_runtime.py", "--base-only"])
        rc_all = rc_all or rc

    if not args.skip_llm:
        llm_cmd = [PY, "scripts/review_effect_semantics.py", "--sleep", str(args.llm_sleep)]
        if args.resume_llm:
            llm_cmd.append("--resume")
        if args.llm_limit and args.llm_limit > 0:
            llm_cmd.extend(["--limit", str(args.llm_limit)])
        rc = _run("semantic_llm", llm_cmd)
        rc_all = rc_all or rc

    rc = _run("queue", [PY, "scripts/build_effect_problem_queue.py"])
    rc_all = rc_all or rc
    print("\nDone. See meta/effect_problem_queue.md", flush=True)
    return rc_all


if __name__ == "__main__":
    raise SystemExit(main())
