# OPCG Next.js frontend

## Dev

Terminal 1 (API):

```bash
cd "/Users/jayden/Documents/OPCG_Project/Chinese HK"
# Prefer no --reload while playing: rooms are in-memory and a reload wipes them.
# (.venv / transformers file churn can also trigger endless reloads if you watch `.`)
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
```

If you need auto-reload for Python edits only:

```bash
.venv/bin/uvicorn app:app --reload --reload-dir battle --reload-dir . --reload-include 'app.py' --reload-include 'battle/**/*.py' --port 8000
```

Terminal 2 (web):

```bash
cd "/Users/jayden/Documents/OPCG_Project/Chinese HK/frontend"
export NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
npm run dev
```

Open http://localhost:3000

## Production build

```bash
cd frontend
NEXT_PUBLIC_API_BASE_URL=https://api.optcgassistant.com npm ci
NEXT_PUBLIC_API_BASE_URL=https://api.optcgassistant.com npm run build
# standalone needs static assets beside server.js
cp -R .next/static .next/standalone/.next/static
cp -R public .next/standalone/public
npm run start
# or: PORT=3000 node .next/standalone/server.js
```

## Cutover

1. Use Next.js as the only web frontend (`127.0.0.1:3000`) — see `deploy/optcgassistant/`.
2. Set `OPCG_CORS_ORIGINS` to the public site origin(s).
3. Keep API served by FastAPI (`127.0.0.1:8000`).
