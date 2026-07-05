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
        event = storage.create_event(
            event_type="fall_candidate",
            summary="客厅摄像头 连续检测到疑似跌倒姿态。",
            level="critical",
            camera_id=int(camera["id"]),
            room="客厅",
            snapshot_id=int(snapshot["id"]),
            payload={"evidence": {"schema_version": "gohome-event-evidence-v1"}},
        )
        storage.enqueue_event_upload_jobs(event)

        settings = SimpleNamespace(
            app_server_base_url="http://app-server.test",
            device_api_token="dev-token",
            snapshot_dir=snapshot_dir,
            upload_worker_enabled=True,
            upload_worker_batch_size=4,
            upload_worker_interval_seconds=5,
            upload_request_timeout_seconds=2,
        )
        agent = UploadAgent(
            storage=storage,
            settings=settings,
            device_id_resolver=lambda: "edge-test",
            token_resolver=lambda: "",
        )
        calls: list[dict] = []

        def fake_request(method: str, path: str, **kwargs: object) -> dict:
            calls.append({"method": method, "path": path, **kwargs})
            if path.startswith("/api/v1/device/media-assets/upload"):
                return {"asset": {"id": 77, "storage_url": "https://media.example/fall.jpg"}}
            if path == "/api/v1/device/events":
                body = kwargs.get("json_body")
                if not isinstance(body, dict):
                    raise AssertionError("event upload must send json_body")
                media_result = ((body.get("payload") or {}).get("media_upload_result") or {})
                if not media_result.get("asset"):
                    raise AssertionError("event upload must include completed media result")
                return {"event": {"id": 8801, "type": body.get("event_type")}, "media_asset": media_result["asset"]}
            raise AssertionError(f"unexpected upload path: {path}")

        agent._request_json = fake_request  # type: ignore[method-assign]
        result = agent.process_once(max_jobs=2)
        summary = storage.upload_queue_summary()
        completed = storage.list_upload_jobs(status="completed", limit=10)
        if result["completed"] != 2 or summary["completed"] != 2:
            raise SystemExit(f"upload agent did not complete both jobs: result={result} summary={summary}")
        if [call["method"] for call in calls] != ["POST", "POST"]:
            raise SystemExit(f"unexpected upload calls: {calls}")
        if completed[0]["payload"].get("upload_result") is None:
            raise SystemExit("completed jobs must retain upload_result")

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
