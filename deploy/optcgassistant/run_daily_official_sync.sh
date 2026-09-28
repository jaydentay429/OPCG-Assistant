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

read_env_value() {
  local key="$1"
  local file="$APP_ROOT/.env"
  if [[ ! -f "$file" ]]; then
    return 0
  fi
  grep -E "^${key}=" "$file" | tail -n 1 | cut -d= -f2- | tr -d '"' | tr -d "'"
}

{
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ======== DAILY OFFICIAL SYNC START ========"
  "$PY" -u sync_official_cards.py --with-images
  rc=$?
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ======== DAILY OFFICIAL SYNC END rc=$rc ========"

  # Full rebuild of the card-image manifest from R2 object bytes (not etags).
  # The file is picked up by the next GitHub Actions build; this job does not deploy.
  remote="$(read_env_value OPCG_R2_RCLONE_REMOTE)"
  if [[ -n "$remote" ]] && command -v rclone >/dev/null 2>&1; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] card image manifest from $remote"
    if ! "$PY" -u scripts/build_card_image_manifest.py --rclone-remote "$remote"; then
      echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] card image manifest FAILED (previous file kept if the count guard tripped)"
      if [[ "$rc" -eq 0 ]]; then
        rc=1
      fi
    fi
  else
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] skip card image manifest: rclone or OPCG_R2_RCLONE_REMOTE is not set"
  fi
  exit $rc
} >>"$LOG" 2>&1
