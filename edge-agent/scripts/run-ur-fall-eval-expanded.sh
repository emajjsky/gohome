#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"
FALL_SEQUENCES="${GOHOME_UR_FALL_FALLS:-01 02 03 04 05 06 07 08}"
ADL_SEQUENCES="${GOHOME_UR_FALL_ADLS:-01 02 03 04 05 06 07 08 09 10}"

"$PYTHON_BIN" scripts/import-ur-fall-sample.py \
  --fall ${FALL_SEQUENCES} \
  --adl ${ADL_SEQUENCES} \
  --positive-per-fall "${GOHOME_UR_FALL_POSITIVE_PER_FALL:-4}" \
  --negative-per-fall "${GOHOME_UR_FALL_NEGATIVE_PER_FALL:-2}" \
  "$@"

"$PYTHON_BIN" scripts/eval-fall.py \
  --use-pose \
  --samples-dir data/eval/samples/fall/ur_fall \
  --manifest data/eval/samples/fall/ur_fall/manifest.jsonl \
  --detector-backend "${GOHOME_DETECTOR_BACKEND:-yolo}" \
  --yolo-model "${GOHOME_YOLO_MODEL:-yolo11n.pt}" \
  --yolo-confidence "${GOHOME_YOLO_CONFIDENCE:-0.20}" \
  --yolo-imgsz "${GOHOME_YOLO_IMGSZ:-640}"
