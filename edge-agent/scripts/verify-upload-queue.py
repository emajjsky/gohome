from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.storage import Storage
from app.event_agent import EventAgent


class SilentNotifier:
    def send(self, **_: object) -> None:
        return None


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
        transition_snapshot = storage.create_snapshot(
            camera_id=int(camera["id"]),
            image_path="camera_1/transition.jpg",
            width=1280,
            height=720,
            brightness=119.0,
            motion_score=0.12,
            tags=["person_detected", "pose_detected"],
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
                        "selection_policy": "role-aware-pose-transition-v2",
                        "snapshots": [
                            {
                                "snapshot_id": before_snapshot["id"],
                                "snapshot_path": before_snapshot["image_path"],
                                "observed_at": before_snapshot["captured_at"],
                                "postures": ["standing"],
                                "role": "before",
                            },
                            {
                                "snapshot_id": transition_snapshot["id"],
                                "snapshot_path": transition_snapshot["image_path"],
                                "observed_at": transition_snapshot["captured_at"],
                                "postures": ["bending"],
                                "role": "transition",
                            },
                            {
                                "snapshot_id": snapshot["id"],
                                "snapshot_path": snapshot["image_path"],
                                "observed_at": snapshot["captured_at"],
                                "postures": ["lying"],
                                "role": "current",
                            },
                        ]
                    },
                }
            },
        )
        jobs = storage.enqueue_event_upload_jobs(event)
        summary = storage.upload_queue_summary()
        if len(jobs) != 4:
            raise SystemExit(f"expected 4 upload jobs, got {len(jobs)}")
        job_types = sorted(job["job_type"] for job in jobs)
        if job_types != ["event_upload", "media_upload", "media_upload", "media_upload"]:
            raise SystemExit(f"unexpected job types: {job_types}")
        media_jobs = [job for job in jobs if job["job_type"] == "media_upload"]
        purposes = sorted(job["payload"].get("purpose") for job in media_jobs)
        roles = sorted(job["payload"].get("evidence_frame_role") for job in media_jobs)
        if purposes != ["event_evidence", "event_evidence_keyframe", "event_evidence_keyframe"] or roles != ["before", "current", "transition"]:
            raise SystemExit(f"event evidence sequence missing: purposes={purposes} roles={roles}")
        if any(job["payload"].get("evidence_selection_policy") != "role-aware-pose-transition-v2" for job in media_jobs):
            raise SystemExit("all event evidence uploads must preserve the selection policy")
        current_job = next(job for job in media_jobs if job["payload"].get("evidence_frame_role") == "current")
        if current_job["payload"].get("captured_at") != snapshot["captured_at"]:
            raise SystemExit("current evidence must retain frame capture time instead of upload time")
        if summary["pending"] != 4 or summary["pending_critical"] != 4:
            raise SystemExit(f"unexpected upload summary: {summary}")
        deduped = storage.enqueue_event_upload_jobs(event)
        if [job["id"] for job in deduped] != [job["id"] for job in jobs]:
            raise SystemExit("upload job idempotency check failed")

        deferred_event = EventAgent(storage, SilentNotifier(), throttle_seconds=30).emit(
            event_type="fall_candidate",
            summary="客厅摄像头 检测到快速倒地过程，已进入云端复核。",
            level="critical",
            camera=camera,
            snapshot_id=int(snapshot["id"]),
            payload={
                "evidence": {
                    "schema_version": "gohome-event-evidence-v1",
                    "temporal_evidence_bundle": {
                        "schema_version": "temporal-evidence-bundle-v1",
                        "selection_policy": "role-aware-pose-transition-v2",
                        "track_id": "person-settle-1",
                        "snapshots": [
                            {
                                "snapshot_id": before_snapshot["id"],
                                "snapshot_path": before_snapshot["image_path"],
                                "observed_at": before_snapshot["captured_at"],
                                "postures": ["standing"],
                                "role": "before",
                            },
                            {
                                "snapshot_id": transition_snapshot["id"],
                                "snapshot_path": transition_snapshot["image_path"],
                                "observed_at": transition_snapshot["captured_at"],
                                "postures": ["bending"],
                                "role": "transition",
                            },
                            {
                                "snapshot_id": snapshot["id"],
                                "snapshot_path": snapshot["image_path"],
                                "observed_at": snapshot["captured_at"],
                                "postures": ["lying"],
                                "role": "current",
                            },
                        ],
                    },
                },
            },
            force=True,
        )
        if deferred_event is None:
            raise SystemExit("fall event was not created")
        finalize_jobs = storage.upload_jobs_for_event(
            event_id=int(deferred_event["id"]),
            job_type="event_evidence_finalize",
        )
        if len(finalize_jobs) != 1:
            raise SystemExit(f"fall event must persist one evidence finalizer before uploads: {finalize_jobs}")
        if storage.upload_jobs_for_event(event_id=int(deferred_event["id"]), job_type="event_upload"):
            raise SystemExit("fall event must not expose its upload before settled evidence finalization")

        settled_snapshot = storage.create_snapshot(
            camera_id=int(camera["id"]),
            image_path="camera_1/settled.jpg",
            width=1280,
            height=720,
            brightness=121.0,
            motion_score=0.01,
            tags=["person_detected", "pose_detected", "pose_low_body"],
            person_count=1,
            analysis={
                "pose_factor_graph": {
                    "tracks": [
                        {
                            "track_id": "person-settle-1",
                            "posture": "lying",
                            "posture_confidence": 0.88,
                        }
                    ]
                }
            },
        )
        settled_at = (
            datetime.fromisoformat(str(deferred_event["occurred_at"]).replace("Z", "+00:00"))
            + timedelta(seconds=1)
        ).isoformat()
        with storage.connect() as conn:
            conn.execute(
                "UPDATE snapshots SET captured_at = ? WHERE id = ?",
                (settled_at, int(settled_snapshot["id"])),
            )
        finalized = storage.finalize_event_evidence(
            int(deferred_event["id"]),
            settle_seconds=0.3,
            max_wait_seconds=2.0,
        )
        finalization = finalized.get("payload", {}).get("evidence_finalization") or {}
        finalized_bundle = finalized.get("payload", {}).get("evidence", {}).get("temporal_evidence_bundle") or {}
        finalized_frames = finalized_bundle.get("snapshots") or []
        if finalization.get("reason") != "same_track_settled_lying":
            raise SystemExit(f"settled evidence finalization reason mismatch: {finalization}")
        if int(finalized.get("snapshot_id") or 0) != int(settled_snapshot["id"]):
            raise SystemExit("settled same-track frame did not replace the premature current frame")
        if [item.get("role") for item in finalized_frames] != ["before", "transition", "current"]:
            raise SystemExit(f"finalized evidence roles are invalid: {finalized_frames}")
        if finalized_bundle.get("selection_policy") != "role-aware-post-settle-v3":
            raise SystemExit(f"settled evidence policy is missing: {finalized_bundle}")
        deferred_jobs = storage.enqueue_event_upload_jobs(finalized)
        deferred_media = [item for item in deferred_jobs if item.get("job_type") == "media_upload"]
        if len(deferred_media) != 3:
            raise SystemExit(f"settled finalization must still queue exactly three evidence frames: {deferred_jobs}")
        repeated_deferred_jobs = storage.enqueue_event_upload_jobs(finalized)
        if [item["id"] for item in repeated_deferred_jobs] != [item["id"] for item in deferred_jobs]:
            raise SystemExit("settled evidence upload jobs are not idempotent")

        media_only_event = storage.create_event(
            event_type="legacy_local_event",
            summary="Legacy event with media but no event upload",
            level="info",
            camera_id=int(camera["id"]),
            room="客厅",
        )
        media_only_job = storage.enqueue_upload_job(
            job_type="media_upload",
            object_type="event_media",
            idempotency_key=f"legacy-media-only:{media_only_event['id']}",
            event_id=int(media_only_event["id"]),
            camera_id=int(camera["id"]),
            payload={"snapshot_path": "camera_1/legacy.jpg"},
        )
        storage.complete_upload_job(
            int(media_only_job["id"]),
            {"uploaded": True, "asset": {"id": 99}},
        )
        reconciled_media_only_event = storage.get_event(int(media_only_event["id"]))
        if reconciled_media_only_event is None or reconciled_media_only_event.get("cloud_sync_status") != "local_only":
            raise SystemExit(f"media-only legacy event remained pending: {reconciled_media_only_event}")
        print(
            json.dumps(
                {
                    "ok": True,
                    "job_types": job_types,
                    "summary": summary,
                    "event_id": event["id"],
                    "snapshot_id": snapshot["id"],
                    "settled_event_id": deferred_event["id"],
                    "settled_snapshot_id": settled_snapshot["id"],
                    "media_only_event_status": reconciled_media_only_event["cloud_sync_status"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
