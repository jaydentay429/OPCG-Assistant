#!/usr/bin/env bash
# Daily VPS job: official cardlist + limited variants + pack images.
# Split from price sync so a yuyu 429 cannot kill image ingest, and vice versa.
set -uo pipefail

APP_ROOT=/opt/opcg/app
LOG_DIR=/opt/opcg/logs
LOCK=/opt/opcg/logs/daily_official_sync.lock
PY="$APP_ROOT/.venv/bin/python"
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG="$LOG_DIR/daily_official_${TS}.log"

mkdir -p "$LOG_DIR"
ln -sfn "$LOG" "$LOG_DIR/daily_official_latest.log"

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] skip: another official sync is running" | tee -a "$LOG_DIR/daily_official_skip.log"
  exit 0
fi

cd "$APP_ROOT"
export PYTHONUNBUFFERED=1

{
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ======== DAILY OFFICIAL SYNC START ========"
  "$PY" -u sync_official_cards.py --with-images
  rc=$?
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ======== DAILY OFFICIAL SYNC END rc=$rc ========"
  exit $rc
} >>"$LOG" 2>&1
