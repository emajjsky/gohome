#!/usr/bin/env bash
set -euo pipefail

TARGET_HOST="${GOHOME_PROXY_TARGET_HOST:-127.0.0.1}"
TARGET_PORT="${GOHOME_AGENT_PORT:-8711}"
SERVER_NAME="${GOHOME_ADMIN_SERVER_NAME:-gohome.local}"
EXTRA_SERVER_NAMES="${GOHOME_PROXY_EXTRA_SERVER_NAMES:-10.42.0.1 captive.apple.com www.apple.com connectivitycheck.gstatic.com clients3.google.com www.gstatic.com www.msftconnecttest.com dns.msftncsi.com}"
SITE_NAME="${GOHOME_ADMIN_PROXY_SITE:-gohome-edge-agent}"
AVAILABLE_DIR="/etc/nginx/sites-available"
ENABLED_DIR="/etc/nginx/sites-enabled"
SITE_PATH="$AVAILABLE_DIR/$SITE_NAME"
COMMAND="${1:-install}"

usage() {
  cat <<'EOF'
usage: sudo bash scripts/install-admin-proxy.sh

Installs an nginx reverse proxy so setup/admin pages can be opened without :8711:

  http://10.42.0.1
  http://gohome.local/admin

Environment overrides:
  GOHOME_AGENT_PORT             default 8711
  GOHOME_PROXY_TARGET_HOST      default 127.0.0.1
  GOHOME_ADMIN_SERVER_NAME      default gohome.local
  GOHOME_PROXY_EXTRA_SERVER_NAMES hotspot IP and captive portal hosts
  GOHOME_ADMIN_PROXY_SITE       default gohome-edge-agent
EOF
}

case "$COMMAND" in
  install)
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

if [[ "${EUID}" -ne 0 ]]; then
  echo "please run with sudo: sudo bash scripts/install-admin-proxy.sh" >&2
  exit 1
fi

if ! command -v nginx >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    apt-get install -y nginx
  else
    echo "nginx not found. Install nginx first, then rerun this script." >&2
    exit 1
  fi
fi

install -d -m 0755 "$AVAILABLE_DIR"
install -d -m 0755 "$ENABLED_DIR"

cat > "$SITE_PATH" <<EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name ${SERVER_NAME} ${EXTRA_SERVER_NAMES};

    client_max_body_size 20m;

    location / {
        proxy_pass http://${TARGET_HOST}:${TARGET_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
EOF

ln -sf "$SITE_PATH" "$ENABLED_DIR/$SITE_NAME"
rm -f "$ENABLED_DIR/default"

nginx -t
systemctl enable nginx >/dev/null 2>&1 || true
systemctl restart nginx

cat <<EOF

GoHome admin proxy installed.
Setup URL: http://10.42.0.1
Admin URL: http://${SERVER_NAME}/admin
Proxy target: http://${TARGET_HOST}:${TARGET_PORT}
EOF
