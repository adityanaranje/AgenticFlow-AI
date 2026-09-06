#!/usr/bin/env bash
# ============================================================
# AgentFlow AI - run the FastAPI backend in development mode.
#
# Requires: backend dependencies installed (scripts/bootstrap.sh)
# and a backend/.env file (copy backend/.env.example).
# ============================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -x "$ROOT_DIR/.venv/bin/uvicorn" ]; then
  echo "Backend dependencies missing. Run scripts/bootstrap.sh first." >&2
  exit 1
fi

cd "$ROOT_DIR/backend"

exec "$ROOT_DIR/.venv/bin/uvicorn" \
  app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload
