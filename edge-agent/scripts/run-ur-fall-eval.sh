#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON:-python}"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi

"$PYTHON_BIN" scripts/import-ur-fall-sample.py "$@"
"$PYTHON_BIN" scripts/eval-fall.py \
  --use-pose \
  --samples-dir data/eval/samples/fall/ur_fall \
  --manifest data/eval/samples/fall/ur_fall/manifest.jsonl \
  --detector-backend yolo \
  --yolo-model yolo11n.pt \
  --yolo-confidence 0.20 \
  --yolo-imgsz 960
