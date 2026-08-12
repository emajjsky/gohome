from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.camera_endpoint_resolver import CameraEndpoint
from app.config_sync_agent import ConfigSyncAgent
from app.storage import Storage


def verify_cloud_network_identity_recovery() -> None:
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
        reconciled_camera_sets: list[list[dict]] = []
        camera_agent = SimpleNamespace(
            reconcile_managed_streams=lambda cameras: reconciled_camera_sets.append([
                dict(camera) for camera in cameras if camera.get("enabled", True)
            ]),
            managed_camera_status=lambda camera: {
                "camera_id": int(camera["id"]),
                "state": "streaming",
                "unique_frames": 12,
                "latest_frame_age_ms": 40.0,
                "decoded_fps": 15.0,
                "last_error": "",
            },
        )

        class CloudIdentityResolver:
            def __init__(self) -> None:
                self.resolve_calls: list[dict] = []

            def observe(self, _camera: dict) -> CameraEndpoint:
                return CameraEndpoint("192.168.1.11", 554, "/1/2", "00:11:22:33:44:55")

            def resolve(self, camera: dict, **kwargs: object) -> CameraEndpoint:
                self.resolve_calls.append({"camera": dict(camera), **kwargs})
                return CameraEndpoint("192.168.1.44", 554, "/1/2", "aa:bb:cc:dd:ee:ff")

        resolver = CloudIdentityResolver()
        agent = ConfigSyncAgent(
            storage=storage,
            settings=settings,
            camera_agent=camera_agent,
            device_id_resolver=lambda: "edge-cloud-identity-test",
            token_resolver=lambda: "",
            runtime_status_resolver=lambda: {"worker_running": True},
            endpoint_resolver=resolver,  # type: ignore[arg-type]
        )
        config_holder = {
            "payload": {
                "ok": True,
                "device_id": "edge-cloud-identity-test",
                "config_version": "cloud-identity-1",
                "cameras": [{
                    "id": 201,
                    "camera_id": 201,
                    "name": "客厅主视",
                    "room": "客厅",
                    "stream_url": "rtsp://192.168.1.11:554/1/2",
                    "network_identity": "AA-BB-CC-DD-EE-FF",
                    "enabled": True,
                }],
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
        recovered = agent.process_once()
        cameras = storage.list_cameras(include_secret=True)
        state = json.loads((root / "runtime" / "config-sync-state.json").read_text(encoding="utf-8"))
        binding = dict((state.get("camera_endpoints") or {}).get("201") or {})
        connection_update = dict(reports[-1]["cameras"][0].get("connection_update") or {})
        if (
            recovered.get("ok") is not True
            or len(resolver.resolve_calls) != 1
            or resolver.resolve_calls[0].get("network_identity") != "aa:bb:cc:dd:ee:ff"
            or len(cameras) != 1
            or cameras[0].get("stream_url") != "rtsp://192.168.1.44:554/1/2"
            or binding.get("network_identity") != "aa:bb:cc:dd:ee:ff"
            or connection_update.get("reason") != "dhcp_endpoint_changed"
        ):
            raise SystemExit(
                "cloud camera identity did not seed DHCP endpoint recovery: "
                f"result={recovered} calls={resolver.resolve_calls} cameras={cameras} "
                f"binding={binding} report={reports[-1:] }"
            )

        config_holder["payload"] = {
            **config_holder["payload"],
            "config_version": "cloud-identity-conflict",
            "cameras": [{
                **config_holder["payload"]["cameras"][0],
                "network_identity": "11:22:33:44:55:66",
            }],
        }
        conflict = agent.process_once()
        conflict_report = reports[-1]["cameras"][0]
        camera_after_conflict = storage.list_cameras(include_secret=True)[0]
        state_after_conflict = json.loads(
            (root / "runtime" / "config-sync-state.json").read_text(encoding="utf-8")
        )
        binding_after_conflict = dict(
            (state_after_conflict.get("camera_endpoints") or {}).get("201") or {}
        )
        if (
            conflict.get("ok") is not True
            or conflict_report.get("sync_status") != "edge_error"
            or conflict_report.get("last_error") != "network_identity_conflict"
            or camera_after_conflict.get("stream_url") != "rtsp://192.168.1.44:554/1/2"
            or binding_after_conflict.get("network_identity") != "aa:bb:cc:dd:ee:ff"
        ):
            raise SystemExit(
                "conflicting cloud camera identity was not rejected explicitly: "
                f"result={conflict} report={conflict_report} camera={camera_after_conflict} "
                f"binding={binding_after_conflict}"
            )


def main() -> None:
    verify_cloud_network_identity_recovery()
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
        reconciled_camera_sets: list[list[dict]] = []
        camera_agent = SimpleNamespace(
            capture_frame=lambda *_args, **_kwargs: {"width": 640, "height": 360},
            reconcile_managed_streams=lambda cameras: reconciled_camera_sets.append([
                dict(camera) for camera in cameras
                if camera.get("enabled", True)
            ]),
            managed_camera_status=lambda camera: {
                "camera_id": int(camera["id"]),
                "state": "streaming",
                "unique_frames": 12,
                "latest_frame_age_ms": 40.0,
                "decoded_fps": 15.0,
                "last_error": "",
            },
        )
        monotonic_now = [100.0]
        agent = ConfigSyncAgent(
            storage=storage,
            settings=settings,
            camera_agent=camera_agent,
            device_id_resolver=lambda: "edge-test",
            token_resolver=lambda: "",
            runtime_status_resolver=lambda: {"worker_running": True},
            live_status_resolver=lambda camera_id: {
                "source_status": "streaming",
                "source_ready": True,
                "privacy_status": "scene_review_required" if camera_id == 1 else "ready",
                "publish_ready": True,
                "media_ready": True,
                "privacy_ready": camera_id != 1,
                "privacy_mode": "skeleton",
                "delivered_mode": "privacy_hold" if camera_id == 1 else "skeleton",
                "output_fps": 14.0 if camera_id == 1 else 14.5,
                "reason": "scene_revalidation_required" if camera_id == 1 else "",
            },
            monotonic_clock=lambda: monotonic_now[0],
        )

        class InitialRecoveryResolver:
            def __init__(self) -> None:
                self.resolve_calls: list[dict] = []

            def observe(self, _camera: dict) -> None:
                return None

            def resolve(self, camera: dict, **kwargs: object) -> CameraEndpoint:
                self.resolve_calls.append({"camera": dict(camera), **kwargs})
                return CameraEndpoint("192.168.1.44", 554, "/1/2", "00:11:22:33:44:55")

        initial_recovery_resolver = InitialRecoveryResolver()
        agent.endpoint_resolver = initial_recovery_resolver  # type: ignore[assignment]
        binding, connection_update = agent._reconcile_camera_endpoint(
            camera={
                "id": 1,
                "stream_url": "rtsp://192.168.1.11:554/1/2",
                "enabled": True,
                "status": "online",
            },
            remote_stream_url="rtsp://192.168.1.11:554/1/2",
            endpoint_binding={},
            used_endpoint_identities=set(),
        )
        if (
            len(initial_recovery_resolver.resolve_calls) != 1
            or initial_recovery_resolver.resolve_calls[0].get("network_identity") != ""
            or binding.get("resolved_stream_url") != "rtsp://192.168.1.44:554/1/2"
            or not connection_update
            or connection_update.get("reason") != "dhcp_endpoint_changed"
        ):
            raise SystemExit(
                "an unreachable camera without stored MAC identity did not enter scene-based recovery: "
                f"calls={initial_recovery_resolver.resolve_calls} binding={binding} update={connection_update}"
            )
        agent.endpoint_resolver = None

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
        if cameras[0]["stream_url"] != "demo:living_room" or cameras[0]["status"] != "online":
            raise SystemExit(f"unexpected created camera: {cameras[0]}")
        if reports[-1]["cameras"][0]["sync_status"] != "synced":
            raise SystemExit(f"sync report did not mark camera synced: {reports[-1]}")
        if not reconciled_camera_sets or reconciled_camera_sets[-1][0]["stream_url"] != "demo:living_room":
            raise SystemExit("config sync did not immediately reconcile the active camera runtime")
        local_camera_id = int(cameras[0]["id"])
        if agent.remote_camera_id_for_local_camera(local_camera_id) != "101":
            raise SystemExit("remote camera resolver did not publish the committed camera map")

        config_holder["payload"] = {
            "ok": True,
            "device_id": "edge-test",
            "config_version": "camera-config-setup-required",
            "cameras": [
                {
                    "id": 101,
                    "camera_id": 101,
                    "name": "客厅主视",
                    "room": "客厅",
                    "stream_url": "",
                    "enabled": True,
                    "setup_required": True,
                }
            ],
        }
        setup_required = agent.process_once()
        setup_camera = storage.get_camera(local_camera_id, include_secret=True)
        if (
            setup_required["ok"] is not True
            or not setup_camera
            or setup_camera.get("enabled")
            or setup_camera.get("status") != "setup_required"
            or not reconciled_camera_sets
            or reconciled_camera_sets[-1]
        ):
            raise SystemExit(
                "setup-required cloud camera left the previous local source active: "
                f"result={setup_required} camera={setup_camera} reconcile={reconciled_camera_sets[-1:] }"
            )

        config_holder["payload"] = {
            **config_holder["payload"],
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
        restored = agent.process_once()
        restored_camera = storage.get_camera(local_camera_id, include_secret=True)
        if (
            restored["ok"] is not True
            or not restored_camera
            or not restored_camera.get("enabled")
            or restored_camera.get("stream_url") != "demo:living_room"
            or not reconciled_camera_sets[-1]
        ):
            raise SystemExit(
                "complete connection config did not re-enable the existing camera: "
                f"result={restored} camera={restored_camera} reconcile={reconciled_camera_sets[-1:] }"
            )
        state_path = root / "runtime" / "config-sync-state.json"
        state_path.write_text('{"camera_map":', encoding="utf-8")
        if agent.remote_camera_id_for_local_camera(local_camera_id) != "101":
            raise SystemExit("remote camera resolver must not reread a partially written state file")
        agent._save_state({
            "camera_map": {"101": local_camera_id},
            "config_version": "camera-config-test-1",
            "video_privacy_mode": agent.video_privacy_mode(),
        })
        persisted_after_repair = json.loads(state_path.read_text(encoding="utf-8"))
        if persisted_after_repair.get("camera_map") != {"101": local_camera_id}:
            raise SystemExit(f"atomic state repair lost the camera map: {persisted_after_repair}")
        if list(state_path.parent.glob(f".{state_path.name}.*.tmp")):
            raise SystemExit("atomic config state persistence left temporary files behind")
        if "presence" not in reports[-1]["cameras"][0]:
            raise SystemExit("sync report must include camera presence status")
        expected_live = {
            "source_status": "streaming",
            "source_ready": True,
            "privacy_status": "scene_review_required",
            "publish_ready": True,
            "media_ready": True,
            "privacy_ready": False,
            "privacy_mode": "skeleton",
            "delivered_mode": "privacy_hold",
            "output_fps": 14.0,
            "reason": "scene_revalidation_required",
        }
        if reports[-1]["cameras"][0].get("live") != expected_live:
            raise SystemExit(f"sync report lost live delivery state: {reports[-1]}")
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
        if len(reconciled_camera_sets) < 2 or reconciled_camera_sets[-1][0]["room"] != "卧室":
            raise SystemExit("updated camera configuration was not reconciled in the same sync cycle")
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

        state_before_duplicate = state_path.read_bytes()
        rules_before_duplicate = storage.get_rules()
        duplicate = agent.process_once()
        state_after_duplicate = state_path.read_bytes()
        rules_after_duplicate = storage.get_rules()
        duplicate_reports = reports[-1].get("event_state_commands") or []
        if duplicate.get("ok") is not True or len(duplicate_reports) != 1 or duplicate_reports[0].get("status") != "already_applied":
            raise SystemExit(f"duplicate event state command was not idempotent: {duplicate_reports}")
        if state_after_duplicate != state_before_duplicate:
            raise SystemExit("unchanged config sync rewrote durable state")
        if rules_after_duplicate.get("updated_at") != rules_before_duplicate.get("updated_at"):
            raise SystemExit("unchanged config sync rewrote the active rules")

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
