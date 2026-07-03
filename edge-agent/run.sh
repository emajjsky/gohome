#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

load_env_file() {
  local file_path="$1"
  if [ ! -f "$file_path" ]; then
    return 0
  fi
  while IFS= read -r assignment; do
    if [ -n "$assignment" ]; then
      eval "export $assignment"
    fi
  done < <(python3 - "$file_path" <<'PY'
from pathlib import Path
import os
import shlex
import sys

from app.env_loader import load_env_file

for key, value in load_env_file(Path(sys.argv[1])).items():
    if key not in os.environ:
        print(f"{key}={shlex.quote(value)}")
PY
)
}

load_env_file ".env"
load_env_file ".env.local"

require_file() {
  local file_path="$1"
  if [ ! -s "$file_path" ]; then
    echo "required file missing or empty: $file_path" >&2
    exit 1
  fi
}

for demo_asset in quality person stillness fall meal night fire camera; do
  require_file "admin/assets/algorithm-demos/${demo_asset}.webm"
done

PYTHON_BIN="${PYTHON_BIN:-./.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

exec "$PYTHON_BIN" -m uvicorn app.main:app \
  --host "${GOHOME_AGENT_HOST:-0.0.0.0}" \
  --port "${GOHOME_AGENT_PORT:-8711}"
