#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import main as edge_main
from app.vision.privacy_background import PrivacyCalibrationRequired


class StorageStub:
    def get_camera(self, camera_id: int, *, include_secret: bool = False):
        assert camera_id == 7
        assert include_secret is True
        return {"id": 7, "name": "客厅", "enabled": True}


class CameraAgentStub:
    def raw_frames(self, camera, **options):
        assert camera["id"] == 7
        assert options == {"fps": 15, "max_width": 640, "max_height": 360}
        yield {
            "frame": np.full((36, 64, 3), 40, dtype=np.uint8),
            "source_key": "camera-7:g2",
            "frame_id": "7-1",
            "captured_at": "2026-08-03T03:00:00+00:00",
            "captured_monotonic": 100.0,
        }


class RelayStub:
    def __init__(self) -> None:
        self.wake_count = 0

    def wake(self) -> None:
        self.wake_count += 1


class RendererStub:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.begin_count = 0
        self.cancel_reasons = []

    def begin_calibration(self, camera_id: int, **options):
        self.begin_count += 1
        assert camera_id == 7
        assert options["source_key"] == "camera-7:g2"
        assert options["width"] == 64 and options["height"] == 36
        if self.mode == "already_active":
            raise PrivacyCalibrationRequired(camera_id, "calibration_in_progress")
        return {"ready": False, "calibration_active": True}

    def observe_calibration_frame(self, camera_id: int, _frame, **options):
        assert camera_id == 7
        assert options["source_key"] == "camera-7:g2"
        assert options["frame_id"] == "7-1"
        if self.mode == "success":
            return {"ready": True, "calibration_active": False, "baseline_retained": True}
        if self.mode == "persistence_failure":
            raise OSError("disk unavailable")
        return {
            "ready": False,
            "calibration_active": True,
            "baseline_retained": True,
            "last_error": "scene_unstable",
        }

    def cancel_calibration(self, camera_id: int, **options):
        assert camera_id == 7
        self.cancel_reasons.append(options["reason"])
        return {
            "ready": False,
            "calibrated": True,
            "baseline_retained": True,
            "calibration_active": False,
            "last_error": options["reason"],
        }


def assert_http_error(mode: str, *, status_code: int, code: str, cancel_reason: str | None) -> None:
    renderer = RendererStub(mode)
    edge_main.privacy_frame_renderer = renderer
    try:
        edge_main.calibrate_privacy_background(7)
    except edge_main.HTTPException as exc:
        assert exc.status_code == status_code
        assert exc.detail["code"] == code
        calibration = exc.detail.get("calibration") or {}
        if cancel_reason is None:
            assert renderer.cancel_reasons == []
        else:
            assert renderer.cancel_reasons == [cancel_reason]
            assert calibration["calibration_active"] is False
            assert calibration["baseline_retained"] is True
    else:
        raise AssertionError(f"{mode} must fail")


def main() -> None:
    original_storage = edge_main.storage
    original_camera_agent = edge_main.camera_agent
    original_renderer = edge_main.privacy_frame_renderer
    original_relay = edge_main.live_relay_agent
    original_calibration_status = edge_main.privacy_calibration_status
    relay = RelayStub()
    try:
        edge_main.storage = StorageStub()
        edge_main.camera_agent = CameraAgentStub()
        edge_main.live_relay_agent = relay

        success = RendererStub("success")
        edge_main.privacy_frame_renderer = success
        response = edge_main.calibrate_privacy_background(7)
        assert response["ok"] is True
        assert response["calibration"]["ready"] is True
        assert success.cancel_reasons == []
        assert relay.wake_count == 1

        assert_http_error(
            "timeout",
            status_code=409,
            code="scene_unstable",
            cancel_reason="scene_unstable",
        )
        assert_http_error(
            "persistence_failure",
            status_code=503,
            code="calibration_persistence_failed",
            cancel_reason="calibration_persistence_failed",
        )
        assert_http_error(
            "already_active",
            status_code=409,
            code="calibration_in_progress",
            cancel_reason=None,
        )

        edge_main.privacy_calibration_status = lambda: [
            {"camera_id": 7, "status": "calibration_required", "ready": False},
        ]
        edge_main.require_privacy_stream_ready(7, "original")
        edge_main.require_privacy_stream_ready(7, "person_blur")
        try:
            edge_main.require_privacy_stream_ready(7, "skeleton")
        except edge_main.HTTPException as exc:
            assert exc.status_code == 409
            assert exc.detail["code"] == "calibration_required"
            assert exc.detail["camera_id"] == 7
        else:
            raise AssertionError("uncalibrated skeleton stream must fail before MJPEG starts")
        edge_main.privacy_calibration_status = lambda: [
            {
                "camera_id": 7,
                "status": "revalidating",
                "ready": False,
                "calibrated": True,
                "baseline_retained": True,
            },
        ]
        edge_main.require_privacy_stream_ready(7, "skeleton")
        edge_main.privacy_calibration_status = lambda: [
            {"camera_id": 7, "status": "ready", "ready": True},
        ]
        edge_main.require_privacy_stream_ready(7, "skeleton")
    finally:
        edge_main.storage = original_storage
        edge_main.camera_agent = original_camera_agent
        edge_main.privacy_frame_renderer = original_renderer
        edge_main.live_relay_agent = original_relay
        edge_main.privacy_calibration_status = original_calibration_status

    print({
        "ok": True,
        "success_commits": True,
        "timeout_cancels": True,
        "persistence_failure_cancels": True,
        "concurrent_calibration_preserved": True,
        "uncalibrated_stream_rejected": True,
        "revalidating_stream_allowed": True,
        "calibrated_stream_allowed": True,
    })


if __name__ == "__main__":
    main()
