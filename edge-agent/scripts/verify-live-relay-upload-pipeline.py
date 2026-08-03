#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from threading import Event, Lock
from urllib.parse import parse_qs, urlsplit
import json
import numpy as np
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.live_relay_agent import LiveRelayAgent
from app.vision.privacy_background import PrivacyCalibrationRequired


class SettingsStub:
    live_relay_enabled = True
    live_relay_fps = 15
    live_relay_width = 640
    live_relay_height = 360
    live_relay_quality = 55
    live_relay_request_timeout_seconds = 2
    app_server_base_url = "https://example.invalid"
    device_api_token = "device-token"
    require_issued_device_token = False


class CameraAgentStub:
    def __init__(self, stop_event: Event) -> None:
        self.stop_event = stop_event

    def raw_frames(self, camera, **_options):
        for index in range(20):
            yield {
                "frame": np.full((36, 64, 3), index, dtype=np.uint8),
                "frame_id": f"{camera['id']}-{index + 1}",
                "source_key": f"camera-{camera['id']}-source",
                "captured_at": "2026-07-29T16:00:00+00:00",
                "captured_monotonic": time.monotonic(),
            }
            time.sleep(0.001)
        self.stop_event.set()

    def frame_source_key(self, camera):
        return f"camera-{camera['id']}-source"


class PrivacyRendererStub:
    def __init__(self, blocked_frames: int = 0) -> None:
        self.render_calls = 0
        self.blocked_frames = max(0, int(blocked_frames))

    def render_frame(
        self,
        _camera_id,
        _frame,
        mode,
        *,
        quality,
        source_key,
        frame_id,
        captured_at,
        captured_monotonic=None,
    ):
        del captured_monotonic
        assert quality == SettingsStub.live_relay_quality
        assert source_key == f"camera-{_camera_id}-source"
        assert frame_id.startswith(f"{_camera_id}-")
        assert captured_at == "2026-07-29T16:00:00+00:00"
        assert mode == "skeleton"
        self.render_calls += 1
        if self.render_calls <= self.blocked_frames:
            raise PrivacyCalibrationRequired(_camera_id, "stream_revalidation_required")
        return b"server-composed-skeleton"


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

    def delayed_upload(_camera_id, frame, **metadata):
        nonlocal active, max_active
        del frame
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
    assert max_active == 1
    assert stats["submitted"] == 20
    assert stats["completed"] == len(submitted)
    assert stats["replaced_pending"] == 20 - len(submitted)
    assert stats["failed"] == 0
    assert len({epoch for epoch, _sequence in submitted}) == 1
    sequences = [sequence for _epoch, sequence in submitted]
    assert sequences == sorted(sequences)
    assert sequences[-1] == 20

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
        captured_monotonic=time.monotonic() - 0.025,
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
    assert measured["source_to_cloud_ms_p95"] >= 25

    skeleton_stop = Event()
    skeleton_renderer = PrivacyRendererStub(blocked_frames=3)
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
    def delayed_skeleton_upload(*args, **kwargs):
        uploaded_frames.append((args, kwargs))
        time.sleep(0.04)

    skeleton_relay._post_frame = delayed_skeleton_upload
    skeleton_relay._run_camera({"id": 2}, skeleton_stop)
    assert skeleton_renderer.render_calls == 20
    skeleton_sequences = [item[1]["sequence"] for item in uploaded_frames]
    assert skeleton_sequences == sorted(skeleton_sequences)
    assert skeleton_sequences[-1] == 17
    skeleton_stats = skeleton_relay.status()["cameras"]["2"]
    assert skeleton_stats["submitted"] == 17
    assert skeleton_stats["completed"] == len(uploaded_frames)
    assert skeleton_stats["replaced_pending"] == 17 - len(uploaded_frames)
    assert skeleton_stats["privacy_blocked"] == 3
    assert skeleton_stats["failed"] == 0
    assert skeleton_relay._camera_privacy_modes[2] == "skeleton"
    assert skeleton_relay.status()["camera_privacy_states"]["2"]["status"] == "ready"

    print({
        "ok": True,
        "maximum_concurrent_uploads": max_active,
        "submitted": stats["submitted"],
        "replaced_pending": stats["replaced_pending"],
        "latest_frame_uploaded": sequences[-1] == 20,
        "monotonic_upload": True,
        "skeleton_live_frame_uploads": len(uploaded_frames),
        "calibration_does_not_restart_capture": skeleton_renderer.render_calls == 20,
        "single_server_composition": True,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
