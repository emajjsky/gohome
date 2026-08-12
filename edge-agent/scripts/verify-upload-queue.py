from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.storage import Storage
from app.event_agent import EventAgent
import app.rule_engine as rule_engine_module
from app.rule_engine import RuleEngine


def production_rotation_analysis(posture: str, bbox: list[float], motion_score: float, fall_score: float) -> dict:
    target = {
        "bbox": list(bbox),
        "confidence": 0.82,
        "track_id": "c32-p1",
        "posture": posture,
        "posture_confidence": 0.82,
        "fall_score": fall_score,
        "fall_evidence_eligible": True,
        "normal_lying_zone": False,
        "posture_factors": {"body_aspect": (bbox[2] - bbox[0]) / (bbox[3] - bbox[1])},
    }
    return {
        "pipeline_version": "production-regression",
        "image_width": 640,
        "image_height": 360,
        "brightness": 110.0,
        "contrast": 24.0,
        "black_screen": False,
        "motion_detected": motion_score >= 0.015,
        "motion_score": motion_score,
        "person_count": 1,
        "people": [{**target, "source": "hailo", "fall_candidate": posture == "lying"}],
        "pose_count": 1,
        "poses": [{**target, "source": "hailo_pose"}],
        "pet_count": 0,
        "pets": [],
        "fall_candidate": posture == "lying",
        "fall_score": fall_score,
        "pose_fall_candidate": posture == "lying",
        "pose_fall_score": fall_score,
        "algorithm_results": {"fall": {"status": "candidate" if posture == "lying" else "clear"}},
        "tags": ["person_detected", "pose_detected"],
    }


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
        evidence_snapshot = storage.create_snapshot(
            camera_id=int(camera["id"]),
            image_path="camera_1/evidence.jpg",
            width=1280,
            height=720,
            brightness=119.5,
            motion_score=0.15,
            tags=["person_detected", "pose_detected", "pose_low_body"],
            person_count=1,
            analysis={"person_count": 1, "fall_candidate": True},
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
                        "selection_policy": "role-aware-four-frame-v3",
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
                                "snapshot_id": evidence_snapshot["id"],
                                "snapshot_path": evidence_snapshot["image_path"],
                                "observed_at": evidence_snapshot["captured_at"],
                                "postures": ["low_body"],
                                "role": "evidence",
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
        if len(jobs) != 5:
            raise SystemExit(f"expected 5 upload jobs, got {len(jobs)}")
        job_types = sorted(job["job_type"] for job in jobs)
        if job_types != ["event_upload", "media_upload", "media_upload", "media_upload", "media_upload"]:
            raise SystemExit(f"unexpected job types: {job_types}")
        media_jobs = [job for job in jobs if job["job_type"] == "media_upload"]
        purposes = sorted(job["payload"].get("purpose") for job in media_jobs)
        roles = sorted(job["payload"].get("evidence_frame_role") for job in media_jobs)
        if purposes != ["event_evidence", "event_evidence_keyframe", "event_evidence_keyframe", "event_evidence_keyframe"] or roles != ["before", "current", "evidence", "transition"]:
            raise SystemExit(f"event evidence sequence missing: purposes={purposes} roles={roles}")
        if any(job["payload"].get("evidence_selection_policy") != "role-aware-four-frame-v3" for job in media_jobs):
            raise SystemExit("all event evidence uploads must preserve the selection policy")
        current_job = next(job for job in media_jobs if job["payload"].get("evidence_frame_role") == "current")
        if current_job["payload"].get("captured_at") != snapshot["captured_at"]:
            raise SystemExit("current evidence must retain frame capture time instead of upload time")
        if summary["pending"] != 5 or summary["pending_critical"] != 5:
            raise SystemExit(f"unexpected upload summary: {summary}")
        deduped = storage.enqueue_event_upload_jobs(event)
        if [job["id"] for job in deduped] != [job["id"] for job in jobs]:
            raise SystemExit("upload job idempotency check failed")

        deferred_event = EventAgent(storage, throttle_seconds=30).emit(
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
                        "selection_policy": "role-aware-four-frame-v3",
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
                                "snapshot_id": evidence_snapshot["id"],
                                "snapshot_path": evidence_snapshot["image_path"],
                                "observed_at": evidence_snapshot["captured_at"],
                                "postures": ["low_body"],
                                "role": "evidence",
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
        if [item.get("role") for item in finalized_frames] != ["before", "transition", "evidence", "current"]:
            raise SystemExit(f"finalized evidence roles are invalid: {finalized_frames}")
        if finalized_bundle.get("selection_policy") != "role-aware-post-settle-v4":
            raise SystemExit(f"settled evidence policy is missing: {finalized_bundle}")
        deferred_jobs = storage.enqueue_event_upload_jobs(finalized)
        deferred_media = [item for item in deferred_jobs if item.get("job_type") == "media_upload"]
        if len(deferred_media) != 4:
            raise SystemExit(f"settled finalization must queue exactly four evidence frames: {deferred_jobs}")
        repeated_deferred_jobs = storage.enqueue_event_upload_jobs(finalized)
        if [item["id"] for item in repeated_deferred_jobs] != [item["id"] for item in deferred_jobs]:
            raise SystemExit("settled evidence upload jobs are not idempotent")

        production_engine = RuleEngine()
        production_rules = {
            "black_screen_enabled": False,
            "person_detection_enabled": True,
            "fall_detection_enabled": True,
            "fall_score_threshold": 0.50,
            "fall_confirm_frames": 2,
            "fall_confirm_seconds": 4,
            "fall_recover_frames": 2,
            "activity_detection_enabled": True,
            "no_motion_enabled": False,
            "no_person_seconds": 300,
        }
        production_start = datetime(2026, 8, 12, 14, 10, 23, tzinfo=timezone.utc)
        original_clock = rule_engine_module.utc_now
        try:
            current_time = [production_start]
            rule_engine_module.utc_now = lambda: current_time[0]
            production_engine.evaluate_snapshot(
                camera,
                {"id": before_snapshot["id"]},
                production_rotation_analysis("standing", [468.4, 72.9, 590.2, 360.0], 0.0099, 0.08),
                production_rules,
            )
            current_time[0] = production_start + timedelta(seconds=2.6)
            production_engine.evaluate_snapshot(
                camera,
                {"id": transition_snapshot["id"]},
                production_rotation_analysis("sitting", [383.8, 166.4, 453.2, 278.7], 0.0245, 0.18),
                production_rules,
            )
            current_time[0] = production_start + timedelta(seconds=3.2)
            production_review = production_engine.evaluate_snapshot(
                camera,
                {"id": evidence_snapshot["id"]},
                production_rotation_analysis("lying", [356.9, 185.7, 438.9, 260.2], 0.0039, 0.82),
                production_rules,
            )
        finally:
            rule_engine_module.utc_now = original_clock
        if len(production_review.candidates) != 1:
            raise SystemExit(f"production rotation did not create one cloud-review candidate: {production_review.state}")
        production_candidate = production_review.candidates[0]
        production_event = EventAgent(storage, throttle_seconds=30).emit(
            event_type=production_candidate.event_type,
            summary=production_candidate.summary,
            level=production_candidate.level,
            camera=camera,
            snapshot_id=int(snapshot["id"]),
            payload={
                **(production_candidate.payload or {}),
                "evidence": {
                    **((production_candidate.payload or {}).get("evidence") or {}),
                    "temporal_evidence_bundle": {
                        "schema_version": "temporal-evidence-bundle-v1",
                        "selection_policy": "role-aware-four-frame-v3",
                        "track_id": "c32-p1",
                        "snapshots": [
                            {"snapshot_id": before_snapshot["id"], "snapshot_path": before_snapshot["image_path"], "observed_at": before_snapshot["captured_at"], "postures": ["standing"], "role": "before"},
                            {"snapshot_id": transition_snapshot["id"], "snapshot_path": transition_snapshot["image_path"], "observed_at": transition_snapshot["captured_at"], "postures": ["sitting"], "role": "transition"},
                            {"snapshot_id": evidence_snapshot["id"], "snapshot_path": evidence_snapshot["image_path"], "observed_at": evidence_snapshot["captured_at"], "postures": ["lying"], "role": "evidence"},
                            {"snapshot_id": snapshot["id"], "snapshot_path": snapshot["image_path"], "observed_at": snapshot["captured_at"], "postures": ["lying"], "role": "current"},
                        ],
                    },
                },
            },
            force=True,
        )
        if production_event is None:
            raise SystemExit("production cloud-review candidate did not persist one event")
        production_finalized = storage.finalize_event_evidence(
            int(production_event["id"]),
            settle_seconds=0.3,
            max_wait_seconds=0.3,
        )
        production_jobs = storage.enqueue_event_upload_jobs(production_finalized)
        production_media = [item for item in production_jobs if item.get("job_type") == "media_upload"]
        production_roles = [item.get("payload", {}).get("evidence_frame_role") for item in production_media]
        production_snapshot_ids = [int(item.get("snapshot_id") or 0) for item in production_media]
        if sorted(production_roles) != ["before", "current", "evidence", "transition"]:
            raise SystemExit(f"production cloud-review event lost evidence roles: {production_roles}")
        if len(production_snapshot_ids) != 4 or len(set(production_snapshot_ids)) != 4:
            raise SystemExit(f"production cloud-review event must upload four distinct frames: {production_snapshot_ids}")
        if len(storage.upload_jobs_for_event(event_id=int(production_event["id"]), job_type="event_upload")) != 1:
            raise SystemExit("production cloud-review event must queue exactly one event upload")

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
                    "production_event_id": production_event["id"],
                    "production_evidence_roles": production_roles,
                    "media_only_event_status": reconciled_media_only_event["cloud_sync_status"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
