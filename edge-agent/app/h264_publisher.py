from __future__ import annotations

from collections import deque
from hashlib import sha256
from threading import Condition, Lock, Thread, current_thread
from typing import Any, Callable, Dict
from urllib.parse import quote, urlsplit, urlunsplit
import os
import select
import subprocess
import time


class H264PublisherError(RuntimeError):
    pass


class _PublisherControlChanged(RuntimeError):
    def __init__(self, *, bytes_written: int, frame_size: int) -> None:
        super().__init__("publisher control changed during frame write")
        self.bytes_written = max(0, int(bytes_written))
        self.frame_size = max(0, int(frame_size))


class _FrameWriteFailed(H264PublisherError):
    def __init__(self, message: str, *, bytes_written: int, frame_size: int) -> None:
        super().__init__(message)
        self.bytes_written = max(0, int(bytes_written))
        self.frame_size = max(0, int(frame_size))


def build_rtsps_publish_url(
    base_url: str,
    *,
    device_id: str,
    device_token: str,
    camera_id: Any,
) -> str:
    parts = urlsplit(str(base_url or "").strip().rstrip("/"))
    if parts.scheme != "rtsps" or not parts.hostname:
        raise H264PublisherError("media publish base URL must use rtsps")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise H264PublisherError("media publish base URL must not contain credentials, query, or fragment")
    resolved_device_id = str(device_id or "").strip()
    resolved_token = str(device_token or "").strip()
    resolved_camera_id = str(camera_id or "").strip()
    if not resolved_device_id:
        raise H264PublisherError("device ID is required for media publishing")
    if not resolved_token:
        raise H264PublisherError("device token is required for media publishing")
    if not resolved_camera_id:
        raise H264PublisherError("camera ID is required for media publishing")
    host = parts.hostname
    if ":" in host:
        host = f"[{host}]"
    if parts.port:
        host = f"{host}:{parts.port}"
    credentials = f"{quote(resolved_device_id, safe='')}:{quote(resolved_token, safe='')}"
    prefix = parts.path.rstrip("/")
    path = f"{prefix}/live/{quote(resolved_device_id, safe='')}/{quote(resolved_camera_id, safe='')}"
    return urlunsplit(("rtsps", f"{credentials}@{host}", path, "", ""))


def redact_publish_url(value: str) -> str:
    parts = urlsplit(str(value or ""))
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


class H264StreamPublisher:
    """Publish only the newest edge-composed frame through one FFmpeg process."""

    version = "edge-h264-publisher-v1"

    def __init__(
        self,
        *,
        camera_id: int,
        publish_url: str,
        ffmpeg_path: str,
        fps: int,
        bitrate_kbps: int,
        write_timeout_seconds: float,
        startup_timeout_seconds: float = 5.0,
        process_factory: Callable[[list[str]], Any] | None = None,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        self.camera_id = int(camera_id)
        self.publish_url = str(publish_url)
        self.ffmpeg_path = str(ffmpeg_path or "ffmpeg")
        self.fps = max(1, min(int(fps), 30))
        self.bitrate_kbps = max(256, min(int(bitrate_kbps), 8000))
        self.write_timeout_seconds = max(0.1, min(float(write_timeout_seconds), 5.0))
        self.startup_timeout_seconds = max(
            self.write_timeout_seconds,
            min(float(startup_timeout_seconds), 15.0),
        )
        self._process_factory = process_factory or self._start_process
        self._clock = monotonic_clock or time.monotonic
        self._condition = Condition()
        self._state_lock = Lock()
        self._pending: Dict[str, Any] | None = None
        self._stopping = False
        self._control_revision = 0
        self._pause_reason = ""
        self._process: Any | None = None
        self._process_geometry: tuple[int, int] | None = None
        self._process_started_at: float | None = None
        self._process_output_started = False
        self._process_reported_frames = 0
        self._context: tuple[str, str] = ("", "")
        self._stderr_thread: Thread | None = None
        self._stderr_tail: deque[str] = deque(maxlen=20)
        self._submitted_at: deque[float] = deque(maxlen=600)
        self._published_at: deque[float] = deque(maxlen=600)
        self._write_latency_ms: deque[float] = deque(maxlen=300)
        self._frame_age_ms: deque[float] = deque(maxlen=300)
        self._stats: Dict[str, Any] = {
            "submitted": 0,
            "frames_written": 0,
            "replaced_pending": 0,
            "dropped_unavailable": 0,
            "process_starts": 0,
            "process_failures": 0,
            "partial_frame_aborts": 0,
            "raw_input_bytes_written": 0,
            "process_stop_reasons": {},
            "last_process_start_reason": "",
            "last_process_stop_reason": "",
            "last_failure_at_monotonic": None,
            "last_recovered_at_monotonic": None,
            "last_recovered_error": "",
            "last_partial_frame_bytes": 0,
            "last_partial_frame_size": 0,
            "last_error": "",
            "last_written_frame_id": "",
        }
        self._consecutive_failures = 0
        self._next_start_at = 0.0
        self._next_process_start_reason = "initial"
        self._thread = Thread(
            target=self._run,
            name=f"gohome-h264-publisher-{self.camera_id}",
            daemon=True,
        )
        self._thread.start()

    def submit(
        self,
        frame: Any,
        *,
        frame_id: str,
        captured_monotonic: Any,
        privacy_mode: str,
        source_key: str,
    ) -> None:
        if frame is None or not getattr(frame, "size", 0):
            raise H264PublisherError("composed frame is unavailable")
        if getattr(frame, "dtype", None) is None or str(frame.dtype) != "uint8":
            raise H264PublisherError("composed frame must use uint8 BGR pixels")
        if len(frame.shape) != 3 or int(frame.shape[2]) != 3:
            raise H264PublisherError("composed frame must use BGR24 layout")
        flags = getattr(frame, "flags", None)
        if flags is not None and not bool(getattr(flags, "c_contiguous", False)):
            frame = frame.copy(order="C")
        item = {
            "frame": frame,
            "frame_id": str(frame_id or ""),
            "captured_monotonic": captured_monotonic,
            "privacy_mode": str(privacy_mode or ""),
            "source_key": str(source_key or ""),
            "submitted_monotonic": self._clock(),
        }
        with self._condition:
            if self._stopping:
                return
            replaced = self._pending is not None
            self._pending = item
            self._pause_reason = ""
            self._condition.notify()
        with self._state_lock:
            self._stats["submitted"] += 1
            self._submitted_at.append(float(item["submitted_monotonic"]))
            if replaced:
                self._stats["replaced_pending"] += 1

    def pause(self, reason: str) -> None:
        resolved_reason = self._sanitize_text(reason or "paused")[:240]
        with self._condition:
            if self._stopping:
                return
            should_interrupt = self._pending is not None or self._pause_reason != resolved_reason
            self._pending = None
            self._pause_reason = resolved_reason
            if should_interrupt:
                self._control_revision += 1
                self._condition.notify_all()
        with self._state_lock:
            self._stats["last_error"] = resolved_reason

    def close(self) -> None:
        with self._condition:
            already_stopping = self._stopping
            self._stopping = True
            self._pending = None
            self._control_revision += 1
            self._condition.notify_all()
        if current_thread() is self._thread:
            return
        if not already_stopping or self._thread.is_alive():
            self._thread.join(timeout=self.write_timeout_seconds + 4.0)

    def status(self) -> Dict[str, Any]:
        now = self._clock()
        with self._condition:
            paused = bool(self._pause_reason)
        with self._state_lock:
            submitted = [value for value in self._submitted_at if value >= now - 10.0]
            published = [value for value in self._published_at if value >= now - 10.0]
            write_latency = sorted(self._write_latency_ms)
            frame_age = sorted(self._frame_age_ms)
            process = self._process
            process_started_at = self._process_started_at
            return {
                "schema_version": self.version,
                "camera_id": self.camera_id,
                "transport": "h264-rtsps",
                "publish_url": redact_publish_url(self.publish_url),
                "fps_target": self.fps,
                "bitrate_kbps": self.bitrate_kbps,
                "running": process is not None and process.poll() is None,
                "publish_ready": bool(
                    process is not None
                    and process.poll() is None
                    and self._process_output_started
                ),
                "paused": paused,
                "pid": int(process.pid) if process is not None and getattr(process, "pid", None) else None,
                "input_fps_10s": self._rate(submitted),
                "encoder_input_fps_10s": self._rate(published),
                "write_latency_ms_p95": self._percentile(write_latency, 0.95),
                "write_latency_ms_max": round(write_latency[-1], 2) if write_latency else 0.0,
                "source_to_encoder_input_ms_p95": self._percentile(frame_age, 0.95),
                "source_to_encoder_input_ms_max": round(frame_age[-1], 2) if frame_age else 0.0,
                "consecutive_failures": self._consecutive_failures,
                "next_start_in_seconds": round(max(0.0, self._next_start_at - now), 2),
                "startup_timeout_seconds": self.startup_timeout_seconds,
                "process_age_seconds": round(max(0.0, now - process_started_at), 2)
                if process_started_at is not None and process is not None
                else 0.0,
                "encoded_frames_reported": self._process_reported_frames,
                "context": {
                    "privacy_mode": self._context[0],
                    "source_generation": self._source_generation(self._context[1]),
                },
                "stderr_tail": list(self._stderr_tail),
                **dict(self._stats),
            }

    def _run(self) -> None:
        applied_control_revision = 0
        try:
            while True:
                with self._condition:
                    while (
                        self._pending is None
                        and not self._stopping
                        and applied_control_revision == self._control_revision
                    ):
                        self._condition.wait()
                    if self._stopping:
                        return
                    control_changed = applied_control_revision != self._control_revision
                    applied_control_revision = self._control_revision
                    item = self._pending
                    self._pending = None
                if control_changed:
                    self._stop_process("control_changed")
                if item is None:
                    continue
                try:
                    self._publish(item, control_revision=applied_control_revision)
                except _PublisherControlChanged as exc:
                    self._stop_process(
                        "control_changed",
                        partial_frame_bytes=exc.bytes_written,
                        frame_size=exc.frame_size,
                    )
                except Exception as exc:
                    self._record_failure(exc)
        finally:
            self._stop_process("publisher_stopping")

    def _publish(self, item: Dict[str, Any], *, control_revision: int) -> None:
        now = self._clock()
        if now < self._next_start_at:
            with self._state_lock:
                self._stats["dropped_unavailable"] += 1
            return
        frame = item["frame"]
        height, width = frame.shape[:2]
        context = (str(item["privacy_mode"]), str(item["source_key"]))
        with self._state_lock:
            context_changed = self._context != context
        if context_changed:
            self._stop_process("context_changed")
            with self._state_lock:
                self._context = context
        process = self._ensure_process(int(width), int(height))
        started_at = self._clock()
        try:
            payload = memoryview(frame).cast("B")
        except (TypeError, ValueError) as exc:
            raise H264PublisherError("composed frame must be contiguous BGR24") from exc
        self._write_all(process, payload, control_revision=control_revision)
        finished_at = self._clock()
        try:
            captured = float(item.get("captured_monotonic"))
        except (TypeError, ValueError):
            captured = finished_at
        if captured <= 0.0 or captured > finished_at + 1.0 or finished_at - captured > 3600.0:
            captured = finished_at
        with self._state_lock:
            recovered_error = str(self._stats.get("last_error") or "") if self._consecutive_failures else ""
            self._stats["frames_written"] += 1
            self._stats["raw_input_bytes_written"] += len(payload)
            if recovered_error:
                self._stats["last_recovered_at_monotonic"] = round(finished_at, 6)
                self._stats["last_recovered_error"] = recovered_error
            self._stats["last_error"] = ""
            self._stats["last_written_frame_id"] = str(item.get("frame_id") or "")
            self._published_at.append(finished_at)
            self._write_latency_ms.append((finished_at - started_at) * 1000.0)
            self._frame_age_ms.append((finished_at - captured) * 1000.0)
            self._consecutive_failures = 0
            self._next_start_at = 0.0

    def _ensure_process(self, width: int, height: int) -> Any:
        process = self._process
        if process is not None:
            returncode = process.poll()
            if returncode is None and self._process_geometry == (width, height):
                return process
            if returncode is not None:
                self._stop_process("process_exited")
                raise H264PublisherError(f"FFmpeg exited with code {returncode}")
        self._stop_process("geometry_changed")
        command = self.command(width=width, height=height)
        process = self._process_factory(command)
        try:
            if process.stdin is None:
                raise H264PublisherError("FFmpeg publisher has no stdin")
            os.set_blocking(process.stdin.fileno(), False)
        except Exception:
            try:
                process.terminate()
                process.wait(timeout=1.0)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
            raise
        with self._state_lock:
            self._process = process
            self._process_geometry = (width, height)
            self._process_started_at = self._clock()
            self._process_output_started = False
            self._process_reported_frames = 0
            self._stats["process_starts"] += 1
            self._stats["last_process_start_reason"] = self._next_process_start_reason
            self._next_process_start_reason = "process_recovery"
        if process.stderr is not None:
            self._stderr_thread = Thread(
                target=self._read_stderr,
                args=(process,),
                name=f"gohome-h264-stderr-{self.camera_id}",
                daemon=True,
            )
            self._stderr_thread.start()
        return process

    def command(self, *, width: int, height: int) -> list[str]:
        keyframe_interval = max(1, self.fps)
        maximum_bitrate = max(self.bitrate_kbps, int(round(self.bitrate_kbps * 1.2)))
        buffer_size = max(256, int(round(self.bitrate_kbps * 0.5)))
        return [
            self.ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-nostdin",
            "-nostats",
            "-stats_period",
            "0.25",
            "-progress",
            "pipe:2",
            "-f",
            "rawvideo",
            "-pixel_format",
            "bgr24",
            "-video_size",
            f"{int(width)}x{int(height)}",
            "-framerate",
            str(self.fps),
            "-fflags",
            "+genpts",
            "-i",
            "pipe:0",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-tune",
            "zerolatency",
            "-pix_fmt",
            "yuv420p",
            "-vf",
            "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-profile:v",
            "baseline",
            "-bf",
            "0",
            "-refs",
            "1",
            "-g",
            str(keyframe_interval),
            "-keyint_min",
            str(keyframe_interval),
            "-sc_threshold",
            "0",
            "-b:v",
            f"{self.bitrate_kbps}k",
            "-maxrate",
            f"{maximum_bitrate}k",
            "-bufsize",
            f"{buffer_size}k",
            "-rtsp_transport",
            "tcp",
            "-fps_mode",
            "passthrough",
            "-f",
            "rtsp",
            self.publish_url,
        ]

    def _write_all(self, process: Any, payload: memoryview, *, control_revision: int) -> None:
        descriptor = process.stdin.fileno()
        deadline = self._write_deadline(process)
        offset = 0
        while offset < len(payload):
            if self._control_changed(control_revision):
                raise _PublisherControlChanged(
                    bytes_written=offset,
                    frame_size=len(payload),
                )
            if process.poll() is not None:
                raise _FrameWriteFailed(
                    f"FFmpeg exited with code {process.returncode}",
                    bytes_written=offset,
                    frame_size=len(payload),
                )
            remaining = deadline - self._clock()
            if remaining <= 0.0:
                raise _FrameWriteFailed(
                    "FFmpeg frame write timed out",
                    bytes_written=offset,
                    frame_size=len(payload),
                )
            _readable, writable, _errors = select.select(
                [],
                [descriptor],
                [],
                min(remaining, 0.05),
            )
            if not writable:
                continue
            try:
                written = os.write(descriptor, payload[offset:])
            except BlockingIOError:
                continue
            if written <= 0:
                raise _FrameWriteFailed(
                    "FFmpeg stdin closed",
                    bytes_written=offset,
                    frame_size=len(payload),
                )
            offset += written

    def _record_failure(self, exc: Exception) -> None:
        partial_bytes = max(0, int(getattr(exc, "bytes_written", 0) or 0))
        frame_size = max(0, int(getattr(exc, "frame_size", 0) or 0))
        self._stop_process(
            "publish_failure",
            partial_frame_bytes=partial_bytes,
            frame_size=frame_size,
        )
        now = self._clock()
        with self._state_lock:
            self._consecutive_failures += 1
            self._stats["process_failures"] += 1
            self._stats["last_error"] = self._sanitize_text(exc)[:240]
            self._stats["last_failure_at_monotonic"] = round(now, 6)
            delay = min(8.0, 0.5 * (2 ** min(self._consecutive_failures - 1, 4)))
            self._next_start_at = now + delay

    def _stop_process(
        self,
        reason: str,
        *,
        partial_frame_bytes: int = 0,
        frame_size: int = 0,
    ) -> None:
        resolved_reason = str(reason or "unspecified")
        partial_bytes = max(0, int(partial_frame_bytes))
        resolved_frame_size = max(0, int(frame_size))
        with self._state_lock:
            process = self._process
            stderr_thread = self._stderr_thread
            self._process = None
            self._process_geometry = None
            self._process_started_at = None
            self._process_output_started = False
            self._process_reported_frames = 0
            self._stderr_thread = None
            if process is not None:
                stop_reasons = dict(self._stats.get("process_stop_reasons") or {})
                stop_reasons[resolved_reason] = int(stop_reasons.get(resolved_reason) or 0) + 1
                self._stats["process_stop_reasons"] = stop_reasons
                self._stats["last_process_stop_reason"] = resolved_reason
                self._next_process_start_reason = resolved_reason
                if partial_bytes > 0:
                    self._stats["partial_frame_aborts"] += 1
                    self._stats["last_partial_frame_bytes"] = partial_bytes
                    self._stats["last_partial_frame_size"] = resolved_frame_size
        if process is None:
            return
        if partial_bytes > 0 and process.poll() is None:
            try:
                process.kill()
                process.wait(timeout=1.0)
            except Exception:
                pass
        try:
            if process.stdin is not None:
                process.stdin.close()
        except Exception:
            pass
        if process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=1.5)
            except Exception:
                try:
                    process.kill()
                    process.wait(timeout=1.0)
                except Exception:
                    pass
        if stderr_thread is not None and stderr_thread is not current_thread():
            stderr_thread.join(timeout=0.5)

    def _read_stderr(self, process: Any) -> None:
        try:
            for raw_line in process.stderr:
                line = (
                    raw_line.decode("utf-8", errors="replace")
                    if isinstance(raw_line, bytes)
                    else str(raw_line)
                ).strip()
                if line:
                    if self._consume_progress_line(process, line):
                        continue
                    with self._state_lock:
                        self._stderr_tail.append(self._sanitize_text(line)[:500])
        except Exception:
            return

    def _start_process(self, command: list[str]) -> Any:
        return subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            bufsize=0,
            start_new_session=True,
        )

    def _control_changed(self, expected_revision: int) -> bool:
        with self._condition:
            return self._stopping or self._control_revision != int(expected_revision)

    def _write_deadline(self, process: Any) -> float:
        now = self._clock()
        with self._state_lock:
            startup_deadline = (
                float(self._process_started_at) + self.startup_timeout_seconds
                if self._process is process
                and self._process_started_at is not None
                and not self._process_output_started
                else 0.0
            )
        return max(now + self.write_timeout_seconds, startup_deadline)

    def _consume_progress_line(self, process: Any, line: str) -> bool:
        key, separator, value = str(line).partition("=")
        if not separator or key not in {"frame", "progress"}:
            return False
        with self._state_lock:
            if self._process is not process:
                return True
            if key == "frame":
                try:
                    reported_frames = max(0, int(value.strip()))
                except ValueError:
                    return False
                self._process_reported_frames = max(
                    self._process_reported_frames,
                    reported_frames,
                )
                if reported_frames > 0:
                    self._process_output_started = True
            elif value.strip() in {"continue", "end"} and self._process_reported_frames > 0:
                self._process_output_started = True
        return True

    def _sanitize_text(self, value: Any) -> str:
        text = str(value or "")
        redacted_url = redact_publish_url(self.publish_url)
        text = text.replace(self.publish_url, redacted_url)
        parts = urlsplit(self.publish_url)
        if parts.username:
            text = text.replace(parts.username, "[device]")
        if parts.password:
            text = text.replace(parts.password, "[token]")
        return text

    @staticmethod
    def _source_generation(source_key: str) -> str:
        value = str(source_key or "")
        return sha256(value.encode("utf-8")).hexdigest()[:12] if value else ""

    @staticmethod
    def _rate(samples: list[float]) -> float:
        if len(samples) < 2:
            return 0.0
        return round((len(samples) - 1) / max(0.001, samples[-1] - samples[0]), 2)

    @staticmethod
    def _percentile(values: list[float], ratio: float) -> float:
        if not values:
            return 0.0
        index = min(len(values) - 1, max(0, int((len(values) - 1) * ratio)))
        return round(float(values[index]), 2)
