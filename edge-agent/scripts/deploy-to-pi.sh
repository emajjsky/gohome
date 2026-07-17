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
  --exclude 'scripts/send-test-notification.sh' \
  --exclude 'scripts/verify-adaptive-analysis-persistence.py' \
  --exclude 'scripts/verify-adaptive-edge-worker.py' \
  --exclude 'scripts/verify-adaptive-inference-scheduler.py' \
  --exclude 'scripts/verify-alert-dedupe.py' \
  --exclude 'scripts/verify-camera-stream-resilience.py' \
  --exclude 'scripts/verify-config-sync-agent.py' \
  --exclude 'scripts/verify-dataset-readiness-audit.py' \
  --exclude 'scripts/verify-fall-rule-engine.py' \
  --exclude 'scripts/verify-observation-logs.py' \
  --exclude 'scripts/verify-pose-factor-graph.py' \
  --exclude 'scripts/verify-posture-classifier.py' \
  --exclude 'scripts/verify-posture-episodes.py' \
  --exclude 'scripts/verify-presence-sessions.py' \
  --exclude 'scripts/verify-prolonged-floor-rule.py' \
  --exclude 'scripts/verify-runtime-retention.py' \
  --exclude 'scripts/verify-temporal-observation-engine.py' \
  --exclude 'scripts/verify-upload-agent.py' \
  --exclude 'scripts/verify-upload-queue.py' \
  --exclude 'scripts/verify-vision-pipeline.py' \
  "$AGENT_ROOT/" "$PI_SSH:$PI_ROOT/"

ssh "$PI_SSH" "cd '$PI_ROOT' && rm -rf eval && find scripts -maxdepth 1 -type f \\
  \\( -name 'audit-vision-dataset-readiness.py' \\
  -o -name 'configure-demo-mode.sh' \\
  -o -name 'emit-public-fall-validation.py' \\
  -o -name 'eval*.py' \\
  -o -name 'import-*.py' \\
  -o -name 'init-vision-eval-data.py' \\
  -o -name 'prepare-factory-network-test.sh' \\
  -o -name 'prepare-vision-smoke-samples.py' \\
  -o -name 'run-*-eval*.sh' \\
  -o -name 'send-test-notification.sh' \\
  -o -name 'verify-adaptive-analysis-persistence.py' \\
  -o -name 'verify-adaptive-edge-worker.py' \\
  -o -name 'verify-adaptive-inference-scheduler.py' \\
  -o -name 'verify-alert-dedupe.py' \\
  -o -name 'verify-camera-stream-resilience.py' \\
  -o -name 'verify-config-sync-agent.py' \\
  -o -name 'verify-dataset-readiness-audit.py' \\
  -o -name 'verify-fall-rule-engine.py' \\
  -o -name 'verify-observation-logs.py' \\
  -o -name 'verify-pose-factor-graph.py' \\
  -o -name 'verify-posture-classifier.py' \\
  -o -name 'verify-posture-episodes.py' \\
  -o -name 'verify-presence-sessions.py' \\
  -o -name 'verify-prolonged-floor-rule.py' \\
  -o -name 'verify-runtime-retention.py' \\
  -o -name 'verify-temporal-observation-engine.py' \\
  -o -name 'verify-upload-agent.py' \\
  -o -name 'verify-upload-queue.py' \\
  -o -name 'verify-vision-pipeline.py' \\) -delete"

ssh "$PI_SSH" "cd '$PI_ROOT' && .venv-pi/bin/python scripts/verify-vision-runtime.py --require-yolo --require-pose"
echo "deployed without replacing Pi runtime or device data: $PI_SSH:$PI_ROOT"
