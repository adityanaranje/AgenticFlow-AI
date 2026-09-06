#!/usr/bin/env bash
# ============================================================
# AgentFlow AI - poll backend/frontend health endpoints.
#   ./scripts/check-health.sh [backend_url] [frontend_url]
# Defaults: http://localhost:8000 http://localhost:3000
# Exits non-zero if the backend reports anything but HTTP 200.
# ============================================================
set -uo pipefail

BACKEND_URL="${1:-http://localhost:8000}"
FRONTEND_URL="${2:-http://localhost:3000}"

echo "== Backend health: $BACKEND_URL/health"
BACKEND_STATUS=$(curl -s -o /tmp/agentflow-health.json -w "%{http_code}" "$BACKEND_URL/health" || true)

if [ "$BACKEND_STATUS" = "200" ]; then
  echo "   HTTP 200"
  python3 -m json.tool /tmp/agentflow-health.json 2>/dev/null || cat /tmp/agentflow-health.json
else
  echo "   HTTP $BACKEND_STATUS (degraded or unreachable)" >&2
  exit 1
fi

echo ""
echo "== Frontend: $FRONTEND_URL"
FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$FRONTEND_URL" || true)
echo "   HTTP $FRONTEND_STATUS"
