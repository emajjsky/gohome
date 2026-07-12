from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.storage import Storage
from app.upload_agent import UploadAgent


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        snapshot_dir = root / "snapshots"
        snapshot_path = snapshot_dir / "camera_1" / "fall.jpg"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_bytes(b"\xff\xd8gohome-test-jpeg\xff\xd9")
        before_path = snapshot_dir / "camera_1" / "before.jpg"
        before_path.write_bytes(b"\xff\xd8gohome-before-jpeg\xff\xd9")

        storage = Storage(root / "agent.db")
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
            image_path="camera_1/fall.jpg",
            width=640,
            height=360,
            brightness=120.0,
            motion_score=0.02,
            tags=["fall_candidate"],
            person_count=1,
            analysis={"fall_candidate": True},
        )
        before_snapshot = storage.create_snapshot(
            camera_id=int(camera["id"]),
            image_path="camera_1/before.jpg",
            width=640,
            height=360,
            brightness=118.0,
            motion_score=0.08,
            tags=["person_detected"],
            person_count=1,
            analysis={"fall_candidate": False},
        )
        event = storage.create_event(
            event_type="fall_candidate",
            summary="客厅摄像头 连续检测到疑似跌倒姿态。",
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
        storage.enqueue_event_upload_jobs(event)

        settings = SimpleNamespace(
            app_server_base_url="http://app-server.test",
            device_api_token="dev-token",
            snapshot_dir=snapshot_dir,
            upload_worker_enabled=True,
            upload_worker_batch_size=6,
            upload_worker_interval_seconds=5,
            upload_request_timeout_seconds=2,
        )
        agent = UploadAgent(
            storage=storage,
            settings=settings,
            device_id_resolver=lambda: "edge-test",
            token_resolver=lambda: "",
            remote_camera_id_resolver=lambda camera_id: camera_id + 100,
        )
        calls: list[dict] = []

        def fake_request(method: str, path: str, **kwargs: object) -> dict:
            calls.append({"method": method, "path": path, **kwargs})
            if path.startswith("/api/v1/device/media-assets/upload"):
                asset_id = 70 + len([call for call in calls if str(call["path"]).startswith("/api/v1/device/media-assets/upload")])
                return {"asset": {"id": asset_id, "storage_url": f"https://media.example/{asset_id}.jpg"}}
            if path == "/api/v1/device/events":
                body = kwargs.get("json_body")
                if not isinstance(body, dict):
                    raise AssertionError("event upload must send json_body")
                media_result = ((body.get("payload") or {}).get("media_upload_result") or {})
                if not media_result.get("asset"):
                    raise AssertionError("event upload must include completed media result")
                evidence_assets = ((body.get("payload") or {}).get("evidence_media_assets") or [])
                if len(evidence_assets) != 2 or {item.get("role") for item in evidence_assets} != {"before", "current"}:
                    raise AssertionError(f"event upload must include ordered evidence assets: {evidence_assets}")
                return {"event": {"id": 8801, "type": body.get("event_type")}, "media_asset": media_result["asset"]}
            if path.startswith("/api/v1/device/vision-verifications?"):
                return {
                    "ok": True,
                    "configured": True,
                    "records": [{"event_id": 8801, "verification": {"status": "confirmed"}}],
                }
            if path.startswith("/api/v1/device/event-log?"):
                return {
                    "ok": True,
                    "records": [{"event_id": 8801, "edge_event_id": str(event["id"]), "incident": {"status": "confirmed"}}],
                }
            if path == f"/api/v1/device/events/{event['id']}/feedback":
                return {"ok": True, "event": {"edge_event_id": str(event["id"]), "resolution": "false_positive"}}
            raise AssertionError(f"unexpected upload path: {path}")

        agent._request_json = fake_request  # type: ignore[method-assign]
        result = agent.process_once(max_jobs=3)
        summary = storage.upload_queue_summary()
        completed = storage.list_upload_jobs(status="completed", limit=10)
        verification_status = agent.vision_verification_status(limit=6)
        event_log_status = agent.event_log_status(limit=20)
        feedback_status = agent.submit_event_feedback(event["id"], resolution="false_positive")
        if result["completed"] != 3 or summary["completed"] != 3:
            raise SystemExit(f"upload agent did not complete all jobs: result={result} summary={summary}")
        if [call["method"] for call in calls] != ["POST", "POST", "POST", "GET", "GET", "POST"]:
            raise SystemExit(f"unexpected upload calls: {calls}")
        media_paths = [str(call["path"]) for call in calls[:2]]
        if not all("camera_id=101" in path and "local_camera_id=1" in path for path in media_paths):
            raise SystemExit(f"media upload did not map local camera id: {media_paths}")
        if not any("evidence_frame_role=before" in path for path in media_paths):
            raise SystemExit(f"keyframe role missing from upload path: {media_paths}")
        event_body = calls[2].get("json_body") or {}
        if event_body.get("camera_id") != 101:
            raise SystemExit(f"event upload did not use remote camera id: {event_body}")
        if completed[0]["payload"].get("upload_result") is None:
            raise SystemExit("completed jobs must retain upload_result")
        if verification_status.get("records", [{}])[0].get("verification", {}).get("status") != "confirmed":
            raise SystemExit(f"cloud verification status was not returned: {verification_status}")
        if event_log_status.get("records", [{}])[0].get("incident", {}).get("status") != "confirmed":
            raise SystemExit(f"cloud event log status was not returned: {event_log_status}")
        if feedback_status.get("event", {}).get("resolution") != "false_positive":
            raise SystemExit(f"event feedback was not returned: {feedback_status}")

        print(
            json.dumps(
                {
                    "ok": True,
                    "processed": result["processed"],
                    "completed": result["completed"],
                    "summary": summary,
                    "paths": [call["path"].split("?", 1)[0] for call in calls],
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
