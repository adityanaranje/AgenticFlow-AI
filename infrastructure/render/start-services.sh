#!/bin/bash
# ============================================================
# AgentFlow AI - combined API + workers start script
#
# Runs all three Python processes in ONE container:
#   1. app.workers.document_worker   (ingestion queue consumer)
#   2. app.workers.research_worker   (research queue consumer)
#   3. uvicorn app.main:app          (FastAPI HTTP API)
#
# Why one container: Render's free tier has no background-worker
# service type (only web services), so the queue consumers ride
# along with the API in a single free web service. The compose
# topology (separate containers) stays the right model anywhere
# with a paid/free worker type; see infrastructure/render/README.md.
#
# This script runs inside the backend image (WORKDIR=/app,
# PYTHONPATH=/app/backend), where it is installed at
# /app/infrastructure/render/start-services.sh by backend/Dockerfile.
#
#   PORT: Render injects this (default 10000) and routes public
#         traffic to it; fall back to 8000 for bare-metal runs.
# ============================================================

set -u

PORT="${PORT:-8000}"
API_LOG_LEVEL="${API_LOG_LEVEL:-info}"

log() { echo "[start-services] $*"; }

# --- graceful shutdown -----------------------------------------------------
# Render sends SIGTERM on every deploy/restart/spin-down. Stop the API and
# both workers together so a deploy never leaves an orphaned consumer
# holding Redis jobs it will never finish.
shutdown() {
    local exit_code="${1:-0}"
    log "Stopping API and workers (exit ${exit_code})..."
    kill "${API_PID:-}" "${DOC_PID:-}" "${RES_PID:-}" 2>/dev/null || true
    # Give them a few seconds to finish in-flight work, then force it.
    local i
    for i in 1 2 3 4 5; do
        if ! kill -0 "${API_PID:-0}" 2>/dev/null \
            && ! kill -0 "${DOC_PID:-0}" 2>/dev/null \
            && ! kill -0 "${RES_PID:-0}" 2>/dev/null; then
            break
        fi
        sleep 1
    done
    kill -9 "${API_PID:-}" "${DOC_PID:-}" "${RES_PID:-}" 2>/dev/null || true
    wait 2>/dev/null || true
    log "All processes stopped."
    exit "${exit_code}"
}

trap 'shutdown 0' TERM INT

# --- start the queue consumers ---------------------------------------------
# Without a document consumer, uploads stay "pending" forever; without a
# research consumer, research runs never leave the queue.
log "Starting document worker..."
python -m app.workers.document_worker &
DOC_PID=$!

log "Starting research worker..."
python -m app.workers.research_worker &
RES_PID=$!

# --- start the HTTP API ----------------------------------------------------
log "Starting FastAPI on 0.0.0.0:${PORT}..."
uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" --log-level "${API_LOG_LEVEL}" &
API_PID=$!

log "Processes up: api=${API_PID} document_worker=${DOC_PID} research_worker=${RES_PID}"

# --- supervise ---------------------------------------------------------------
# `wait -n` returns as soon as ANY child exits, or immediately when a
# trapped signal fires (the trap then runs shutdown). If a worker or the
# API dies, the container is incomplete: tear it down and exit non-zero
# so Render's restart policy replaces the instance.
wait -n
log "A background process exited unexpectedly; stopping the container."
shutdown 1
