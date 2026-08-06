from __future__ import annotations

from hashlib import sha256
from threading import Event, Lock, Thread
from typing import Any, Callable, Dict
import shutil
import time

from .camera_agent import bounded_stream_fps
from .h264_publisher import H264StreamPublisher, build_rtsps_publish_url, redact_publish_url
from .video_privacy import normalize_privacy_mode
from .vision.privacy_background import PrivacyCalibrationRequired


class LiveRelayAgent:
    """Own one persistent encoded publisher for each enabled camera."""

    version = "persistent-live-relay-v1"

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
        privacy_renderer: Any | None = None,
        publisher_factory: Callable[..., H264StreamPublisher] | None = None,
    ) -> None:
        self.storage = storage
        self.settings = settings
        self.camera_agent = camera_agent
        self.device_id_resolver = device_id_resolver
        self.token_resolver = token_resolver
        self.remote_camera_id_resolver = remote_camera_id_resolver
        self.privacy_mode_resolver = privacy_mode_resolver or (lambda: "original")
        self.privacy_renderer = privacy_renderer
        self.publisher_factory = publisher_factory or H264StreamPublisher
        self._stop = Event()
        self._wake = Event()
        self._thread: Thread | None = None
        self._camera_threads: Dict[int, Thread] = {}
        self._camera_stops: Dict[int, Event] = {}
        self._camera_stop_reasons: Dict[int, str] = {}
        self._camera_signatures: Dict[int, tuple[Any, ...]] = {}
        self._camera_lifecycle: Dict[int, Dict[str, Any]] = {}
        self._publishers: Dict[int, H264StreamPublisher] = {}
        self._state_lock = Lock()
        self._camera_privacy_modes: Dict[int, str] = {}
        self._camera_privacy_states: Dict[int, Dict[str, Any]] = {}
        self._camera_errors: Dict[int, Dict[str, str]] = {}
        self._recovered_camera_errors: Dict[int, Dict[str, str]] = {}
        self._delivery_status_callback: Callable[[], Any] | None = None
        self._delivery_status_signatures: Dict[int, tuple[Any, ...]] = {}
        self._service_error = ""
        self.last_loop_started_at: str | None = None
        self.last_relay_at: str | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def last_error(self) -> str:
        with self._state_lock:
            if self._service_error:
                return self._service_error
            for camera_id in sorted(self._camera_errors):
                message = str(self._camera_errors[camera_id].get("message") or "")
                if message:
                    return f"camera {camera_id}: {message}"
            return ""

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
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=10.0)
        if thread is None or not thread.is_alive():
            self._thread = None

    def wake(self) -> None:
        self._wake.set()

    def set_delivery_status_callback(self, callback: Callable[[], Any] | None) -> None:
        self._delivery_status_callback = callback

    def camera_delivery_status(self, camera_id: int) -> Dict[str, Any]:
        camera_id = int(camera_id)
        with self._state_lock:
            publisher = self._publishers.get(camera_id)
            privacy_state = dict(self._camera_privacy_states.get(camera_id) or {})
            privacy_mode = self._camera_privacy_modes.get(
                camera_id,
                normalize_privacy_mode(self.privacy_mode_resolver()),
            )
            camera_error = str((self._camera_errors.get(camera_id) or {}).get("message") or "")
            thread = self._camera_threads.get(camera_id)
            thread_active = bool(thread and thread.is_alive())
        publisher_status = publisher.status() if publisher is not None else {}
        privacy_status = str(privacy_state.get("status") or ("starting" if thread_active else "unavailable"))
        reason = str(
            privacy_state.get("reason")
            or publisher_status.get("last_error")
            or camera_error
            or ""
        )[:120]
        publish_ready = bool(
            privacy_status == "ready"
            and publisher_status.get("publish_ready")
            and publisher_status.get("running")
            and not publisher_status.get("paused")
        )
        return {
            "privacy_status": privacy_status,
            "publish_ready": publish_ready,
            "privacy_mode": normalize_privacy_mode(privacy_mode),
            "output_fps": round(float(publisher_status.get("encoder_input_fps_10s") or 0.0), 2),
            "reason": reason,
        }

    def handle_camera_source_transition(self, transition: Dict[str, Any]) -> None:
        camera_id = int(transition.get("camera_id") or 0)
        if camera_id <= 0:
            return
        reason = str(transition.get("reason") or "source_transition")
        if self._is_stream_discontinuity(transition):
            self._pause_camera_publisher(camera_id, reason)
            self._wake.set()
            return
        self._request_camera_stop(
            camera_id,
            reason,
        )
        self._wake.set()

    @staticmethod
    def _is_stream_discontinuity(transition: Dict[str, Any]) -> bool:
        transition_type = str(transition.get("transition_type") or "").strip().lower()
        if transition_type:
            return transition_type == "stream_discontinuity"
        return str(transition.get("reason") or "").strip().lower().startswith("stream_")

    def _pause_camera_publisher(self, camera_id: int, reason: str) -> None:
        resolved_reason = str(reason or "stream_discontinuity")[:240]
        with self._state_lock:
            publisher = self._publishers.get(int(camera_id))
        if publisher is not None:
            publisher.pause(resolved_reason)
        self._set_privacy_state(
            int(camera_id),
            "revalidating",
            "stream_revalidation_required",
        )
        self._notify_delivery_status_if_changed(int(camera_id))

    def status(self) -> Dict[str, Any]:
        configured, reason = self._configured()
        with self._state_lock:
            publishers = list(sorted(self._publishers.items()))
            privacy_modes = dict(self._camera_privacy_modes)
            privacy_states = {
                str(camera_id): dict(state)
                for camera_id, state in sorted(self._camera_privacy_states.items())
            }
            active_cameras = sorted(
                camera_id
                for camera_id, thread in self._camera_threads.items()
                if thread.is_alive()
            )
            camera_errors = {
                str(camera_id): dict(error)
                for camera_id, error in sorted(self._camera_errors.items())
            }
            recovered_camera_errors = {
                str(camera_id): dict(error)
                for camera_id, error in sorted(self._recovered_camera_errors.items())
            }
            camera_lifecycle = {
                str(camera_id): {
                    **dict(state),
                    "active": bool(
                        self._camera_threads.get(camera_id)
                        and self._camera_threads[camera_id].is_alive()
                    ),
                }
                for camera_id, state in sorted(self._camera_lifecycle.items())
            }
            current_error = self._service_error
            if not current_error:
                for camera_id in sorted(self._camera_errors):
                    message = str(self._camera_errors[camera_id].get("message") or "")
                    if message:
                        current_error = f"camera {camera_id}: {message}"
                        break
        publisher_status = {
            str(camera_id): publisher.status()
            for camera_id, publisher in publishers
        }
        return {
            "schema_version": self.version,
            "enabled": bool(getattr(self.settings, "live_relay_enabled", True)),
            "running": self.is_running,
            "configured": configured,
            "reason": reason,
            "transport": "h264-rtsps",
            "publish_base_url": redact_publish_url(self._publish_base_url()),
            "fps": self._fps(),
            "bitrate_kbps": self._bitrate_kbps(),
            "active_cameras": active_cameras,
            "last_loop_started_at": self.last_loop_started_at,
            "last_relay_at": self.last_relay_at,
            "last_error": current_error,
            "camera_errors": camera_errors,
            "recovered_camera_errors": recovered_camera_errors,
            "camera_lifecycle": camera_lifecycle,
            "cameras": publisher_status,
            "privacy_mode": normalize_privacy_mode(self.privacy_mode_resolver()),
            "camera_privacy_modes": {
                str(camera_id): privacy_modes.get(
                    camera_id,
                    normalize_privacy_mode(self.privacy_mode_resolver()),
                )
                for camera_id in active_cameras
            },
            "camera_privacy_states": privacy_states,
            "privacy_renderer": (
                self.privacy_renderer.status()
                if callable(getattr(self.privacy_renderer, "status", None))
                else {}
            ),
        }

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                self.last_loop_started_at = self._utc_iso()
                configured, reason = self._configured()
                if configured:
                    self._set_service_error("")
                    self._sync_camera_threads()
                else:
                    self._stop_all_camera_threads(reason=reason)
                    self._set_service_error("" if reason == "live_relay_disabled" else reason)
                self._wake.wait(3.0)
                self._wake.clear()
        finally:
            self._stop_all_camera_threads(reason="relay_stopping")

    def _sync_camera_threads(self) -> None:
        cameras = [
            camera for camera in self.storage.list_cameras(include_secret=True)
            if camera.get("enabled") and str(camera.get("stream_url") or "").strip()
        ]
        active_ids = {int(camera["id"]) for camera in cameras if camera.get("id")}
        signatures = {
            int(camera["id"]): self._camera_signature(camera)
            for camera in cameras
            if camera.get("id")
        }
        with self._state_lock:
            existing = {
                camera_id: (
                    thread,
                    self._camera_stops.get(camera_id),
                    self._camera_signatures.get(camera_id),
                )
                for camera_id, thread in self._camera_threads.items()
            }
        restart_reasons: Dict[int, str] = {}
        for camera_id, (thread, stop_event, signature) in existing.items():
            changed = signature != signatures.get(camera_id)
            stopping = stop_event is not None and stop_event.is_set()
            if camera_id not in active_ids:
                reason = "camera_removed_or_disabled"
            elif not thread.is_alive():
                reason = "camera_thread_exited"
            elif changed:
                reason = "camera_signature_changed"
            elif stopping:
                with self._state_lock:
                    reason = self._camera_stop_reasons.get(camera_id, "camera_stop_requested")
            else:
                continue
            stopped = self._stop_camera(camera_id, reason=reason)
            if stopped and camera_id in active_ids:
                restart_reasons[camera_id] = reason

        for camera in cameras:
            camera_id = int(camera["id"])
            with self._state_lock:
                thread = self._camera_threads.get(camera_id)
            if thread is not None and thread.is_alive():
                continue
            stop_event = Event()
            thread = Thread(
                target=self._run_camera,
                args=(dict(camera), stop_event),
                name=f"gohome-live-relay-camera-{camera_id}",
                daemon=True,
            )
            with self._state_lock:
                self._camera_stop_reasons.pop(camera_id, None)
                self._camera_stops[camera_id] = stop_event
                self._camera_signatures[camera_id] = signatures[camera_id]
                self._camera_threads[camera_id] = thread
                lifecycle = dict(self._camera_lifecycle.get(camera_id) or {})
                start_reason = restart_reasons.get(
                    camera_id,
                    "initial" if not int(lifecycle.get("thread_starts") or 0) else "camera_thread_recovered",
                )
                self._camera_lifecycle[camera_id] = {
                    **lifecycle,
                    "thread_starts": int(lifecycle.get("thread_starts") or 0) + 1,
                    "thread_stops": int(lifecycle.get("thread_stops") or 0),
                    "last_start_reason": start_reason,
                    "last_started_at": self._utc_iso(),
                }
            thread.start()

    def _request_camera_stop(self, camera_id: int, reason: str) -> None:
        camera_id = int(camera_id)
        resolved_reason = str(reason or "camera_stop_requested")
        with self._state_lock:
            stop_event = self._camera_stops.get(camera_id)
            publisher = self._publishers.get(camera_id)
            thread = self._camera_threads.get(camera_id)
            if stop_event is None and publisher is None and thread is None:
                return
            self._camera_stop_reasons[camera_id] = resolved_reason
        if stop_event is not None:
            stop_event.set()
        if publisher is not None:
            publisher.pause(resolved_reason)

    def _stop_camera(self, camera_id: int, *, reason: str) -> bool:
        camera_id = int(camera_id)
        resolved_reason = str(reason or "camera_stopping")
        with self._state_lock:
            stop_event = self._camera_stops.get(camera_id)
            publisher = self._publishers.get(camera_id)
            thread = self._camera_threads.get(camera_id)
            requested_reason = self._camera_stop_reasons.get(camera_id)
        if requested_reason:
            resolved_reason = requested_reason
        if stop_event is not None:
            stop_event.set()
        if publisher is not None:
            publisher.pause(resolved_reason)
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)
        if thread is not None and thread.is_alive():
            self._set_camera_error(camera_id, "capture thread did not stop within 5 seconds")
            return False
        with self._state_lock:
            if self._camera_threads.get(camera_id) is thread:
                self._camera_threads.pop(camera_id, None)
            if self._camera_stops.get(camera_id) is stop_event:
                self._camera_stops.pop(camera_id, None)
            self._camera_stop_reasons.pop(camera_id, None)
            self._camera_signatures.pop(camera_id, None)
            self._camera_privacy_modes.pop(camera_id, None)
            self._camera_privacy_states.pop(camera_id, None)
            lifecycle = dict(self._camera_lifecycle.get(camera_id) or {})
            self._camera_lifecycle[camera_id] = {
                **lifecycle,
                "thread_starts": int(lifecycle.get("thread_starts") or 0),
                "thread_stops": int(lifecycle.get("thread_stops") or 0) + 1,
                "last_stop_reason": resolved_reason,
                "last_stopped_at": self._utc_iso(),
            }
        self._clear_camera_error(camera_id)
        return True

    def _stop_all_camera_threads(self, *, reason: str) -> None:
        with self._state_lock:
            stop_events = list(self._camera_stops.values())
            publishers = list(self._publishers.values())
            camera_ids = list(self._camera_threads)
            for camera_id in camera_ids:
                self._camera_stop_reasons[camera_id] = str(reason or "relay_stopping")
        for stop_event in stop_events:
            stop_event.set()
        for publisher in publishers:
            publisher.pause(reason)
        for camera_id in camera_ids:
            self._stop_camera(camera_id, reason=reason)

    def _camera_signature(self, camera: Dict[str, Any]) -> tuple[Any, ...]:
        token_digest = sha256(self._device_token().encode("utf-8")).hexdigest()
        return (
            int(camera.get("id") or 0),
            str(camera.get("stream_url") or "").strip(),
            str(camera.get("username") or ""),
            str(camera.get("password") or ""),
            bool(camera.get("enabled", True)),
            str(self.remote_camera_id_resolver(int(camera.get("id") or 0)) or ""),
            self.device_id_resolver(),
            token_digest,
            self._publish_base_url(),
            self._ffmpeg_path(),
            self._fps(),
            self._width(),
            self._height(),
            self._bitrate_kbps(),
            self._write_timeout_seconds(),
            self._startup_timeout_seconds(),
        )

    def _run_camera(self, camera: Dict[str, Any], stop_event: Event) -> None:
        camera_id = int(camera["id"])
        publisher: H264StreamPublisher | None = None
        try:
            remote_camera_id = self.remote_camera_id_resolver(camera_id) or camera_id
            publish_url = build_rtsps_publish_url(
                self._publish_base_url(),
                device_id=self.device_id_resolver(),
                device_token=self._device_token(),
                camera_id=remote_camera_id,
            )
            publisher = self.publisher_factory(
                camera_id=camera_id,
                publish_url=publish_url,
                ffmpeg_path=self._ffmpeg_path(),
                fps=self._fps(),
                bitrate_kbps=self._bitrate_kbps(),
                write_timeout_seconds=self._write_timeout_seconds(),
                startup_timeout_seconds=self._startup_timeout_seconds(),
            )
            with self._state_lock:
                self._publishers[camera_id] = publisher
            while not self._stop.is_set() and not stop_event.is_set():
                try:
                    for capture in self.camera_agent.raw_frames(
                        camera,
                        fps=self._fps(),
                        max_width=self._width(),
                        max_height=self._height(),
                    ):
                        if self._stop.is_set() or stop_event.is_set():
                            break
                        source_frame = capture.get("frame") if isinstance(capture, dict) else None
                        if source_frame is None:
                            continue
                        source_key = str(capture.get("source_key") or "")
                        privacy_mode = normalize_privacy_mode(self.privacy_mode_resolver())
                        with self._state_lock:
                            self._camera_privacy_modes[camera_id] = privacy_mode
                        try:
                            if privacy_mode == "skeleton" and self.privacy_renderer is None:
                                raise PrivacyCalibrationRequired(camera_id, "privacy_renderer_unavailable")
                            output = (
                                self.privacy_renderer.render_image(
                                    camera_id,
                                    source_frame,
                                    privacy_mode,
                                    source_key=source_key,
                                    frame_id=str(capture.get("frame_id") or ""),
                                    captured_at=str(capture.get("captured_at") or ""),
                                    captured_monotonic=capture.get("captured_monotonic"),
                                )
                                if self.privacy_renderer is not None
                                else source_frame
                            )
                        except PrivacyCalibrationRequired as exc:
                            publisher.pause(exc.reason)
                            self._clear_camera_error(camera_id)
                            self._set_privacy_state(
                                camera_id,
                                self._privacy_block_status(exc.reason),
                                exc.reason,
                            )
                            self._notify_delivery_status_if_changed(camera_id)
                            continue
                        except Exception as exc:
                            publisher.pause(f"render_error: {exc}")
                            self._set_privacy_state(camera_id, "render_error", str(exc)[:240])
                            self._set_camera_error(camera_id, f"privacy render failed: {exc}")
                            self._notify_delivery_status_if_changed(camera_id)
                            continue
                        if self._stop.is_set() or stop_event.is_set():
                            publisher.pause("camera_stopping")
                            break
                        self._set_privacy_state(camera_id, "ready", "")
                        publisher.submit(
                            output,
                            frame_id=str(
                                capture.get("delivery_frame_id")
                                or capture.get("frame_id")
                                or ""
                            ),
                            captured_monotonic=(
                                capture.get("delivery_captured_monotonic")
                                if capture.get("delivery_captured_monotonic") is not None
                                else capture.get("captured_monotonic")
                            ),
                            privacy_mode=privacy_mode,
                            source_key=source_key,
                        )
                        self._notify_delivery_status_if_changed(camera_id)
                        self._clear_camera_error(camera_id)
                        self.last_relay_at = self._utc_iso()
                    if not self._stop.is_set() and not stop_event.is_set():
                        time.sleep(0.5)
                except Exception as exc:
                    self._set_camera_error(camera_id, str(exc))
                    publisher.pause(str(exc))
                    self._notify_delivery_status_if_changed(camera_id)
                    time.sleep(2.0)
        except Exception as exc:
            self._set_camera_error(camera_id, f"publisher setup failed: {exc}")
            self._set_privacy_state(camera_id, "publisher_error", str(exc)[:240])
        finally:
            if publisher is not None:
                publisher.close()
            with self._state_lock:
                if self._publishers.get(camera_id) is publisher:
                    self._publishers.pop(camera_id, None)

    def _set_privacy_state(self, camera_id: int, status: str, reason: str) -> None:
        with self._state_lock:
            self._camera_privacy_states[int(camera_id)] = {
                "status": str(status),
                "reason": str(reason),
            }

    def _notify_delivery_status_if_changed(self, camera_id: int) -> None:
        status = self.camera_delivery_status(camera_id)
        signature = (
            status["privacy_status"],
            status["publish_ready"],
            status["privacy_mode"],
            status["reason"],
        )
        with self._state_lock:
            if self._delivery_status_signatures.get(int(camera_id)) == signature:
                return
            self._delivery_status_signatures[int(camera_id)] = signature
            callback = self._delivery_status_callback
        if callback is not None:
            callback()

    def _set_service_error(self, message: str) -> None:
        with self._state_lock:
            self._service_error = str(message or "")[:240]

    def _set_camera_error(self, camera_id: int, message: str) -> None:
        resolved = str(message or "")[:240]
        if not resolved:
            self._clear_camera_error(camera_id)
            return
        with self._state_lock:
            self._camera_errors[int(camera_id)] = {
                "message": resolved,
                "occurred_at": self._utc_iso(),
            }

    def _clear_camera_error(self, camera_id: int) -> None:
        with self._state_lock:
            previous = self._camera_errors.pop(int(camera_id), None)
            if previous is not None:
                self._recovered_camera_errors[int(camera_id)] = {
                    **previous,
                    "recovered_at": self._utc_iso(),
                }

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

    def _configured(self) -> tuple[bool, str]:
        if not bool(getattr(self.settings, "live_relay_enabled", True)):
            return False, "live_relay_disabled"
        if not self._publish_base_url():
            return False, "media_publish_base_url_missing"
        if not self.device_id_resolver():
            return False, "device_id_missing"
        if not self._device_token():
            return False, "device_token_missing"
        try:
            build_rtsps_publish_url(
                self._publish_base_url(),
                device_id=self.device_id_resolver(),
                device_token=self._device_token(),
                camera_id="probe",
            )
        except Exception as exc:
            return False, str(exc)
        if shutil.which(self._ffmpeg_path()) is None:
            return False, "ffmpeg_unavailable"
        return True, "ready"

    def _publish_base_url(self) -> str:
        return str(getattr(self.settings, "media_publish_base_url", "") or "").strip().rstrip("/")

    def _device_token(self) -> str:
        issued_token = str(self.token_resolver() or "").strip()
        if bool(getattr(self.settings, "require_issued_device_token", False)):
            return issued_token
        return issued_token or str(getattr(self.settings, "device_api_token", "") or "").strip()

    def _ffmpeg_path(self) -> str:
        return str(getattr(self.settings, "media_publish_ffmpeg_path", "ffmpeg") or "ffmpeg").strip()

    def _fps(self) -> int:
        return bounded_stream_fps(getattr(self.settings, "live_relay_fps", 15), default=15)

    def _width(self) -> int:
        return max(240, min(int(getattr(self.settings, "live_relay_width", 640)), 1280))

    def _height(self) -> int:
        return max(135, min(int(getattr(self.settings, "live_relay_height", 360)), 720))

    def _bitrate_kbps(self) -> int:
        return max(256, min(int(getattr(self.settings, "media_publish_bitrate_kbps", 1200)), 8000))

    def _write_timeout_seconds(self) -> float:
        return max(0.1, float(getattr(self.settings, "media_publish_write_timeout_seconds", 0.75)))

    def _startup_timeout_seconds(self) -> float:
        return max(
            self._write_timeout_seconds(),
            float(getattr(self.settings, "media_publish_startup_timeout_seconds", 5.0)),
        )

    @staticmethod
    def _utc_iso() -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()
