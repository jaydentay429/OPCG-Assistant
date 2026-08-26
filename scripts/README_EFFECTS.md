# Effect library compile

Offline:
  .venv/bin/python scripts/compile_card_effects.py
  .venv/bin/python scripts/compile_card_effects.py --fill-gaps
  .venv/bin/python scripts/compile_card_effects.py --llm --fill-gaps
  .venv/bin/python scripts/track_effect_gaps.py

Full-library semantic scan → problem queue (recommended):
  .venv/bin/python scripts/run_full_effect_scan.py
  .venv/bin/python scripts/run_full_effect_scan.py --skip-llm
  .venv/bin/python scripts/run_full_effect_scan.py --llm-limit 50
  .venv/bin/python scripts/run_full_effect_scan.py --resume-llm
  → meta/effect_problem_queue.json / .md
  → meta/effect_semantic_review.json
  → meta/effect_runtime_smoke.json

  Goal: each meaningful card is either later verified, or has a concrete Chinese
  diagnosis in the queue. Fix by walking the queue top-down (parser or overrides).

LLM semantic review alone:
  .venv/bin/python scripts/review_effect_semantics.py --limit 20
  .venv/bin/python scripts/review_effect_semantics.py

Rebuild queue from existing reports:
  .venv/bin/python scripts/build_effect_problem_queue.py

Full-library effect audit (text vs compiled ops; read-only):
  .venv/bin/python scripts/audit_card_effects.py
  .venv/bin/python scripts/audit_card_effects.py --base-only
  .venv/bin/python scripts/audit_card_effects.py --category ko_own_as_opp
  → meta/effect_audit_report.json / .md

Full-library paper fidelity:
  .venv/bin/python scripts/audit_effect_fidelity.py
  .venv/bin/python scripts/audit_effect_fidelity.py --severity high
  .venv/bin/python scripts/audit_effect_fidelity.py --all-variants
  → meta/effect_fidelity_full_report.json / .md

  Focus ABC goldens:
  .venv/bin/python scripts/report_effect_fidelity.py
  → meta/effect_fidelity_report.md

Batch-fix high-confidence fidelity gaps:
  .venv/bin/python scripts/fix_fidelity_batch.py --dry-run
  .venv/bin/python scripts/fix_fidelity_batch.py

Recommended loop:
  1) run_full_effect_scan.py (resume LLM until semantic review complete)
  2) fix_fidelity_batch.py for easy auto-fixes
  3) walk meta/effect_problem_queue.md: parser or card_effect_overrides.json (verified)
  4) mark fixed; add golden test when possible

Targeted gap recompile:
  .venv/bin/python scripts/compile_gap_cards.py --dry-run
  .venv/bin/python scripts/compile_gap_cards.py --llm --timing when_attacking
  .venv/bin/python scripts/compile_gap_cards.py --llm --reason complex_trigger --limit 50
  .venv/bin/python scripts/compile_gap_cards.py --llm --ids OP14-017,OP04-085
  .venv/bin/python scripts/compile_gap_cards.py --llm --include-empty

Flags (compile_card_effects):
  --fill-gaps     Recompile cards that have text timings without runnable abilities
  --llm           Fill remaining unsupported/missing timings via DeepSeek
  --incremental   Only missing / all-unsupported cards (legacy)
  --sleep N       Delay between LLM calls (default 0.15)

Outputs:
  index/card_effects.json
  meta/effect_compile_report.json
  meta/effect_gap_tracker.json / .md
  meta/effect_audit_report.json / .md
  meta/effect_fidelity_full_report.json / .md
  meta/effect_fidelity_report.md
  meta/effect_semantic_review.json
  meta/effect_runtime_smoke.json / .md
  meta/effect_problem_queue.json / .md

Overrides (win over auto compile):
  index/card_effect_overrides.json
  POST /battle/effect-library/override

Tests:
  .venv/bin/python battle/tests/test_effect_library.py
  .venv/bin/python battle/tests/test_effect_audit.py
  .venv/bin/python battle/tests/test_effect_fidelity.py
  .venv/bin/python battle/tests/test_abc_fidelity.py
