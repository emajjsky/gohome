#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-./.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

exec "$PYTHON_BIN" -m uvicorn app.main:app \
  --host "${GOHOME_AGENT_HOST:-0.0.0.0}" \
  --port "${GOHOME_AGENT_PORT:-8711}"
