#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUN_SH="$AGENT_ROOT/run.sh"
SERVICE_NAME="${SERVICE_NAME:-gohome-edge-agent}"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
USER_NAME="${SUDO_USER:-$(id -un)}"

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

if [[ ! -f "$RUN_SH" ]]; then
  echo "run.sh not found: $RUN_SH" >&2
  exit 1
fi

PYTHON_BIN="$(select_python_bin)" || {
  echo "python runtime not found" >&2
  exit 1
}

if [[ "${EUID}" -ne 0 ]]; then
  echo "please run with sudo: sudo bash scripts/install-systemd-service.sh" >&2
  exit 1
fi

install -d -m 0755 "$AGENT_ROOT/data"
install -d -m 0755 "$AGENT_ROOT/data/runtime"
install -d -m 0755 "$AGENT_ROOT/data/runtime/app"
install -d -m 0755 "$AGENT_ROOT/data/runtime/app/logs"
if [[ "$USER_NAME" != "root" ]]; then
  chown -R "$USER_NAME:$USER_NAME" "$AGENT_ROOT/data" || true
fi

INIT_BOX_SCRIPT="$SCRIPT_DIR/init-box.sh"
if [[ -f "$INIT_BOX_SCRIPT" ]]; then
  GOHOME_BOX_USER="$USER_NAME" PYTHON_BIN="$PYTHON_BIN" bash "$INIT_BOX_SCRIPT" init
fi

if getent group netdev >/dev/null 2>&1; then
  usermod -aG netdev "$USER_NAME" || true
fi

if [[ -d /etc/polkit-1/rules.d && "$USER_NAME" != "root" ]]; then
  cat > /etc/polkit-1/rules.d/49-gohome-networkmanager.rules <<EOF
polkit.addRule(function(action, subject) {
  if (subject.user == "$USER_NAME" && (
    action.id == "org.freedesktop.NetworkManager.network-control" ||
    action.id == "org.freedesktop.NetworkManager.settings.modify.system" ||
    action.id == "org.freedesktop.NetworkManager.settings.modify.own" ||
    action.id == "org.freedesktop.NetworkManager.wifi.scan" ||
    action.id == "org.freedesktop.NetworkManager.enable-disable-wifi"
  )) {
    return polkit.Result.YES;
  }
});
EOF
  chmod 0644 /etc/polkit-1/rules.d/49-gohome-networkmanager.rules
  systemctl restart polkit 2>/dev/null || true
fi

cat > /usr/local/sbin/gohome-nmcli <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

NMCLI_BIN="$(command -v nmcli || true)"
if [[ -z "$NMCLI_BIN" ]]; then
  echo "nmcli not found" >&2
  exit 127
fi

wifi_ifname() {
  "$NMCLI_BIN" -t -f DEVICE,TYPE dev status | awk -F: '$2 == "wifi" {print $1; exit}'
}

command_name="${1:-}"
shift || true

case "$command_name" in
  wifi-list)
    exec "$NMCLI_BIN" -t -f SSID,SIGNAL,SECURITY dev wifi list --rescan yes
    ;;
  wifi-connect)
    ssid="${1:-}"
    password="${2:-}"
    if [[ -z "$ssid" ]]; then
      echo "missing ssid" >&2
      exit 2
    fi
    ifname="$(wifi_ifname)"
    if [[ -z "$ifname" ]]; then
      echo "no wifi interface found" >&2
      exit 1
    fi
    if [[ -n "$password" ]]; then
      "$NMCLI_BIN" connection delete "$ssid" >/dev/null 2>&1 || true
      "$NMCLI_BIN" dev wifi connect "$ssid" password "$password" ifname "$ifname" && exit 0
      "$NMCLI_BIN" connection delete "$ssid" >/dev/null 2>&1 || true
      "$NMCLI_BIN" connection add type wifi ifname "$ifname" con-name "$ssid" ssid "$ssid"
      "$NMCLI_BIN" connection modify "$ssid" 802-11-wireless-security.key-mgmt wpa-psk
      "$NMCLI_BIN" connection modify "$ssid" 802-11-wireless-security.psk "$password"
      exec "$NMCLI_BIN" connection up "$ssid"
    fi
    "$NMCLI_BIN" connection up id "$ssid" 2>/dev/null && exit 0
    exec "$NMCLI_BIN" dev wifi connect "$ssid" ifname "$ifname"
    ;;
  *)
    echo "unsupported command" >&2
    exit 2
    ;;
esac
EOF
chmod 0755 /usr/local/sbin/gohome-nmcli

if command -v sudo >/dev/null 2>&1 && [[ "$USER_NAME" != "root" ]]; then
  cat > /etc/sudoers.d/gohome-networkmanager <<EOF
$USER_NAME ALL=(root) NOPASSWD: /usr/local/sbin/gohome-nmcli *
EOF
  chmod 0440 /etc/sudoers.d/gohome-networkmanager
  if command -v visudo >/dev/null 2>&1; then
    visudo -cf /etc/sudoers.d/gohome-networkmanager >/dev/null
  fi
fi

cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=GoHome Edge Agent
After=NetworkManager.service
Wants=NetworkManager.service

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

HOTSPOT_INSTALLER="$SCRIPT_DIR/install-setup-hotspot-service.sh"
if [[ -f "$HOTSPOT_INSTALLER" ]]; then
  bash "$HOTSPOT_INSTALLER" || true
fi

echo "installed: $SERVICE_PATH"
systemctl --no-pager --full status "$SERVICE_NAME" || true
