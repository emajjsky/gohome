#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.pose_relay_agent import PoseRelayAgent


class SettingsStub:
    pose_relay_enabled = True
    pose_relay_fps = 90
    app_server_base_url = "https://example.invalid"
    device_api_token = "test-token"
    require_issued_device_token = False


class StorageStub:
    def list_cameras(self, *, include_secret: bool):
        assert include_secret is False
        return []


class TrackerStub:
    def latest_metadata(self, _camera_id: int):
        return {}


def agent() -> PoseRelayAgent:
    return PoseRelayAgent(
        storage=StorageStub(),
        settings=SettingsStub(),
        tracker=TrackerStub(),
        device_id_resolver=lambda: "edge-test",
        token_resolver=lambda: "issued-token",
        remote_camera_id_resolver=lambda camera_id: camera_id + 100,
    )


def observed_metadata() -> dict:
    return {
        "image_width": 640,
        "image_height": 360,
        "tracking": {
            "frame_id": "frame-12",
            "captured_at": "2026-07-28T08:00:00Z",
            "state": "observed",
            "poses": [{
                "track_id": "person-1",
                "confidence": 1.4,
                "bbox": [100, 20, 500, 350],
                "keypoints": [
                    {"name": "nose", "x": 220.5, "y": 52.25, "confidence": 0.93, "visible": True},
                    {"name": "left_wrist", "x": -900, "y": 9999, "confidence": -2, "visible": False},
                    {"name": "bad", "x": "nan", "y": 12, "confidence": 1, "visible": True},
                ],
            }],
        },
        "analysis_context": {"frame": "must-not-leak"},
        "jpeg": b"must-not-leak",
    }


def main() -> int:
    relay = agent()
    assert relay._fps() == 30.0
    packet = relay._display_packet(2, observed_metadata())
    assert packet["state"] == "observed"
    assert packet["display_only"] is True
    assert packet["formal_evidence_eligible"] is False
    assert packet["image_width"] == 640 and packet["image_height"] == 360
    assert len(packet["poses"]) == 1
    assert packet["poses"][0]["confidence"] == 1.0
    assert len(packet["poses"][0]["keypoints"]) == 2
    assert packet["poses"][0]["keypoints"][1]["x"] == -256.0
    assert packet["poses"][0]["keypoints"][1]["y"] == 616.0
    serialized = json.dumps(packet, ensure_ascii=True)
    for forbidden in ("jpeg", "image_data", "analysis_context", "must-not-leak"):
        assert forbidden not in serialized

    empty = relay._display_packet(2, {
        "tracking": {
            "frame_id": "frame-13",
            "captured_at": "2026-07-28T08:00:00.050Z",
            "state": "empty",
            "poses": observed_metadata()["tracking"]["poses"],
        },
    })
    assert empty["state"] == "empty"
    assert empty["poses"] == []
    assert empty["image_width"] == 640 and empty["image_height"] == 360
    assert relay._packet_key(packet) == "observed:frame-12"
    assert relay._packet_key(empty) == "empty:frame-13"
    assert relay._packet_key({"state": "empty", "frame_id": ""}) == "empty:"

    assert relay._configured() == (True, "ready")
    print("pose relay verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
