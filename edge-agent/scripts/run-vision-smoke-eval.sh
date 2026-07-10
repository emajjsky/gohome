#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x ".venv-pi/bin/python" ]]; then
    PYTHON_BIN=".venv-pi/bin/python"
  elif [[ -x ".venv/bin/python" ]]; then
    PYTHON_BIN=".venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

"$PYTHON_BIN" scripts/init-vision-eval-data.py
"$PYTHON_BIN" scripts/prepare-vision-smoke-samples.py
"$PYTHON_BIN" scripts/verify-vision-pipeline.py

"$PYTHON_BIN" scripts/eval-person.py
"$PYTHON_BIN" scripts/eval-pose.py --pose-enabled
"$PYTHON_BIN" scripts/eval-fall.py
"$PYTHON_BIN" scripts/eval-fire.py --target visual
"$PYTHON_BIN" scripts/eval-fire.py --target event
