#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PI_SSH="${GOHOME_PI_SSH:-gohome@192.168.1.12}"
PI_ROOT="${GOHOME_PI_ROOT:-/home/gohome/gohome/edge-agent}"

command -v rsync >/dev/null 2>&1 || {
  echo "rsync is required" >&2
  exit 1
}

rsync -az \
  --exclude '.venv/' \
  --exclude '.venv-pi/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude 'data/' \
  --exclude 'logs/' \
  --exclude 'backups/' \
  --exclude '*.log' \
  --exclude '*.bak*' \
  --exclude '.env' \
  --exclude '.env.local' \
  --exclude '.env.local.*' \
  --exclude 'tools/' \
  --exclude 'eval/' \
  --exclude 'scripts/audit-vision-dataset-readiness.py' \
  --exclude 'scripts/configure-demo-mode.sh' \
  --exclude 'scripts/emit-public-fall-validation.py' \
  --exclude 'scripts/eval*.py' \
  --exclude 'scripts/import-*.py' \
  --exclude 'scripts/init-vision-eval-data.py' \
  --exclude 'scripts/prepare-factory-network-test.sh' \
  --exclude 'scripts/prepare-vision-smoke-samples.py' \
  --exclude 'scripts/run-*-eval*.sh' \
  --include 'scripts/verify-vision-runtime.py' \
  --exclude 'scripts/verify-*.py' \
  "$AGENT_ROOT/" "$PI_SSH:$PI_ROOT/"

ssh "$PI_SSH" "cd '$PI_ROOT' && \
  sudo rm -rf backups && \
  rm -rf eval __pycache__ scripts/__pycache__ app/__pycache__ app/vision/__pycache__ && \
  rm -f app/apns_relay_service.py app/app_push_service.py app/edge_bootstrap_service.py \
    app/notifier.py app/pose_relay_agent.py app/public_pilot_service.py app/video_app.py \
    app/video_distribution_service.py app/video_profiles.py app/video_service.py && \
  find scripts -maxdepth 1 -type f \
    \( -name 'audit-vision-dataset-readiness.py' \
    -o -name 'configure-demo-mode.sh' \
    -o -name 'emit-public-fall-validation.py' \
    -o -name 'eval*.py' \
    -o -name 'import-*.py' \
    -o -name 'init-vision-eval-data.py' \
    -o -name 'prepare-factory-network-test.sh' \
    -o -name 'prepare-vision-smoke-samples.py' \
    -o -name 'run-*-eval*.sh' \) -delete && \
  find scripts -maxdepth 1 -type f -name 'verify-*.py' ! -name 'verify-vision-runtime.py' -delete && \
  find . -type f -name '*.pyc' -delete && \
  find . -maxdepth 2 -type f \( -name '*.log' -o -name '*.bak*' \) -delete"

ssh "$PI_SSH" "cd '$PI_ROOT' && .venv-pi/bin/python -m pip install --requirement requirements-security.txt"
ssh "$PI_SSH" "cd '$PI_ROOT' && .venv-pi/bin/python scripts/verify-vision-runtime.py --require-yolo --require-pose --require-hailo"
echo "deployed without replacing Pi runtime or device data: $PI_SSH:$PI_ROOT"
