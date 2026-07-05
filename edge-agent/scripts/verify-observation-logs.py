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
        if len(aggregated_candidates) != 2:
            raise SystemExit(f"expected two aggregated candidates, got {len(aggregated_candidates)}")
        if upload_summary["pending"] != 0:
            raise SystemExit(f"life observation should not enqueue uploads: {upload_summary}")

        worker._close_recovered_observations(
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

        print(
            json.dumps(
                {
                    "ok": True,
                    "open_logs_after_recovery": len(storage.list_observation_logs(status="open")),
                    "closed_logs": len(closed_logs),
                    "aggregated_candidates": len(aggregated_candidates),
                    "formal_events": len(event_agent.events),
                    "upload_pending": upload_summary["pending"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
