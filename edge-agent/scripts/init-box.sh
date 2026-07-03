#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$AGENT_ROOT/.venv/bin/python}"
BOX_USER="${GOHOME_BOX_USER:-${SUDO_USER:-$(id -un)}}"
BOX_HOSTNAME="${GOHOME_BOX_HOSTNAME:-gohome}"
ADMIN_MUST_CHANGE_PASSWORD="${GOHOME_ADMIN_MUST_CHANGE_PASSWORD:-0}"
COMMAND="${1:-init}"

cd "$AGENT_ROOT"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "python3 not found" >&2
  exit 1
fi

case "$COMMAND" in
  init|status|reset-admin)
    ;;
  --reset-admin)
    COMMAND="reset-admin"
    ;;
  *)
    echo "usage: bash scripts/init-box.sh [init|status|reset-admin]" >&2
    exit 2
    ;;
esac

if [[ "${EUID}" -eq 0 && -n "$BOX_HOSTNAME" ]] && command -v hostnamectl >/dev/null 2>&1; then
  current_hostname="$(hostname || true)"
  if [[ "$current_hostname" != "$BOX_HOSTNAME" ]]; then
    hostnamectl set-hostname "$BOX_HOSTNAME" || true
  fi
fi

install -d -m 0755 "$AGENT_ROOT/data"
install -d -m 0755 "$AGENT_ROOT/data/snapshots"
install -d -m 0755 "$AGENT_ROOT/data/runtime"

password_change_flag="--no-force-password-change"
if [[ "$ADMIN_MUST_CHANGE_PASSWORD" == "1" || "$ADMIN_MUST_CHANGE_PASSWORD" == "true" ]]; then
  password_change_flag="--force-password-change"
fi

"$PYTHON_BIN" -m app.box_init_service "$COMMAND" --username admin --password 123456 "$password_change_flag"

if [[ "${EUID}" -eq 0 && -n "$BOX_USER" && "$BOX_USER" != "root" ]]; then
  chown -R "$BOX_USER:$BOX_USER" "$AGENT_ROOT/data" || true
fi

cat <<'EOF'

GoHome box initialized.
Admin URL: http://gohome.local/admin
Initial admin: admin / 123456
Development default: initial password can be used directly
EOF
