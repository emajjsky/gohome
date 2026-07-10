#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="${GOHOME_PI_VENV_DIR:-$AGENT_ROOT/.venv-pi}"
PYTHON_BOOTSTRAP="${PYTHON_BOOTSTRAP:-$(command -v python3)}"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "aarch64" ]]; then
  echo "this installer is only for Linux aarch64 Raspberry Pi devices" >&2
  exit 1
fi

if [[ -f "$VENV_DIR/pyvenv.cfg" ]] && grep -Eq '/opt/homebrew/|/Users/|\\Users\\' "$VENV_DIR/pyvenv.cfg"; then
  echo "foreign virtual environment detected: $VENV_DIR" >&2
  echo "move it aside before installing; do not copy a Mac .venv to the Pi" >&2
  exit 1
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON_BOOTSTRAP" -m venv "$VENV_DIR"
fi

cd "$AGENT_ROOT"
PIP_CONFIG_FILE=/dev/null "$VENV_DIR/bin/python" -m pip install \
  --index-url "$PIP_INDEX_URL" \
  --timeout 120 \
  --retries 5 \
  -r requirements-pose.txt

"$VENV_DIR/bin/python" scripts/verify-vision-runtime.py --require-yolo --require-pose --smoke
echo "Pi vision runtime is ready: $VENV_DIR"
