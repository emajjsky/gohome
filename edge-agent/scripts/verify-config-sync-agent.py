from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config_sync_agent import ConfigSyncAgent
from app.storage import Storage


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        storage = Storage(root / "agent.db")
        storage.init_schema()

        settings = SimpleNamespace(
            app_server_base_url="http://app-server.test",
            device_api_token="dev-token",
            runtime_dir=root / "runtime",
            config_sync_enabled=True,
            config_sync_interval_seconds=10,
            video_privacy_sync_interval_seconds=1,
            config_sync_request_timeout_seconds=2,
            config_sync_test_capture_enabled=False,
        )
        camera_agent = SimpleNamespace(capture_frame=lambda *_args, **_kwargs: {"width": 640, "height": 360})
        monotonic_now = [100.0]
        agent = ConfigSyncAgent(
            storage=storage,
            settings=settings,
            camera_agent=camera_agent,
            device_id_resolver=lambda: "edge-test",
            token_resolver=lambda: "",
            runtime_status_resolver=lambda: {"worker_running": True},
            monotonic_clock=lambda: monotonic_now[0],
        )

        if not agent.wake() or agent.wake():
            raise SystemExit("config sync wake requests must be coalesced for two seconds")
        monotonic_now[0] += 2.0
        if not agent.wake():
            raise SystemExit("config sync wake must become available after the debounce window")
        agent._wake.clear()

        if not agent.observe_video_privacy_mode("person_blur"):
            raise SystemExit("privacy observations must update the shared runtime mode")
        if agent.video_privacy_mode() != "person_blur":
            raise SystemExit("privacy observations must be visible to the management API")
        if agent.observe_video_privacy_mode("invalid"):
            raise SystemExit("invalid privacy observations must preserve the current mode")
        monotonic_now[0] += 2.0
        if not agent.observe_video_privacy_mode("skeleton", wake=True) or not agent._wake.is_set():
            raise SystemExit("changed relay observations must wake durable config sync")
        agent._wake.clear()

        privacy_requests: list[str] = []

        def fake_privacy_request(method: str, path: str, **_kwargs: object) -> dict:
            privacy_requests.append(f"{method} {path}")
            return {"ok": True, "minimum_mode": "person_blur"}

        agent._request_json = fake_privacy_request  # type: ignore[method-assign]
        privacy_result = agent.process_video_privacy_once()
        if not privacy_result["changed"] or agent.video_privacy_mode() != "person_blur":
            raise SystemExit("lightweight privacy sync must update the shared runtime mode")
        if privacy_requests != ["GET /api/v1/device/video-privacy"]:
            raise SystemExit(f"privacy sync used the wrong endpoint: {privacy_requests}")

        config_holder = {
            "payload": {
                "ok": True,
                "device_id": "edge-test",
                "config_version": "camera-config-test-1",
                "cameras": [
                    {
                        "id": 101,
                        "camera_id": 101,
                        "name": "客厅主视",
                        "room": "客厅",
                        "stream_url": "demo:living_room",
                        "enabled": True,
                    }
                ],
            }
        }
        reports: list[dict] = []

        def fake_request(method: str, path: str, **kwargs: object) -> dict:
            if method == "GET" and path == "/api/v1/device/config":
                return config_holder["payload"]
            if method == "POST" and path == "/api/v1/device/sync":
                body = kwargs.get("json_body")
                if not isinstance(body, dict):
                    raise AssertionError("sync report must send json_body")
                reports.append(body)
                return {"ok": True}
            raise AssertionError(f"unexpected request: {method} {path}")

        agent._request_json = fake_request  # type: ignore[method-assign]

        created = agent.process_once()
        cameras = storage.list_cameras(include_secret=True)
        if created["applied"] != 1 or len(cameras) != 1:
            raise SystemExit(f"camera was not created from config: result={created} cameras={cameras}")
        if cameras[0]["stream_url"] != "demo:living_room" or cameras[0]["status"] != "configured":
            raise SystemExit(f"unexpected created camera: {cameras[0]}")
        if reports[-1]["cameras"][0]["sync_status"] != "synced":
            raise SystemExit(f"sync report did not mark camera synced: {reports[-1]}")
        if "presence" not in reports[-1]["cameras"][0]:
            raise SystemExit("sync report must include camera presence status")
        edge_event = storage.create_event(
            event_type="fall_candidate",
            summary="test fall",
            level="critical",
            camera_id=int(cameras[0]["id"]),
        )
        storage.create_snapshot(
            camera_id=int(cameras[0]["id"]),
            image_path="presence-test.jpg",
            width=640,
            height=360,
            brightness=90,
            motion_score=0.02,
            tags=["person"],
            person_count=1,
            analysis={"person_count": 1},
        )
        storage.create_snapshot(
            camera_id=int(cameras[0]["id"]),
            image_path="pet-presence-test.jpg",
            width=640,
            height=360,
            brightness=92,
            motion_score=0.03,
            tags=["pet_detected", "no_person_detected"],
            person_count=0,
            analysis={"person_count": 0, "pet_count": 1, "pet_types": ["cat"]},
        )

        config_holder["payload"] = {
            **config_holder["payload"],
            "config_version": "camera-config-test-2",
            "event_state_commands": [
                {
                    "command_id": "event-state-test-1",
                    "edge_event_id": str(edge_event["id"]),
                    "state": "resolved",
                    "resolution": "handled",
                    "updated_at": "2026-07-29T13:50:32Z",
                }
            ],
            "cameras": [
                {
                    **config_holder["payload"]["cameras"][0],
                    "room": "卧室",
                }
            ],
        }
        stale_local = storage.create_camera({
            "name": "本地旁路摄像头",
            "room": "错误配置",
            "stream_url": "demo:stale-local",
            "enabled": True,
        })
        updated = agent.process_once()
        cameras = storage.list_cameras(include_secret=True)
        if updated["applied"] != 1 or len(cameras) != 1 or cameras[0]["room"] != "卧室":
            raise SystemExit(f"camera was not updated in place: result={updated} cameras={cameras}")
        stale_delete = next((
            item for item in reports[-1]["cameras"]
            if item.get("local_camera_id") == stale_local["id"] and item.get("status") == "deleted"
        ), None)
        if stale_delete is None:
            raise SystemExit(f"unmapped local camera was not reported as deleted: {reports[-1]}")
        presence = reports[-1]["cameras"][0]["presence"]
        if not presence.get("last_person_seen_at") or presence.get("person_samples") != 1:
            raise SystemExit(f"presence report did not include person observation: {presence}")
        if not presence.get("last_pet_seen_at") or presence.get("last_pet_count") != 1 or presence.get("pet_types") != ["cat"]:
            raise SystemExit(f"presence report did not include independent pet activity: {presence}")
        synced_event = storage.get_event(int(edge_event["id"]))
        if not synced_event or not synced_event.get("acknowledged") or synced_event.get("payload", {}).get("resolution") != "handled":
            raise SystemExit(f"cloud event state did not update the edge event: {synced_event}")
        command_reports = reports[-1].get("event_state_commands") or []
        if len(command_reports) != 1 or command_reports[0].get("status") != "applied":
            raise SystemExit(f"event state command was not reported as applied: {reports[-1]}")

        duplicate = agent.process_once()
        duplicate_reports = reports[-1].get("event_state_commands") or []
        if duplicate.get("ok") is not True or len(duplicate_reports) != 1 or duplicate_reports[0].get("status") != "already_applied":
            raise SystemExit(f"duplicate event state command was not idempotent: {duplicate_reports}")

        config_holder["payload"] = {
            "ok": True,
            "device_id": "edge-test",
            "config_version": "camera-config-test-3",
            "cameras": [],
        }
        deleted = agent.process_once()
        cameras = storage.list_cameras(include_secret=True)
        if deleted["applied"] != 0 or deleted["reported"] != 1 or cameras:
            raise SystemExit(f"camera was not deleted after remote removal: result={deleted} cameras={cameras}")

        offline_privacy = agent.update_video_privacy("person_blur")
        persisted_state = json.loads((root / "runtime" / "config-sync-state.json").read_text(encoding="utf-8"))
        if offline_privacy.get("synced") is not False or agent.video_privacy_mode() != "person_blur":
            raise SystemExit(f"offline privacy update did not apply locally: {offline_privacy}")
        if persisted_state.get("video_privacy_mode") != "person_blur":
            raise SystemExit(f"offline privacy update was not persisted: {persisted_state}")

        def privacy_request(method: str, path: str, **kwargs: object) -> dict:
            if method == "PUT" and path == "/api/v1/device/video-privacy":
                return {"ok": True, "minimum_mode": "skeleton", "updated_at": "cloud-now"}
            return fake_request(method, path, **kwargs)

        agent._request_json = privacy_request  # type: ignore[method-assign]
        synced_privacy = agent.update_video_privacy("skeleton")
        if synced_privacy.get("synced") is not True or agent.video_privacy_mode() != "skeleton":
            raise SystemExit(f"cloud privacy update did not converge: {synced_privacy}")

        print(
            json.dumps(
                {
                    "ok": True,
                    "reports": len(reports),
                    "last_config_version": agent.last_config_version,
                    "last_report": reports[-1],
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
