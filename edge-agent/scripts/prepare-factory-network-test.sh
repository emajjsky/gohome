#!/usr/bin/env bash
set -euo pipefail

WIFI_IFACE="${GOHOME_WIFI_IFACE:-}"
HOTSPOT_SERVICE="${HOTSPOT_SERVICE:-gohome-setup-hotspot.service}"
EDGE_SERVICE="${SERVICE_NAME:-gohome-edge-agent.service}"
CONFIRM="${1:-}"

usage() {
  cat <<'EOF'
usage: sudo bash scripts/prepare-factory-network-test.sh --yes

Simulates a factory-new GoHome box network state on Raspberry Pi:
- disconnects Wi-Fi
- deletes saved non-GoHome Wi-Fi profiles
- restarts setup hotspot service
- restarts edge-agent

This can drop your SSH session. Use a keyboard/monitor, Ethernet, or be ready to reconnect through the GoHome hotspot.
EOF
}

if [[ "$CONFIRM" != "--yes" ]]; then
  usage >&2
  exit 2
fi

if [[ "${EUID}" -ne 0 ]]; then
  echo "please run with sudo: sudo bash scripts/prepare-factory-network-test.sh --yes" >&2
  exit 1
fi

if ! command -v nmcli >/dev/null 2>&1; then
  echo "nmcli not found. Install/enable NetworkManager first." >&2
  exit 1
fi

if command -v rfkill >/dev/null 2>&1; then
  rfkill unblock wifi || true
fi
nmcli radio wifi on || true

if [[ -z "$WIFI_IFACE" ]]; then
  WIFI_IFACE="$(nmcli -t -f DEVICE,TYPE dev status | awk -F: '$2 == "wifi" {print $1; exit}')"
fi

if [[ -z "$WIFI_IFACE" && -d /sys/class/net/wlan0 ]]; then
  WIFI_IFACE="wlan0"
fi

if [[ -z "$WIFI_IFACE" ]]; then
  echo "No Wi-Fi interface found. Current devices:" >&2
  nmcli dev status >&2 || true
  exit 1
fi

echo "Current active connections:"
nmcli -t -f NAME,TYPE,DEVICE connection show --active || true

echo "Deleting saved non-GoHome Wi-Fi profiles."
while IFS=: read -r name type; do
  [[ -z "$name" ]] && continue
  if [[ "$type" == "802-11-wireless" || "$type" == "wifi" ]]; then
    if [[ "$name" == GoHome-* ]]; then
      continue
    fi
    echo "Deleting Wi-Fi profile: $name"
    nmcli connection delete "$name" >/dev/null 2>&1 || true
  fi
done < <(nmcli -t -f NAME,TYPE connection show)

echo "Disconnecting ${WIFI_IFACE}."
nmcli device set "$WIFI_IFACE" managed yes || true
nmcli device disconnect "$WIFI_IFACE" >/dev/null 2>&1 || true

echo "Restarting hotspot and edge services."
systemctl restart "$HOTSPOT_SERVICE" || true
systemctl restart "$EDGE_SERVICE" || true

echo
echo "Factory network test state prepared."
echo "Expected phone Wi-Fi: GoHome-XXXX"
echo "Default hotspot password: gohome2026"
echo "Setup URL after joining hotspot: http://10.42.0.1"
echo
systemctl --no-pager --full status "$HOTSPOT_SERVICE" || true
