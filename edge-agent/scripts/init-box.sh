#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BOX_USER="${GOHOME_BOX_USER:-${SUDO_USER:-$(id -un)}}"
BOX_HOSTNAME="${GOHOME_BOX_HOSTNAME:-gohome}"
COMMAND="${1:-init}"

cd "$AGENT_ROOT"

select_python_bin() {
  if [[ -n "${PYTHON_BIN:-}" && -x "$PYTHON_BIN" ]]; then
    printf '%s\n' "$PYTHON_BIN"
    return 0
  fi

  for candidate in "$AGENT_ROOT/.venv-pi/bin/python" "$AGENT_ROOT/.venv/bin/python" "$(command -v python3 || true)"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

PYTHON_BIN="$(select_python_bin)" || {
  echo "python runtime not found" >&2
  exit 1
}

case "$COMMAND" in
  init|status|reset-admin|credential)
    ;;
  --reset-admin)
    COMMAND="reset-admin"
    ;;
  *)
    echo "usage: bash scripts/init-box.sh [init|status|reset-admin|credential]" >&2
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

"$PYTHON_BIN" -m app.box_init_service "$COMMAND" --username admin

if [[ "${EUID}" -eq 0 && -n "$BOX_USER" && "$BOX_USER" != "root" ]]; then
  chown -R "$BOX_USER:$BOX_USER" "$AGENT_ROOT/data" || true
fi

if [[ "$COMMAND" == "init" || "$COMMAND" == "reset-admin" ]]; then
  cat <<'EOF'

GoHome box initialized.
Admin URL: http://gohome.local/admin
Admin username: admin
The one-time credential printed above must be changed after first login.
Retrieve a pending credential locally: bash scripts/init-box.sh credential
EOF
fi
