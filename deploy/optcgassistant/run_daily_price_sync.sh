#!/usr/bin/env bash
# Daily VPS job: sweep every yuyu family (miss/ghost first), checkpoint on 429.
# Official cardlist + images are a separate cron (run_daily_official_sync.sh).
set -uo pipefail

APP_ROOT=/opt/opcg/app
LOG_DIR=/opt/opcg/logs
LOCK=/opt/opcg/logs/daily_price_sync.lock
PY="$APP_ROOT/.venv/bin/python"
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG="$LOG_DIR/daily_price_${TS}.log"

mkdir -p "$LOG_DIR"
ln -sfn "$LOG" "$LOG_DIR/daily_price_latest.log"

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] skip: another daily price sync is running" | tee -a "$LOG_DIR/daily_price_skip.log"
  exit 0
fi

cd "$APP_ROOT"
export PYTHONUNBUFFERED=1

{
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ======== DAILY PRICE SYNC START ========"
  echo "Daily: rotate all families, expand members, stop+checkpoint on 429 (no two-pass)."

  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] STEP1: yuyutei rotate-families"
  "$PY" -u sync_yuyutei_prices.py \
    --rotate-families \
    --strict-variant \
    --by-family \
    --expand-family \
    --stop-on-429 \
    --batch-size 40 \
    --batch-sleep 2 \
    --request-sleep 0.9 \
    --cooldown-on-429 120 \
    --retry-sleep-on-429 60 \
    --progress-every 25
  rc=$?
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] STEP1 rc=$rc"

  "$PY" - <<'PY'
import json
from pathlib import Path
from collections import Counter
obj = json.loads(Path("meta/market_prices.json").read_text(encoding="utf-8"))
cards = obj.get("cards") or {}
priced = sum(1 for v in cards.values() if isinstance(v, dict) and int(v.get("current_price") or 0) > 0)
st = Counter(str((v or {}).get("status") or "none") for v in cards.values() if isinstance(v, dict))
print(f"price_updated_at={obj.get('updated_at')}")
print(f"price_entries={len(cards)} priced={priced}")
print("status=" + json.dumps(dict(st.most_common()), ensure_ascii=False))
cur_path = Path("meta/yuyu_sync_cursor.json")
if cur_path.exists():
    cur = json.loads(cur_path.read_text(encoding="utf-8"))
    print(
        "cursor date={date} done={done} stopped_on_429={stopped}".format(
            date=cur.get("date"),
            done=len(cur.get("done") or []),
            stopped=cur.get("stopped_on_429"),
        )
    )
PY

  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ======== DAILY PRICE SYNC END rc=$rc ========"
  exit $rc
} >>"$LOG" 2>&1
