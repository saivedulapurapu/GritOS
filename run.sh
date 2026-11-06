#!/usr/bin/env bash
# Start GritOS from a fresh clone (macOS / Linux / Git Bash). Usage: ./run.sh [--load-data]
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d backend/.venv ]; then python3 -m venv backend/.venv || python -m venv backend/.venv; fi
if [ -x backend/.venv/bin/python ]; then PY=backend/.venv/bin/python; else PY=backend/.venv/Scripts/python; fi
"$PY" -m pip install -q -r backend/requirements.txt

if [ "${1:-}" = "--load-data" ]; then
  (cd backend && "../$PY" -m etl.edgar_ingest --fetch --load)   # needs SEC_USER_AGENT (env or .env)
fi

[ -d frontend/node_modules ] || npm ci --prefix frontend

(cd backend && "../$PY" -m uvicorn main:app --port 8000) &
BACKEND_PID=$!
trap 'kill $BACKEND_PID 2>/dev/null' EXIT
echo "Backend  http://localhost:8000  (API docs: /docs)"
echo "Frontend http://localhost:3000"
npm run dev --prefix frontend
