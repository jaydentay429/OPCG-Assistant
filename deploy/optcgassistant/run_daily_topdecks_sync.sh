#!/usr/bin/env bash
# Daily VPS job (14:00 HKT): check onepiecetopdecks.com for meta updates;
# re-fetch only changed pages and rewrite meta/topdecks_decks.json when needed.
# API reloads via ensure_topdecks_data_fresh() — no service restart.
set -uo pipefail

APP_ROOT=/opt/opcg/app
LOG_DIR=/opt/opcg/logs
LOCK=/opt/opcg/logs/daily_topdecks_sync.lock
PY="$APP_ROOT/.venv/bin/python"
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG="$LOG_DIR/daily_topdecks_${TS}.log"

mkdir -p "$LOG_DIR"
ln -sfn "$LOG" "$LOG_DIR/daily_topdecks_latest.log"

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] skip: another topdecks sync is running" | tee -a "$LOG_DIR/daily_topdecks_skip.log"
  exit 0
fi

cd "$APP_ROOT"
export PYTHONUNBUFFERED=1

{
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ======== DAILY TOPDECKS SYNC START ========"
  # Always re-check the newest metas; TablePress rows often change without page.modified.
  "$PY" -u sync_topdecks.py --sleep 0.35 --always-refetch-newest 8
  rc=$?
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ======== DAILY TOPDECKS SYNC END rc=$rc ========"
  exit $rc
} >>"$LOG" 2>&1
