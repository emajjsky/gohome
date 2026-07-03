#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA_DIR="${GOHOME_AGENT_DATA_DIR:-$AGENT_ROOT/data}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="${DATA_DIR}.backup-${STAMP}"
BACKUP_CREATED=""
SERVICE_NAME="${SERVICE_NAME:-gohome-edge-agent}"
MODE="${1:---preserve-admin}"
BOX_USER="${GOHOME_BOX_USER:-${SUDO_USER:-$(id -un)}}"

usage() {
  cat <<'EOF'
usage: bash scripts/reset-runtime-data.sh [--preserve-admin|--factory]

Resets runtime data in the current edge-agent directory.

--preserve-admin  keep device_id, box_state, and admin password files if they exist
--factory         reset everything including device identity and admin password
EOF
}

case "$MODE" in
  --preserve-admin|--factory)
    ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

cd "$AGENT_ROOT"

service_exists() {
  command -v systemctl >/dev/null 2>&1 \
    && systemctl list-unit-files "${SERVICE_NAME}.service" --no-legend 2>/dev/null | grep -q "^${SERVICE_NAME}\\.service"
}

if service_exists; then
  if [[ "${EUID}" -eq 0 ]]; then
    systemctl stop "$SERVICE_NAME" || true
  else
    echo "Service ${SERVICE_NAME} exists. Run with sudo so the script can stop/start it safely:" >&2
    echo "sudo bash scripts/reset-runtime-data.sh ${MODE}" >&2
    exit 1
  fi
fi

if [[ -e "$DATA_DIR" ]]; then
  mv "$DATA_DIR" "$BACKUP_DIR"
  BACKUP_CREATED="$BACKUP_DIR"
fi

install -d -m 0755 "$DATA_DIR"
install -d -m 0755 "$DATA_DIR/snapshots"
install -d -m 0755 "$DATA_DIR/runtime"

if [[ "$MODE" == "--preserve-admin" && -d "$BACKUP_DIR" ]]; then
  for name in device_id.txt box_state.json admin_auth.json; do
    if [[ -f "$BACKUP_DIR/$name" ]]; then
      cp "$BACKUP_DIR/$name" "$DATA_DIR/$name"
    fi
  done
fi

GOHOME_BOX_USER="$BOX_USER" bash "$SCRIPT_DIR/init-box.sh" init

if [[ "${EUID}" -eq 0 && -n "$BOX_USER" && "$BOX_USER" != "root" ]]; then
  chown -R "$BOX_USER:$BOX_USER" "$DATA_DIR" || true
fi

if service_exists && [[ "${EUID}" -eq 0 ]]; then
  systemctl start "$SERVICE_NAME" || true
fi

cat <<EOF

GoHome runtime data reset in place.
Project directory: $AGENT_ROOT
Fresh data dir:    $DATA_DIR
Backup data dir:   ${BACKUP_CREATED:-none}
Mode:              $MODE

Admin:
- preserved mode keeps the previous admin password if admin_auth.json existed
- factory mode resets admin to admin / 123456
- development default does not force a password change unless GOHOME_ADMIN_MUST_CHANGE_PASSWORD=1
EOF
