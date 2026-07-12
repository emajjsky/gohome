from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Generator, Tuple
from urllib.parse import quote, urlsplit, urlunsplit
import logging
import os
import time


NETWORK_CAPTURE_OPTIONS = "rtsp_transport;tcp|stimeout;3000000|fflags;nobuffer|flags;low_delay|max_delay;100000|probesize;32|analyzeduration;0"
LOCAL_CAPTURE_WARMUP_SECONDS = 1.0
NETWORK_CAPTURE_WARMUP_SECONDS = 3.0
NETWORK_CAPTURE_MIN_READS = 8
NETWORK_CAPTURE_MAX_READS = 45
DEMO_STREAM_PREFIXES = ("demo:", "sample:", "mock:")
logger = logging.getLogger(__name__)


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
        self._frame_cache_lock = Lock()
        self._frame_cache: Dict[str, Dict[str, Any]] = {}

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
        with self._capture_lock:
            capture = self._capture_frame_unlocked(camera)
        self._store_latest_frame(camera, capture["frame"], capture["source"])
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
            }

    def _store_latest_frame(self, camera: Dict[str, Any], frame: Any, source_label: str) -> None:
        try:
            height, width = frame.shape[:2]
        except (AttributeError, ValueError):
            return
        key = self._frame_cache_key(camera)
        with self._frame_cache_lock:
            self._frame_cache[key] = {
                "frame": frame.copy(),
                "width": width,
                "height": height,
                "source": source_label,
                "monotonic": time.monotonic(),
            }

    def _frame_cache_key(self, camera: Dict[str, Any]) -> str:
        camera_id = camera.get("id")
        stream_url = str(camera.get("stream_url", "")).strip()
        return f"{camera_id or 'source'}::{stream_url}"

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
        drop_stale_frames: int = 4,
    ) -> Generator[bytes, None, None]:
        cv2 = _load_cv2()
        source, _backend, source_label = self.resolve_capture_source(camera)
        if self._is_demo_source(source):
            yield from self._demo_mjpeg_frames(
                cv2,
                camera,
                fps=fps,
                jpeg_quality=jpeg_quality,
                max_width=max_width,
                max_height=max_height,
            )
            return

        is_local_source = isinstance(source, int)
        cap = None
        last_good_frame = None
        black_frame_streak = 0
        reconnect_count = 0
        delay = 1.0 / max(1, min(int(fps), 15))
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), max(35, min(int(jpeg_quality), 95))]
        stale_frame_reads = max(0, min(int(drop_stale_frames), 12))
        black_confirm_frames = max(3, min(int(fps), 12))
        try:
            while True:
                if cap is None or not cap.isOpened():
                    if cap is not None:
                        cap.release()
                    cap = self._open_stream_capture(cv2, source, is_local_source)
                    if not cap.isOpened():
                        cap.release()
                        cap = None
                        time.sleep(0.35)
                        continue
                    if reconnect_count:
                        logger.info("camera %s stream recovered after %s reconnect(s)", camera.get("id"), reconnect_count)
                        reconnect_count = 0
                ok, frame = self._latest_stream_frame(cap, stale_frame_reads)
                if not ok or frame is None:
                    reconnect_count += 1
                    logger.warning("camera %s stream read failed; reopening capture", camera.get("id"))
                    cap.release()
                    cap = None
                    time.sleep(0.18)
                    continue

                if self._frame_is_near_black(cv2, frame):
                    black_frame_streak += 1
                    if black_frame_streak == 1:
                        logger.warning("camera %s emitted a near-black frame; holding last valid preview frame", camera.get("id"))
                    display_frame = last_good_frame if last_good_frame is not None and black_frame_streak < black_confirm_frames else frame
                else:
                    if black_frame_streak:
                        logger.info("camera %s recovered from %s near-black frame(s)", camera.get("id"), black_frame_streak)
                    black_frame_streak = 0
                    last_good_frame = frame.copy()
                    display_frame = frame

                self._store_latest_frame(camera, display_frame, source_label)
                output_frame = self._resize_for_stream(cv2, display_frame, max_width=max_width, max_height=max_height)
                ok, encoded = cv2.imencode(".jpg", output_frame, encode_params)
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
            if cap is not None:
                cap.release()

    def _open_stream_capture(self, cv2: Any, source: Any, is_local_source: bool) -> Any:
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
        if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not is_local_source and hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000)
        if not is_local_source and hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 8000)
        return cap

    def _frame_is_near_black(self, cv2: Any, frame: Any) -> bool:
        try:
            sample = frame[::8, ::8]
            gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
            return float(gray.mean()) < 6.0 and float(gray.std()) < 3.0
        except (AttributeError, TypeError, ValueError):
            return True

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

    def _demo_mjpeg_frames(
        self,
        cv2: Any,
        camera: Dict[str, Any],
        fps: int,
        jpeg_quality: int,
        max_width: int,
        max_height: int,
    ) -> Generator[bytes, None, None]:
        delay = 1.0 / max(1, min(int(fps), 15))
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), max(35, min(int(jpeg_quality), 95))]
        frame_index = 0
        while True:
            frame = self._demo_frame(cv2, camera, frame_index=frame_index)
            self._store_latest_frame(camera, frame, "demo stream")
            frame = self._resize_for_stream(cv2, frame, max_width=max_width, max_height=max_height)
            ok, encoded = cv2.imencode(".jpg", frame, encode_params)
            if ok:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Cache-Control: no-store\r\n\r\n"
                    + encoded.tobytes()
                    + b"\r\n"
                )
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
