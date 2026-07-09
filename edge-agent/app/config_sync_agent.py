from __future__ import annotations

from pathlib import Path
from threading import Event, Thread
from typing import Any, Callable, Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json


class ConfigSyncAgent:
    def __init__(
        self,
        *,
        storage: Any,
        settings: Any,
        camera_agent: Any,
        device_id_resolver: Callable[[], str],
        token_resolver: Callable[[], str],
        runtime_status_resolver: Callable[[], Dict[str, Any]] | None = None,
    ) -> None:
        self.storage = storage
        self.settings = settings
        self.camera_agent = camera_agent
        self.device_id_resolver = device_id_resolver
        self.token_resolver = token_resolver
        self.runtime_status_resolver = runtime_status_resolver or (lambda: {})
        self._stop = Event()
        self._wake = Event()
        self._thread: Thread | None = None
        self.last_loop_started_at: str | None = None
        self.last_sync_at: str | None = None
        self.last_config_version = ""
        self.last_error = ""
        self.last_result: Dict[str, Any] = {}

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._wake.clear()
        self._thread = Thread(target=self._run, name="gohome-config-sync-agent", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5)

    def wake(self) -> None:
        self._wake.set()

    def status(self) -> Dict[str, Any]:
        configured, reason = self._configured()
        return {
            "enabled": bool(getattr(self.settings, "config_sync_enabled", True)),
            "running": self.is_running,
            "configured": configured,
            "reason": reason,
            "app_server_base_url": self._base_url(),
            "last_loop_started_at": self.last_loop_started_at,
            "last_sync_at": self.last_sync_at,
            "last_config_version": self.last_config_version,
            "last_error": self.last_error,
            "last_result": self.last_result,
        }

    def process_once(self) -> Dict[str, Any]:
        configured, reason = self._configured()
        if not configured:
            return {"ok": False, "reason": reason, "applied": 0, "reported": 0}
        config = self._request_json("GET", "/api/v1/device/config")
        apply_result = self._apply_config(config)
        report_payload = self._build_report(config, apply_result)
        report_response = self._request_json("POST", "/api/v1/device/sync", json_body=report_payload)
        self.last_config_version = str(config.get("config_version") or "")
        self.last_sync_at = self._utc_iso()
        self.last_error = ""
        self.last_result = {
            "config_version": self.last_config_version,
            "applied": apply_result,
            "report_ok": bool(report_response.get("ok", True)),
        }
        return {
            "ok": True,
            "config_version": self.last_config_version,
            "applied": apply_result.get("applied", 0),
            "reported": len(report_payload.get("cameras") or []),
            "report": report_response,
        }

    def _run(self) -> None:
        while not self._stop.is_set():
            self.last_loop_started_at = self._utc_iso()
            if bool(getattr(self.settings, "config_sync_enabled", True)):
                try:
                    self.process_once()
                except Exception as exc:
                    self.last_error = str(exc)
                    self.last_result = {"ok": False, "error": str(exc)}
            interval = max(1.0, float(getattr(self.settings, "config_sync_interval_seconds", 10)))
            self._wake.wait(interval)
            self._wake.clear()

    def _apply_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        state = self._load_state()
        camera_map = dict(state.get("camera_map") or {})
        desired_remote_ids: set[str] = set()
        reports: list[Dict[str, Any]] = []
        applied = 0
        skipped = 0
        deleted = 0

        for camera_config in config.get("cameras") or []:
            remote_id = self._remote_camera_id(camera_config)
            if not remote_id:
                skipped += 1
                reports.append({
                    "camera_id": "",
                    "status": "skipped",
                    "sync_status": "edge_error",
                    "last_error": "camera_id_missing",
                })
                continue
            desired_remote_ids.add(remote_id)
            report = self._apply_camera(camera_config, camera_map)
            reports.append(report)
            if report.get("sync_status") == "synced":
                applied += 1
            else:
                skipped += 1

        for remote_id, local_id in list(camera_map.items()):
            if remote_id in desired_remote_ids:
                continue
            if self._delete_local_camera(local_id):
                deleted += 1
                reports.append({
                    "camera_id": remote_id,
                    "local_camera_id": local_id,
                    "status": "deleted",
                    "sync_status": "synced",
                    "last_error": "",
                    "enabled": False,
                })
            camera_map.pop(remote_id, None)

        state["camera_map"] = camera_map
        state["config_version"] = str(config.get("config_version") or "")
        state["last_applied_at"] = self._utc_iso()
        rules_result = self._apply_rules(config.get("rules") or {}, str(config.get("rules_version") or ""))
        if rules_result.get("applied"):
            state["rules_version"] = rules_result.get("rules_version") or ""
        self._save_state(state)

        return {
            "applied": applied,
            "skipped": skipped,
            "deleted": deleted,
            "camera_reports": reports,
            "rules": rules_result,
        }

    def _apply_rules(self, rules: Dict[str, Any], rules_version: str = "") -> Dict[str, Any]:
        if not rules:
            return {"applied": False, "rules_version": ""}
        try:
            updated = self.storage.update_rules(rules)
            return {
                "applied": True,
                "rules_version": str(rules_version or updated.get("updated_at") or ""),
                "updated_at": str(updated.get("updated_at") or ""),
            }
        except Exception as exc:
            return {
                "applied": False,
                "rules_version": str(rules_version or ""),
                "error": str(exc),
            }

    def _apply_camera(self, camera_config: Dict[str, Any], camera_map: Dict[str, Any]) -> Dict[str, Any]:
        remote_id = self._remote_camera_id(camera_config)
        stream_url = str(camera_config.get("stream_url") or "").strip()
        enabled = self._as_bool(camera_config.get("enabled", True))
        if not stream_url or bool(camera_config.get("setup_required")):
            local_id = camera_map.get(remote_id)
            if local_id:
                self._update_local_camera_status(local_id, "setup_required", "stream_url_missing")
            return {
                "camera_id": remote_id,
                "local_camera_id": local_id or None,
                "status": "setup_required",
                "sync_status": "pending_local_setup",
                "enabled": enabled,
                "last_error": "stream_url_missing",
            }

        payload = {
            "name": str(camera_config.get("name") or f"摄像头 {remote_id}"),
            "room": str(camera_config.get("room") or ""),
            "stream_url": stream_url,
            "username": str(camera_config.get("username") or "") or None,
            "password": str(camera_config.get("password") or "") or None,
            "enabled": enabled,
        }

        local_camera = self._mapped_camera(camera_map.get(remote_id)) or self._camera_by_stream_url(stream_url)
        action = "unchanged"
        if local_camera is None:
            local_camera = self.storage.create_camera(payload)
            action = "created"
        else:
            patch = self._camera_patch(local_camera, payload)
            if patch:
                local_camera = self.storage.update_camera(int(local_camera["id"]), patch) or local_camera
                action = "updated"

        local_camera = self.storage.get_camera(int(local_camera["id"]), include_secret=True) or local_camera
        camera_map[remote_id] = int(local_camera["id"])

        status = str(local_camera.get("status") or "")
        last_error = str(local_camera.get("last_error") or "")
        if not enabled:
            self.storage.update_camera_status(int(local_camera["id"]), "disabled", "")
            status = "disabled"
            last_error = ""
        elif bool(getattr(self.settings, "config_sync_test_capture_enabled", False)):
            status, last_error = self._verify_camera(local_camera)
        elif status in {"", "unknown", "disabled", "setup_required"}:
            self.storage.update_camera_status(int(local_camera["id"]), "configured", "")
            status = "configured"
            last_error = ""

        return {
            "camera_id": remote_id,
            "local_camera_id": int(local_camera["id"]),
            "name": payload["name"],
            "room": payload["room"],
            "enabled": enabled,
            "status": status,
            "sync_status": "synced" if not last_error else "edge_error",
            "last_error": last_error,
            "action": action,
        }

    def _build_report(self, config: Dict[str, Any], apply_result: Dict[str, Any]) -> Dict[str, Any]:
        runtime = self.runtime_status_resolver() or {}
        worker_running = bool(runtime.get("worker_running", runtime.get("running", False)))
        return {
            "device_id": self.device_id_resolver(),
            "config_version": str(config.get("config_version") or ""),
            "applied_rule_version": str((apply_result.get("rules") or {}).get("rules_version") or ""),
            "worker_running": worker_running,
            "status": {
                "status": "online",
                "sync_status": "healthy" if not self.last_error else "degraded",
                "applied": apply_result.get("applied", 0),
                "skipped": apply_result.get("skipped", 0),
                "deleted": apply_result.get("deleted", 0),
            },
            "runtime": runtime,
            "cameras": apply_result.get("camera_reports") or [],
        }

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        normalized_path = path if path.startswith("/") else f"/{path}"
        url = f"{self._base_url()}{normalized_path}"
        body = None
        if json_body is not None:
            body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        request = Request(
            url,
            data=body,
            method=method.upper(),
            headers={
                "Authorization": f"Bearer {self._device_token()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        timeout = max(2.0, float(getattr(self.settings, "config_sync_request_timeout_seconds", 12)))
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {url} failed: HTTP {exc.code} {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"{method} {url} failed: {exc.reason}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{method} {url} returned non-json response") from exc

    def _configured(self) -> tuple[bool, str]:
        if not bool(getattr(self.settings, "config_sync_enabled", True)):
            return False, "config_sync_disabled"
        if not self._base_url():
            return False, "app_server_base_url_missing"
        if not self._device_token():
            return False, "device_token_missing"
        return True, "ready"

    def _camera_patch(self, current: Dict[str, Any], desired: Dict[str, Any]) -> Dict[str, Any]:
        patch: Dict[str, Any] = {}
        for key in ("name", "room", "stream_url", "username", "password"):
            if str(current.get(key) or "") != str(desired.get(key) or ""):
                patch[key] = desired.get(key)
        if self._as_bool(current.get("enabled", True)) != self._as_bool(desired.get("enabled", True)):
            patch["enabled"] = desired.get("enabled", True)
        return patch

    def _mapped_camera(self, local_id: Any) -> Dict[str, Any] | None:
        try:
            return self.storage.get_camera(int(local_id), include_secret=True) if local_id else None
        except (TypeError, ValueError):
            return None

    def _camera_by_stream_url(self, stream_url: str) -> Dict[str, Any] | None:
        for camera in self.storage.list_cameras(include_secret=True):
            if str(camera.get("stream_url") or "").strip() == stream_url:
                return camera
        return None

    def _delete_local_camera(self, local_id: Any) -> bool:
        try:
            camera_id = int(local_id)
        except (TypeError, ValueError):
            return False
        return bool(self.storage.delete_camera(camera_id))

    def _update_local_camera_status(self, local_id: Any, status: str, last_error: str) -> None:
        try:
            self.storage.update_camera_status(int(local_id), status, last_error)
        except (TypeError, ValueError):
            return

    def _verify_camera(self, camera: Dict[str, Any]) -> tuple[str, str]:
        try:
            self.camera_agent.capture_frame(camera, prefer_cache=False)
        except Exception as exc:
            self.storage.update_camera_status(int(camera["id"]), "offline", str(exc))
            return "offline", str(exc)
        self.storage.update_camera_status(int(camera["id"]), "online", "")
        return "online", ""

    def _remote_camera_id(self, camera_config: Dict[str, Any]) -> str:
        return str(camera_config.get("camera_id") or camera_config.get("id") or "").strip()

    def _load_state(self) -> Dict[str, Any]:
        path = self._state_path()
        if not path.exists():
            return {"camera_map": {}}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"camera_map": {}}
        if not isinstance(data, dict):
            return {"camera_map": {}}
        data["camera_map"] = data.get("camera_map") if isinstance(data.get("camera_map"), dict) else {}
        return data

    def _save_state(self, state: Dict[str, Any]) -> None:
        path = self._state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{json.dumps(state, ensure_ascii=False, indent=2)}\n", encoding="utf-8")

    def _state_path(self) -> Path:
        return Path(getattr(self.settings, "runtime_dir")) / "config-sync-state.json"

    def _base_url(self) -> str:
        return str(getattr(self.settings, "app_server_base_url", "") or "").strip().rstrip("/")

    def _device_token(self) -> str:
        return str(getattr(self.settings, "device_api_token", "") or "").strip() or str(self.token_resolver() or "").strip()

    def _as_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() not in {"", "0", "false", "no", "off"}
        return bool(value)

    def _utc_iso(self) -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()
