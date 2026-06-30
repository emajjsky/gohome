#!/usr/bin/env bash
set -euo pipefail

AGENT_BASE_URL="${AGENT_BASE_URL:-http://127.0.0.1:8711}"
TITLE="${1:-想家了吗测试通知}"
BODY="${2:-这是一条部署前自测消息。}"
EXTRA_JSON="${3:-{}}"

if ! command -v curl >/dev/null 2>&1; then
  echo "curl not found" >&2
  exit 1
fi

PAYLOAD="$(python3 - "$TITLE" "$BODY" "$EXTRA_JSON" <<'PY'
import json
import sys

title = sys.argv[1]
body = sys.argv[2]
extra_raw = sys.argv[3]

try:
    extra = json.loads(extra_raw)
except json.JSONDecodeError as exc:
    raise SystemExit(f"invalid extra json: {exc}")

print(json.dumps({
    "title": title,
    "body": body,
    "extra": extra,
}, ensure_ascii=False))
PY
)"

curl --fail --show-error --silent \
  -X POST "${AGENT_BASE_URL%/}/api/notify/test" \
  -H "Content-Type: application/json" \
  --data "$PAYLOAD"

echo
