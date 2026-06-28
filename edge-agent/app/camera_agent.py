from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Generator, Tuple
from urllib.parse import quote, urlsplit, urlunsplit
import os
import time


NETWORK_CAPTURE_OPTIONS = "rtsp_transport;tcp|stimeout;3000000|fflags;nobuffer|max_delay;500000"


class CameraError(RuntimeError):
    pass


def _load_cv2():
    try:
        import cv2  # type: ignore
    except ModuleNotFoundError as exc:
        raise CameraError("OpenCV is not installed. Run: python -m pip install -r requirements.txt") from exc
    return cv2


class CameraAgent:
    def __init__(self, snapshot_dir: Path) -> None:
        self.snapshot_dir = snapshot_dir
        self._capture_lock = Lock()

    def resolve_capture_source(self, camera: Dict[str, Any]) -> Tuple[Any, int | None, str]:
        stream_url = str(camera["stream_url"]).strip()
        lowered = stream_url.lower()
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

    def capture_frame(self, camera: Dict[str, Any]) -> Dict[str, Any]:
        with self._capture_lock:
            return self._capture_frame_unlocked(camera)

    def _capture_frame_unlocked(self, camera: Dict[str, Any]) -> Dict[str, Any]:
        cv2 = _load_cv2()

        source, _backend, source_label = self.resolve_capture_source(camera)
        started_at = time.monotonic()
        is_local_source = isinstance(source, int)
        if is_local_source:
            os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")
            backend = getattr(cv2, "CAP_AVFOUNDATION", 0)
            cap = cv2.VideoCapture(source, backend) if backend else cv2.VideoCapture(source)
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(source)
        else:
            os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", NETWORK_CAPTURE_OPTIONS)
            cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)

        try:
            if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not is_local_source and hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000)
            if not is_local_source and hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
                cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 8000)

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
        if not warm_up:
            ok, frame = cap.read()
            if ok and frame is not None:
                return frame
            raise CameraError(f"{source_label} opened but no frame was returned")

        frame = None
        deadline = time.monotonic() + 1.0
        reads = 0
        while reads < 8 or time.monotonic() < deadline:
            ok, candidate = cap.read()
            reads += 1
            if ok and candidate is not None:
                frame = candidate
            time.sleep(0.035)

        if frame is None:
            raise CameraError(f"{source_label} opened but no frame was returned")
        return frame

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
        drop_stale_frames: int = 4,
    ) -> Generator[bytes, None, None]:
        cv2 = _load_cv2()
        source, _backend, source_label = self.resolve_capture_source(camera)
        is_local_source = isinstance(source, int)
        if is_local_source:
            os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")
            backend = getattr(cv2, "CAP_AVFOUNDATION", 0)
            cap = cv2.VideoCapture(source, backend) if backend else cv2.VideoCapture(source)
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(source)
        else:
            os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", NETWORK_CAPTURE_OPTIONS)
            cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)

        try:
            if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not is_local_source and hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000)
            if not is_local_source and hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
                cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 8000)

            if not cap.isOpened():
                hint = ""
                if is_local_source:
                    hint = ". On macOS, grant Camera permission to Terminal/Codex and retry"
                raise CameraError(f"Cannot open {source_label}{hint}")

            delay = 1.0 / max(1, min(int(fps), 15))
            encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), max(35, min(int(jpeg_quality), 95))]
            stale_frame_reads = max(0, min(int(drop_stale_frames), 12))
            while True:
                ok, frame = self._latest_stream_frame(cap, stale_frame_reads)
                if not ok or frame is None:
                    break
                frame = self._resize_for_stream(cv2, frame, max_width=max_width, max_height=max_height)
                ok, encoded = cv2.imencode(".jpg", frame, encode_params)
                if not ok:
                    continue
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Cache-Control: no-store\r\n\r\n"
                    + encoded.tobytes()
                    + b"\r\n"
                )
                time.sleep(delay)
        finally:
            cap.release()

    def _latest_stream_frame(self, cap: Any, drop_stale_frames: int) -> Tuple[bool, Any]:
        if drop_stale_frames <= 0:
            return cap.read()

        grabbed = False
        for _ in range(drop_stale_frames):
            grabbed = bool(cap.grab())
            if not grabbed:
                break

        if grabbed:
            return cap.retrieve()
        return cap.read()

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
