# Raspberry Pi 5 Deploy Guide

This guide is only for hardware validation after the Mac local loop is stable.
Do not move main development to Raspberry Pi.

## Goal

- Bring up `edge-agent` on Raspberry Pi 5 quickly.
- Reuse the current repository and `.env` runtime path.
- Verify boot, `systemd`, logs, one-camera live flow, and 24-hour stability.

## Target Device

- Raspberry Pi 5
- 8GB RAM
- Raspberry Pi OS 64-bit
- Wired Ethernet preferred
- Stable 27W USB-C power supply
- Active cooling or verified heatsink/fan
- SSD or high-quality microSD for the first round

## Validation Boundary

- Raspberry Pi only validates low-power deployment and runtime stability.
- Keep the current Mac as the main reference environment.
- Start with one RTSP camera only.
- Prefer H.264 substream, 720p or lower, low FPS, and conservative capture interval.

## Directory Layout

Assume the repo is placed at:

```bash
/home/pi/gohome
```

Then the edge service root is:

```bash
/home/pi/gohome/edge-agent
```

## System Packages

Install base packages first:

```bash
sudo apt update
sudo apt install -y \
  python3 \
  python3-venv \
  python3-pip \
  ffmpeg \
  git \
  curl \
  jq \
  rsync
```

Optional but recommended for diagnostics:

```bash
sudo apt install -y htop iotop vcgencmd
```

## Python Environment

```bash
cd /home/pi/gohome/edge-agent
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
./.venv/bin/pip install -r requirements-yolo.txt
```

If the first round only validates service boot and RTSP flow, it is acceptable to postpone YOLO and start with:

```bash
./.venv/bin/pip install -r requirements.txt
```

## Environment File

Create `.env` from the example:

```bash
cd /home/pi/gohome/edge-agent
cp .env.example .env
```

Recommended first-round fields:

```bash
GOHOME_AGENT_HOST=0.0.0.0
GOHOME_AGENT_PORT=8711
GOHOME_DETECTOR_BACKEND=basic
GOHOME_CAPTURE_INTERVAL_SECONDS=8
GOHOME_NO_MOTION_SECONDS=300
GOHOME_EVENT_THROTTLE_SECONDS=300
GOHOME_NOTIFY_CHANNEL=off
```

Second-round fields after the base flow is stable:

```bash
GOHOME_DETECTOR_BACKEND=yolo
GOHOME_YOLO_MODEL=yolov8n.pt
GOHOME_YOLO_CONFIDENCE=0.35
```

## First Start

Run once in the foreground before installing `systemd`:

```bash
cd /home/pi/gohome/edge-agent
./run.sh
```

Then confirm:

- `http://<pi-lan-ip>:8711/admin/index.html` opens
- `http://<pi-lan-ip>:8711/ui/index.html` opens
- `GET /api/health` returns success if present in your current build
- logs and database are created under `edge-agent/data`

## Camera Strategy

Use one camera only for the first day:

- RTSP
- H.264
- substream preferred
- 720p or lower
- avoid H.265 main stream
- avoid multi-camera setup before single-camera stability is proven

Recommended product-side verification order:

1. `connect.html`
2. `watch.html`
3. `monitor.html`
4. `events.html`
5. `event_detail.html`

## systemd Install

Use the provided helper script:

```bash
cd /home/pi/gohome/edge-agent
bash scripts/install-systemd-service.sh
```

This installs:

- `/etc/systemd/system/gohome-edge-agent.service`

Then verify:

```bash
sudo systemctl status gohome-edge-agent --no-pager
sudo systemctl restart gohome-edge-agent
sudo systemctl enable gohome-edge-agent
```

## Runtime Checks

After `systemd` is active, confirm:

```bash
curl -I http://127.0.0.1:8711/ui/index.html
curl -I http://127.0.0.1:8711/admin/index.html
```

If camera setup is complete, also confirm:

```bash
curl -I "http://127.0.0.1:8711/api/v1/video/cameras/9/stream.mjpg?profile=mobile"
```

Adjust the camera id to the real one on the Pi.

## Logs

Useful commands:

```bash
journalctl -u gohome-edge-agent -n 200 --no-pager
journalctl -u gohome-edge-agent -f
```

Application data stays under:

```bash
/home/pi/gohome/edge-agent/data
```

Key locations:

- `data/agent.db`
- `data/snapshots`
- `data/runtime`

## Log Rotation

For the Pi round, prefer journald first:

- keep logs in `journalctl`
- do not add a custom log daemon before the base flow is stable
- only add extra file rotation after the first 24-hour run

If disk growth becomes visible, cap journald:

```bash
sudo mkdir -p /etc/systemd/journald.conf.d
cat <<'EOF' | sudo tee /etc/systemd/journald.conf.d/gohome.conf
[Journal]
SystemMaxUse=200M
RuntimeMaxUse=100M
EOF
sudo systemctl restart systemd-journald
```

## 24-Hour Checklist

Check these during the first day:

- service stays up after boot
- one RTSP camera remains reachable
- MJPEG live page remains openable
- at least one snapshot is generated
- at least one real event can be produced
- CPU temperature is acceptable
- no repeated crash loop in `journalctl`

Recommended commands:

```bash
uptime
free -h
df -h
vcgencmd measure_temp
systemctl status gohome-edge-agent --no-pager
```

## Performance Strategy

For Raspberry Pi 5 first round:

- start with `basic` detector if needed
- prefer lower-resolution substream
- increase capture interval before chasing model quality
- avoid simultaneous admin preview and multiple product live pages for long periods
- enable YOLO only after the single-camera base path is stable

## Rollback

If the service becomes unstable:

```bash
sudo systemctl stop gohome-edge-agent
cd /home/pi/gohome/edge-agent
./run.sh
```

This brings you back to a foreground debug path.

If the `systemd` unit must be removed:

```bash
sudo systemctl disable --now gohome-edge-agent
sudo rm -f /etc/systemd/system/gohome-edge-agent.service
sudo systemctl daemon-reload
```

## Tomorrow's First Execution Order

1. Power, cooling, Ethernet, and storage check
2. Clone repo and create `.venv`
3. Copy `.env.example` to `.env`
4. Run `./run.sh` in foreground
5. Open admin and product pages from LAN
6. Add one RTSP camera
7. Install `systemd`
8. Reboot once and verify recovery
9. Start 24-hour observation

## Pass Signal

This Pi preparation is considered ready when:

- the Pi can start `edge-agent` without editing source files
- `systemd` can start and restart the service
- one camera can complete `connect -> watch -> monitor -> events`
- logs are readable through `journalctl`
- reboot does not require manual re-entry
