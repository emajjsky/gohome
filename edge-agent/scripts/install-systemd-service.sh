#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUN_SH="$AGENT_ROOT/run.sh"
PYTHON_BIN="${PYTHON_BIN:-$AGENT_ROOT/.venv/bin/python}"
SERVICE_NAME="${SERVICE_NAME:-gohome-edge-agent}"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
USER_NAME="${SUDO_USER:-$(id -un)}"

if [[ ! -f "$RUN_SH" ]]; then
  echo "run.sh not found: $RUN_SH" >&2
  exit 1
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "python3 not found" >&2
  exit 1
fi

if [[ "${EUID}" -ne 0 ]]; then
  echo "please run with sudo: sudo bash scripts/install-systemd-service.sh" >&2
  exit 1
fi

install -d -m 0755 "$AGENT_ROOT/data"
install -d -m 0755 "$AGENT_ROOT/data/runtime"
install -d -m 0755 "$AGENT_ROOT/data/runtime/app"
install -d -m 0755 "$AGENT_ROOT/data/runtime/app/logs"

cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=GoHome Edge Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$AGENT_ROOT
ExecStart=/bin/bash $RUN_SH
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1
Environment=PYTHON_BIN=$PYTHON_BIN
Environment=GOHOME_AGENT_DATA_DIR=$AGENT_ROOT/data

# Use journald first on Raspberry Pi. Add file rotation only after the base path is stable.
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

chmod 0644 "$SERVICE_PATH"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo "installed: $SERVICE_PATH"
systemctl --no-pager --full status "$SERVICE_NAME" || true
