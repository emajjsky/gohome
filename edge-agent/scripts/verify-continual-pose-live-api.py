from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import main as edge_main


class Storage:
    def get_camera(self, camera_id: int, *, include_secret: bool = False) -> dict | None:
        return {"id": camera_id, "stream_url": "rtsp://camera.invalid/live"} if camera_id == 24 else None


class Tracker:
    def __init__(self, frame: np.ndarray) -> None:
        self.frame = frame
        self.state = "tracked"

    def latest_frame(self, camera_id: int) -> dict | None:
        if self.state not in {"tracked", "coasting"}:
            return None
        display_only_stale = self.state == "coasting"
        return {
            "frame": self.frame.copy(),
            "tracking": {
                "state": self.state,
                "reason": "forward_backward_error" if display_only_stale else "",
                "frame_id": "24-101",
                "captured_at": "2026-07-17T06:00:00.100000+00:00",
                "age_seconds": 0.11,
                "pose_count": 1,
                "poses": [{
                    "track_id": "c24-p1",
                    "bbox": [10, 10, 40, 70],
                    "confidence": 0.7,
                    "tracking_state": self.state,
                    "tracking_source": "last_good_overlay" if display_only_stale else "klt",
                    "fall_evidence_eligible": False,
                    "person_evidence_eligible": False,
                    "keypoints": [],
                }],
                "quality": {"tracked_point_count": 9, "forward_backward_error": 0.12},
                "formal_evidence_eligible": False,
                "display_only_stale": display_only_stale,
            },
            "analysis_context": {"detector_backend": "yolo", "pose_model_status": "ready"},
        }

    def latest(self, camera_id: int) -> dict:
        if self.state in {"tracked", "coasting"}:
            return dict(self.latest_frame(camera_id)["tracking"])
        return {
            "state": "expired",
            "reason": "anchor_expired",
            "frame_id": "24-102",
            "captured_at": "2026-07-17T06:00:00.800000+00:00",
            "age_seconds": 0.7,
            "pose_count": 0,
            "poses": [],
            "quality": {},
            "formal_evidence_eligible": False,
        }

    def latest_metadata(self, camera_id: int) -> dict:
        tracking = self.latest(camera_id)
        return {
            "tracking": tracking,
            "analysis_context": {
                "detector_backend": "yolo",
                "pose_model_status": "ready",
            },
            "image_width": 128,
            "image_height": 72,
        }

    def has_anchor(self, camera_id: int) -> bool:
        return self.state in {"tracked", "coasting"}


class Worker:
    def __init__(self, tracker: Tracker) -> None:
        self.continual_pose_tracker = tracker


class CameraAgent:
    def __init__(self, frame: np.ndarray) -> None:
        self.frame = frame

    def latest_cached_frame(self, camera: dict, max_age_seconds: float) -> dict:
        return {
            "frame": self.frame.copy(),
            "frame_id": "24-102",
            "captured_at": "2026-07-17T06:00:00.800000+00:00",
            "source": "camera cache",
        }

    def frame_data_url(self, frame: np.ndarray, *, jpeg_quality: int, max_width: int) -> str:
        if frame.shape != self.frame.shape:
            raise SystemExit("live API encoded pixels from the wrong frame")
        return "data:image/jpeg;base64,contract"


def main() -> None:
    frame = np.full((72, 128, 3), 96, dtype=np.uint8)
    tracker = Tracker(frame)
    edge_main.storage = Storage()
    edge_main.worker = Worker(tracker)
    edge_main.camera_agent = CameraAgent(frame)

    tracked = edge_main.continual_pose_live_snapshot(24)
    snapshot = tracked.get("snapshot") or {}
    analysis = snapshot.get("analysis") or {}
    if tracked.get("source") != "eacp_same_frame" or snapshot.get("frame_id") != "24-101":
        raise SystemExit("live API did not preserve the tracked frame identity")
    if analysis.get("pose_tracking_state") != "tracked" or analysis.get("pose_count") != 1:
        raise SystemExit("live API omitted tracked pose display data")
    if not analysis.get("people", [{}])[0].get("display_only"):
        raise SystemExit("tracked pose was not marked as display-only")
    if analysis.get("continual_pose", {}).get("formal_evidence_eligible"):
        raise SystemExit("tracked pose entered formal evidence through the management API")
    json.dumps(tracked)

    tracker.state = "coasting"
    coasting = edge_main.continual_pose_live_snapshot(24, include_frame=False)
    coasting_analysis = (coasting.get("snapshot") or {}).get("analysis") or {}
    coasting_person = (coasting_analysis.get("people") or [{}])[0]
    coasting_pose = (coasting_analysis.get("poses") or [{}])[0]
    if (
        coasting.get("tracking", {}).get("state") != "coasting"
        or coasting_analysis.get("pose_count") != 1
        or not coasting_person.get("display_only")
        or coasting_pose.get("fall_evidence_eligible")
        or coasting_pose.get("person_evidence_eligible")
    ):
        raise SystemExit("management API did not isolate bounded coasting display data")
    tracker.state = "tracked"

    status_only = edge_main.continual_pose_live_snapshot(24, include_frame=False)
    metadata_snapshot = status_only.get("snapshot") or {}
    metadata_analysis = metadata_snapshot.get("analysis") or {}
    if not status_only.get("frame_available") or not metadata_snapshot:
        raise SystemExit("status-only live API lost active overlay metadata")
    if metadata_snapshot.get("image_url") or "data:image" in json.dumps(status_only):
        raise SystemExit("status-only live API encoded pixels")
    if metadata_analysis.get("image_width") != 128 or metadata_analysis.get("pose_count") != 1:
        raise SystemExit("status-only live API lost overlay dimensions or poses")
    main_source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    if "include_frame: bool = Query(default=False)" not in main_source:
        raise SystemExit("live API still defaults legacy clients to JPEG encoding")

    tracker.state = "expired"
    expired = edge_main.continual_pose_live_snapshot(24)
    expired_analysis = (expired.get("snapshot") or {}).get("analysis") or {}
    if expired_analysis.get("pose_count") != 0 or expired.get("tracking", {}).get("state") != "expired":
        raise SystemExit("expired pose remained visible in the management API")

    print({
        "ok": True,
        "same_frame": True,
        "tracked_display_only": True,
        "coasting_display_only": True,
        "formal_evidence_isolated": True,
        "status_only_overlay_metadata": True,
        "expired_pose_hidden": True,
    })


if __name__ == "__main__":
    main()
