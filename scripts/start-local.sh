#!/usr/bin/env bash
# Local dev: API on :8000, frontend on :3000 (runs from /tmp to avoid Documents I/O errors).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_SRC="$ROOT/frontend"
FRONTEND_RUN="/tmp/opcg-frontend-run"
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:${HOME}/.local/node/bin:${PATH:-}"
PY=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3

# Detach so the process survives when this script's shell/session exits
# (Cursor agent shells and some terminals otherwise kill the process group).
start_detached() {
  local cwd="$1"
  local log="$2"
  shift 2
  "$PY" - "$cwd" "$log" "$@" <<'PY'
import os, sys, subprocess
cwd, log_path, cmd = sys.argv[1], sys.argv[2], sys.argv[3:]
os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
log = open(log_path, "w")
subprocess.Popen(
    cmd,
    cwd=cwd,
    stdin=subprocess.DEVNULL,
    stdout=log,
    stderr=subprocess.STDOUT,
    start_new_session=True,
)
PY
}

echo "==> Stopping old dev servers..."
pkill -9 -f 'uvicorn app:app' 2>/dev/null || true
pkill -9 -f 'next dev' 2>/dev/null || true
pkill -9 -f 'next-server' 2>/dev/null || true
pkill -9 -f 'npm run dev' 2>/dev/null || true
for port in 3000 3001 8000; do
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | xargs kill -9 2>/dev/null || true
done
sleep 2

echo "==> Starting API on http://127.0.0.1:8000 ..."
if ! "$PY" -c "import websockets" 2>/dev/null; then
  echo "==> Installing websockets for local API ..."
  "$PY" -m pip install 'uvicorn[standard]' websockets
fi
# Bind 0.0.0.0 so both 127.0.0.1 and localhost (incl. IPv6→IPv4) can reach the API.
start_detached "$ROOT" /tmp/opcg-api-local.log \
  "$PY" -m uvicorn app:app --host 0.0.0.0 --port 8000

echo "==> Syncing frontend to $FRONTEND_RUN ..."
mkdir -p "$FRONTEND_RUN"
rsync -a --delete --exclude node_modules --exclude .next "$FRONTEND_SRC/" "$FRONTEND_RUN/"
if [[ ! -f "$FRONTEND_RUN/node_modules/next/package.json" ]]; then
  echo "==> npm ci (first run) ..."
  (cd "$FRONTEND_RUN" && npm ci)
fi
echo "NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000" > "$FRONTEND_RUN/.env.local"
SYNC_TS="$(date '+%Y-%m-%d %H:%M:%S')"
echo "NEXT_PUBLIC_DEV_SYNC_TS=$SYNC_TS" >> "$FRONTEND_RUN/.env.local"
echo "==> Frontend synced at $SYNC_TS"

PORT=3000
if lsof -tiTCP:3000 -sTCP:LISTEN >/dev/null 2>&1; then
  PORT=3001
  echo "==> Port 3000 busy, using 3001"
fi
echo "==> Starting frontend on http://localhost:$PORT ..."
# Prefer local next binary so we don't depend on npx in PATH inside the detached session.
if [[ -x "$FRONTEND_RUN/node_modules/.bin/next" ]]; then
  start_detached "$FRONTEND_RUN" /tmp/opcg-frontend-tmp.log \
    "$FRONTEND_RUN/node_modules/.bin/next" dev --port "$PORT"
else
  start_detached "$FRONTEND_RUN" /tmp/opcg-frontend-tmp.log \
    npx next dev --port "$PORT"
fi

echo "==> Waiting for services (API may take ~30s on first boot) ..."
for _ in $(seq 1 36); do
  fe=$(curl -sS -m 2 -o /dev/null -w "%{http_code}" "http://127.0.0.1:${PORT}/" 2>/dev/null || echo 000)
  api=$(curl -sS -m 2 -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/ 2>/dev/null || echo 000)
  if [[ "$fe" == "200" && "$api" == "200" ]]; then
    echo ""
    echo "Ready:"
    echo "  Frontend  http://localhost:${PORT}"
    echo "  API       http://127.0.0.1:8000"
    echo "  Synced    $SYNC_TS"
    echo ""
    echo "本地预览请用 localhost — 线上 optcgassistant.com 需单独部署。"
    echo "改代码后重新运行:  cd ~/Documents/OPCG_Project && ./start-local.sh"
    echo "Logs: /tmp/opcg-frontend-tmp.log  /tmp/opcg-api-local.log"
    exit 0
  fi
  sleep 5
done

echo "Timed out. Check logs:"
tail -20 /tmp/opcg-frontend-tmp.log 2>/dev/null || true
tail -20 /tmp/opcg-api-local.log 2>/dev/null || true
exit 1
