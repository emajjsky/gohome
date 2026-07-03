#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOTSPOT_SCRIPT="${SCRIPT_DIR}/gohome-setup-hotspot.sh"
SERVICE_PATH="/etc/systemd/system/gohome-setup-hotspot.service"

if [ ! -f "$HOTSPOT_SCRIPT" ]; then
  echo "Missing hotspot script: $HOTSPOT_SCRIPT"
  exit 1
fi

if [[ "${EUID}" -ne 0 ]]; then
  echo "please run with sudo: sudo bash scripts/install-setup-hotspot-service.sh" >&2
  exit 1
fi

chmod +x "$HOTSPOT_SCRIPT"

cat > "$SERVICE_PATH" <<SERVICE
[Unit]
Description=GoHome setup hotspot when Wi-Fi is not configured
Wants=NetworkManager.service
After=NetworkManager.service

[Service]
Type=oneshot
Environment=GOHOME_HOTSPOT_PREFIX=GoHome
Environment=GOHOME_HOTSPOT_PASSWORD=gohome2026
Environment=GOHOME_WIFI_BOOT_GRACE_SECONDS=45
Environment=GOHOME_WIFI_PROFILE_CONNECT_TIMEOUT=18
ExecStart=${HOTSPOT_SCRIPT}
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable gohome-setup-hotspot.service
systemctl start gohome-setup-hotspot.service || true
echo "Installed gohome-setup-hotspot.service"
