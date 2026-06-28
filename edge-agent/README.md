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
```

Optional YOLO backend:

```bash
python -m pip install -r requirements-yolo.txt
export GOHOME_DETECTOR_BACKEND=yolo
export GOHOME_YOLO_MODEL=yolov8n.pt
```

The default backend is `basic`, which only uses brightness and frame-difference checks. Use `yolo` when you need person count and fall-candidate experiments.

## Run

Recommended demo command:

```bash
GOHOME_AGENT_PORT=8711 GOHOME_DETECTOR_BACKEND=yolo ./run.sh
```

Basic mode:

```bash
GOHOME_AGENT_PORT=8711 ./run.sh
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

Admin flow:

1. Add and test a camera on `cameras.html`.
2. Configure capture interval, visual thresholds, YOLO switches, and event rules on `algorithms.html`.
3. Use `index.html` to watch the live MJPEG stream and handle events.

The admin home page uses `/api/cameras/{camera_id}/stream.mjpg?width=1280&height=720&quality=70&drop=4` for a 720p MJPEG preview. Detection still runs from worker snapshots, so the product can explain each event with a saved frame and analysis payload.

For LAN cameras, prefer an H.264 720p substream RTSP URL. H.265 main streams can show high latency or gray-block artifacts when OpenCV/FFmpeg loses reference frames.

## Notification environment variables

Only one channel is needed for the first MVP.

Generic webhook:

```bash
export GOHOME_NOTIFY_CHANNEL=webhook
export GOHOME_GENERIC_WEBHOOK_URL=https://example.com/webhook
```

Feishu:

```bash
export GOHOME_NOTIFY_CHANNEL=feishu
export GOHOME_FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
```

Bark:

```bash
export GOHOME_NOTIFY_CHANNEL=bark
export GOHOME_BARK_URL=https://api.day.app/your-key
```

Telegram:

```bash
export GOHOME_NOTIFY_CHANNEL=telegram
export GOHOME_TELEGRAM_BOT_TOKEN=123456:xxx
export GOHOME_TELEGRAM_CHAT_ID=123456
```

## Minimal API flow

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
