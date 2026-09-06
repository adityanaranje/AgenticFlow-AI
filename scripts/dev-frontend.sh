#!/usr/bin/env bash
# ============================================================
# AgentFlow AI - run the Next.js frontend in development mode.
#
# Requires: frontend/.env.local with NEXT_PUBLIC_* variables
# (copy frontend/.env.example) and Node.js 20+.
# ============================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/frontend"

if [ ! -d "node_modules" ]; then
  echo "Installing frontend dependencies ..."
  npm install
fi

exec npm run dev
