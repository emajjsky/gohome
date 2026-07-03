#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$AGENT_ROOT/.env"

set_env() {
  local key="$1"
  local value="$2"
  touch "$ENV_FILE"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

set_env GOHOME_AGENT_HOST 0.0.0.0
set_env GOHOME_AGENT_PORT 8711
set_env GOHOME_AGENT_DISABLE_WORKER 0
set_env GOHOME_DETECTOR_BACKEND yolo
set_env GOHOME_CAPTURE_INTERVAL_SECONDS 5
set_env GOHOME_NO_MOTION_SECONDS 300
set_env GOHOME_HOTSPOT_PREFIX GoHome
set_env GOHOME_HOTSPOT_PASSWORD gohome2026

echo "Demo mode configured in $ENV_FILE"
echo "Detector backend is set to yolo. If ultralytics is not installed, the app uses visual demo fallback."
