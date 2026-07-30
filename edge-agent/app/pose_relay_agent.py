from __future__ import annotations

from datetime import datetime, timezone
from http.client import HTTPConnection, HTTPSConnection
from math import isfinite
from threading import Event, Thread
from typing import Any, Callable, Dict
from urllib.parse import urlencode, urlsplit
import json
import time


class PoseRelayAgent:
    """Relay pixel-free EACP display packets without affecting safety evidence."""

    version = "eacp-pose-relay-v1"
    states = {"observed", "tracked", "coasting", "empty", "expired"}

    def __init__(
        self,
        *,
        storage: Any,
        settings: Any,
        tracker: Any,
        device_id_resolver: Callable[[], str],
        token_resolver: Callable[[], str],
        remote_camera_id_resolver: Callable[[int], Any],
    ) -> None:
        self.storage = storage
        self.settings = settings
        self.tracker = tracker
        self.device_id_resolver = device_id_resolver
        self.token_resolver = token_resolver
        self.remote_camera_id_resolver = remote_camera_id_resolver
        self._stop = Event()
        self._wake = Event()
        self._thread: Thread | None = None
        self._camera_threads: Dict[int, Thread] = {}
        self._camera_stops: Dict[int, Event] = {}
        self._connections: Dict[int, Any] = {}
        self._dimensions: Dict[int, tuple[int, int]] = {}
        self._metrics: Dict[int, Dict[str, Any]] = {}
        self.last_loop_started_at: str | None = None
        self.last_relay_at: str | None = None
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
        self._thread = Thread(target=self._run, name="gohome-pose-relay-agent", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        for stop_event in list(self._camera_stops.values()):
            stop_event.set()
        self._close_connections()
        for thread in list(self._camera_threads.values()):
            thread.join(timeout=2)
        if self._thread:
            self._thread.join(timeout=5)

    def wake(self) -> None:
        self._wake.set()

    def status(self) -> Dict[str, Any]:
        configured, reason = self._configured()
        return {
            "schema_version": self.version,
            "enabled": bool(getattr(self.settings, "pose_relay_enabled", True)),
            "running": self.is_running,
            "configured": configured,
            "reason": reason,
            "fps": self._fps(),
            "active_cameras": sorted(self._camera_threads),
            "last_loop_started_at": self.last_loop_started_at,
            "last_relay_at": self.last_relay_at,
            "last_error": self.last_error,
            "last_result": self.last_result,
            "cameras": {str(camera_id): dict(metrics) for camera_id, metrics in sorted(self._metrics.items())},
        }

    def _run(self) -> None:
        while not self._stop.is_set():
            self.last_loop_started_at = self._utc_iso()
            configured, reason = self._configured()
            if configured:
                self._sync_camera_threads()
            else:
                self._stop_all_camera_threads()
                self.last_error = "" if reason == "pose_relay_disabled" else reason
            self._wake.wait(3.0)
            self._wake.clear()
        self._stop_all_camera_threads()

    def _sync_camera_threads(self) -> None:
        cameras = [
            camera for camera in self.storage.list_cameras(include_secret=False)
            if camera.get("enabled") and camera.get("id")
        ]
        active_ids = {int(camera["id"]) for camera in cameras}
        for camera_id in list(self._camera_threads):
            thread = self._camera_threads.get(camera_id)
            if camera_id not in active_ids or thread is None or not thread.is_alive():
                stop_event = self._camera_stops.pop(camera_id, None)
                if stop_event:
                    stop_event.set()
                self._camera_threads.pop(camera_id, None)
                self._close_connection(camera_id)
                self._dimensions.pop(camera_id, None)
        for camera_id in sorted(active_ids):
            thread = self._camera_threads.get(camera_id)
            if thread is not None and thread.is_alive():
                continue
            stop_event = Event()
            self._camera_stops[camera_id] = stop_event
            thread = Thread(
                target=self._run_camera,
                args=(camera_id, stop_event),
                name=f"gohome-pose-relay-camera-{camera_id}",
                daemon=True,
            )
            self._camera_threads[camera_id] = thread
            thread.start()

    def _stop_all_camera_threads(self) -> None:
        for stop_event in list(self._camera_stops.values()):
            stop_event.set()
        self._close_connections()
        for thread in list(self._camera_threads.values()):
            thread.join(timeout=1)
        self._camera_stops.clear()
        self._camera_threads.clear()
        self._dimensions.clear()

    def _run_camera(self, camera_id: int, stop_event: Event) -> None:
        interval = 1.0 / self._fps()
        last_packet_key = ""
        while not self._stop.is_set() and not stop_event.is_set():
            started = time.monotonic()
            try:
                metadata = dict(self.tracker.latest_metadata(camera_id) or {})
                packet = self._display_packet(camera_id, metadata)
                packet_key = self._packet_key(packet)
                metrics = self._metric(camera_id)
                if packet_key != last_packet_key:
                    self._post_packet(camera_id, packet)
                    last_packet_key = packet_key
                    metrics["sent_count"] += 1
                    metrics["last_state"] = packet["state"]
                    metrics["last_frame_id"] = packet["frame_id"]
                    metrics["last_sent_at"] = self.last_relay_at
                else:
                    metrics["duplicate_skips"] += 1
            except Exception as exc:
                self._metric(camera_id)["error_count"] += 1
                self.last_error = f"camera {camera_id}: {exc}"
                self._close_connection(camera_id)
            remaining = interval - (time.monotonic() - started)
            if remaining > 0:
                stop_event.wait(remaining)

    def _display_packet(self, camera_id: int, metadata: Dict[str, Any]) -> Dict[str, Any]:
        tracking = dict(metadata.get("tracking") or {})
        state = str(tracking.get("state") or "empty")
        if state not in self.states:
            state = "empty"
        width = self._bounded_int(metadata.get("image_width"), 0, 8192)
        height = self._bounded_int(metadata.get("image_height"), 0, 8192)
        if width > 0 and height > 0:
            self._dimensions[int(camera_id)] = (width, height)
        else:
            width, height = self._dimensions.get(int(camera_id), (0, 0))
        poses = [self._pose(item, width, height) for item in list(tracking.get("poses") or [])[:4]]
        poses = [item for item in poses if item is not None]
        return {
            "schema_version": self.version,
            "camera_id": int(camera_id),
            "frame_id": str(tracking.get("frame_id") or "")[:160],
            "captured_at": str(tracking.get("captured_at") or "")[:64],
            "state": state,
            "source": state,
            "image_width": width,
            "image_height": height,
            "poses": poses if state in {"observed", "tracked", "coasting"} else [],
            "display_only": True,
            "formal_evidence_eligible": False,
        }

    def _pose(self, value: Any, width: int, height: int) -> Dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        points = []
        for point in list(value.get("keypoints") or [])[:24]:
            if not isinstance(point, dict) or not point.get("name"):
                continue
            x = self._finite_float(point.get("x"))
            y = self._finite_float(point.get("y"))
            if x is None or y is None:
                continue
            points.append({
                "name": str(point["name"])[:40],
                "x": round(max(-256.0, min(float(width or 8192) + 256.0, x)), 3),
                "y": round(max(-256.0, min(float(height or 8192) + 256.0, y)), 3),
                "confidence": round(max(0.0, min(1.0, self._finite_float(point.get("confidence")) or 0.0)), 4),
                "visible": bool(point.get("visible")),
            })
        if not points:
            return None
        box = []
        for index, coordinate in enumerate(list(value.get("bbox") or [])[:4]):
            number = self._finite_float(coordinate)
            if number is None:
                box = []
                break
            axis_limit = float((width if index % 2 == 0 else height) or 8192)
            box.append(round(max(-256.0, min(axis_limit + 256.0, number)), 3))
        return {
            "track_id": str(value.get("track_id") or value.get("id") or "")[:96],
            "confidence": round(max(0.0, min(1.0, self._finite_float(value.get("confidence")) or 0.0)), 4),
            "bbox": box,
            "keypoints": points,
        }

    def _post_packet(self, local_camera_id: int, packet: Dict[str, Any]) -> None:
        remote_camera_id = self.remote_camera_id_resolver(local_camera_id) or local_camera_id
        params = {"camera_id": str(remote_camera_id), "local_camera_id": str(local_camera_id)}
        url = f"{self._base_url()}/api/v1/device/live-poses/upload?{urlencode(params)}"
        body = json.dumps(packet, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._device_token()}",
            "X-GoHome-Device-Id": self.device_id_resolver(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        timeout = max(0.5, float(getattr(self.settings, "pose_relay_request_timeout_seconds", 2.0)))
        raw = self._post_keepalive(local_camera_id, url, body, headers, timeout)
        self.last_relay_at = self._utc_iso()
        payload = json.loads(raw) if raw else {}
        self.last_result = {
            "camera_id": int(local_camera_id),
            "remote_camera_id": str(remote_camera_id),
            "frame_id": packet["frame_id"],
            "state": packet["state"],
            "pose_count": len(packet["poses"]),
            "size": len(body),
            "response": payload,
        }
        self.last_error = ""

    def _post_keepalive(self, camera_id: int, url: str, body: bytes, headers: Dict[str, str], timeout: float) -> str:
        try:
            return self._post_with_connection(camera_id, url, body, headers, timeout)
        except Exception:
            self._close_connection(camera_id)
            return self._post_with_connection(camera_id, url, body, headers, timeout)

    def _post_with_connection(self, camera_id: int, url: str, body: bytes, headers: Dict[str, str], timeout: float) -> str:
        parts = urlsplit(url)
        connection = self._connections.get(camera_id)
        if connection is None:
            connection_class = HTTPSConnection if parts.scheme == "https" else HTTPConnection
            connection = connection_class(parts.hostname, parts.port, timeout=timeout)
            self._connections[camera_id] = connection
        path = f"{parts.path}?{parts.query}" if parts.query else parts.path
        connection.request("POST", path, body=body, headers={**headers, "Connection": "keep-alive"})
        response = connection.getresponse()
        raw = response.read().decode("utf-8", errors="replace")
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"pose upload failed: HTTP {response.status} {raw}")
        return raw

    def _close_connection(self, camera_id: int) -> None:
        connection = self._connections.pop(int(camera_id), None)
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

    def _close_connections(self) -> None:
        for camera_id in list(self._connections):
            self._close_connection(camera_id)

    def _configured(self) -> tuple[bool, str]:
        if not bool(getattr(self.settings, "pose_relay_enabled", True)):
            return False, "pose_relay_disabled"
        if self.tracker is None:
            return False, "continual_pose_tracker_missing"
        if not self._base_url():
            return False, "app_server_base_url_missing"
        if not self._device_token():
            return False, "device_token_missing"
        return True, "ready"

    def _metric(self, camera_id: int) -> Dict[str, Any]:
        return self._metrics.setdefault(int(camera_id), {
            "sent_count": 0,
            "duplicate_skips": 0,
            "error_count": 0,
            "last_state": "",
            "last_frame_id": "",
            "last_sent_at": None,
        })

    def _base_url(self) -> str:
        return str(getattr(self.settings, "app_server_base_url", "") or "").strip().rstrip("/")

    def _device_token(self) -> str:
        issued = str(self.token_resolver() or "").strip()
        if bool(getattr(self.settings, "require_issued_device_token", False)):
            return issued
        return issued or str(getattr(self.settings, "device_api_token", "") or "").strip()

    def _fps(self) -> float:
        return max(1.0, min(float(getattr(self.settings, "pose_relay_fps", 20.0)), 30.0))

    def _packet_key(self, packet: Dict[str, Any]) -> str:
        return f"{packet.get('state') or 'empty'}:{packet.get('frame_id') or ''}"

    def _finite_float(self, value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if isfinite(number) else None

    def _bounded_int(self, value: Any, minimum: int, maximum: int) -> int:
        try:
            return max(minimum, min(maximum, int(value)))
        except (TypeError, ValueError):
            return minimum

    def _utc_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()
