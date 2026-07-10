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
  --exclude 'data/' \
  --exclude 'logs/' \
  --exclude '.env' \
  --exclude '.env.local' \
  --exclude '.env.local.*' \
  "$AGENT_ROOT/" "$PI_SSH:$PI_ROOT/"

ssh "$PI_SSH" "cd '$PI_ROOT' && .venv-pi/bin/python scripts/verify-vision-runtime.py --require-yolo --require-pose"
echo "deployed without replacing Pi runtime or device data: $PI_SSH:$PI_ROOT"
