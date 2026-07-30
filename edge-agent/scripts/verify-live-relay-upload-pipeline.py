#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from threading import Event, Lock
from urllib.parse import parse_qs, urlsplit
import json
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.live_relay_agent import LiveRelayAgent


class SettingsStub:
    live_relay_enabled = True
    live_relay_fps = 15
    live_relay_width = 640
    live_relay_height = 360
    live_relay_quality = 55
    live_relay_drop_stale_frames = 1
    live_relay_upload_workers = 4
    live_relay_request_timeout_seconds = 2
    app_server_base_url = "https://example.invalid"
    device_api_token = "device-token"
    require_issued_device_token = False


class CameraAgentStub:
    def __init__(self, stop_event: Event) -> None:
        self.stop_event = stop_event

    def mjpeg_frames(self, _camera, **_options):
        for index in range(20):
            yield f"frame-{index}".encode("ascii")
            time.sleep(0.001)
        self.stop_event.set()


class PrivacyRendererStub:
    def __init__(self) -> None:
        self.scene_calls = 0

    def safe_scene_jpeg(self, _camera_id, _frame, *, quality):
        assert quality == SettingsStub.live_relay_quality
        self.scene_calls += 1
        return b"safe-scene"


def main() -> int:
    stop_event = Event()
    relay = LiveRelayAgent(
        storage=None,
        settings=SettingsStub(),
        camera_agent=CameraAgentStub(stop_event),
        device_id_resolver=lambda: "edge-test",
        token_resolver=lambda: "issued-token",
        remote_camera_id_resolver=lambda camera_id: camera_id + 100,
    )

    lock = Lock()
    active = 0
    max_active = 0
    submitted = []

    def delayed_upload(_camera_id, _frame, **metadata):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
            submitted.append((metadata["stream_epoch_ms"], metadata["sequence"]))
        time.sleep(0.04)
        with lock:
            active -= 1

    original_post_frame = relay._post_frame
    relay._post_frame = delayed_upload
    relay._run_camera({"id": 2}, stop_event)
    relay._post_frame = original_post_frame

    stats = relay.status()["cameras"]["2"]
    assert max_active == SettingsStub.live_relay_upload_workers
    assert stats["submitted"] == SettingsStub.live_relay_upload_workers
    assert stats["completed"] == SettingsStub.live_relay_upload_workers
    assert stats["dropped_busy"] == 20 - SettingsStub.live_relay_upload_workers
    assert stats["failed"] == 0
    assert len({epoch for epoch, _sequence in submitted}) == 1
    assert sorted(sequence for _epoch, sequence in submitted) == list(
        range(1, SettingsStub.live_relay_upload_workers + 1)
    )

    captured_url = ""

    def capture_request(_camera_id, url, _frame, _headers, _timeout):
        nonlocal captured_url
        captured_url = url
        return json.dumps({"requested_privacy_mode": "original"})

    relay._post_frame_keepalive = capture_request
    relay._post_frame(
        2,
        b"frame",
        captured_at="2026-07-29T16:00:00+00:00",
        stream_epoch_ms=123456,
        sequence=7,
    )
    query = parse_qs(urlsplit(captured_url).query)
    assert query["stream_epoch_ms"] == ["123456"]
    assert query["sequence"] == ["7"]
    assert query["captured_at"] == ["2026-07-29T16:00:00+00:00"]
    measured = relay.status()["cameras"]["2"]
    assert measured["accepted_fps"] > 0
    assert measured["upload_latency_ms_max"] >= measured["upload_latency_ms_p95"]

    skeleton_stop = Event()
    skeleton_renderer = PrivacyRendererStub()
    skeleton_relay = LiveRelayAgent(
        storage=None,
        settings=SettingsStub(),
        camera_agent=CameraAgentStub(skeleton_stop),
        device_id_resolver=lambda: "edge-test",
        token_resolver=lambda: "issued-token",
        remote_camera_id_resolver=lambda camera_id: camera_id + 100,
        privacy_mode_resolver=lambda: "skeleton",
        privacy_renderer=skeleton_renderer,
    )
    uploaded_frames = []
    uploaded_scenes = []
    skeleton_relay._post_frame = lambda *args, **kwargs: uploaded_frames.append((args, kwargs))
    skeleton_relay._post_safe_scene = lambda camera_id, frame: uploaded_scenes.append((camera_id, frame))
    skeleton_relay._run_camera({"id": 2}, skeleton_stop)
    assert uploaded_frames == []
    assert uploaded_scenes == [(2, b"safe-scene")]
    assert skeleton_renderer.scene_calls == 1
    assert skeleton_relay._camera_privacy_modes[2] == "skeleton"

    print({
        "ok": True,
        "upload_workers": max_active,
        "submitted": stats["submitted"],
        "dropped_busy": stats["dropped_busy"],
        "ordered_upload": True,
        "skeleton_live_frame_uploads": 0,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
