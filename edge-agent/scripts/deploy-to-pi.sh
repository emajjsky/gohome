#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$AGENT_ROOT/.." && pwd)"
PI_SSH="${GOHOME_PI_SSH:-gohome@192.168.1.12}"
PI_ROOT="${GOHOME_PI_ROOT:-/home/gohome/gohome/edge-agent}"
PI_SERVICE="${GOHOME_PI_SERVICE:-gohome-edge-agent.service}"

command -v rsync >/dev/null 2>&1 || {
  echo "rsync is required" >&2
  exit 1
}

cd "$REPO_ROOT"
staging_root="$(mktemp -d "${TMPDIR:-/tmp}/gohome-edge-release.XXXXXX")"
cleanup() {
  rm -rf -- "$staging_root"
}
trap cleanup EXIT HUP INT TERM

PAYLOAD_BUILDER="$REPO_ROOT/deploy/edge-agent/build-production-payload.sh"
staged_agent="$staging_root/edge-agent"
"$PAYLOAD_BUILDER" "$staging_root" >/dev/null

rsync -az \
  --delete \
  --delete-delay \
  --exclude '/.venv/' \
  --exclude '/.venv-pi/' \
  --exclude '/__pycache__/' \
  --exclude '/data/' \
  --exclude '/logs/' \
  --exclude '/backups/' \
  --exclude '*.log' \
  --exclude '*.bak*' \
  --exclude '/.env' \
  --exclude '/.env.local' \
  --exclude '/.env.local.*' \
  --exclude '/tools/' \
  --exclude '/eval/' \
  --exclude '/scripts/audit-vision-dataset-readiness.py' \
  --exclude '/scripts/configure-demo-mode.sh' \
  --exclude '/scripts/eval*.py' \
  --exclude '/scripts/import-*.py' \
  --exclude '/scripts/init-vision-eval-data.py' \
  --exclude '/scripts/prepare-factory-network-test.sh' \
  --exclude '/scripts/prepare-vision-smoke-samples.py' \
  --exclude '/scripts/run-*-eval*.sh' \
  --include '/scripts/verify-vision-runtime.py' \
  --exclude '/scripts/verify-*.py' \
  "$staged_agent/" "$PI_SSH:$PI_ROOT/"

ssh "$PI_SSH" "cd '$PI_ROOT' && sudo rm -rf backups"

ssh "$PI_SSH" "cd '$PI_ROOT' && PYTHONDONTWRITEBYTECODE=1 .venv-pi/bin/python -m pip install --requirement requirements-security.txt"
ssh "$PI_SSH" "cd '$PI_ROOT' && PYTHONDONTWRITEBYTECODE=1 .venv-pi/bin/python scripts/verify-vision-runtime.py --require-yolo --require-pose --require-hailo"
ssh "$PI_SSH" "sudo systemctl restart '$PI_SERVICE'"

healthy=false
attempt=0
while [[ "$attempt" -lt 30 ]]; do
  if ssh "$PI_SSH" "curl -fsS --max-time 2 http://127.0.0.1:8711/health >/dev/null"; then
    healthy=true
    break
  fi
  attempt=$((attempt + 1))
  sleep 1
done

if [[ "$healthy" != true ]]; then
  echo "Pi health check failed after restarting $PI_SERVICE" >&2
  exit 1
fi

echo "deployed without replacing Pi runtime or device data: $PI_SSH:$PI_ROOT"
