#!/usr/bin/env bash
# Daily VPS job: official cardlist + limited variants + pack images.
# Split from price sync so a yuyu 429 cannot kill image ingest, and vice versa.
# After packs/ is updated, copy <ID>.png keys that R2 does not already have
# (rclone copy --ignore-existing; never sync, never delete), then rebuild the
# card-image manifest. A copy failure is logged and does not skip the rebuild.
set -uo pipefail

APP_ROOT="${OPCG_APP_ROOT:-/opt/opcg/app}"
LOG_DIR="${OPCG_LOG_DIR:-/opt/opcg/logs}"
LOCK="${OPCG_OFFICIAL_SYNC_LOCK:-$LOG_DIR/daily_official_sync.lock}"
PY="${OPCG_SYNC_PYTHON:-$APP_ROOT/.venv/bin/python}"
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

  # Upload <ID>.png keys that are missing on R2, then rebuild the manifest
  # from object bytes (not etags). copy --ignore-existing does not overwrite
  # or delete. The manifest is picked up by the next GitHub Actions build;
  # this job does not deploy. Copy failures are logged and do not skip the rebuild.
  remote="$(read_env_value OPCG_R2_RCLONE_REMOTE)"
  if [[ -n "$remote" ]]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] copy new pack images to $remote"
    copy_rc=0
    "$PY" -u scripts/copy_new_pack_images_to_r2.py \
      --packs "$APP_ROOT/packs" \
      --rclone-remote "$remote" || copy_rc=$?
    if [[ "$copy_rc" -ne 0 ]]; then
      echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] copy new pack images FAILED rc=$copy_rc; continuing to card image manifest"
    fi
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] card image manifest from $remote"
    if ! "$PY" -u scripts/build_card_image_manifest.py --rclone-remote "$remote"; then
      echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] card image manifest FAILED (previous file kept if the count guard tripped)"
      if [[ "$rc" -eq 0 ]]; then
        rc=1
      fi
    fi
  else
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] skip card image manifest: OPCG_R2_RCLONE_REMOTE is not set"
  fi
  exit $rc
} >>"$LOG" 2>&1
