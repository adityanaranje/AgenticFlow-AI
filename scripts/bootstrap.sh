#!/usr/bin/env bash
# ============================================================
# AgentFlow AI - bootstrap the backend Python environment.
# Creates `.venv` at the repository root and installs the
# dependencies declared in requirements.txt.
# ============================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -d ".venv" ]; then
  echo "Creating .venv ..."
  python3 -m venv .venv
fi

echo "Installing backend dependencies ..."
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo ""
echo "Bootstrap complete. Activate with:"
echo "  source .venv/bin/activate"
