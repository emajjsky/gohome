from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.storage import Storage
from app.upload_agent import UploadAgent


def main() -> None:
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        storage = Storage(root / "agent.db")
        storage.init_schema()
        camera = storage.create_camera({
            "name": "客厅摄像头",
            "room": "客厅",
            "stream_url": "demo:activity",
            "enabled": True,
        })
        camera_id = int(camera["id"])

        first = storage.advance_activity_export(
            camera_id=camera_id,
            room="客厅",
            observed_at="2026-07-28T08:00:00+08:00",
            visible=True,
            person_count=1,
            postures=["standing"],
            confidence=0.91,
            flush=False,
            reason="person_visible",
            max_gap_seconds=1200,
        )
        assert first == []

        changed = storage.advance_activity_export(
            camera_id=camera_id,
            room="客厅",
            observed_at="2026-07-28T08:05:00+08:00",
            visible=True,
            person_count=1,
            postures=["sitting"],
            confidence=0.88,
            flush=True,
            reason="posture_changed",
            max_gap_seconds=1200,
        )
        assert len(changed) == 1
        interval = changed[0]["payload"]
        assert interval["postures"] == ["standing"]
        assert interval["started_at"] == "2026-07-28T00:00:00+00:00"
        assert interval["ended_at"] == "2026-07-28T00:05:00+00:00"

        storage.advance_activity_export(
            camera_id=camera_id,
            room="客厅",
            observed_at="2026-07-28T08:40:00+08:00",
            visible=True,
            person_count=1,
            postures=["standing"],
            confidence=0.90,
            flush=True,
            reason="activity_heartbeat",
            max_gap_seconds=1200,
        )
        closed = storage.advance_activity_export(
            camera_id=camera_id,
            room="客厅",
            observed_at="2026-07-28T08:45:00+08:00",
            visible=False,
            person_count=0,
            postures=[],
            confidence=None,
            flush=True,
            reason="person_not_visible",
            max_gap_seconds=1200,
        )
        assert len(closed) == 1
        assert closed[0]["payload"]["started_at"] == "2026-07-28T00:40:00+00:00"
        assert closed[0]["payload"]["ended_at"] == "2026-07-28T00:45:00+00:00"

        storage.advance_activity_export(
            camera_id=camera_id,
            room="客厅",
            observed_at="2026-07-28T09:00:00+08:00",
            visible=True,
            person_count=1,
            postures=["standing"],
            confidence=0.93,
            flush=False,
            reason="person_visible",
            max_gap_seconds=1200,
        )
        storage.advance_activity_export(
            camera_id=camera_id,
            room="客厅",
            observed_at="2026-07-28T09:03:00+08:00",
            visible=True,
            person_count=1,
            postures=["standing"],
            confidence=0.94,
            flush=False,
            reason="person_visible",
            max_gap_seconds=1200,
        )
        runtime_close = storage.close_camera_runtime_state(camera_id, reason="camera_offline")
        assert runtime_close["activity_intervals_enqueued"] == 1

        jobs = storage.list_upload_jobs(limit=20, job_type="activity_interval_upload")
        assert len(jobs) == 3
        runtime_job = next(job for job in jobs if job["payload"]["metadata"]["close_reason"] == "camera_offline")
        assert runtime_job["payload"]["ended_at"] == "2026-07-28T01:03:00+00:00"
        assert all(job["snapshot_id"] is None for job in jobs)
        assert all(job["payload"]["metadata"]["contains_media"] is False for job in jobs)

        requests: list[tuple[str, str, dict]] = []
        settings = SimpleNamespace(
            upload_worker_enabled=True,
            upload_worker_batch_size=4,
            upload_worker_interval_seconds=1,
            upload_request_timeout_seconds=2,
            app_server_base_url="https://example.invalid",
            device_token="token",
            snapshot_dir=root / "snapshots",
        )
        agent = UploadAgent(
            storage=storage,
            settings=settings,
            device_id_resolver=lambda: "edge-test",
            token_resolver=lambda: "token",
            remote_camera_id_resolver=lambda value: 42 if value == camera_id else value,
        )

        def unauthorized_request(_method: str, _path: str, **_kwargs):
            raise RuntimeError("POST activity intervals failed: HTTP 401 revoked device token")

        agent._request_json = unauthorized_request  # type: ignore[method-assign]
        unauthorized = agent.process_once(max_jobs=1)
        assert unauthorized == {"ok": False, "processed": 1, "completed": 0, "failed": 1}
        failed_jobs = storage.list_upload_jobs(status="failed", limit=10, job_type="activity_interval_upload")
        assert len(failed_jobs) == 1
        assert failed_jobs[0]["next_attempt_at"]
        assert failed_jobs[0]["payload"]["source_interval_id"]
        assert "401" in failed_jobs[0]["last_error"]

        def request(method: str, path: str, **kwargs):
            requests.append((method, path, kwargs["json_body"]))
            return {"ok": True, "accepted": 1, "inserted": 1}

        agent._request_json = request  # type: ignore[method-assign]
        result = agent.process_once(max_jobs=4)
        assert result["completed"] == 2
        assert len(requests) == 2
        assert all(item[1] == "/api/v1/device/activity-intervals" for item in requests)
        assert all(item[2]["device_id"] == "edge-test" for item in requests)
        assert all(item[2]["intervals"][0]["camera_id"] == "42" for item in requests)

        print({
            "ok": True,
            "interval_jobs": len(jobs),
            "media_jobs": 0,
            "offline_gap_not_bridged": True,
            "unauthorized_retry_retained": True,
            "remote_camera_id": requests[0][2]["intervals"][0]["camera_id"],
        })


if __name__ == "__main__":
    main()
