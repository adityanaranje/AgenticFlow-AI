#!/usr/bin/env bash
# ============================================================
# AgentFlow AI - run the background workers in development.
#
# Uploads land in `pending` and research runs in `queued` until a worker
# consumes the Redis queue, so the API server alone is not enough:
#
#   document-worker  -> parse + chunk + embed + upsert uploaded documents
#   research-worker  -> run the multi-step research pipeline
#
# Usage:  ./scripts/dev-workers.sh
# Stop:   Ctrl+C (both workers are shut down together)
#
# Requires: backend dependencies installed (scripts/bootstrap.sh) and a
# backend/.env with REDIS_URL pointing at a reachable Redis.
# On Windows use scripts/dev-workers.ps1 instead.
# ============================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT_DIR/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "Backend dependencies missing. Run scripts/bootstrap.sh first." >&2
  exit 1
fi

cd "$ROOT_DIR/backend"

pids=()
cleanup() {
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup INT TERM EXIT

echo "Starting document worker and research worker (Ctrl+C stops both)..."
"$PYTHON" -m app.workers.document_worker & pids+=("$!")
"$PYTHON" -m app.workers.research_worker & pids+=("$!")

wait
