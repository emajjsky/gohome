#!/usr/bin/env bash
set -euo pipefail

HOTSPOT_PREFIX="${GOHOME_HOTSPOT_PREFIX:-GoHome}"
HOTSPOT_PASSWORD="${GOHOME_HOTSPOT_PASSWORD:-gohome2026}"
WIFI_IFACE="${GOHOME_WIFI_IFACE:-}"
CAPTIVE_DNS="${GOHOME_CAPTIVE_DNS:-1}"
CAPTIVE_IP="${GOHOME_CAPTIVE_IP:-10.42.0.1}"
BOOT_GRACE_SECONDS="${GOHOME_WIFI_BOOT_GRACE_SECONDS:-45}"
PROFILE_CONNECT_TIMEOUT="${GOHOME_WIFI_PROFILE_CONNECT_TIMEOUT:-18}"

if ! command -v nmcli >/dev/null 2>&1; then
  echo "NetworkManager nmcli is required for setup hotspot."
  exit 1
fi

if command -v rfkill >/dev/null 2>&1; then
  rfkill unblock wifi || true
fi

nmcli radio wifi on || true

if [[ "$CAPTIVE_DNS" == "1" && "${EUID}" -eq 0 ]]; then
  install -d -m 0755 /etc/NetworkManager/dnsmasq-shared.d
  cat > /etc/NetworkManager/dnsmasq-shared.d/gohome-captive.conf <<EOF
address=/#/${CAPTIVE_IP}
EOF
fi

if [[ -z "$WIFI_IFACE" ]]; then
  WIFI_IFACE="$(nmcli -t -f DEVICE,TYPE dev status | awk -F: '$2 == "wifi" {print $1; exit}')"
fi

if [[ -z "$WIFI_IFACE" && -d /sys/class/net/wlan0 ]]; then
  WIFI_IFACE="wlan0"
fi

if [[ -z "$WIFI_IFACE" ]]; then
  echo "No Wi-Fi interface found. nmcli device status:" >&2
  nmcli dev status >&2 || true
  exit 1
fi

wifi_connected() {
  nmcli -t -f DEVICE,STATE dev status | awk -F: -v iface="$WIFI_IFACE" '$1 == iface && $2 == "connected" {found=1} END {exit found ? 0 : 1}'
}

lan_connected() {
  nmcli -t -f DEVICE,TYPE,STATE dev status | awk -F: '$2 != "loopback" && $3 == "connected" {found=1} END {exit found ? 0 : 1}'
}

saved_home_wifi_profiles() {
  nmcli -t -f NAME,TYPE connection show | while IFS=: read -r name type; do
    [[ -z "$name" ]] && continue
    if [[ "$type" == "802-11-wireless" || "$type" == "wifi" ]]; then
      if [[ "$name" == "${HOTSPOT_PREFIX}-"* ]]; then
        continue
      fi
      printf '%s\n' "$name"
    fi
  done
}

device_state="$(nmcli -t -f DEVICE,STATE dev status | awk -F: -v iface="$WIFI_IFACE" '$1 == iface {print $2; exit}')"
if [[ "$device_state" == "unavailable" || "$device_state" == "unmanaged" ]]; then
  echo "Wi-Fi interface ${WIFI_IFACE} is ${device_state}. Cannot start setup hotspot." >&2
  nmcli dev status >&2 || true
  exit 1
fi

if wifi_connected; then
  echo "Wi-Fi already connected. Setup hotspot is not needed."
  exit 0
fi

if lan_connected; then
  echo "Network already connected through another interface. Setup hotspot is not needed."
  exit 0
fi

if nmcli -t -f NAME connection show --active | grep -E "^${HOTSPOT_PREFIX}-" >/dev/null 2>&1; then
  echo "Setup hotspot already active."
  exit 0
fi

if [[ "$BOOT_GRACE_SECONDS" =~ ^[0-9]+$ && "$BOOT_GRACE_SECONDS" -gt 0 ]]; then
  echo "Waiting up to ${BOOT_GRACE_SECONDS}s for saved Wi-Fi to reconnect."
  for _second in $(seq 1 "$BOOT_GRACE_SECONDS"); do
    if wifi_connected || lan_connected; then
      echo "Network connected during boot grace. Setup hotspot is not needed."
      exit 0
    fi
    sleep 1
  done
fi

mapfile -t home_profiles < <(saved_home_wifi_profiles)
if [[ "${#home_profiles[@]}" -gt 0 ]]; then
  echo "Trying saved Wi-Fi profiles before starting setup hotspot."
  for profile in "${home_profiles[@]}"; do
    [[ -z "$profile" ]] && continue
    echo "Trying Wi-Fi profile: $profile"
    timeout "$PROFILE_CONNECT_TIMEOUT" nmcli connection up "$profile" ifname "$WIFI_IFACE" >/dev/null 2>&1 || true
    if wifi_connected || lan_connected; then
      echo "Saved Wi-Fi profile connected. Setup hotspot is not needed."
      exit 0
    fi
  done
fi

suffix="$(hostname | tr -cd '[:alnum:]' | tail -c 4 | tr '[:lower:]' '[:upper:]')"
if [ -z "$suffix" ]; then
  suffix="BOX"
fi

ssid="${HOTSPOT_PREFIX}-${suffix}"
echo "Starting setup hotspot ${ssid} on ${WIFI_IFACE}."
nmcli device set "${WIFI_IFACE}" managed yes || true
nmcli dev wifi hotspot ifname "${WIFI_IFACE}" ssid "${ssid}" password "${HOTSPOT_PASSWORD}"
echo "Setup hotspot active: ${ssid}"
