from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.rule_engine import EventCandidate, RuleEvaluation
from app.storage import Storage
from app.worker import EdgeWorker


class FakeEventAgent:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, **kwargs):
        self.events.append(kwargs)
        return {"id": len(self.events), **kwargs}


def build_candidate(snapshot_id: int, seconds: int) -> EventCandidate:
    return EventCandidate(
        event_type="no_motion",
        summary="客厅摄像头 已长时间没有明显画面变化。",
        level="info",
        snapshot_id=snapshot_id,
        payload={
            "rule": {
                "id": "no_motion",
                "reason": "连续低运动分数的时长超过配置阈值。",
                "observed": {"no_motion_seconds": seconds, "motion_score": 0.01},
                "threshold": {"no_motion_seconds": 300},
            },
            "evidence": {
                "schema_version": "gohome-event-evidence-v1",
                "event_category": "life_observation",
                "metrics": {"person_count": 1, "motion_score": 0.01},
                "rule": {
                    "observed": {"no_motion_seconds": seconds, "motion_score": 0.01},
                    "threshold": {"no_motion_seconds": 300},
                },
            },
        },
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Storage(Path(tmpdir) / "agent.db")
        storage.init_schema()
        event_agent = FakeEventAgent()
        worker = EdgeWorker(storage, camera_agent=None, detect_agent=None, event_agent=event_agent)
        camera = storage.create_camera(
            {
                "name": "客厅摄像头",
                "room": "客厅",
                "stream_url": "rtsp://192.168.1.11:554/1/2",
                "username": "admin",
                "enabled": True,
            }
        )
        snapshot = storage.create_snapshot(
            camera_id=int(camera["id"]),
            image_path="camera_1/no_motion.jpg",
            width=1280,
            height=720,
            brightness=120.0,
            motion_score=0.01,
            tags=["person_detected"],
            person_count=1,
            analysis={"person_count": 1, "motion_score": 0.01},
        )

        start = datetime.now(timezone.utc)
        for offset in [300, 600]:
            worker._emit_candidates(
                camera,
                evaluation=RuleEvaluation(
                    camera_id=int(camera["id"]),
                    snapshot_id=int(snapshot["id"]),
                    evaluated_at=(start + timedelta(seconds=offset)).isoformat(),
                    candidates=[build_candidate(int(snapshot["id"]), offset)],
                    state={"person_state": "visible", "motion_state": "still", "no_motion_seconds": offset},
                ),
                detection_result_id=None,
                rule_evaluation_id=None,
            )

        open_logs = storage.list_observation_logs(status="open")
        active_candidates = storage.list_event_candidates(status="active")
        aggregated_candidates = storage.list_event_candidates(status="aggregated")
        upload_summary = storage.upload_queue_summary()
        if len(open_logs) != 1:
            raise SystemExit(f"expected one open observation log, got {len(open_logs)}")
        if int(open_logs[0]["sample_count"]) != 2:
            raise SystemExit(f"expected merged sample_count=2, got {open_logs[0]['sample_count']}")
        if event_agent.events:
            raise SystemExit(f"life observation should not emit formal events: {event_agent.events}")
        if active_candidates:
            raise SystemExit(f"life observation candidates should be hidden from active alerts: {active_candidates}")
        if aggregated_candidates:
            raise SystemExit(f"life observations must not create per-sample candidates: {aggregated_candidates}")
        if upload_summary["pending"] != 0:
            raise SystemExit(f"life observation should not enqueue uploads: {upload_summary}")

        worker._close_observation_logs(
            camera,
            RuleEvaluation(
                camera_id=int(camera["id"]),
                snapshot_id=int(snapshot["id"]),
                evaluated_at=(start + timedelta(seconds=720)).isoformat(),
                candidates=[],
                state={"person_state": "visible", "motion_state": "moving", "no_motion_seconds": 0},
            ),
        )
        closed_logs = storage.list_observation_logs(status="closed")
        if len(closed_logs) != 1:
            raise SystemExit(f"expected one closed observation log, got {len(closed_logs)}")

        fall_event = storage.create_event(
            event_type="fall_candidate",
            summary="客厅摄像头检测到疑似跌倒",
            level="critical",
            camera_id=int(camera["id"]),
            room="客厅",
            snapshot_id=int(snapshot["id"]),
            payload={
                "evidence": {"schema_version": "gohome-event-evidence-v1"},
                "evaluation": {"state": {"fall_target": {"track_id": "c1-p1"}}},
            },
        )
        unrelated_event = storage.create_event(
            event_type="fall_candidate",
            summary="旁人轨迹的独立事件",
            level="critical",
            camera_id=int(camera["id"]),
            room="客厅",
            snapshot_id=int(snapshot["id"]),
            payload={"evaluation": {"state": {"fall_target": {"track_id": "c1-bystander"}}}},
        )
        unresolved_evaluation = RuleEvaluation(
            camera_id=int(camera["id"]),
            snapshot_id=int(snapshot["id"]),
            evaluated_at=(start + timedelta(seconds=780)).isoformat(),
            candidates=[],
            state={"person_state": "visible", "motion_state": "moving", "fall_stage": "candidate_cleared"},
        )
        worker._resolve_recovered_fall_incident(camera, unresolved_evaluation)
        if storage.get_event(int(fall_event["id"]))["payload"].get("resolution"):
            raise SystemExit("candidate disappearance must not resolve a fall incident")
        weak_recovery = RuleEvaluation(
            camera_id=int(camera["id"]),
            snapshot_id=int(snapshot["id"]),
            evaluated_at=(start + timedelta(seconds=780)).isoformat(),
            candidates=[],
            state={
                "fall_stage": "candidate_cleared",
                "fall_recovery": {
                    "confirmed": False,
                    "posture": "standing",
                    "confidence": 0.44,
                    "track_id": "c1-p1",
                },
            },
        )
        worker._resolve_recovered_fall_incident(camera, weak_recovery)
        if storage.get_event(int(fall_event["id"]))["payload"].get("resolution"):
            raise SystemExit("unconfirmed recovery evidence must not resolve a fall incident")
        recovered_evaluation = RuleEvaluation(
            camera_id=int(camera["id"]),
            snapshot_id=int(snapshot["id"]),
            evaluated_at=(start + timedelta(seconds=781)).isoformat(),
            candidates=[],
            state={
                "fall_stage": "recovered",
                "fall_recovery": {
                    "schema_version": "gohome-physical-recovery-v1",
                    "confirmed": True,
                    "reason": "same_track_stable_upright",
                    "posture": "standing",
                    "confidence": 0.82,
                    "track_id": "c1-p1",
                    "bbox": [100, 20, 190, 250],
                    "sample_count": 2,
                    "required_samples": 2,
                    "identity_match": "same_track",
                },
            },
        )
        worker._resolve_recovered_fall_incident(camera, recovered_evaluation)
        resolved_fall = storage.get_event(int(fall_event["id"]))
        recovery_jobs = storage.list_upload_jobs(job_type="event_state_upload", limit=10)
        if resolved_fall["payload"].get("resolution") != "person_upright_again" or len(recovery_jobs) != 1:
            raise SystemExit(f"credible upright pose must enqueue one recovery upload: event={resolved_fall} jobs={recovery_jobs}")
        if storage.get_event(int(unrelated_event["id"]))["payload"].get("resolution"):
            raise SystemExit("same-camera recovery must not resolve an unrelated person's event")
        worker._resolve_recovered_fall_incident(camera, recovered_evaluation)
        if len(storage.list_upload_jobs(job_type="event_state_upload", limit=10)) != 1:
            raise SystemExit("repeated recovery frames must remain idempotent")

        print(
            json.dumps(
                {
                    "ok": True,
                    "open_logs_after_recovery": len(storage.list_observation_logs(status="open")),
                    "closed_logs": len(closed_logs),
                    "aggregated_candidates": 0,
                    "formal_events": len(event_agent.events),
                    "upload_pending": upload_summary["pending"],
                    "fall_recovery": resolved_fall["payload"].get("resolution"),
                    "recovery_jobs": len(recovery_jobs),
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
