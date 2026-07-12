#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [[ -x ".venv-pi/bin/python" ]]; then
  PYTHON_BIN=".venv-pi/bin/python"
elif [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
fi

EVAL_ONLY=0
IMPORT_ARGS=()
for arg in "$@"; do
  if [[ "$arg" == "--eval-only" ]]; then
    EVAL_ONLY=1
  else
    IMPORT_ARGS+=("$arg")
  fi
done

if [[ "$EVAL_ONLY" -eq 0 ]]; then
  "$PYTHON_BIN" scripts/import-ur-fall-sample.py ${IMPORT_ARGS[@]+"${IMPORT_ARGS[@]}"}
fi

if [[ ! -f data/eval/samples/fall/ur_fall/manifest.jsonl ]]; then
  echo "UR Fall manifest not found; run without --eval-only first." >&2
  exit 1
fi

"$PYTHON_BIN" scripts/eval-fall.py \
  --use-pose \
  --samples-dir data/eval/samples/fall/ur_fall \
  --manifest data/eval/samples/fall/ur_fall/manifest.jsonl \
  --detector-backend "${GOHOME_DETECTOR_BACKEND:-yolo}" \
  --yolo-model "${GOHOME_YOLO_MODEL:-yolo11n.pt}" \
  --yolo-confidence "${GOHOME_YOLO_CONFIDENCE:-0.20}" \
  --yolo-imgsz "${GOHOME_YOLO_IMGSZ:-416}" \
  --pose-fall-threshold "${GOHOME_POSE_FALL_THRESHOLD:-0.78}" \
  --pose-fall-min-confidence "${GOHOME_POSE_FALL_MIN_CONFIDENCE:-0.36}" \
  --pose-fall-min-visible-keypoints "${GOHOME_POSE_FALL_MIN_VISIBLE_KEYPOINTS:-8}" \
  --pose-fall-min-core-keypoints "${GOHOME_POSE_FALL_MIN_CORE_KEYPOINTS:-2}"
