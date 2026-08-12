#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_ROOT="${1:?usage: build-production-payload.sh OUTPUT_ROOT}"

cd "$REPO_ROOT"
if ! git diff --quiet -- edge-agent deploy/edge-agent \
  || ! git diff --cached --quiet -- edge-agent deploy/edge-agent; then
  echo "tracked Pi payload changes must be committed before building the Pi payload" >&2
  exit 1
fi

commit="$(git rev-parse --verify HEAD)"
rm -rf -- "$OUTPUT_ROOT"
mkdir -p -- "$OUTPUT_ROOT"
git archive --format=tar "$commit" edge-agent | tar -xf - -C "$OUTPUT_ROOT"

agent_root="$OUTPUT_ROOT/edge-agent"
rm -rf -- "$agent_root/eval" "$agent_root/hyperframes" "$agent_root/tools"
rm -f -- "$agent_root/scripts"/{audit-vision-dataset-readiness.py,configure-demo-mode.sh,eval*.py,import-*.py,init-vision-eval-data.py,prepare-factory-network-test.sh,prepare-vision-smoke-samples.py,run-*-eval*.sh,run-wikimedia-person-negative-eval.sh}
find "$agent_root/scripts" -maxdepth 1 -type f -name 'verify-*.py' ! -name 'verify-vision-runtime.py' -delete

# These are the only local model artifacts permitted in the Pi payload. Hailo
# HEF files are installed by the device image and are never copied from here.
for model in yolo11n.pt yolov8n.pt; do
  if [[ -f "$REPO_ROOT/edge-agent/$model" ]]; then
    cp -p "$REPO_ROOT/edge-agent/$model" "$agent_root/$model"
  fi
done

if find "$agent_root" -type f \( -name '*.log' -o -name '*.bak*' -o -name '*.backup-*' -o -name '._*' \) -print -quit | grep -q .; then
  echo "Pi payload contains a generated or backup file" >&2
  exit 1
fi

printf '%s\n' "$commit" > "$agent_root/.release-commit"
(
  cd "$agent_root"
  find . -type f ! -name '.release-manifest.sha256' | LC_ALL=C sort | while IFS= read -r file; do
    shasum -a 256 "$file" | awk -v path="${file#./}" '{print $1 "  " path}'
  done
) > "$agent_root/.release-manifest.sha256"

printf 'commit=%s\npayload=%s\nmanifest=%s\n' \
  "$commit" "$agent_root" "$agent_root/.release-manifest.sha256"
