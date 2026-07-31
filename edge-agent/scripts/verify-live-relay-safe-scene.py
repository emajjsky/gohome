#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.live_relay_agent import LiveRelayAgent


class SettingsStub:
    live_relay_enabled = True
    live_relay_request_timeout_seconds = 2
    app_server_base_url = "https://example.invalid"
    device_api_token = "device-token"
    require_issued_device_token = False


def main() -> int:
    relay = LiveRelayAgent(
        storage=None,
        settings=SettingsStub(),
        camera_agent=None,
        device_id_resolver=lambda: "edge-test",
        token_resolver=lambda: "issued-token",
        remote_camera_id_resolver=lambda camera_id: camera_id + 100,
    )
    captured_urls = []

    def capture_request(_camera_id, url, frame, _headers, _timeout):
        assert frame == b"safe-scene-jpeg"
        captured_urls.append(url)
        return json.dumps({"accepted": True, "stale_ignored": False})

    relay._post_scene_keepalive = capture_request
    relay._post_safe_scene(
        2,
        b"safe-scene-jpeg",
        captured_at="2026-07-31T12:00:00+00:00",
        stream_epoch_ms=123456,
        sequence=7,
    )
    query = parse_qs(urlsplit(captured_urls[0]).query)
    assert query["camera_id"] == ["102"]
    assert query["local_camera_id"] == ["2"]
    assert query["captured_at"] == ["2026-07-31T12:00:00+00:00"]
    assert query["stream_epoch_ms"] == ["123456"]
    assert query["sequence"] == ["7"]
    metrics = relay.status()["scene_cameras"]["2"]
    assert metrics["accepted_fps"] > 0
    assert metrics["upload_latency_ms_max"] >= metrics["upload_latency_ms_p95"]
    assert relay.last_scene_error == ""
    assert relay.last_error == ""
    print("live relay safe-scene ordering metadata verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
