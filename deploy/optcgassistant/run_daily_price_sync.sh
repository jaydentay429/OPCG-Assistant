#!/usr/bin/env bash
# Daily VPS job: refresh prices for cards that already have a price,
# plus fetch newly added cards. Skip known no-price / miss cards.
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
  echo "Daily: refresh all priced cards + new cards; skip known no-price."

  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] STEP1: official cards + limited variants + images"
  "$PY" -u sync_official_cards.py --with-images
  rc1=$?
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] STEP1 rc=$rc1"

  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] STEP2: yuyutei priced-or-new two-pass"
  "$PY" -u sync_yuyutei_prices.py \
    --strict-variant \
    --two-pass \
    --by-family \
    --priced-or-new \
    --batch-size 80 \
    --batch-sleep 8 \
    --request-sleep 0.4 \
    --cooldown-on-429 120 \
    --retry-sleep-on-429 60 \
    --progress-every 50
  rc2=$?
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] STEP2 rc=$rc2"

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
PY

  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ======== DAILY PRICE SYNC END rc_official=$rc1 rc_prices=$rc2 ========"
  exit $rc2
} >>"$LOG" 2>&1
