#!/usr/bin/env bash
# Daily VPS job: email yesterday's (Asia/Hong_Kong) site traffic digest.
set -uo pipefail

APP_ROOT=/opt/opcg/app
LOG_DIR=/opt/opcg/logs
LOCK=/opt/opcg/logs/daily_analytics.lock
PY="$APP_ROOT/.venv/bin/python"
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG="$LOG_DIR/daily_analytics_${TS}.log"

mkdir -p "$LOG_DIR"
ln -sfn "$LOG" "$LOG_DIR/daily_analytics_latest.log"

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] skip: analytics email already running" | tee -a "$LOG_DIR/daily_analytics_skip.log"
  exit 0
fi

cd "$APP_ROOT"
export PYTHONUNBUFFERED=1

{
  rc=1
  for attempt in 1 2 3; do
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ======== DAILY ANALYTICS EMAIL START (try $attempt/3) ========"
    if "$PY" -u scripts/send_daily_analytics_report.py; then
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
