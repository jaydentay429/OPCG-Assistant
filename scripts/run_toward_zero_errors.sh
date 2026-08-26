#!/usr/bin/env bash
# Drive toward zero effect errors: deterministic repair → hard overrides →
# fidelity batch → semantic LLM repair rounds → re-review → queue rebuild.
set -uo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-.venv/bin/python}"
LOG_DIR=meta/logs
mkdir -p "$LOG_DIR"
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG="$LOG_DIR/zero_errors_${TS}.log"
ln -sfn "$(pwd)/$LOG" "$LOG_DIR/zero_errors_latest.log"
echo $$> "$LOG_DIR/zero_errors.pid"

{
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] START toward zero"

  echo "=== hard overrides ==="
  "$PY" scripts/apply_hard_effect_overrides.py

  echo "=== repair_from_semantic ==="
  "$PY" scripts/repair_from_semantic.py

  echo "=== fix_fidelity_batch ==="
  "$PY" scripts/fix_fidelity_batch.py

  echo "=== track gaps ==="
  "$PY" scripts/track_effect_gaps.py

  # Multiple semantic LLM repair rounds (critical first, then all issues)
  for round in 1 2 3 4 5 6 7 8 9 10 11 12; do
    echo "=== semantic LLM fix round $round (critical) ==="
    "$PY" -u scripts/fix_semantic_batch.py --severity critical --limit 50 --checkpoint-every 5 --sleep 0.1 \
      || echo "[warn] critical round failed"
    echo "=== semantic LLM fix round $round (any) ==="
    "$PY" -u scripts/fix_semantic_batch.py --limit 50 --checkpoint-every 5 --sleep 0.1 \
      || echo "[warn] any round failed"
    "$PY" scripts/repair_from_semantic.py || true
    # Re-review only bases we likely touched: force re-review of current issues in chunks
    echo "=== re-review issue chunk ==="
    "$PY" -u scripts/review_effect_semantics.py --force --only-verdict issue --limit 80 --sleep 0.1 --progress-every 20 \
      || echo "[warn] rereview failed"
    "$PY" scripts/build_effect_problem_queue.py
    "$PY" scripts/track_effect_gaps.py
    "$PY" - <<'PY'
import json
from pathlib import Path
s=json.loads(Path('meta/effect_semantic_review.json').read_text())
q=json.loads(Path('meta/effect_problem_queue.json').read_text())
t=json.loads(Path('meta/effect_gap_tracker.json').read_text())
print('PROGRESS', {
  'semantic': s.get('totals'),
  'queue_open': (q.get('totals') or {}).get('open'),
  'gaps': t.get('totals'),
})
open_n=int((q.get('totals') or {}).get('open') or 0)
issue_n=int((s.get('totals') or {}).get('issue') or 0)
gap_n=int((t.get('totals') or {}).get('unique_gap_bases') or 0)
empty_n=int((t.get('totals') or {}).get('unique_empty_bases') or 0)
if open_n==0 and issue_n==0 and gap_n==0 and empty_n==0:
  print("ZERO_REACHED")
  raise SystemExit(42)
PY
    rc=$?
    if [ "$rc" -eq 42 ]; then
      echo "ZERO REACHED"
      break
    fi
  done

  echo "=== final audits ==="
  "$PY" scripts/audit_effect_fidelity.py --severity medium || true
  "$PY" scripts/audit_card_effects.py --base-only || true
  "$PY" scripts/build_effect_problem_queue.py
  "$PY" scripts/track_effect_gaps.py
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] DONE"
} 2>&1 | tee -a "$LOG"

echo "log=$LOG"
