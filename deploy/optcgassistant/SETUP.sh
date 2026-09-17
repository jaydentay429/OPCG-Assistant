#!/usr/bin/env bash
# Run on the VPS once as root or ubuntu (after DNS A records for @, www, api point here).
set -euo pipefail

APP_ROOT=/opt/opcg/app

echo "Expects full app tree at $APP_ROOT (app.py, frontend/, deploy/, …)."
echo ""
if [[ ! -f "$APP_ROOT/app.py" ]]; then
  echo "Missing $APP_ROOT/app.py — copy your project first."
  exit 1
fi

sudo apt-get update
# libgl1 is a fallback if someone installs non-headless opencv-python;
# prefer opencv-python-headless via requirements.txt (no GUI libs needed).
sudo apt-get install -y python3-venv python3-pip caddy fonts-noto-cjk fonts-noto-cjk-extra \
  libgl1 libglib2.0-0

cd "$APP_ROOT"
python3 -m venv .venv
if [[ -f "$APP_ROOT/requirements.txt" ]]; then
  .venv/bin/pip install --upgrade pip
  # Avoid both opencv packages coexisting (cv2 import picks GUI build + libGL).
  .venv/bin/pip uninstall -y opencv-python 2>/dev/null || true
  .venv/bin/pip install -r "$APP_ROOT/requirements.txt"
else
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install fastapi "uvicorn[standard]" python-dotenv requests pydantic openai pillow
  echo "Note: No requirements.txt — installed a minimal set. Add full deps if imports fail."
fi

if [[ ! -f "$APP_ROOT/.env" ]]; then
  cp "$APP_ROOT/deploy/optcgassistant/env.production.example" "$APP_ROOT/.env"
  chmod 600 "$APP_ROOT/.env"
  echo "Created $APP_ROOT/.env — review before production."
fi

sudo cp "$APP_ROOT/deploy/optcgassistant/Caddyfile" /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl enable --now caddy

sudo cp "$APP_ROOT/deploy/optcgassistant/opcg-api.service" /etc/systemd/system/
sudo cp "$APP_ROOT/deploy/optcgassistant/opcg-web.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now opcg-api

echo "API enabled. Build frontend then: sudo systemctl enable --now opcg-web"
echo "  cd $APP_ROOT/frontend && NEXT_PUBLIC_API_BASE_URL=https://api.optcgassistant.com npm ci && npm run build"
echo "Done. Check: https://api.optcgassistant.com/docs and https://optcgassistant.com"
