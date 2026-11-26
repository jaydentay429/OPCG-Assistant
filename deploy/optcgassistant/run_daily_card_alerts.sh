#!/usr/bin/env bash
# Daily VPS job: opt-in card alert emails (new cards, watched prices). No-op unless CARD_ALERTS_ENABLED=1.
set -uo pipefail

APP_ROOT=/opt/opcg/app
LOG_DIR=/opt/opcg/logs
LOCK=/opt/opcg/logs/daily_card_alerts.lock
PY="$APP_ROOT/.venv/bin/python"
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG="$LOG_DIR/daily_card_alerts_${TS}.log"

mkdir -p "$LOG_DIR"
ln -sfn "$LOG" "$LOG_DIR/daily_card_alerts_latest.log"

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] skip: card alerts already running" | tee -a "$LOG_DIR/daily_card_alerts_skip.log"
  exit 0
fi

cd "$APP_ROOT"
export PYTHONUNBUFFERED=1

{
  rc=1
  for attempt in 1; do  # one try: a retry could repeat emails already sent
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ======== DAILY CARD ALERTS START (single try) ========"
    if "$PY" -u scripts/send_card_alerts.py; then
      rc=0
      break
    fi
    rc=$?
    if [ "$attempt" -lt 3 ]; then
      wait=$((attempt * 30))
      echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] attempt $attempt failed rc=$rc; sleep ${wait}s"
      sleep "$wait"
    fi
  done
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] done rc=$rc"
  exit "$rc"
} 2>&1 | tee -a "$LOG"
