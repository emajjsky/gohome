from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.storage import Storage


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Storage(Path(tmpdir) / "agent.db")
        storage.init_schema()
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
            image_path="camera_1/test.jpg",
            width=1280,
            height=720,
            brightness=120.0,
            motion_score=0.02,
            tags=["person_detected", "fall_candidate"],
            person_count=1,
            analysis={
                "pipeline_version": "vision-pipeline-v1",
                "person_count": 1,
                "fall_candidate": True,
                "algorithm_results": {"fall": {"status": "candidate"}},
            },
        )
        before_snapshot = storage.create_snapshot(
            camera_id=int(camera["id"]),
            image_path="camera_1/before.jpg",
            width=1280,
            height=720,
            brightness=118.0,
            motion_score=0.08,
            tags=["person_detected"],
            person_count=1,
            analysis={"person_count": 1, "fall_candidate": False},
        )
        event = storage.create_event(
            event_type="fall_candidate",
            summary="客厅摄像头 检测到疑似跌倒姿态。",
            level="critical",
            camera_id=int(camera["id"]),
            room="客厅",
            snapshot_id=int(snapshot["id"]),
            payload={
                "evidence": {
                    "schema_version": "gohome-event-evidence-v1",
                    "temporal_evidence_bundle": {
                        "snapshots": [
                            {
                                "snapshot_id": before_snapshot["id"],
                                "snapshot_path": before_snapshot["image_path"],
                                "observed_at": before_snapshot["captured_at"],
                                "postures": ["standing"],
                            },
                            {
                                "snapshot_id": snapshot["id"],
                                "snapshot_path": snapshot["image_path"],
                                "observed_at": snapshot["captured_at"],
                                "postures": ["lying"],
                            },
                        ]
                    },
                }
            },
        )
        jobs = storage.enqueue_event_upload_jobs(event)
        summary = storage.upload_queue_summary()
        if len(jobs) != 3:
            raise SystemExit(f"expected 3 upload jobs, got {len(jobs)}")
        job_types = sorted(job["job_type"] for job in jobs)
        if job_types != ["event_upload", "media_upload", "media_upload"]:
            raise SystemExit(f"unexpected job types: {job_types}")
        media_jobs = [job for job in jobs if job["job_type"] == "media_upload"]
        purposes = sorted(job["payload"].get("purpose") for job in media_jobs)
        roles = sorted(job["payload"].get("evidence_frame_role") for job in media_jobs)
        if purposes != ["event_evidence", "event_evidence_keyframe"] or roles != ["before", "current"]:
            raise SystemExit(f"event evidence sequence missing: purposes={purposes} roles={roles}")
        if summary["pending"] != 3 or summary["pending_critical"] != 3:
            raise SystemExit(f"unexpected upload summary: {summary}")
        deduped = storage.enqueue_event_upload_jobs(event)
        if [job["id"] for job in deduped] != [job["id"] for job in jobs]:
            raise SystemExit("upload job idempotency check failed")
        print(
            json.dumps(
                {
                    "ok": True,
                    "job_types": job_types,
                    "summary": summary,
                    "event_id": event["id"],
                    "snapshot_id": snapshot["id"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
