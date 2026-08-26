#!/usr/bin/env bash
# Run Next.js from /tmp (Documents folder has errno -11 read/write issues).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_SRC="$ROOT/frontend"
FRONTEND_RUN="/tmp/opcg-frontend-run"
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:${HOME}/.local/node/bin:${PATH:-}"

# Stop broken instances in project folder only
pkill -9 -f "$FRONTEND_SRC/node_modules/.bin/next" 2>/dev/null || true
lsof -ti :3000 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 1

mkdir -p "$FRONTEND_RUN"
rsync -a --exclude node_modules --exclude .next "$FRONTEND_SRC/" "$FRONTEND_RUN/"
if [[ ! -f "$FRONTEND_RUN/node_modules/next/package.json" ]]; then
  echo "==> npm ci in $FRONTEND_RUN ..."
  (cd "$FRONTEND_RUN" && npm ci)
fi

if [[ ! -f "$FRONTEND_SRC/.env.local" ]]; then
  echo "NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000" > "$FRONTEND_RUN/.env.local"
else
  cp "$FRONTEND_SRC/.env.local" "$FRONTEND_RUN/.env.local"
fi

echo "Frontend dev server: http://localhost:3000  (running from $FRONTEND_RUN)"
cd "$FRONTEND_RUN"
exec npx next dev --port 3000
