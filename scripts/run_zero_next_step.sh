#!/usr/bin/env bash
# Next-step after full toward-zero pass: easy audit/fidelity fixes, then
# smarter semantic fix + re-review ONLY changed cards.
set -uo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-.venv/bin/python}"
LOG_DIR=meta/logs
mkdir -p "$LOG_DIR"
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG="$LOG_DIR/zero_next_${TS}.log"
ln -sfn "$(pwd)/$LOG" "$LOG_DIR/zero_next_latest.log"
echo $$> "$LOG_DIR/zero_next.pid"

{
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] START next-step zero push"

  echo "=== easy audit/fidelity ==="
  "$PY" scripts/fix_audit_fidelity_easy.py
  "$PY" scripts/fix_fidelity_batch.py || true
  "$PY" scripts/apply_hard_effect_overrides.py || true

  for round in 1 2 3 4 5 6; do
    echo "=== semantic fix round $round ==="
    "$PY" -u scripts/fix_semantic_batch.py --severity critical --limit 60 --checkpoint-every 5 --sleep 0.1 \
      || echo "[warn] critical fix failed"
    "$PY" -u scripts/fix_semantic_batch.py --limit 40 --checkpoint-every 5 --sleep 0.1 \
      || echo "[warn] any fix failed"
    "$PY" scripts/repair_from_semantic.py || true

    if [ -s meta/logs/semantic_fixed_ids.txt ]; then
      echo "=== re-review changed only ($(wc -l < meta/logs/semantic_fixed_ids.txt | tr -d ' ')) ==="
      "$PY" -u scripts/review_effect_semantics.py --force --ids-file meta/logs/semantic_fixed_ids.txt --sleep 0.1 --progress-every 10 \
        || echo "[warn] rereview changed failed"
    else
      echo "=== no changed ids; skip targeted rereview ==="
    fi

    "$PY" scripts/audit_effect_fidelity.py --severity medium || true
    "$PY" scripts/audit_card_effects.py --base-only || true
    "$PY" scripts/build_effect_problem_queue.py
    "$PY" scripts/track_effect_gaps.py
    "$PY" - <<'PY'
import json
from pathlib import Path
s=json.loads(Path('meta/effect_semantic_review.json').read_text())
q=json.loads(Path('meta/effect_problem_queue.json').read_text())
t=json.loads(Path('meta/effect_gap_tracker.json').read_text())
fid=json.loads(Path('meta/effect_fidelity_full_report.json').read_text()) if Path('meta/effect_fidelity_full_report.json').exists() else {}
aud=json.loads(Path('meta/effect_audit_report.json').read_text()) if Path('meta/effect_audit_report.json').exists() else {}
print('PROGRESS', {
  'semantic': s.get('totals'),
  'queue_open': (q.get('totals') or {}).get('open'),
  'gaps': t.get('totals'),
  'fidelity_findings': len(fid.get('findings') or []),
  'audit_findings': (aud.get('totals') or {}).get('findings'),
})
open_n=int((q.get('totals') or {}).get('open') or 0)
issue_n=int((s.get('totals') or {}).get('issue') or 0)
if open_n == 0 and issue_n == 0:
  print('ZERO_REACHED')
PY
    if grep -q ZERO_REACHED "$LOG"; then
      echo ZERO REACHED
      break
    fi
  done

  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] DONE next-step"
} 2>&1 | tee -a "$LOG"

echo "log=$LOG"
