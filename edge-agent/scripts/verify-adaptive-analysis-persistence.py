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
        self.risk = False

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
            "fall_candidate": self.risk,
            "fall_score": 0.9 if self.risk else 0.0,
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
        self.presence_upserts = 0
        self.presence_closes = 0
        self.presence_active = False
        self.posture_upserts = 0
        self.posture_closes = 0
        self.activity_intervals = 0

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

    def close_presence_session(self, **payload: object) -> dict | None:
        if not self.presence_active:
            return None
        self.presence_closes += 1
        self.presence_active = False
        return {"id": self.presence_closes, **payload}

    def upsert_presence_session(self, **payload: object) -> dict:
        self.presence_upserts += 1
        self.presence_active = True
        return {"id": self.presence_upserts, **payload}

    def upsert_posture_episode(self, **payload: object) -> dict:
        self.posture_upserts += 1
        return {"id": self.posture_upserts, **payload}

    def close_posture_episode(self, **payload: object) -> dict | None:
        self.posture_closes += 1
        return {"id": self.posture_closes, **payload}

    def close_observation_log(self, **payload: object) -> None:
        return None

    def advance_activity_export(self, **payload: object) -> list[dict]:
        if payload.get("visible") and payload.get("flush"):
            self.activity_intervals += 1
        return []

    def close_camera_runtime_state(self, camera_id: int, *, reason: str) -> dict:
        return {}

    def camera_presence_status(self, camera_id: int, *, expected_interval_seconds: int = 5) -> dict:
        return {}


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
    detect_agent = DetectAgent()
    worker = EdgeWorker(
        storage,
        camera_agent,
        detect_agent,
        EventAgent(),
        activity_log_interval_seconds=600,
        risk_evidence_interval_seconds=0.5,
        monotonic_clock=clock,
    )
    camera = {"id": 24, "name": "客厅", "room": "客厅", "stream_url": "rtsp://camera", "enabled": True}

    first = worker.process_camera(camera, rules(), adaptive_pose=True)
    if first.get("persisted") or first.get("activity_persisted"):
        raise SystemExit(f"first no-person frame wrote durable data: {first}")
    if storage.snapshots or storage.detections or storage.evaluations or camera_agent.saved:
        raise SystemExit(f"ordinary no-person frame reached durable storage: {storage.__dict__}")

    clock.value = 101.0
    second = worker.process_camera(camera, rules(), adaptive_pose=True)
    if second.get("persisted"):
        raise SystemExit("ordinary high-frequency anchor was unexpectedly persisted")
    if storage.snapshots or storage.detections or storage.evaluations:
        raise SystemExit(f"high-frequency anchor amplified durable writes: {storage.__dict__}")
    if camera_agent.saved:
        raise SystemExit(f"high-frequency anchor amplified JPEG writes: {camera_agent.saved}")
    if worker.temporal_engine.recent_history(24)[-1]["observed_at"] == worker.temporal_engine.recent_history(24)[-2]["observed_at"]:
        raise SystemExit("non-persisted anchor did not advance in-memory temporal observation")

    detect_agent.risk = True
    clock.value = 102.0
    risk_frame = worker.process_camera(camera, rules(), adaptive_pose=True)
    if not risk_frame.get("persisted") or risk_frame.get("persistence_reason") != "formal_risk_evidence":
        raise SystemExit(f"formal risk did not persist immediately: {risk_frame}")
    if storage.snapshots != 1 or storage.detections != 1 or storage.evaluations != 1 or camera_agent.saved != 1:
        raise SystemExit(f"formal risk did not persist one complete evidence chain: {storage.__dict__}")
    evidence_snapshots = ((storage.last_detection_analysis.get("temporal_evidence_bundle") or {}).get("snapshots") or [])
    if not evidence_snapshots or evidence_snapshots[-1].get("snapshot_id") != 1:
        raise SystemExit(f"durable detection omitted its current evidence frame: {evidence_snapshots}")

    risk_analysis = {
        "person_count": 1,
        "inference_runtime": {"mode": "risk"},
        "fall_candidate": False,
        "pose_fall_candidate": False,
        "fire_event_candidate": False,
        "black_screen": False,
        "pose_factor_graph": {},
    }
    confirmed_analysis = {**risk_analysis, "fall_candidate": True}
    if worker._should_persist_analysis(24, confirmed_analysis, {}, rules(), now=102.49):
        raise SystemExit("visual risk wrote faster than the two-FPS evidence budget")
    if not worker._should_persist_analysis(24, confirmed_analysis, {}, rules(), now=102.5):
        raise SystemExit("visual risk did not retain its two-FPS evidence sample")
    if not worker._should_persist_analysis(24, risk_analysis, {}, rules(), now=103.0):
        raise SystemExit("risk-frequency analysis did not retain its one-second evidence sample")

    presence_snapshot = {
        "id": None,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    absent = {
        "credible_person_present": False,
        "credible_person_count": 0,
        "presence_persistence_state": "absent",
        "active_tracks": [],
    }
    visible_standing = {
        "credible_person_present": True,
        "credible_person_count": 1,
        "credible_track_ids": ["c24-p1"],
        "presence_persistence_state": "visible",
        "active_tracks": [{"track_id": "c24-p1", "posture": "standing"}],
        "posture_episode_updates": [],
        "posture_episode_closures": [],
    }
    if worker._persist_activity_timeline_if_due(camera, presence_snapshot, absent, now=200.0):
        raise SystemExit("initial no-person state must not write an activity record")
    if worker._persist_activity_timeline_if_due(camera, presence_snapshot, absent, now=800.0):
        raise SystemExit("continued no-person state must not write a heartbeat")
    if not worker._persist_activity_timeline_if_due(camera, presence_snapshot, visible_standing, now=801.0):
        raise SystemExit("credible person arrival did not open a structured activity session")
    if worker._persist_activity_timeline_if_due(camera, presence_snapshot, visible_standing, now=900.0):
        raise SystemExit("continued presence wrote before the ten-minute heartbeat")
    if not worker._persist_activity_timeline_if_due(camera, presence_snapshot, visible_standing, now=1401.0):
        raise SystemExit("continued presence omitted the ten-minute heartbeat")
    visible_sitting = {
        **visible_standing,
        "active_tracks": [{"track_id": "c24-p1", "posture": "sitting"}],
    }
    if not worker._persist_activity_timeline_if_due(camera, presence_snapshot, visible_sitting, now=1402.0):
        raise SystemExit("posture transition was not persisted immediately")
    if not worker._persist_activity_timeline_if_due(camera, presence_snapshot, absent, now=1403.0):
        raise SystemExit("person departure did not close the structured activity session")
    if storage.presence_upserts != 3 or storage.presence_closes != 1:
        raise SystemExit(f"unexpected structured presence writes: {storage.__dict__}")
    if storage.snapshots != 1 or camera_agent.saved != 1:
        raise SystemExit("structured activity unexpectedly persisted JPEG evidence")

    print({
        "ok": True,
        "analysis_calls": detect_agent.calls,
        "durable_snapshots": storage.snapshots,
        "durable_detections": storage.detections,
        "durable_evaluations": storage.evaluations,
        "jpeg_writes": camera_agent.saved,
        "risk_persistence_interval_seconds": 0.5,
        "risk_evidence_fps_limit": 2,
        "presence_quality_gate": True,
        "activity_heartbeat_seconds": 600,
    })


if __name__ == "__main__":
    main()
