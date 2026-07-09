from __future__ import annotations

from datetime import datetime, timezone
from http.client import HTTPConnection, HTTPSConnection
from threading import Event, Thread
from typing import Any, Callable, Dict
from urllib.parse import urlencode, urlsplit
import json
import time


class LiveRelayAgent:
    def __init__(
        self,
        *,
        storage: Any,
        settings: Any,
        camera_agent: Any,
        device_id_resolver: Callable[[], str],
        token_resolver: Callable[[], str],
        remote_camera_id_resolver: Callable[[int], Any],
    ) -> None:
        self.storage = storage
        self.settings = settings
        self.camera_agent = camera_agent
        self.device_id_resolver = device_id_resolver
        self.token_resolver = token_resolver
        self.remote_camera_id_resolver = remote_camera_id_resolver
        self._stop = Event()
        self._wake = Event()
        self._thread: Thread | None = None
        self._camera_threads: Dict[int, Thread] = {}
        self._camera_stops: Dict[int, Event] = {}
        self._http_connections: Dict[int, Any] = {}
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
        self._thread = Thread(target=self._run, name="gohome-live-relay-agent", daemon=True)
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
            "enabled": bool(getattr(self.settings, "live_relay_enabled", True)),
            "running": self.is_running,
            "configured": configured,
            "reason": reason,
            "app_server_base_url": self._base_url(),
            "fps": int(getattr(self.settings, "live_relay_fps", 5)),
            "active_cameras": sorted(self._camera_threads.keys()),
            "last_loop_started_at": self.last_loop_started_at,
            "last_relay_at": self.last_relay_at,
            "last_error": self.last_error,
            "last_result": self.last_result,
        }

    def _run(self) -> None:
        while not self._stop.is_set():
            self.last_loop_started_at = self._utc_iso()
            configured, reason = self._configured()
            if configured:
                self._sync_camera_threads()
            else:
                self._stop_all_camera_threads()
                self.last_error = "" if reason == "live_relay_disabled" else reason
            self._wake.wait(3.0)
            self._wake.clear()
        self._stop_all_camera_threads()

    def _sync_camera_threads(self) -> None:
        cameras = [
            camera for camera in self.storage.list_cameras(include_secret=True)
            if camera.get("enabled") and str(camera.get("stream_url") or "").strip()
        ]
        active_ids = {int(camera["id"]) for camera in cameras if camera.get("id")}
        for camera_id in list(self._camera_threads.keys()):
            thread = self._camera_threads.get(camera_id)
            if camera_id not in active_ids or thread is None or not thread.is_alive():
                stop_event = self._camera_stops.pop(camera_id, None)
                if stop_event:
                    stop_event.set()
                self._camera_threads.pop(camera_id, None)

        for camera in cameras:
            camera_id = int(camera["id"])
            thread = self._camera_threads.get(camera_id)
            if thread is not None and thread.is_alive():
                continue
            stop_event = Event()
            self._camera_stops[camera_id] = stop_event
            thread = Thread(
                target=self._run_camera,
                args=(dict(camera), stop_event),
                name=f"gohome-live-relay-camera-{camera_id}",
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

    def _run_camera(self, camera: Dict[str, Any], stop_event: Event) -> None:
        camera_id = int(camera["id"])
        while not self._stop.is_set() and not stop_event.is_set():
            try:
                fps = max(1, min(int(getattr(self.settings, "live_relay_fps", 5)), 10))
                quality = max(35, min(int(getattr(self.settings, "live_relay_quality", 55)), 85))
                width = max(240, min(int(getattr(self.settings, "live_relay_width", 640)), 1280))
                height = max(135, min(int(getattr(self.settings, "live_relay_height", 360)), 720))
                drop = max(0, min(int(getattr(self.settings, "live_relay_drop_stale_frames", 4)), 12))
                for chunk in self.camera_agent.mjpeg_frames(
                    camera,
                    fps=fps,
                    jpeg_quality=quality,
                    max_width=width,
                    max_height=height,
                    drop_stale_frames=drop,
                ):
                    if self._stop.is_set() or stop_event.is_set():
                        break
                    frame = self._extract_jpeg(chunk)
                    if not frame:
                        continue
                    self._post_frame(camera_id, frame)
            except Exception as exc:
                self.last_error = f"camera {camera_id}: {exc}"
                time.sleep(2.0)

    def _post_frame(self, local_camera_id: int, frame: bytes) -> None:
        remote_camera_id = self.remote_camera_id_resolver(local_camera_id) or local_camera_id
        params = {
            "camera_id": str(remote_camera_id),
            "local_camera_id": str(local_camera_id),
            "content_type": "image/jpeg",
            "captured_at": self._utc_iso(),
        }
        url = f"{self._base_url()}/api/v1/device/live-frames/upload?{urlencode(params)}"
        headers = {
            "Authorization": f"Bearer {self._device_token()}",
            "X-GoHome-Device-Id": self.device_id_resolver(),
            "Content-Type": "image/jpeg",
            "Accept": "application/json",
        }
        timeout = max(1.0, float(getattr(self.settings, "live_relay_request_timeout_seconds", 2.0)))
        raw = self._post_frame_keepalive(local_camera_id, url, frame, headers, timeout)
        self.last_relay_at = self._utc_iso()
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {}
        self.last_result = {
            "camera_id": int(local_camera_id),
            "remote_camera_id": str(remote_camera_id),
            "size": len(frame),
            "response": payload,
        }
        self.last_error = ""

    def _post_frame_keepalive(
        self,
        local_camera_id: int,
        url: str,
        frame: bytes,
        headers: Dict[str, str],
        timeout: float,
    ) -> str:
        try:
            return self._post_frame_with_connection(local_camera_id, url, frame, headers, timeout)
        except Exception:
            self._close_connection(local_camera_id)
            return self._post_frame_with_connection(local_camera_id, url, frame, headers, timeout)

    def _post_frame_with_connection(
        self,
        local_camera_id: int,
        url: str,
        frame: bytes,
        headers: Dict[str, str],
        timeout: float,
    ) -> str:
        parts = urlsplit(url)
        connection = self._http_connections.get(local_camera_id)
        if connection is None:
            connection_class = HTTPSConnection if parts.scheme == "https" else HTTPConnection
            connection = connection_class(parts.hostname, parts.port, timeout=timeout)
            self._http_connections[local_camera_id] = connection
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"
        connection.request("POST", path, body=frame, headers={**headers, "Connection": "keep-alive"})
        response = connection.getresponse()
        raw = response.read().decode("utf-8", errors="replace")
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"live frame upload failed: HTTP {response.status} {raw}")
        return raw

    def _close_connection(self, local_camera_id: int) -> None:
        connection = self._http_connections.pop(local_camera_id, None)
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

    def _close_connections(self) -> None:
        for camera_id in list(self._http_connections.keys()):
            self._close_connection(camera_id)

    def _extract_jpeg(self, chunk: bytes) -> bytes:
        if not chunk:
            return b""
        marker = b"\r\n\r\n"
        if marker not in chunk:
            return chunk
        body = chunk.split(marker, 1)[1]
        if body.endswith(b"\r\n"):
            body = body[:-2]
        return body

    def _configured(self) -> tuple[bool, str]:
        if not bool(getattr(self.settings, "live_relay_enabled", True)):
            return False, "live_relay_disabled"
        if not self._base_url():
            return False, "app_server_base_url_missing"
        if not self._device_token():
            return False, "device_token_missing"
        return True, "ready"

    def _base_url(self) -> str:
        return str(getattr(self.settings, "app_server_base_url", "") or "").strip().rstrip("/")

    def _device_token(self) -> str:
        return str(getattr(self.settings, "device_api_token", "") or "").strip() or str(self.token_resolver() or "").strip()

    def _utc_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()
