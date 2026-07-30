#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.live_relay_agent import LiveRelayAgent


class SettingsStub:
    live_relay_enabled = True
    live_scene_relay_interval_seconds = 1
    app_server_base_url = "https://example.invalid"
    device_api_token = "device-token"
    require_issued_device_token = False


class RendererStub:
    def __init__(self):
        self.calls = 0

    def safe_scene_jpeg(self, camera_id: int, frame: bytes, *, quality: int) -> bytes:
        assert camera_id == 2
        assert frame == b"source-jpeg"
        assert quality == 55
        self.calls += 1
        return b"safe-scene-jpeg"


def main() -> int:
    renderer = RendererStub()
    relay = LiveRelayAgent(
        storage=None,
        settings=SettingsStub(),
        camera_agent=None,
        device_id_resolver=lambda: "edge-test",
        token_resolver=lambda: "issued-token",
        remote_camera_id_resolver=lambda camera_id: camera_id + 100,
        privacy_renderer=renderer,
    )

    def fail_upload(_camera_id: int, _frame: bytes) -> None:
        raise RuntimeError("scene endpoint unavailable")

    relay._post_safe_scene = fail_upload
    relay._relay_safe_scene_if_due(2, b"source-jpeg", quality=55)
    assert "scene endpoint unavailable" in relay.last_scene_error
    assert relay.last_error == ""
    assert renderer.calls == 1

    uploaded = []
    relay._last_scene_relay_monotonic[2] = 0
    relay._post_safe_scene = lambda camera_id, frame: uploaded.append((camera_id, frame))
    relay._relay_safe_scene_if_due(2, b"source-jpeg", quality=55)
    assert uploaded == [(2, b"safe-scene-jpeg")]
    assert renderer.calls == 2

    relay._relay_safe_scene_if_due(2, b"source-jpeg", quality=55)
    assert renderer.calls == 2
    print("live relay safe-scene isolation verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
