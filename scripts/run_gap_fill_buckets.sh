#!/usr/bin/env bash
# Durable gap-fill across remaining timing buckets, with per-batch checkpoints.
set -uo pipefail
cd "$(dirname "$0")/.."
PY="${PY:-.venv/bin/python}"
LOG_DIR=meta/logs
mkdir -p "$LOG_DIR"
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG="$LOG_DIR/gap_fill_${TS}.log"
ln -sfn "$(pwd)/$LOG" "$LOG_DIR/gap_fill_latest.log"
echo $$> "$LOG_DIR/gap_fill.pid"

write_ids() {
  local timing="$1"
  "$PY" - "$timing" <<'PY'
import json, re, sys
from pathlib import Path
timing = sys.argv[1]
t = json.loads(Path("meta/effect_gap_tracker.json").read_text(encoding="utf-8"))
bases, seen = [], set()
for g in t.get("top_gaps") or []:
    g_timing = str(g.get("timing") or "")
    reason = str(g.get("reason") or "")
    if g_timing != timing and timing not in reason:
        continue
    b = re.sub(r"-(?:P|R)\d+$", "", str(g.get("id") or ""))
    if not b or b in seen:
        continue
    seen.add(b)
    bases.append(b)
out = Path(f"meta/logs/{timing}_gap_ids.txt")
out.write_text("\n".join(bases) + ("\n" if bases else ""), encoding="utf-8")
print(len(bases), flush=True)
PY
}

run_bucket() {
  local timing="$1"
  local rounds="${2:-12}"
  local limit="${3:-25}"
  local round n
  for round in $(seq 1 "$rounds"); do
    n=$(write_ids "$timing" | tail -1)
    echo "=== ${timing} round ${round} remaining=${n} ===" | tee -a "$LOG"
    if [ "${n:-0}" -eq 0 ]; then
      break
    fi
    if ! "$PY" -u scripts/compile_gap_cards.py \
      --llm --force-llm \
      --timing "$timing" \
      --ids-file "meta/logs/${timing}_gap_ids.txt" \
      --limit "$limit" \
      --sleep 0.12 \
      --checkpoint-every 5 \
      >>"$LOG" 2>&1; then
      echo "[warn] ${timing} round ${round} failed rc=$? — continuing" | tee -a "$LOG"
    fi
  done
}

{
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] START remaining timing buckets"
  # Largest remaining first
  run_bucket when_attacking 8 25
  run_bucket opponent_turn 8 25
  run_bucket your_turn 6 25
  run_bucket end_of_your_turn 6 25
  run_bucket on_ko 4 25
  run_bucket counter_event 4 25
  run_bucket on_opponent_attack 3 25
  run_bucket on_block 2 25
  run_bucket trigger 2 25
  "$PY" scripts/track_effect_gaps.py
  "$PY" scripts/build_effect_problem_queue.py
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] DONE"
} 2>&1 | tee -a "$LOG"

echo "log=$LOG"
