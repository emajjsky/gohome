from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from threading import Condition, Event, Lock, Thread
from typing import Any, Callable, Dict, Generator, Tuple
from urllib.parse import quote, urlsplit, urlunsplit
import base64
import hashlib
import logging
import os
import time


NETWORK_CAPTURE_OPTIONS = "rtsp_transport;tcp|stimeout;3000000|rw_timeout;5000000|fflags;nobuffer|flags;low_delay|max_delay;100000|probesize;32|analyzeduration;0"
LOCAL_CAPTURE_WARMUP_SECONDS = 1.0
NETWORK_CAPTURE_WARMUP_SECONDS = 3.0
NETWORK_CAPTURE_MIN_READS = 8
NETWORK_CAPTURE_MAX_READS = 45
DEMO_STREAM_PREFIXES = ("demo:", "sample:", "mock:")
logger = logging.getLogger(__name__)
MAX_PREVIEW_FPS = 30
STREAM_RECONNECT_BASE_SECONDS = 0.5
STREAM_RECONNECT_MAX_SECONDS = 8.0
STREAM_FROZEN_RECONNECT_SECONDS = 3.0
STREAM_NEAR_BLACK_RECONNECT_SECONDS = 0.75
STREAM_NEAR_BLACK_CONFIRM_FRAMES = 5


class CameraError(RuntimeError):
    pass


def next_stream_frame_delay(
    *,
    previous_deadline: float,
    now: float,
    frame_interval: float,
) -> tuple[float, float]:
    interval = max(0.001, float(frame_interval))
    next_deadline = float(previous_deadline) + interval
    if now - next_deadline >= interval:
        return 0.0, float(now)
    return max(0.0, next_deadline - float(now)), next_deadline


def bounded_stream_fps(value: Any, *, default: int = 15) -> int:
    try:
        requested = int(value)
    except (TypeError, ValueError):
        requested = int(default)
    return max(1, min(requested, MAX_PREVIEW_FPS))


def stream_reconnect_delay(consecutive_failures: int) -> float:
    exponent = max(0, min(int(consecutive_failures) - 1, 8))
    return min(
        STREAM_RECONNECT_MAX_SECONDS,
        STREAM_RECONNECT_BASE_SECONDS * (2 ** exponent),
    )


def _load_cv2():
    try:
        import cv2  # type: ignore
    except ModuleNotFoundError as exc:
        raise CameraError("OpenCV is not installed. Run: python -m pip install -r requirements.txt") from exc
    return cv2


class _SharedStreamReader:
    def __init__(
        self,
        *,
        agent: "CameraAgent",
        camera: Dict[str, Any],
        source: Any,
        is_local_source: bool,
        source_label: str,
        stream_generation: int,
    ) -> None:
        self.agent = agent
        self.camera = dict(camera)
        self.source = source
        self.is_local_source = is_local_source
        self.source_label = source_label
        self.stream_generation = max(1, int(stream_generation))
        self.subscribers = 0
        self._condition = Condition()
        self._stop = Event()
        self._reconnect = Event()
        self._thread = Thread(
            target=self._run,
            name=f"gohome-camera-reader-{camera.get('id') or 'source'}",
            daemon=True,
        )
        self._sequence = 0
        self._last_error = ""
        self._last_error_at = ""
        self._last_frame_at = ""
        self._last_frame_monotonic: float | None = None
        self._frame_arrivals: deque[float] = deque(maxlen=600)
        self._decoded_arrivals: deque[float] = deque(maxlen=600)
        self._read_samples: deque[tuple[float, float]] = deque(maxlen=600)
        self._open_count = 0
        self._open_attempt_count = 0
        self._consecutive_failures = 0
        self._next_retry_monotonic: float | None = None
        self._read_failure_count = 0
        self._source_width = 0
        self._source_height = 0
        self._advertised_fps = 0.0
        self._decoded_frame_count = 0
        self._repeated_frame_count = 0
        self._consecutive_repeated_frames = 0
        self._near_black_frame_count = 0
        self._consecutive_near_black_frames = 0
        self._near_black_started_monotonic: float | None = None
        self._last_content_fingerprint = b""
        self._last_unique_frame_monotonic: float | None = None

    @property
    def is_stopped(self) -> bool:
        return self._stop.is_set()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._reconnect.set()
        with self._condition:
            self._condition.notify_all()
        self._thread.join(timeout=2)

    def request_reconnect(self) -> None:
        self._reconnect.set()

    def wait_for_update(self, after_sequence: int, timeout: float = 3.5) -> tuple[int, str]:
        with self._condition:
            self._condition.wait_for(
                lambda: self._sequence > after_sequence or self._stop.is_set(),
                timeout=max(0.1, float(timeout)),
            )
            if self._sequence <= after_sequence:
                return after_sequence, self._last_error
            return self._sequence, self._last_error

    def status(self) -> Dict[str, Any]:
        now = time.monotonic()
        with self._condition:
            arrivals = [value for value in self._frame_arrivals if value >= now - 10.0]
            decoded_arrivals = [value for value in self._decoded_arrivals if value >= now - 10.0]
            reads = [value for value in self._read_samples if value[0] >= now - 10.0]
            gaps_ms = [
                (current - previous) * 1000.0
                for previous, current in zip(arrivals, arrivals[1:])
            ]
            read_ms = [value[1] for value in reads]
            frame_age = (
                max(0.0, now - self._last_frame_monotonic)
                if self._last_frame_monotonic is not None
                else None
            )
            source_fps = (
                (len(arrivals) - 1) / max(0.001, arrivals[-1] - arrivals[0])
                if len(arrivals) >= 2
                else 0.0
            )
            decoded_fps = (
                (len(decoded_arrivals) - 1) / max(0.001, decoded_arrivals[-1] - decoded_arrivals[0])
                if len(decoded_arrivals) >= 2
                else 0.0
            )
            state = "streaming"
            if self._last_error:
                state = "retrying"
            elif self._consecutive_near_black_frames:
                state = "stale"
            elif frame_age is None:
                state = "warming"
            elif frame_age > 2.0:
                state = "stale"
            return {
                "state": state,
                "source_fps": round(source_fps, 2),
                "effective_fps": round(source_fps, 2),
                "decoded_fps": round(decoded_fps, 2),
                "advertised_fps": round(self._advertised_fps, 2),
                "latest_frame_age_ms": round(frame_age * 1000.0, 1) if frame_age is not None else None,
                "frame_gap_ms_p95": round(self._percentile(gaps_ms, 0.95), 1),
                "frame_gap_ms_max": round(max(gaps_ms), 1) if gaps_ms else 0.0,
                "read_latency_ms_p95": round(self._percentile(read_ms, 0.95), 1),
                "read_latency_ms_max": round(max(read_ms), 1) if read_ms else 0.0,
                "decoded_frames": self._decoded_frame_count,
                "unique_frames": self._sequence,
                "repeated_frames": self._repeated_frame_count,
                "consecutive_repeated_frames": self._consecutive_repeated_frames,
                "near_black_frames": self._near_black_frame_count,
                "consecutive_near_black_frames": self._consecutive_near_black_frames,
                "stream_generation": self.stream_generation,
                "open_count": self._open_count,
                "open_attempt_count": self._open_attempt_count,
                "reconnect_count": max(0, self._open_count - 1),
                "consecutive_failures": self._consecutive_failures,
                "next_retry_in_seconds": round(
                    max(0.0, self._next_retry_monotonic - now),
                    2,
                ) if self._next_retry_monotonic is not None else 0.0,
                "read_failure_count": self._read_failure_count,
                "source_width": self._source_width,
                "source_height": self._source_height,
                "last_frame_at": self._last_frame_at,
                "last_error": self._last_error,
                "last_error_at": self._last_error_at,
            }

    @staticmethod
    def _percentile(values: list[float], quantile: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * quantile))))
        return float(ordered[index])

    def _run(self) -> None:
        cv2 = _load_cv2()
        cap = None
        reconnect_count = 0
        try:
            while not self._stop.is_set():
                if cap is None or not cap.isOpened() or self._reconnect.is_set():
                    requested_reconnect = self._reconnect.is_set()
                    self._reconnect.clear()
                    if cap is not None:
                        cap.release()
                        if requested_reconnect:
                            self._invalidate_stream("stream_reconnect_requested")
                    self._record_open_attempt()
                    cap = self.agent._open_stream_capture(cv2, self.source, self.is_local_source)
                    if not cap.isOpened():
                        cap.release()
                        cap = None
                        self._set_error("stream open failed")
                        self._wait_after_failure()
                        continue
                    self._record_open(cv2, cap)
                    if reconnect_count:
                        logger.info(
                            "camera %s shared stream recovered after %s reconnect(s)",
                            self.camera.get("id"),
                            reconnect_count,
                        )
                    reconnect_count = 0

                read_started_at = time.monotonic()
                ok, frame = cap.read()
                read_finished_at = time.monotonic()
                if not ok or frame is None:
                    reconnect_count += 1
                    self._record_read_failure()
                    self._set_error("stream read failed")
                    logger.warning(
                        "camera %s shared stream read failed; reopening capture",
                        self.camera.get("id"),
                    )
                    cap.release()
                    cap = None
                    self._invalidate_stream("stream_read_failed")
                    self._wait_after_failure()
                    continue

                frame_disposition = self._record_frame(
                    cv2,
                    frame,
                    read_finished_at,
                    (read_finished_at - read_started_at) * 1000.0,
                )
                if frame_disposition == "near_black":
                    if self._consecutive_near_black_frames == 1:
                        self.agent._clear_camera_cache(int(self.camera.get("id") or 0))
                        logger.warning(
                            "camera %s emitted a near-black frame; suppressing invalid live output",
                            self.camera.get("id"),
                        )
                    if self._near_black_timed_out(read_finished_at):
                        self._set_error("stream remained near-black")
                        logger.warning(
                            "camera %s stream remained near-black; reopening capture",
                            self.camera.get("id"),
                        )
                        cap.release()
                        cap = None
                        self._invalidate_stream("stream_near_black")
                        self._wait_after_failure()
                    continue
                if frame_disposition == "repeated":
                    if self._pixels_frozen(read_finished_at):
                        self._set_error("stream pixels frozen")
                        logger.warning(
                            "camera %s stream pixels remained unchanged; reopening capture",
                            self.camera.get("id"),
                        )
                        cap.release()
                        cap = None
                        self._invalidate_stream("stream_pixels_frozen")
                        self._wait_after_failure()
                    continue
                self.agent._store_latest_frame(
                    self.camera,
                    frame,
                    self.source_label,
                    stream_generation=self.stream_generation,
                )
                with self._condition:
                    self._sequence += 1
                    self._last_error = ""
                    self._condition.notify_all()
        finally:
            if cap is not None:
                cap.release()

    def _set_error(self, message: str) -> None:
        with self._condition:
            self._last_error = message
            self._last_error_at = datetime.now(timezone.utc).isoformat()
            self._condition.notify_all()

    def _record_open(self, cv2: Any, cap: Any) -> None:
        with self._condition:
            self._open_count += 1
            try:
                advertised_fps = float(cap.get(cv2.CAP_PROP_FPS))
            except (AttributeError, TypeError, ValueError):
                advertised_fps = 0.0
            if 0.0 < advertised_fps < 240.0:
                self._advertised_fps = advertised_fps

    def _record_open_attempt(self) -> None:
        with self._condition:
            self._open_attempt_count += 1

    def _invalidate_stream(self, reason: str) -> None:
        with self._condition:
            self._last_content_fingerprint = b""
            self._last_unique_frame_monotonic = None
            self._last_frame_monotonic = None
            self._frame_arrivals.clear()
            self._decoded_arrivals.clear()
            self._read_samples.clear()
            self._consecutive_repeated_frames = 0
            self._consecutive_near_black_frames = 0
            self._near_black_started_monotonic = None
        self.stream_generation = self.agent.invalidate_stream_generation(
            self.camera,
            reader=self,
            reason=reason,
        )

    def _wait_after_failure(self) -> None:
        with self._condition:
            self._consecutive_failures += 1
            delay = stream_reconnect_delay(self._consecutive_failures)
            self._next_retry_monotonic = time.monotonic() + delay
        self._stop.wait(delay)
        with self._condition:
            self._next_retry_monotonic = None

    def _record_read_failure(self) -> None:
        with self._condition:
            self._read_failure_count += 1

    def _record_frame(self, cv2: Any, frame: Any, arrived_at: float, read_latency_ms: float) -> str:
        try:
            height, width = frame.shape[:2]
        except (AttributeError, ValueError):
            height, width = 0, 0
        near_black = self.agent._frame_is_near_black(cv2, frame)
        fingerprint = b"" if near_black else self.agent.frame_content_fingerprint(frame)
        with self._condition:
            self._decoded_frame_count += 1
            self._decoded_arrivals.append(float(arrived_at))
            self._read_samples.append((float(arrived_at), max(0.0, float(read_latency_ms))))
            if near_black:
                self._near_black_frame_count += 1
                self._consecutive_near_black_frames += 1
                if self._near_black_started_monotonic is None:
                    self._near_black_started_monotonic = float(arrived_at)
                    self._frame_arrivals.clear()
                    self._last_frame_monotonic = None
                    self._last_unique_frame_monotonic = None
                    self._last_content_fingerprint = b""
                return "near_black"
            self._consecutive_near_black_frames = 0
            self._near_black_started_monotonic = None
            if fingerprint and fingerprint == self._last_content_fingerprint:
                self._repeated_frame_count += 1
                self._consecutive_repeated_frames += 1
                return "repeated"
            self._last_content_fingerprint = fingerprint
            self._consecutive_repeated_frames = 0
            self._frame_arrivals.append(float(arrived_at))
            self._last_frame_monotonic = float(arrived_at)
            self._last_unique_frame_monotonic = float(arrived_at)
            self._last_frame_at = datetime.now(timezone.utc).isoformat()
            self._source_width = int(width)
            self._source_height = int(height)
            self._consecutive_failures = 0
            self._next_retry_monotonic = None
            return "unique"

    def _near_black_timed_out(self, now: float) -> bool:
        with self._condition:
            if self._near_black_started_monotonic is None:
                return False
            return (
                self._consecutive_near_black_frames >= STREAM_NEAR_BLACK_CONFIRM_FRAMES
                and float(now) - self._near_black_started_monotonic
                >= STREAM_NEAR_BLACK_RECONNECT_SECONDS
            )

    def _pixels_frozen(self, now: float) -> bool:
        with self._condition:
            if self._last_unique_frame_monotonic is None:
                return False
            return (
                self._consecutive_repeated_frames > 0
                and float(now) - self._last_unique_frame_monotonic >= STREAM_FROZEN_RECONNECT_SECONDS
            )


class CameraAgent:
    def __init__(self, snapshot_dir: Path) -> None:
        self.snapshot_dir = snapshot_dir
        self._capture_lock = Lock()
        self._frame_cache_lock = Lock()
        self._frame_cache_condition = Condition(self._frame_cache_lock)
        self._frame_cache: Dict[str, Dict[str, Any]] = {}
        self._frame_sequences: Dict[str, int] = {}
        self._shared_stream_lock = Lock()
        self._reconcile_lock = Lock()
        self._shared_streams: Dict[str, _SharedStreamReader] = {}
        self._managed_streams: Dict[int, tuple[Dict[str, Any], _SharedStreamReader]] = {}
        self._stream_generations: Dict[int, int] = {}
        self._source_change_listeners: list[Callable[[Dict[str, Any]], Any]] = []

    def add_source_change_listener(self, listener: Callable[[Dict[str, Any]], Any]) -> None:
        if not callable(listener):
            raise TypeError("camera source change listener must be callable")
        with self._shared_stream_lock:
            if listener not in self._source_change_listeners:
                self._source_change_listeners.append(listener)

    def reconcile_managed_streams(self, cameras: list[Dict[str, Any]]) -> None:
        """Keep one reader per enabled real camera regardless of preview subscribers."""
        desired: dict[int, Dict[str, Any]] = {}
        for camera in cameras:
            if not camera.get("enabled", True):
                continue
            source, _backend, source_label = self.resolve_capture_source(camera)
            if self._is_demo_source(source):
                continue
            camera_id = int(camera.get("id") or 0)
            if camera_id <= 0:
                continue
            desired[camera_id] = {
                **camera,
                "_managed_source": source,
                "_managed_local": isinstance(source, int),
                "_managed_source_label": source_label,
            }

        transitions: list[Dict[str, Any]] = []
        with self._reconcile_lock:
            with self._shared_stream_lock:
                existing = dict(self._managed_streams)
            for camera_id, (previous, reader) in existing.items():
                current = desired.get(camera_id)
                if current is not None and self._camera_signature(previous) == self._camera_signature(current):
                    continue
                with self._shared_stream_lock:
                    self._managed_streams.pop(camera_id, None)
                self._retire_shared_stream(reader)
                self._clear_camera_cache(camera_id)
                transitions.append({
                    "camera_id": camera_id,
                    "reason": "source_changed" if current is not None else "camera_removed_or_disabled",
                    "previous": self._public_camera_identity(previous),
                    "current": self._public_camera_identity(current),
                })

            for transition in transitions:
                self._notify_source_change(transition)

            for camera_id, camera in desired.items():
                with self._shared_stream_lock:
                    if camera_id in self._managed_streams:
                        continue
                reader = self._acquire_shared_stream(
                    camera,
                    source=camera["_managed_source"],
                    is_local_source=bool(camera["_managed_local"]),
                    source_label=str(camera["_managed_source_label"]),
                )
                release_duplicate = False
                with self._shared_stream_lock:
                    if camera_id not in self._managed_streams:
                        self._managed_streams[camera_id] = (camera, reader)
                    else:
                        release_duplicate = True
                if release_duplicate:
                    self._release_shared_stream(camera, reader)

    def managed_stream_status(self) -> Dict[str, Any]:
        with self._shared_stream_lock:
            managed = list(self._managed_streams.items())
        streams = []
        for _camera_id, (camera, reader) in managed:
            streams.append(
                {
                    "camera_id": camera.get("id"),
                    "configured_source_key": self.frame_source_key(camera),
                    "subscribers": reader.subscribers,
                    "running": reader._thread.is_alive(),
                    **reader.status(),
                }
            )
        return {"managed_stream_count": len(streams), "streams": streams}

    def managed_camera_status(self, camera: Dict[str, Any]) -> Dict[str, Any] | None:
        reader = self._managed_reader(camera)
        if reader is None:
            return None
        return {
            "camera_id": int(camera.get("id") or 0),
            "configured_source_key": self.frame_source_key(camera),
            **reader.status(),
        }

    def frame_content_fingerprint(self, frame: Any) -> bytes:
        try:
            height, width = frame.shape[:2]
            sample = frame[::8, ::8]
            identity = int(width).to_bytes(4, "little") + int(height).to_bytes(4, "little")
            return hashlib.blake2s(identity + sample.tobytes(), digest_size=12).digest()
        except (AttributeError, TypeError, ValueError):
            return b""

    def _camera_signature(self, camera: Dict[str, Any]) -> tuple[Any, ...]:
        return (
            int(camera.get("id") or 0),
            self.frame_source_key(camera),
            bool(camera.get("enabled", True)),
        )

    def _public_camera_identity(self, camera: Dict[str, Any] | None) -> Dict[str, Any] | None:
        if camera is None:
            return None
        return {
            "camera_id": int(camera.get("id") or 0),
            "stream_url": str(camera.get("stream_url") or ""),
            "enabled": bool(camera.get("enabled", True)),
            "source_key": self.frame_source_key(camera),
        }

    def _clear_camera_cache(self, camera_id: int) -> None:
        with self._frame_cache_condition:
            for key, cached in list(self._frame_cache.items()):
                if int(cached.get("camera_id") or 0) == int(camera_id):
                    self._frame_cache.pop(key, None)
            self._frame_cache_condition.notify_all()

    def _notify_source_change(self, transition: Dict[str, Any]) -> None:
        with self._shared_stream_lock:
            listeners = list(self._source_change_listeners)
        for listener in listeners:
            try:
                listener(dict(transition))
            except Exception:
                logger.exception(
                    "camera %s source transition listener failed",
                    transition.get("camera_id"),
                )

    def invalidate_stream_generation(
        self,
        camera: Dict[str, Any],
        *,
        reader: _SharedStreamReader,
        reason: str,
    ) -> int:
        camera_id = int(camera.get("id") or 0)
        if camera_id <= 0:
            return int(reader.stream_generation)
        with self._shared_stream_lock:
            current_generation = max(
                int(reader.stream_generation),
                int(self._stream_generations.get(camera_id, 0)),
            )
            generation = current_generation + 1
            self._stream_generations[camera_id] = generation
        self._clear_camera_cache(camera_id)
        identity = self._public_camera_identity(camera)
        self._notify_source_change({
            "camera_id": camera_id,
            "reason": str(reason or "stream_discontinuity"),
            "previous": identity,
            "current": identity,
            "stream_generation": generation,
        })
        return generation

    def resolve_capture_source(self, camera: Dict[str, Any]) -> Tuple[Any, int | None, str]:
        stream_url = str(camera["stream_url"]).strip()
        lowered = stream_url.lower()
        if lowered.startswith(DEMO_STREAM_PREFIXES):
            scene = stream_url.split(":", 1)[1] or "living_room"
            return stream_url, None, f"demo scene {scene}"

        for prefix in ("local:", "webcam:", "device:", "camera:"):
            if lowered.startswith(prefix):
                value = lowered.split(":", 1)[1] or "0"
                try:
                    return int(value), None, f"local camera {value}"
                except ValueError as exc:
                    raise CameraError(f"Invalid local camera source: {stream_url}") from exc

        if lowered.isdigit():
            return int(lowered), None, f"local camera {lowered}"

        return self.build_stream_url(camera), None, "network stream"

    def build_stream_url(self, camera: Dict[str, Any]) -> str:
        stream_url = camera["stream_url"]
        username = camera.get("username")
        password = camera.get("password")
        if not username or "@" in urlsplit(stream_url).netloc:
            return stream_url

        parts = urlsplit(stream_url)
        credentials = quote(username)
        if password:
            credentials += f":{quote(password)}"
        netloc = f"{credentials}@{parts.netloc}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))

    def capture_frame(
        self,
        camera: Dict[str, Any],
        prefer_cache: bool = True,
        max_cache_age_seconds: float = 2.0,
    ) -> Dict[str, Any]:
        if prefer_cache:
            cached = self.latest_cached_frame(camera, max_age_seconds=max_cache_age_seconds)
            if cached is not None:
                return cached
            managed_reader = self._managed_reader(camera)
            if managed_reader is not None:
                managed_status = managed_reader.status()
                if (
                    str(managed_status.get("state") or "") == "retrying"
                    and int(managed_status.get("decoded_frames") or 0) == 0
                ):
                    raise CameraError(
                        f"Cannot open {managed_reader.source_label}: "
                        f"{managed_status.get('last_error') or 'stream unavailable'}"
                    )
                managed_reader.wait_for_update(0, timeout=2.0)
                cached = self.latest_cached_frame(camera, max_age_seconds=max_cache_age_seconds)
                if cached is not None:
                    return cached
                managed_status = managed_reader.status()
                raise CameraError(
                    f"Cannot read {managed_reader.source_label}: "
                    f"{managed_status.get('last_error') or managed_status.get('state') or 'stream unavailable'}"
                )
        with self._capture_lock:
            capture = self._capture_frame_unlocked(camera)
        frame_identity = self._store_latest_frame(camera, capture["frame"], capture["source"])
        if frame_identity:
            capture.update(frame_identity)
        return capture

    def latest_cached_frame(self, camera: Dict[str, Any], max_age_seconds: float = 2.0) -> Dict[str, Any] | None:
        key = self._frame_cache_key(camera)
        now = time.monotonic()
        with self._frame_cache_lock:
            cached = self._frame_cache.get(key)
            if not cached:
                return None
            age = now - float(cached.get("monotonic", 0.0))
            if age > max(0.1, float(max_age_seconds)):
                return None
            frame = cached["frame"].copy()
            return {
                "frame": frame,
                "width": cached["width"],
                "height": cached["height"],
                "elapsed_ms": int(age * 1000),
                "source": f"{cached['source']} cached",
                "frame_id": cached["frame_id"],
                "captured_at": cached["captured_at"],
                "captured_monotonic": cached["captured_monotonic"],
                "camera_id": cached["camera_id"],
                "source_key": cached["source_key"],
                "configured_source_key": cached["configured_source_key"],
                "stream_generation": cached["stream_generation"],
            }

    def wait_for_frame_update(
        self,
        cameras: list[Dict[str, Any]],
        after_frame_ids: Dict[int, str],
        *,
        timeout: float = 0.25,
    ) -> bool:
        watched = [
            (self._frame_cache_key(camera), int(camera.get("id") or 0))
            for camera in cameras
            if camera.get("id")
        ]
        if not watched:
            return False

        def has_update() -> bool:
            for key, camera_id in watched:
                cached = self._frame_cache.get(key)
                if cached and str(cached.get("frame_id") or "") != str(after_frame_ids.get(camera_id) or ""):
                    return True
            return False

        with self._frame_cache_condition:
            return bool(
                self._frame_cache_condition.wait_for(
                    has_update,
                    timeout=max(0.01, float(timeout)),
                )
            )

    def _store_latest_frame(
        self,
        camera: Dict[str, Any],
        frame: Any,
        source_label: str,
        *,
        stream_generation: int = 0,
    ) -> Dict[str, Any] | None:
        try:
            height, width = frame.shape[:2]
        except (AttributeError, ValueError):
            return None
        key = self._frame_cache_key(camera)
        camera_id = int(camera.get("id") or 0)
        configured_source_key = self.frame_source_key(camera)
        source_key = f"{configured_source_key}:g{max(0, int(stream_generation))}"
        captured_at = datetime.now(timezone.utc).isoformat()
        captured_monotonic = time.monotonic()
        with self._frame_cache_condition:
            sequence_key = str(camera_id or key)
            sequence = self._frame_sequences.get(sequence_key, 0) + 1
            self._frame_sequences[sequence_key] = sequence
            frame_id = f"{camera_id or 'source'}-{sequence}"
            self._frame_cache[key] = {
                "frame": frame.copy(),
                "width": width,
                "height": height,
                "source": source_label,
                "monotonic": captured_monotonic,
                "frame_id": frame_id,
                "captured_at": captured_at,
                "captured_monotonic": captured_monotonic,
                "camera_id": camera_id,
                "source_key": source_key,
                "configured_source_key": configured_source_key,
                "stream_generation": max(0, int(stream_generation)),
            }
            self._frame_cache_condition.notify_all()
        return {
            "frame_id": frame_id,
            "captured_at": captured_at,
            "captured_monotonic": captured_monotonic,
            "camera_id": camera_id,
            "source_key": source_key,
            "configured_source_key": configured_source_key,
            "stream_generation": max(0, int(stream_generation)),
        }

    def frame_data_url(self, frame: Any, jpeg_quality: int = 62, max_width: int = 768) -> str:
        cv2 = _load_cv2()
        output_frame = self._resize_for_stream(
            cv2,
            frame,
            max_width=max(320, int(max_width)),
            max_height=4320,
        )
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), max(35, min(int(jpeg_quality), 90))]
        ok, encoded = cv2.imencode(".jpg", output_frame, encode_params)
        if not ok:
            raise CameraError("Failed to encode live analysis frame")
        payload = base64.b64encode(encoded.tobytes()).decode("ascii")
        return f"data:image/jpeg;base64,{payload}"

    def _frame_cache_key(self, camera: Dict[str, Any]) -> str:
        camera_id = camera.get("id")
        return f"{camera_id or 'source'}::{self.frame_source_key(camera)}"

    def frame_source_key(self, camera: Dict[str, Any]) -> str:
        camera_id = int(camera.get("id") or 0)
        stream_url = str(camera.get("stream_url") or "").strip()
        username = str(camera.get("username") or "")
        password = str(camera.get("password") or "")
        identity = f"{camera_id}\0{stream_url}\0{username}\0{password}".encode("utf-8", errors="strict")
        return hashlib.sha256(identity).hexdigest()[:24]

    def active_frame_source_key(self, camera: Dict[str, Any]) -> str:
        key = self._frame_cache_key(camera)
        with self._frame_cache_lock:
            cached = self._frame_cache.get(key)
            if cached and cached.get("source_key"):
                return str(cached["source_key"])
        return f"{self.frame_source_key(camera)}:g0"

    def frame_source_matches(self, camera: Dict[str, Any], source_key: Any) -> bool:
        configured = self.frame_source_key(camera)
        candidate = str(source_key or "")
        return candidate == configured or candidate.startswith(f"{configured}:g")

    def _managed_reader(self, camera: Dict[str, Any]) -> _SharedStreamReader | None:
        camera_id = int(camera.get("id") or 0)
        with self._shared_stream_lock:
            managed = self._managed_streams.get(camera_id)
            if managed is None or self._camera_signature(managed[0]) != self._camera_signature(camera):
                return None
            return managed[1]

    def _is_demo_source(self, source: Any) -> bool:
        return isinstance(source, str) and source.strip().lower().startswith(DEMO_STREAM_PREFIXES)

    def _capture_frame_unlocked(self, camera: Dict[str, Any]) -> Dict[str, Any]:
        cv2 = _load_cv2()
        started_at = time.monotonic()
        source, _backend, source_label = self.resolve_capture_source(camera)
        if self._is_demo_source(source):
            frame = self._demo_frame(cv2, camera, frame_index=int(time.monotonic() * 10))
            height, width = frame.shape[:2]
            return {
                "frame": frame,
                "width": width,
                "height": height,
                "elapsed_ms": int((time.monotonic() - started_at) * 1000),
                "source": source_label,
            }

        is_local_source = isinstance(source, int)
        os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")
        if is_local_source:
            backend = getattr(cv2, "CAP_AVFOUNDATION", 0)
            cap = cv2.VideoCapture(source, backend) if backend else cv2.VideoCapture(source)
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(source)
        else:
            cap = self._open_network_capture(cv2, source)

        try:
            if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not is_local_source and hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000)
            if not is_local_source and hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
                cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)

            if not cap.isOpened():
                hint = ""
                if is_local_source:
                    hint = ". On macOS, grant Camera permission to Terminal/Codex and retry"
                raise CameraError(f"Cannot open {source_label}{hint}")

            frame = self._read_frame(cap, source_label, warm_up=is_local_source)
            height, width = frame.shape[:2]
            return {
                "frame": frame,
                "width": width,
                "height": height,
                "elapsed_ms": int((time.monotonic() - started_at) * 1000),
                "source": source_label,
            }
        finally:
            cap.release()

    def _read_frame(self, cap: Any, source_label: str, warm_up: bool) -> Any:
        cv2 = _load_cv2()
        frame = None
        best_score = -1.0
        deadline = time.monotonic() + (LOCAL_CAPTURE_WARMUP_SECONDS if warm_up else NETWORK_CAPTURE_WARMUP_SECONDS)
        min_reads = 8 if warm_up else NETWORK_CAPTURE_MIN_READS
        max_reads = 18 if warm_up else NETWORK_CAPTURE_MAX_READS
        reads = 0
        while reads < max_reads and (reads < min_reads or time.monotonic() < deadline):
            ok, candidate = cap.read()
            reads += 1
            if ok and candidate is not None:
                score = self._frame_quality_score(cv2, candidate)
                if score > best_score:
                    best_score = score
                    frame = candidate.copy()
                if not warm_up and reads >= min_reads and self._frame_is_usable_for_snapshot(cv2, candidate, score):
                    return candidate
            time.sleep(0.035)

        if frame is None:
            raise CameraError(f"{source_label} opened but no frame was returned")
        return frame

    def _frame_quality_score(self, cv2: Any, frame: Any) -> float:
        try:
            height, width = frame.shape[:2]
        except (AttributeError, ValueError):
            return -1.0
        if height < 16 or width < 16:
            return -1.0

        sample = frame[::8, ::8]
        gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())
        contrast = float(gray.std())
        edge_score = float(cv2.Laplacian(gray, cv2.CV_64F).var() ** 0.5)
        exposure_penalty = 0.0
        if brightness < 8:
            exposure_penalty = 18.0 - brightness
        elif brightness > 248:
            exposure_penalty = brightness - 238.0
        return contrast + min(edge_score, 80.0) * 0.2 - max(0.0, exposure_penalty)

    def _frame_is_usable_for_snapshot(self, cv2: Any, frame: Any, score: float) -> bool:
        sample = frame[::8, ::8]
        gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())
        contrast = float(gray.std())

        # Keep true black/covered evidence, but do not accept low-contrast grey decoder warm-up frames.
        if brightness < 20 and contrast < 5:
            return True
        return 12 <= brightness <= 245 and contrast >= 8 and score >= 8

    def snapshot_relative_path(self, camera_id: int) -> str:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"camera_{camera_id}/{stamp}.jpg"

    def save_frame(self, frame: Any, relative_path: str) -> Path:
        cv2 = _load_cv2()
        output_path = self.snapshot_dir / relative_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_frame = self._enhance_frame_for_storage(frame)
        ok = cv2.imwrite(str(output_path), output_frame)
        if not ok:
            raise CameraError(f"Failed to write snapshot: {output_path}")
        return output_path

    def mjpeg_frames(
        self,
        camera: Dict[str, Any],
        fps: int = 5,
        jpeg_quality: int = 70,
        max_width: int = 1280,
        max_height: int = 720,
    ) -> Generator[bytes, None, None]:
        cv2 = _load_cv2()
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), max(35, min(int(jpeg_quality), 95))]
        for capture in self.raw_frames(
            camera,
            fps=fps,
            max_width=max_width,
            max_height=max_height,
        ):
            ok, encoded = cv2.imencode(".jpg", capture["frame"], encode_params)
            if not ok:
                continue
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Cache-Control: no-store\r\n\r\n"
                + encoded.tobytes()
                + b"\r\n"
            )

    def raw_frames(
        self,
        camera: Dict[str, Any],
        *,
        fps: int = 15,
        max_width: int = 1280,
        max_height: int = 720,
    ) -> Generator[Dict[str, Any], None, None]:
        cv2 = _load_cv2()
        source, _backend, source_label = self.resolve_capture_source(camera)
        if self._is_demo_source(source):
            yield from self._demo_raw_frames(
                cv2,
                camera,
                fps=fps,
                max_width=max_width,
                max_height=max_height,
            )
            return

        is_local_source = isinstance(source, int)
        reader = self._acquire_shared_stream(
            camera,
            source=source,
            is_local_source=is_local_source,
            source_label=source_label,
        )
        last_sequence = 0
        last_frame_id = ""
        frame_interval = 1.0 / bounded_stream_fps(fps)
        frame_deadline = time.monotonic()
        try:
            while True:
                sequence, _error = reader.wait_for_update(last_sequence)
                if sequence <= last_sequence:
                    if reader.is_stopped:
                        return
                    continue
                last_sequence = sequence
                capture = self.latest_cached_frame(camera, max_age_seconds=0.75)
                if capture is None:
                    continue
                frame_id = str(capture.get("frame_id") or "")
                if not frame_id or frame_id == last_frame_id:
                    continue
                last_frame_id = frame_id
                frame = capture["frame"]
                output_frame = self._resize_for_stream(
                    cv2,
                    frame,
                    max_width=max_width,
                    max_height=max_height,
                )
                yield {
                    **capture,
                    "frame": output_frame,
                    "width": int(output_frame.shape[1]),
                    "height": int(output_frame.shape[0]),
                }
                delay, frame_deadline = next_stream_frame_delay(
                    previous_deadline=frame_deadline,
                    now=time.monotonic(),
                    frame_interval=frame_interval,
                )
                if delay > 0:
                    time.sleep(delay)
        finally:
            self._release_shared_stream(camera, reader)

    def _acquire_shared_stream(
        self,
        camera: Dict[str, Any],
        *,
        source: Any,
        is_local_source: bool,
        source_label: str,
    ) -> _SharedStreamReader:
        key = self._frame_cache_key(camera)
        with self._shared_stream_lock:
            reader = self._shared_streams.get(key)
            if reader is None:
                camera_id = int(camera.get("id") or 0)
                generation = self._stream_generations.get(camera_id, 0) + 1
                self._stream_generations[camera_id] = generation
                reader = _SharedStreamReader(
                    agent=self,
                    camera=camera,
                    source=source,
                    is_local_source=is_local_source,
                    source_label=source_label,
                    stream_generation=generation,
                )
                self._shared_streams[key] = reader
                reader.subscribers = 1
                reader.start()
                return reader
            reader.subscribers += 1
            return reader

    def _release_shared_stream(self, camera: Dict[str, Any], reader: _SharedStreamReader) -> None:
        key = self._frame_cache_key(camera)
        should_stop = False
        with self._shared_stream_lock:
            current = self._shared_streams.get(key)
            if current is not reader:
                return
            reader.subscribers = max(0, reader.subscribers - 1)
            if reader.subscribers == 0:
                self._shared_streams.pop(key, None)
                should_stop = True
        if should_stop:
            reader.stop()

    def _retire_shared_stream(self, reader: _SharedStreamReader) -> None:
        with self._shared_stream_lock:
            for key, current in list(self._shared_streams.items()):
                if current is reader:
                    self._shared_streams.pop(key, None)
            reader.subscribers = 0
        reader.stop()

    def _open_stream_capture(self, cv2: Any, source: Any, is_local_source: bool) -> Any:
        if is_local_source:
            os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")
            backend = getattr(cv2, "CAP_AVFOUNDATION", 0)
            cap = cv2.VideoCapture(source, backend) if backend else cv2.VideoCapture(source)
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(source)
        else:
            cap = self._open_network_capture(cv2, source)
        if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not is_local_source and hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000)
        if not is_local_source and hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
        return cap

    def _open_network_capture(self, cv2: Any, source: Any) -> Any:
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", NETWORK_CAPTURE_OPTIONS)
        params: list[int] = []
        if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
            params.extend([int(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC), 8000])
        if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
            params.extend([int(cv2.CAP_PROP_READ_TIMEOUT_MSEC), 5000])
        if params:
            try:
                return cv2.VideoCapture(source, cv2.CAP_FFMPEG, params)
            except Exception:
                logger.warning("OpenCV rejected capture timeout parameters; using backend defaults")
        return cv2.VideoCapture(source, cv2.CAP_FFMPEG)

    def _frame_is_near_black(self, cv2: Any, frame: Any) -> bool:
        try:
            sample = frame[::8, ::8]
            gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
            return float(gray.mean()) < 6.0 and float(gray.std()) < 3.0
        except (AttributeError, TypeError, ValueError):
            return True

    def _resize_for_stream(self, cv2: Any, frame: Any, max_width: int, max_height: int) -> Any:
        height, width = frame.shape[:2]
        target_width = max(0, int(max_width or 0))
        target_height = max(0, int(max_height or 0))
        if not target_width and not target_height:
            return frame

        width_scale = target_width / width if target_width else 1.0
        height_scale = target_height / height if target_height else 1.0
        scale = min(width_scale, height_scale, 1.0)
        if scale >= 0.999:
            return frame

        resized_width = max(1, int(width * scale))
        resized_height = max(1, int(height * scale))
        return cv2.resize(frame, (resized_width, resized_height), interpolation=cv2.INTER_AREA)

    def _demo_raw_frames(
        self,
        cv2: Any,
        camera: Dict[str, Any],
        fps: int,
        max_width: int,
        max_height: int,
    ) -> Generator[Dict[str, Any], None, None]:
        delay = 1.0 / bounded_stream_fps(fps)
        frame_index = 0
        while True:
            frame = self._demo_frame(cv2, camera, frame_index=frame_index)
            identity = self._store_latest_frame(camera, frame, "demo stream") or {}
            output = self._resize_for_stream(cv2, frame, max_width=max_width, max_height=max_height)
            yield {
                "frame": output,
                "width": int(output.shape[1]),
                "height": int(output.shape[0]),
                "elapsed_ms": 0,
                "source": "demo stream",
                **identity,
            }
            frame_index += 1
            time.sleep(delay)

    def _demo_frame(self, cv2: Any, camera: Dict[str, Any], frame_index: int = 0) -> Any:
        try:
            import numpy as np  # type: ignore
        except ModuleNotFoundError as exc:
            raise CameraError("NumPy is not installed. Run: python -m pip install -r requirements.txt") from exc

        width, height = 1280, 720
        gradient = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
        top = np.array([239, 244, 242], dtype=np.float32).reshape(1, 1, 3)
        bottom = np.array([218, 225, 220], dtype=np.float32).reshape(1, 1, 3)
        frame = np.repeat(top * (1 - gradient) + bottom * gradient, width, axis=1).astype("uint8")

        tick = frame_index / 8.0
        sway = int(10 * np.sin(tick))
        breath = int(4 * np.sin(tick * 1.7))

        # A quiet living-room scene gives the demo stream real visual structure without external assets.
        cv2.rectangle(frame, (0, 510), (width, height), (205, 207, 197), -1)
        for x in range(-80, width, 90):
            cv2.line(frame, (x, 720), (x + 230, 510), (193, 195, 187), 1, cv2.LINE_AA)

        cv2.rectangle(frame, (70, 78), (422, 322), (228, 232, 224), -1)
        cv2.rectangle(frame, (92, 100), (400, 300), (203, 223, 230), -1)
        cv2.circle(frame, (318, 152), 34, (82, 176, 238), -1, cv2.LINE_AA)
        cv2.rectangle(frame, (236, 100), (244, 300), (228, 232, 224), -1)
        cv2.rectangle(frame, (92, 196), (400, 204), (228, 232, 224), -1)

        cv2.rectangle(frame, (118, 394), (655, 565), (124, 151, 158), -1)
        cv2.ellipse(frame, (386, 394), (268, 62), 0, 180, 360, (138, 166, 172), -1, cv2.LINE_AA)
        cv2.rectangle(frame, (148, 332), (626, 455), (139, 166, 172), -1)
        cv2.rectangle(frame, (188, 356), (350, 456), (126, 150, 158), -1)
        cv2.rectangle(frame, (370, 356), (588, 456), (126, 150, 158), -1)
        cv2.rectangle(frame, (152, 556), (238, 590), (88, 105, 110), -1)
        cv2.rectangle(frame, (542, 556), (626, 590), (88, 105, 110), -1)

        cv2.ellipse(frame, (835, 532), (205, 70), 0, 0, 360, (118, 142, 150), -1, cv2.LINE_AA)
        cv2.ellipse(frame, (835, 520), (190, 58), 0, 0, 360, (218, 218, 207), -1, cv2.LINE_AA)
        cv2.circle(frame, (782, 510), 34, (225, 231, 231), -1, cv2.LINE_AA)
        cv2.circle(frame, (782, 510), 21, (185, 197, 190), 2, cv2.LINE_AA)
        cv2.circle(frame, (876, 510), 26, (88, 126, 154), -1, cv2.LINE_AA)
        cv2.line(frame, (748, 552), (728, 642), (89, 96, 94), 8, cv2.LINE_AA)
        cv2.line(frame, (918, 552), (944, 642), (89, 96, 94), 8, cv2.LINE_AA)

        cv2.rectangle(frame, (1040, 260), (1098, 520), (92, 108, 95), -1)
        cv2.circle(frame, (1068, 232), 64, (93, 145, 112), -1, cv2.LINE_AA)
        cv2.circle(frame, (1018, 270), 42, (105, 160, 124), -1, cv2.LINE_AA)
        cv2.circle(frame, (1120, 286), 46, (82, 132, 102), -1, cv2.LINE_AA)

        person_x = 516 + sway
        cv2.circle(frame, (person_x, 248 + breath), 34, (78, 93, 116), -1, cv2.LINE_AA)
        cv2.ellipse(frame, (person_x, 360 + breath), (58, 92), 0, 0, 360, (63, 86, 124), -1, cv2.LINE_AA)
        cv2.line(frame, (person_x - 44, 338), (person_x - 95, 424 + breath), (70, 86, 118), 16, cv2.LINE_AA)
        cv2.line(frame, (person_x + 40, 338), (person_x + 90, 414 - breath), (70, 86, 118), 16, cv2.LINE_AA)
        cv2.line(frame, (person_x - 28, 438), (person_x - 70, 570), (58, 70, 94), 18, cv2.LINE_AA)
        cv2.line(frame, (person_x + 28, 438), (person_x + 68, 570), (58, 70, 94), 18, cv2.LINE_AA)
        cv2.ellipse(frame, (person_x - 76, 580), (34, 12), 0, 0, 360, (45, 53, 67), -1, cv2.LINE_AA)
        cv2.ellipse(frame, (person_x + 77, 580), (34, 12), 0, 0, 360, (45, 53, 67), -1, cv2.LINE_AA)

        return frame

    def _enhance_frame_for_storage(self, frame: Any) -> Any:
        cv2 = _load_cv2()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())
        contrast = float(gray.std())

        # Keep truly black/covered frames untouched so black-screen evidence stays honest.
        if brightness >= 55 or contrast < 6:
            return frame

        ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
        channels = list(cv2.split(ycrcb))
        clahe = cv2.createCLAHE(clipLimit=2.8, tileGridSize=(8, 8))
        channels[0] = clahe.apply(channels[0])
        enhanced = cv2.cvtColor(cv2.merge(channels), cv2.COLOR_YCrCb2BGR)
        alpha = 1.24 if brightness < 35 else 1.14
        beta = 28 if brightness < 35 else 14
        return cv2.convertScaleAbs(enhanced, alpha=alpha, beta=beta)
