# gohome edge-agent

`edge-agent` turns the current computer into the first local guardian-box prototype.

It connects to the laptop camera or LAN cameras, captures frames, runs detection, stores events locally, serves the Web prototype, and can send temporary mobile notifications through Bark, Feishu, Telegram, or a generic webhook.

For the first local demo, use the laptop camera:

```text
stream_url = local:0
```

After the local camera flow works, switch the same API to a LAN RTSP camera.

## Setup

```bash
cd /Users/tanyihua/trae比赛/gohome/edge-agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
brew install ffmpeg
cp .env.example .env
```

Optional YOLO backend:

```bash
python -m pip install -r requirements-yolo.txt
```

The agent now auto-loads `edge-agent/.env` and `edge-agent/.env.local`. Shell-exported variables still win if both are set.

The default backend is `basic`, which only uses brightness and frame-difference checks. Use `yolo` when you need real person boxes, person count, and fall-candidate experiments. The default model is `yolo11n.pt`; on Raspberry Pi 5, keep the 720p substream and use an exported NCNN model through `GOHOME_YOLO_MODEL=yolo11n_ncnn_model` when you need lower latency.

When `GOHOME_DETECTOR_BACKEND=yolo`, the person detector runs YOLO first. If YOLO has no high-confidence person box, it then runs the seated / half-body presence enhancement layer. Enhancement candidates are returned as `presence_candidate=true` with sources such as `presence_yolo`, `presence_face`, `presence_upperbody`, or `presence_skin`, so the admin console can show them as “人体存在候选” instead of pretending they are normal high-confidence YOLO hits.

`GOHOME_ENABLE_DEMO_CAMERA` defaults to `0`. Keep it disabled for real camera testing so the admin console starts from clean camera data. Set it to `1` only when you intentionally need the built-in demo source.

## Run

Recommended demo command:

```bash
./run.sh
```

Basic mode:

```bash
GOHOME_DETECTOR_BACKEND=basic ./run.sh
```

Open:

- Product home: `http://127.0.0.1:8711/ui/index.html`
- Live monitor: `http://127.0.0.1:8711/ui/monitor.html`
- Events: `http://127.0.0.1:8711/ui/events.html`
- Admin home: `http://127.0.0.1:8711/admin/index.html`
- Camera setup: `http://127.0.0.1:8711/admin/cameras.html`
- Algorithm setup: `http://127.0.0.1:8711/admin/algorithms.html`
- API health: `http://127.0.0.1:8711/health`
- API docs: `http://127.0.0.1:8711/docs`

For phone testing on the same Wi-Fi, replace `127.0.0.1` with this computer's LAN IP from `/health`.

## Raspberry Pi clean test

Use the original Pi project directory. Do not create a second `gohome-clean` project just to retest.

Runtime state lives under `edge-agent/data`. For a clean test, move the old runtime data aside and reinitialize in place:

```bash
cd /home/gohome/gohome/edge-agent
sudo bash scripts/reset-runtime-data.sh --preserve-admin
```

This keeps the existing code, `.venv`, `.env`, systemd service, device id, and admin password. It clears the local database, cameras, events, snapshots, object uploads, and algorithm runtime files. The previous data directory is moved to `data.backup-YYYYmmdd-HHMMSS`.

For a full factory-style reset of the development box:

```bash
cd /home/gohome/gohome/edge-agent
sudo bash scripts/reset-runtime-data.sh --factory
```

Factory mode also resets box identity and admin login back to `admin / 123456`. For development boxes, this initial password can be used directly so repeated clean tests do not get blocked by a forced password-change step. Set `GOHOME_ADMIN_MUST_CHANGE_PASSWORD=1` before running `scripts/init-box.sh` if you want the product-style first-login password change.

## Real Wi-Fi provisioning test

Product first boot must work without a preconfigured home Wi-Fi. On Raspberry Pi, install the edge service and the port-80 proxy first:

```bash
cd /home/gohome/gohome/edge-agent
sudo bash scripts/install-systemd-service.sh
sudo bash scripts/install-admin-proxy.sh
```

Then simulate a factory-new network state. This can drop SSH because it deletes saved Wi-Fi profiles and starts the setup hotspot:

```bash
cd /home/gohome/gohome/edge-agent
sudo bash scripts/prepare-factory-network-test.sh --yes
```

Expected result:

1. Phone sees a Wi-Fi named `GoHome-XXXX`.
2. Phone joins it with password `gohome2026`.
3. The phone may open the setup page automatically. If it does not, open `http://10.42.0.1`.
4. Select the home Wi-Fi and enter its password.
5. Phone may disconnect from `GoHome-XXXX`; reconnect the phone to the same home Wi-Fi.
6. Open the `回家` App to bind the device. Developer/admin mode is separate at `http://gohome.local/admin`.

The edge service starts after NetworkManager, not after `network-online.target`, so a factory-new box can still serve `/setup` while waiting for home Wi-Fi.

## Port and local URL

The FastAPI service listens on `8711` by default because a normal non-root systemd service should not bind directly to port `80`. For development, keep:

```text
http://gohome.local:8711/admin
```

For product-like access without showing a port, put nginx or Caddy in front of the agent and proxy port `80` to `127.0.0.1:8711`. Then the admin URL becomes:

```text
http://gohome.local/admin
```

On Raspberry Pi, install the nginx proxy with:

```bash
cd /home/gohome/gohome/edge-agent
sudo bash scripts/install-admin-proxy.sh
```

With the proxy installed, the user-facing setup URL is:

```text
http://10.42.0.1
```

The local admin console is a developer/installer mode only:

```text
http://gohome.local/admin
```

## Pilot install SOP

This SOP is the current first-version field flow for a 1-5 home pilot on macOS.

### 1. Required materials

- One host computer: current priority is `M4 Mac` or `Mac mini / N100` for the first pilot.
- One H.264 RTSP camera with a low-resolution substream.
- Stable power adapter and power strip.
- Wired network first, Wi-Fi only as fallback.
- One installation phone on the same LAN for live preview and notification checks.
- One test account for the installer, or a fresh household account created on site.

### 2. Pre-install checklist

- Confirm the camera can expose a valid RTSP URL.
- Confirm the host can install `ffmpeg` and Python dependencies.
- Confirm the target LAN allows the host to reach the camera over RTSP.
- Confirm the family accepts local video processing and on-device snapshot storage.
- Confirm at least one notification channel is planned for the pilot.

### 3. Host setup

```bash
cd /Users/tanyihua/trae比赛/gohome/edge-agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
brew install ffmpeg
python -m pip install -r requirements-yolo.txt
```

Recommended runtime:

```bash
GOHOME_AGENT_PORT=8711 GOHOME_DETECTOR_BACKEND=yolo ./run.sh
```

Verify:

- `http://127.0.0.1:8711/health`
- `http://127.0.0.1:8711/docs`
- `http://127.0.0.1:8711/ui/login.html`

### 4. Account and household setup

Installer flow:

1. Open `http://127.0.0.1:8711/ui/login.html`.
2. Register a new user or log in to the target test account.
3. Create one household.
4. Bind the current host device to that household.

The same flow is available through the official APIs:

- `POST /api/v1/identity/register`
- `POST /api/v1/identity/login`
- `POST /api/v1/households`
- `POST /api/device-bindings`

### 5. Camera setup and live verification

1. Open `http://127.0.0.1:8711/admin/cameras.html`.
2. Scan the LAN, select the camera IP if discovered, then fill only the required RTSP fields.
3. Use port `554`, username `admin` unless the camera says otherwise. Keep channel `1` and stream `2` by default; the generated RTSP path is `/1/2`.
4. Click test first. The test call does not save the camera.
5. Save and enable only after a frame is captured.
6. Open the product home and live pages:
   - `http://127.0.0.1:8711/ui/index.html`
   - `http://127.0.0.1:8711/ui/watch.html`
   - `http://127.0.0.1:8711/ui/monitor.html`
7. Confirm snapshots, event list, and MJPEG live preview all work.

### 6. Enable system service

After login and device binding, install the current-user LaunchAgent so the box can auto-start through the bootstrap entry:

1. Call `GET /api/v1/runtime/edge-service` and confirm the bootstrap paths are generated.
2. Call `POST /api/v1/runtime/edge-service/install`.
3. Confirm `installed = true`, `loaded = true`.
4. Call `POST /api/v1/runtime/edge-service/reload` once to verify reload behavior.
5. Keep `POST /api/v1/runtime/edge-service/uninstall` only for rollback or cleanup.

For Raspberry Pi 5 hardware validation, use the dedicated deploy guide and `systemd` helper instead of the macOS LaunchAgent flow:

- `../docs/raspberry-pi-deploy.md`
- `scripts/install-systemd-service.sh`

### 7. First-day acceptance

- The camera stays online and can produce live MJPEG output.
- The household can open the live page from phone on the same LAN.
- At least one event appears in the list with a real snapshot.
- The runtime status API returns valid process state.
- The edge-service status API returns valid LaunchAgent state.
- Logs are written under `data/runtime/app/logs` and `data/runtime/edge-bootstrap/logs`.

## Hardware checklist

### Required now

- Host device:
  - `M4 Mac / 24GB` for development and fastest local verification
  - `Mac mini / N100` for near-term small pilot deployment
- Camera:
  - RTSP
  - H.264
  - low-resolution substream preferred
- Network:
  - wired Ethernet preferred
  - stable router with reserved LAN IPs if possible
- Storage and power:
  - reliable SSD or internal storage
  - stable power strip and surge protection

### Recommended for pilot

- External temperature monitoring or a simple thermal check routine.
- UPS or at least a documented recovery flow after power loss.
- Spare network cable and spare camera power adapter.
- A phone on the same LAN for installer verification.
- One printed or digital deployment checklist for the installer.

### Not recommended for this round

- H.265 main-stream-only cameras as the primary pilot input.
- Raspberry Pi as the main development machine.
- High-resolution multi-camera deployments before single-camera stability is proven.
- Wi-Fi-only placement when wired networking is available.
- Unverified AI accelerator stacks before the base edge-agent flow is stable.

## Small-batch validation

Use this matrix for the first 1-5 household pilot.

| Item | Target | Pass signal |
| --- | --- | --- |
| Installer time | finish first install within 30 minutes | one installer can complete setup without editing code |
| Service startup | boot and reload through LaunchAgent | `edge-service` reports `installed=true` and `loaded=true` |
| Camera stability | keep one camera online for daily use | no manual re-add during the observation window |
| Live access | phone can open live page on the same LAN | household can reach `watch.html` and see MJPEG output |
| Event chain | at least one real event can be produced and explained | snapshot, event list, and detail page all work |
| Notification | at least one chosen channel is configured | one real message reaches the installer or family phone |
| 24-hour run | no service collapse in one day | health page and runtime APIs stay reachable |
| 7-day observation | reach stable pilot threshold | no blocking issue forces site rollback |

### Roles

- Installer: network, host, camera, account, and service setup.
- Family operator: daily live viewing and alert feedback.
- Developer/operator: logs, runtime status, event quality, and rollback support.

### Exit conditions for this round

- A single installer can deploy the host without editing source files.
- The household can log in, bind, and view live video.
- The system service can be installed, reloaded, and removed cleanly.
- One camera can run through the live + event + snapshot chain.
- The team has enough evidence to decide whether to expand to more homes.

Admin flow:

1. Add and test a camera on `cameras.html`.
2. Configure capture interval, visual thresholds, YOLO switches, and event rules on `algorithms.html`.
3. Use `index.html` to watch the live MJPEG stream and handle events.

The admin home page uses `/api/cameras/{camera_id}/stream.mjpg?width=1280&height=720&quality=70&drop=4` for a 720p MJPEG preview. Detection still runs from worker snapshots, so the product can explain each event with a saved frame and analysis payload.

For LAN cameras, prefer an H.264 720p substream RTSP URL. H.265 main streams can show high latency or gray-block artifacts when OpenCV/FFmpeg loses reference frames.

## Configuration file

Use `.env` for the normal runtime path:

```bash
cd /Users/tanyihua/trae比赛/gohome/edge-agent
cp .env.example .env
```

Recommended first fields:

```bash
GOHOME_AGENT_PORT=8711
GOHOME_DETECTOR_BACKEND=yolo
GOHOME_YOLO_MODEL=yolo11n.pt
GOHOME_YOLO_IMGSZ=960
GOHOME_YOLO_CONFIDENCE=0.20
GOHOME_APP_DEEP_LINK_SCHEME=gohome
```

For one-off experiments, shell variables still override `.env`.

## Notification environment variables

Only one channel is needed for the first MVP.

Generic webhook:

```bash
GOHOME_NOTIFY_CHANNEL=webhook
GOHOME_GENERIC_WEBHOOK_URL=https://example.com/webhook
```

Feishu:

```bash
GOHOME_NOTIFY_CHANNEL=feishu
GOHOME_FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
```

Bark:

```bash
GOHOME_NOTIFY_CHANNEL=bark
GOHOME_BARK_URL=https://api.day.app/your-key
```

Telegram:

```bash
GOHOME_NOTIFY_CHANNEL=telegram
GOHOME_TELEGRAM_BOT_TOKEN=123456:xxx
GOHOME_TELEGRAM_CHAT_ID=123456
```

Quick local test after the channel is configured:

```bash
cd /Users/tanyihua/trae比赛/gohome/edge-agent
bash scripts/send-test-notification.sh
```

## App push and APNs

Put the App push settings in `.env`:

```bash
GOHOME_APP_PUSH_PROVIDER=apns
GOHOME_APP_PUSH_RELAY_SECRET=replace-with-random-secret
GOHOME_APP_DEEP_LINK_SCHEME=gohome
GOHOME_APNS_AUTH_KEY_PATH=/absolute/path/to/AuthKey_XXXXXX.p8
GOHOME_APNS_KEY_ID=YOUR_KEY_ID
GOHOME_APNS_TEAM_ID=YOUR_TEAM_ID
GOHOME_APNS_TOPIC=com.gohome.family
GOHOME_APNS_DEFAULT_ENVIRONMENT=sandbox
```

Runtime checks:

- `GET /api/v1/runtime/app-push-relay`
- `POST /api/v1/app/push-tokens`
- `POST /api/v1/app/push-test`

## iOS shell

The repo now includes a minimal iOS shell scaffold under `ios-shell/`.

Use it for:

- requesting push permission on a real iPhone
- calling `registerForRemoteNotifications()`
- receiving the APNs device token
- bridging `push_token`, `app_install_id`, and notification launch payload back to `app-shell.html`

The shell uses `WKWebView` and the existing `window.webkit.messageHandlers.gohomeNativeApp` bridge contract already consumed by `assets/scripts/edge-client.js`.

## Minimal API flow

Verify the vision pipeline without a camera:

```bash
cd /home/gohome/gohome/edge-agent
./.venv/bin/python scripts/verify-vision-pipeline.py
```

The script checks black-screen detection, fire-candidate detection, demo person detection, and the unified `quality / person / fall / activity / fire` algorithm result envelope.

Create a local laptop camera:

```bash
curl -X POST http://127.0.0.1:8711/api/cameras \
  -H 'Content-Type: application/json' \
  -d '{"name":"笔记本摄像头","room":"本机测试","stream_url":"local:0"}'
```

Create an RTSP camera:

```bash
curl -X POST http://127.0.0.1:8711/api/cameras \
  -H 'Content-Type: application/json' \
  -d '{"name":"客厅摄像头","room":"客厅","stream_url":"rtsp://user:pass@192.168.1.10:554/stream1"}'
```

Test stream:

```bash
curl -X POST http://127.0.0.1:8711/api/cameras/1/test
```

Capture one frame:

```bash
curl -X POST http://127.0.0.1:8711/api/cameras/1/capture
```

List events:

```bash
curl 'http://127.0.0.1:8711/api/events?limit=10'
```
