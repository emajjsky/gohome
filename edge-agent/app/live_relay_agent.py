from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from http.client import HTTPConnection, HTTPSConnection
from threading import Condition, Event, Lock, Thread, get_ident
from typing import Any, Callable, Dict
from urllib.parse import urlencode, urlsplit
import json
import time

from .video_privacy import normalize_privacy_mode
from .camera_agent import _load_cv2, bounded_stream_fps
from .vision.privacy_background import PrivacyCalibrationRequired


class _LatestFrameUploader:
    """Upload serially while retaining only the freshest pending live frame."""

    def __init__(
        self,
        camera_id: int,
        upload: Callable[[Dict[str, Any]], None],
        completed: Callable[[], None],
        failed: Callable[[Exception], None],
        replaced: Callable[[], None],
    ) -> None:
        self.camera_id = int(camera_id)
        self._upload = upload
        self._completed = completed
        self._failed = failed
        self._replaced = replaced
        self._condition = Condition()
        self._pending: Dict[str, Any] | None = None
        self._stopping = False
        self._drain = False
        self._thread = Thread(
            target=self._run,
            name=f"gohome-live-upload-{self.camera_id}",
            daemon=True,
        )
        self._thread.start()

    def submit(self, payload: Dict[str, Any]) -> None:
        with self._condition:
            if self._stopping:
                return
            was_replaced = self._pending is not None
            self._pending = payload
            self._condition.notify()
        if was_replaced:
            self._replaced()

    def close(self, *, drain: bool) -> None:
        with self._condition:
            self._stopping = True
            self._drain = bool(drain)
            if not self._drain:
                self._pending = None
            self._condition.notify()
        self._thread.join(timeout=5.0)

    def _run(self) -> None:
        while True:
            with self._condition:
                while self._pending is None and not self._stopping:
                    self._condition.wait()
                if self._pending is None and self._stopping:
                    return
                payload = self._pending
                self._pending = None
            try:
                self._upload(payload)
                self._completed()
            except Exception as exc:
                self._failed(exc)
            with self._condition:
                if self._stopping and (not self._drain or self._pending is None):
                    return


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
        privacy_mode_resolver: Callable[[], str] | None = None,
        privacy_mode_observer: Callable[[str], Any] | None = None,
        privacy_renderer: Any | None = None,
    ) -> None:
        self.storage = storage
        self.settings = settings
        self.camera_agent = camera_agent
        self.device_id_resolver = device_id_resolver
        self.token_resolver = token_resolver
        self.remote_camera_id_resolver = remote_camera_id_resolver
        self.privacy_mode_resolver = privacy_mode_resolver or (lambda: "original")
        self.privacy_mode_observer = privacy_mode_observer
        self.privacy_renderer = privacy_renderer
        self._stop = Event()
        self._wake = Event()
        self._thread: Thread | None = None
        self._camera_threads: Dict[int, Thread] = {}
        self._camera_stops: Dict[int, Event] = {}
        self._camera_signatures: Dict[int, tuple[Any, ...]] = {}
        self._http_connections: Dict[tuple[int, int], Any] = {}
        self._http_connections_lock = Lock()
        self._upload_stats_lock = Lock()
        self._camera_upload_stats: Dict[int, Dict[str, int]] = {}
        self._camera_upload_samples: Dict[int, Any] = {}
        self._camera_privacy_modes: Dict[int, str] = {}
        self._camera_privacy_states: Dict[int, Dict[str, Any]] = {}
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
        deadline = time.monotonic() + 5.0
        for thread in list(self._camera_threads.values()):
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        if self._thread:
            self._thread.join(timeout=max(0.0, deadline - time.monotonic()))

    def wake(self) -> None:
        self._wake.set()

    def handle_camera_source_transition(self, transition: Dict[str, Any]) -> None:
        camera_id = int(transition.get("camera_id") or 0)
        if camera_id <= 0:
            return
        stop_event = self._camera_stops.get(camera_id)
        if stop_event is not None:
            stop_event.set()
        self._close_connection(camera_id)
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
            "upload_strategy": "one_in_flight_latest_pending",
            "active_cameras": sorted(self._camera_threads.keys()),
            "last_loop_started_at": self.last_loop_started_at,
            "last_relay_at": self.last_relay_at,
            "last_error": self.last_error,
            "last_result": self.last_result,
            "cameras": self._upload_stats_snapshot(),
            "privacy_mode": normalize_privacy_mode(self.privacy_mode_resolver()),
            "camera_privacy_modes": {
                str(camera_id): self._camera_privacy_modes.get(
                    camera_id,
                    normalize_privacy_mode(self.privacy_mode_resolver()),
                )
                for camera_id in sorted(self._camera_threads.keys())
            },
            "camera_privacy_states": {
                str(camera_id): dict(state)
                for camera_id, state in sorted(self._camera_privacy_states.items())
            },
            "privacy_renderer": (
                self.privacy_renderer.status()
                if callable(getattr(self.privacy_renderer, "status", None))
                else {}
            ),
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
        camera_signatures = {
            int(camera["id"]): self._camera_signature(camera)
            for camera in cameras
            if camera.get("id")
        }
        for camera_id in list(self._camera_threads.keys()):
            thread = self._camera_threads.get(camera_id)
            configuration_changed = self._camera_signatures.get(camera_id) != camera_signatures.get(camera_id)
            if camera_id not in active_ids or thread is None or not thread.is_alive() or configuration_changed:
                stop_event = self._camera_stops.pop(camera_id, None)
                if stop_event:
                    stop_event.set()
                if thread is not None and thread.is_alive():
                    thread.join(timeout=5)
                self._camera_threads.pop(camera_id, None)
                self._camera_signatures.pop(camera_id, None)
                self._camera_privacy_modes.pop(camera_id, None)
                self._camera_privacy_states.pop(camera_id, None)
                with self._upload_stats_lock:
                    self._camera_upload_stats.pop(camera_id, None)
                    self._camera_upload_samples.pop(camera_id, None)
                self._close_connection(camera_id)

        for camera in cameras:
            camera_id = int(camera["id"])
            thread = self._camera_threads.get(camera_id)
            if thread is not None and thread.is_alive():
                continue
            stop_event = Event()
            self._camera_stops[camera_id] = stop_event
            self._camera_signatures[camera_id] = camera_signatures[camera_id]
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
        deadline = time.monotonic() + 5.0
        for thread in list(self._camera_threads.values()):
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        self._camera_stops.clear()
        self._camera_threads.clear()
        self._camera_signatures.clear()
        self._camera_privacy_modes.clear()
        self._camera_privacy_states.clear()
        with self._upload_stats_lock:
            self._camera_upload_stats.clear()
            self._camera_upload_samples.clear()

    def _camera_signature(self, camera: Dict[str, Any]) -> tuple[Any, ...]:
        return (
            int(camera.get("id") or 0),
            str(camera.get("stream_url") or "").strip(),
            str(camera.get("username") or ""),
            str(camera.get("password") or ""),
            bool(camera.get("enabled", True)),
        )

    def _run_camera(self, camera: Dict[str, Any], stop_event: Event) -> None:
        camera_id = int(camera["id"])
        while not self._stop.is_set() and not stop_event.is_set():
            uploader: _LatestFrameUploader | None = None
            try:
                fps = bounded_stream_fps(getattr(self.settings, "live_relay_fps", 30), default=30)
                quality = max(35, min(int(getattr(self.settings, "live_relay_quality", 55)), 85))
                width = max(240, min(int(getattr(self.settings, "live_relay_width", 640)), 1280))
                height = max(135, min(int(getattr(self.settings, "live_relay_height", 360)), 720))
                stream_epoch_ms = int(time.time() * 1000)
                sequence = 0
                uploader = _LatestFrameUploader(
                    camera_id,
                    upload=lambda payload: self._post_frame(camera_id, **payload),
                    completed=lambda: self._record_upload_stat(camera_id, "completed"),
                    failed=lambda exc: self._record_upload_failure(camera_id, exc),
                    replaced=lambda: self._record_upload_stat(camera_id, "replaced_pending"),
                )
                for capture in self.camera_agent.raw_frames(
                    camera,
                    fps=fps,
                    max_width=width,
                    max_height=height,
                ):
                    if self._stop.is_set() or stop_event.is_set():
                        break
                    source_frame = capture.get("frame") if isinstance(capture, dict) else None
                    if source_frame is None:
                        continue
                    source_key = str(capture.get("source_key") or "")
                    privacy_mode = normalize_privacy_mode(self.privacy_mode_resolver())
                    self._camera_privacy_modes[int(camera_id)] = privacy_mode
                    try:
                        if privacy_mode == "skeleton" and self.privacy_renderer is None:
                            raise PrivacyCalibrationRequired(camera_id, "privacy_renderer_unavailable")
                        if self.privacy_renderer is not None:
                            frame = self.privacy_renderer.render_frame(
                                camera_id,
                                source_frame,
                                privacy_mode,
                                quality=quality,
                                source_key=source_key,
                                frame_id=str(capture.get("frame_id") or ""),
                                captured_at=str(capture.get("captured_at") or ""),
                                captured_monotonic=capture.get("captured_monotonic"),
                            )
                        else:
                            frame = self._encode_frame(source_frame, quality)
                    except PrivacyCalibrationRequired as exc:
                        self._record_upload_stat(camera_id, "privacy_blocked")
                        self._camera_privacy_states[camera_id] = {
                            "status": self._privacy_block_status(exc.reason),
                            "reason": exc.reason,
                        }
                        continue
                    except Exception as exc:
                        self._record_upload_stat(camera_id, "render_failed")
                        self._camera_privacy_states[camera_id] = {
                            "status": "render_error",
                            "reason": str(exc)[:240],
                        }
                        self.last_error = f"camera {camera_id}: privacy render failed: {exc}"
                        continue
                    self._camera_privacy_states[camera_id] = {
                        "status": "ready",
                        "reason": "",
                    }
                    sequence += 1
                    captured_at = str(capture.get("captured_at") or self._utc_iso())
                    uploader.submit({
                        "frame": frame,
                        "privacy_mode": privacy_mode,
                        "captured_at": captured_at,
                        "captured_monotonic": capture.get("captured_monotonic"),
                        "stream_epoch_ms": stream_epoch_ms,
                        "sequence": sequence,
                    })
                    self._record_upload_stat(camera_id, "submitted")
            except Exception as exc:
                self.last_error = f"camera {camera_id}: {exc}"
                time.sleep(2.0)
            finally:
                if uploader is not None:
                    uploader.close(drain=not self._stop.is_set())
                self._close_connection(camera_id)

    def _encode_frame(self, frame: Any, quality: int) -> bytes:
        cv2 = _load_cv2()
        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), max(35, min(int(quality), 85))],
        )
        if not ok:
            raise RuntimeError("live relay frame encoding failed")
        return encoded.tobytes()

    @staticmethod
    def _privacy_block_status(reason: str) -> str:
        normalized = str(reason or "calibration_required")
        if normalized == "calibration_in_progress":
            return "calibrating"
        if normalized == "scene_revalidation_required":
            return "scene_review_required"
        if normalized in {"stream_revalidation_required", "background_state_changed"}:
            return "revalidating"
        return "calibration_required"

    def _record_upload_stat(self, camera_id: int, field: str) -> None:
        with self._upload_stats_lock:
            stats = self._camera_upload_stats.setdefault(int(camera_id), {
                "submitted": 0,
                "completed": 0,
                "failed": 0,
                "replaced_pending": 0,
                "privacy_blocked": 0,
                "render_failed": 0,
            })
            stats[field] = int(stats.get(field, 0)) + 1

    def _record_upload_failure(self, camera_id: int, exc: Exception) -> None:
        self._record_upload_stat(camera_id, "failed")
        self.last_error = f"camera {camera_id}: {exc}"

    def _record_upload_sample(
        self,
        camera_id: int,
        latency_ms: float,
        *,
        accepted: bool,
        frame_age_ms: float | None = None,
    ) -> None:
        now = time.monotonic()
        with self._upload_stats_lock:
            samples = self._camera_upload_samples.setdefault(int(camera_id), deque())
            samples.append((
                now,
                max(0.0, float(latency_ms)),
                bool(accepted),
                max(0.0, float(frame_age_ms)) if frame_age_ms is not None else None,
            ))
            cutoff = now - 60.0
            while samples and samples[0][0] < cutoff:
                samples.popleft()

    def _upload_stats_snapshot(self) -> Dict[str, Dict[str, Any]]:
        now = time.monotonic()
        with self._upload_stats_lock:
            snapshot: Dict[str, Dict[str, Any]] = {}
            stats_store = self._camera_upload_stats
            sample_store = self._camera_upload_samples
            camera_ids = sorted(set(stats_store) | set(sample_store))
            for camera_id in camera_ids:
                stats = stats_store.get(camera_id, {})
                samples = sample_store.get(camera_id, ())
                recent = [sample for sample in samples if sample[0] >= now - 10.0]
                latencies = sorted(sample[1] for sample in recent)
                accepted = sum(1 for sample in recent if sample[2])
                frame_ages = sorted(sample[3] for sample in recent if sample[3] is not None)
                completed = len(recent)
                item: Dict[str, Any] = dict(stats)
                item["window_seconds"] = 10
                item["completed_fps"] = round(completed / 10.0, 2)
                item["accepted_fps"] = round(accepted / 10.0, 2)
                item["upload_latency_ms_p95"] = round(self._percentile(latencies, 0.95), 2)
                item["upload_latency_ms_max"] = round(latencies[-1], 2) if latencies else 0.0
                item["source_to_cloud_ms_p95"] = round(self._percentile(frame_ages, 0.95), 2)
                item["source_to_cloud_ms_max"] = round(frame_ages[-1], 2) if frame_ages else 0.0
                submitted = int(stats.get("submitted", 0))
                item["pending_replace_ratio"] = round(
                    int(stats.get("replaced_pending", 0)) / submitted,
                    4,
                ) if submitted else 0.0
                snapshot[str(camera_id)] = item
            return snapshot

    def _percentile(self, values: list[float], percentile: float) -> float:
        if not values:
            return 0.0
        index = min(len(values) - 1, max(0, int((len(values) - 1) * percentile)))
        return values[index]

    @staticmethod
    def _frame_age_ms(captured_monotonic: Any) -> float | None:
        try:
            captured = float(captured_monotonic)
        except (TypeError, ValueError):
            return None
        now = time.monotonic()
        if captured <= 0.0 or captured > now + 1.0 or now - captured > 3600.0:
            return None
        return (now - captured) * 1000.0

    def _post_frame(
        self,
        local_camera_id: int,
        frame: bytes,
        *,
        privacy_mode: str = "original",
        captured_at: str | None = None,
        captured_monotonic: float | None = None,
        stream_epoch_ms: int | None = None,
        sequence: int | None = None,
    ) -> None:
        remote_camera_id = self.remote_camera_id_resolver(local_camera_id) or local_camera_id
        params = {
            "camera_id": str(remote_camera_id),
            "local_camera_id": str(local_camera_id),
            "content_type": "image/jpeg",
            "captured_at": captured_at or self._utc_iso(),
            "privacy_mode": normalize_privacy_mode(privacy_mode),
        }
        if stream_epoch_ms is not None:
            params["stream_epoch_ms"] = str(max(0, int(stream_epoch_ms)))
        if sequence is not None:
            params["sequence"] = str(max(0, int(sequence)))
        url = f"{self._base_url()}/api/v1/device/live-frames/upload?{urlencode(params)}"
        headers = {
            "Authorization": f"Bearer {self._device_token()}",
            "X-GoHome-Device-Id": self.device_id_resolver(),
            "Content-Type": "image/jpeg",
            "Accept": "application/json",
        }
        timeout = max(1.0, float(getattr(self.settings, "live_relay_request_timeout_seconds", 2.0)))
        started = time.monotonic()
        raw = self._post_frame_keepalive(local_camera_id, url, frame, headers, timeout)
        self.last_relay_at = self._utc_iso()
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {}
        requested_privacy_mode = normalize_privacy_mode(
            payload.get("requested_privacy_mode"),
            privacy_mode,
        )
        accepted = payload.get("accepted") is not False and payload.get("stale_ignored") is not True
        self._record_upload_sample(
            local_camera_id,
            (time.monotonic() - started) * 1000.0,
            accepted=accepted,
            frame_age_ms=self._frame_age_ms(captured_monotonic),
        )
        if self.privacy_mode_observer is not None:
            self.privacy_mode_observer(requested_privacy_mode)
        self._camera_privacy_modes[int(local_camera_id)] = normalize_privacy_mode(privacy_mode)
        self.last_result = {
            "camera_id": int(local_camera_id),
            "remote_camera_id": str(remote_camera_id),
            "size": len(frame),
            "privacy_mode": normalize_privacy_mode(privacy_mode),
            "requested_privacy_mode": requested_privacy_mode,
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
            self._close_current_connection(local_camera_id)
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
        connection_key = (int(local_camera_id), get_ident())
        with self._http_connections_lock:
            connection = self._http_connections.get(connection_key)
        if connection is None:
            connection_class = HTTPSConnection if parts.scheme == "https" else HTTPConnection
            connection = connection_class(parts.hostname, parts.port, timeout=timeout)
            with self._http_connections_lock:
                self._http_connections[connection_key] = connection
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
        with self._http_connections_lock:
            connections = [
                self._http_connections.pop(key)
                for key in list(self._http_connections)
                if key[0] == int(local_camera_id)
            ]
        for connection in connections:
            try:
                connection.close()
            except Exception:
                pass

    def _close_current_connection(self, local_camera_id: int) -> None:
        connection_key = (int(local_camera_id), get_ident())
        with self._http_connections_lock:
            connection = self._http_connections.pop(connection_key, None)
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

    def _close_connections(self) -> None:
        with self._http_connections_lock:
            camera_ids = {key[0] for key in self._http_connections}
        for camera_id in camera_ids:
            self._close_connection(camera_id)

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
        issued_token = str(self.token_resolver() or "").strip()
        if bool(getattr(self.settings, "require_issued_device_token", False)):
            return issued_token
        return issued_token or str(getattr(self.settings, "device_api_token", "") or "").strip()

    def _utc_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()
