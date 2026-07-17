from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.worker import EdgeWorker


class Clock:
    def __init__(self, value: float) -> None:
        self.value = float(value)

    def __call__(self) -> float:
        return self.value


class Frame:
    shape = (360, 640, 3)

    def copy(self) -> "Frame":
        return self


class CameraAgent:
    def __init__(self) -> None:
        self.saved = 0

    def capture_frame(self, camera: dict) -> dict:
        return {
            "frame": Frame(),
            "width": 640,
            "height": 360,
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }

    def snapshot_relative_path(self, camera_id: int) -> str:
        return f"camera-{camera_id}/sample.jpg"

    def save_frame(self, frame: Frame, relative_path: str) -> None:
        self.saved += 1


class DetectAgent:
    def __init__(self) -> None:
        self.calls = 0

    def analyze_frame_with_config(self, frame: Frame, previous_frame: Frame | None, config: dict) -> dict:
        self.calls += 1
        return {
            "pipeline_version": "test",
            "model_version": "test",
            "detector_backend": "test",
            "image_width": 640,
            "image_height": 360,
            "brightness": 90.0,
            "contrast": 20.0,
            "black_screen": False,
            "motion_score": 0.0,
            "motion_detected": False,
            "person_count": 0,
            "people": [],
            "pet_count": 0,
            "pets": [],
            "pet_types": [],
            "pose_count": 0,
            "poses": [],
            "fall_candidate": False,
            "fall_score": 0.0,
            "pose_fall_candidate": False,
            "pose_fall_score": 0.0,
            "fire_candidate": False,
            "fire_event_candidate": False,
            "fire_score": 0.0,
            "meal_candidate": False,
            "stillness_candidate": False,
            "daze_candidate": False,
            "tags": [],
            "thresholds": {},
            "algorithm_results": {},
        }


class Storage:
    def __init__(self) -> None:
        self.snapshots = 0
        self.detections = 0
        self.evaluations = 0
        self.last_detection_analysis: dict = {}

    def create_snapshot(self, **payload: object) -> dict:
        self.snapshots += 1
        return {
            "id": self.snapshots,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "image_path": str(payload.get("image_path") or ""),
        }

    def create_detection_result(self, **payload: object) -> dict:
        self.detections += 1
        self.last_detection_analysis = dict(payload.get("analysis") or {})
        return {"id": self.detections}

    def create_rule_evaluation(self, **payload: object) -> dict:
        self.evaluations += 1
        return {"id": self.evaluations, **dict(payload.get("evaluation") or {})}

    def update_camera_status(self, camera_id: int, status: str, error: str | None = None) -> None:
        return None

    def close_presence_session(self, **payload: object) -> None:
        return None

    def close_observation_log(self, **payload: object) -> None:
        return None


class EventAgent:
    def emit(self, **payload: object) -> None:
        raise SystemExit(f"ordinary frame unexpectedly emitted an event: {payload}")


def rules() -> dict:
    return {
        "updated_at": "2026-07-17T00:00:00+00:00",
        "capture_interval_seconds": 5,
        "black_screen_enabled": True,
        "person_detection_enabled": True,
        "no_person_seconds": 43200,
        "fall_detection_enabled": True,
        "fall_score_threshold": 0.5,
        "fall_confirm_frames": 2,
        "fall_confirm_seconds": 1,
        "fall_recover_frames": 2,
        "fire_detection_enabled": True,
        "fire_event_score_threshold": 0.62,
        "fire_motion_threshold": 0.12,
        "fire_temporal_threshold": 0.35,
        "fire_confirm_frames": 3,
        "no_motion_enabled": False,
        "no_motion_seconds": 900,
        "activity_detection_enabled": True,
    }


def main() -> None:
    clock = Clock(100.0)
    storage = Storage()
    camera_agent = CameraAgent()
    worker = EdgeWorker(
        storage,
        camera_agent,
        DetectAgent(),
        EventAgent(),
        monotonic_clock=clock,
    )
    camera = {"id": 24, "name": "客厅", "room": "客厅", "stream_url": "rtsp://camera", "enabled": True}

    first = worker.process_camera(camera, rules(), adaptive_pose=True)
    if not first.get("persisted") or storage.snapshots != 1 or storage.detections != 1 or storage.evaluations != 1:
        raise SystemExit(f"first baseline was not fully persisted: {first}, {storage.__dict__}")
    evidence_snapshots = ((storage.last_detection_analysis.get("temporal_evidence_bundle") or {}).get("snapshots") or [])
    if not evidence_snapshots or evidence_snapshots[-1].get("snapshot_id") != 1:
        raise SystemExit(f"durable detection omitted its current evidence frame: {evidence_snapshots}")

    clock.value = 101.0
    second = worker.process_camera(camera, rules(), adaptive_pose=True)
    if second.get("persisted"):
        raise SystemExit("ordinary high-frequency anchor was unexpectedly persisted")
    if storage.snapshots != 1 or storage.detections != 1 or storage.evaluations != 1:
        raise SystemExit(f"high-frequency anchor amplified durable writes: {storage.__dict__}")
    if camera_agent.saved != 1:
        raise SystemExit(f"high-frequency anchor amplified JPEG writes: {camera_agent.saved}")
    if worker.temporal_engine.recent_history(24)[-1]["observed_at"] == worker.temporal_engine.recent_history(24)[-2]["observed_at"]:
        raise SystemExit("non-persisted anchor did not advance in-memory temporal observation")

    print({
        "ok": True,
        "analysis_calls": 2,
        "durable_snapshots": storage.snapshots,
        "durable_detections": storage.detections,
        "durable_evaluations": storage.evaluations,
        "jpeg_writes": camera_agent.saved,
    })


if __name__ == "__main__":
    main()
