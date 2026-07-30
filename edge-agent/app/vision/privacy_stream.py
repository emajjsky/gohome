from __future__ import annotations

from collections import OrderedDict
from threading import RLock
from typing import Any, Callable, Dict, Generator

import numpy as np

from ..camera_agent import _load_cv2
from ..video_privacy import normalize_privacy_mode, stricter_privacy_mode
from .privacy_background import PrivacyBackgroundReconstructor
from .synchronized_pose_stream import DEFAULT_SKELETON_EDGES


class PrivacyFrameRenderer:
    """Render privacy-safe relay frames without changing safety inference inputs."""

    version = "privacy-frame-renderer-v6"

    def __init__(
        self,
        tracker: Any,
        background_reconstructor: PrivacyBackgroundReconstructor | None = None,
    ) -> None:
        self.tracker = tracker
        self.background_reconstructor = background_reconstructor or PrivacyBackgroundReconstructor()
        self._render_cache: OrderedDict[tuple[Any, ...], bytes] = OrderedDict()
        self._latest_safe_scenes: OrderedDict[tuple[int, int, int], Any] = OrderedDict()
        self._cache_lock = RLock()

    def render_jpeg(self, camera_id: int, jpeg: bytes, mode: str, *, quality: int = 55) -> bytes:
        resolved_mode = normalize_privacy_mode(mode)
        if resolved_mode == "original":
            return jpeg

        cv2 = _load_cv2()
        encoded = np.frombuffer(jpeg, dtype=np.uint8)
        frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if frame is None or frame.size == 0:
            raise RuntimeError("privacy frame decode failed")

        synchronized = self._synchronized_bundle(int(camera_id))
        if synchronized is not None:
            source = synchronized.get("frame")
            tracking = dict(synchronized.get("tracking") or {})
            if source is None or not str(tracking.get("frame_id") or ""):
                output = self._safe_fallback_scene(cv2, int(camera_id), frame)
                return self._encode_jpeg(cv2, output, quality)
            cache_key = (
                int(camera_id),
                resolved_mode,
                str(tracking.get("frame_id")),
                int(frame.shape[1]),
                int(frame.shape[0]),
                int(quality),
            )
            cached = self._cached_render(cache_key)
            if cached is not None:
                return cached
            source_height, source_width = source.shape[:2]
            output_frame = cv2.resize(
                source,
                (int(frame.shape[1]), int(frame.shape[0])),
                interpolation=cv2.INTER_AREA if source_width > frame.shape[1] else cv2.INTER_LINEAR,
            )
            metadata = {
                "tracking": tracking,
                "analysis_context": dict(synchronized.get("analysis_context") or {}),
                "image_width": int(source_width),
                "image_height": int(source_height),
            }
            privacy_boxes = self._privacy_boxes(metadata, output_frame.shape[1], output_frame.shape[0])
            if not privacy_boxes:
                self.background_reconstructor.reconstruct(
                    cv2,
                    int(camera_id),
                    output_frame,
                    np.zeros(output_frame.shape[:2], dtype=np.uint8),
                    clear_token=str(tracking.get("frame_id") or ""),
                )
            if resolved_mode == "person_blur":
                output = self._render_person_blur(cv2, output_frame, metadata)
            else:
                output = self._render_skeleton(cv2, int(camera_id), output_frame, metadata)
            rendered = self._encode_jpeg(cv2, output, quality)
            self._store_cached_render(cache_key, rendered)
            return rendered

        if self._supports_synchronized_frames():
            output = self._safe_fallback_scene(cv2, int(camera_id), frame)
            return self._encode_jpeg(cv2, output, quality)

        metadata = self._tracking_metadata(int(camera_id))
        if resolved_mode == "person_blur":
            output = self._render_person_blur(cv2, frame, metadata)
        else:
            output = self._render_skeleton(cv2, int(camera_id), frame, metadata)
        return self._encode_jpeg(cv2, output, quality)

    def _supports_synchronized_frames(self) -> bool:
        return self.tracker is not None and callable(getattr(self.tracker, "latest_synchronized_frame", None))

    def _synchronized_bundle(self, camera_id: int) -> Dict[str, Any] | None:
        if not self._supports_synchronized_frames():
            return None
        try:
            bundle = self.tracker.latest_synchronized_frame(camera_id)
            return dict(bundle) if isinstance(bundle, dict) else None
        except Exception:
            return None

    def _encode_jpeg(self, cv2: Any, output: Any, quality: int) -> bytes:
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), max(40, min(int(quality), 85))]
        ok, rendered = cv2.imencode(".jpg", output, encode_params)
        if not ok:
            raise RuntimeError("privacy frame encode failed")
        return rendered.tobytes()

    def safe_scene_jpeg(self, camera_id: int, jpeg: bytes, *, quality: int = 55) -> bytes:
        """Return only a retained person-free scene for client-side pose rendering."""
        cv2 = _load_cv2()
        encoded = np.frombuffer(jpeg, dtype=np.uint8)
        frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if frame is None or frame.size == 0:
            raise RuntimeError("safe scene frame decode failed")
        synchronized = self._synchronized_bundle(int(camera_id))
        if synchronized is not None:
            source = synchronized.get("frame")
            tracking = dict(synchronized.get("tracking") or {})
            if source is not None:
                source_height, source_width = source.shape[:2]
                frame = cv2.resize(
                    source,
                    (int(frame.shape[1]), int(frame.shape[0])),
                    interpolation=cv2.INTER_AREA if source_width > frame.shape[1] else cv2.INTER_LINEAR,
                )
                metadata = {
                    "tracking": tracking,
                    "analysis_context": dict(synchronized.get("analysis_context") or {}),
                    "image_width": int(source_width),
                    "image_height": int(source_height),
                }
            else:
                metadata = self._tracking_metadata(int(camera_id))
        else:
            metadata = self._tracking_metadata(int(camera_id))
        scene = self._person_free_scene(cv2, int(camera_id), frame, metadata)
        return self._encode_jpeg(cv2, scene, quality)

    def _person_free_scene(
        self,
        cv2: Any,
        camera_id: int,
        frame: Any,
        metadata: Dict[str, Any],
    ) -> Any:
        height, width = frame.shape[:2]
        boxes = self._privacy_boxes(metadata, width, height)
        if boxes:
            return self._safe_fallback_scene(cv2, camera_id, frame)
        tracking = dict(metadata.get("tracking") or {})
        scene = self.background_reconstructor.reconstruct(
            cv2,
            camera_id,
            frame,
            np.zeros((height, width), dtype=np.uint8),
            clear_token=str(tracking.get("frame_id") or ""),
        )
        self._store_safe_scene(camera_id, scene)
        return scene

    def _cached_render(self, key: tuple[Any, ...]) -> bytes | None:
        with self._cache_lock:
            value = self._render_cache.get(key)
            if value is not None:
                self._render_cache.move_to_end(key)
            return value

    def _store_cached_render(self, key: tuple[Any, ...], value: bytes) -> None:
        with self._cache_lock:
            self._render_cache[key] = value
            self._render_cache.move_to_end(key)
            while len(self._render_cache) > 32:
                self._render_cache.popitem(last=False)

    def _safe_fallback_scene(self, cv2: Any, camera_id: int, frame: Any) -> Any:
        height, width = frame.shape[:2]
        key = (int(camera_id), int(width), int(height))
        with self._cache_lock:
            scene = self._latest_safe_scenes.get(key)
            if scene is not None:
                self._latest_safe_scenes.move_to_end(key)
                return scene.copy()
        return self.background_reconstructor.safe_scene(cv2, int(camera_id), frame)

    def _store_safe_scene(self, camera_id: int, scene: Any) -> None:
        height, width = scene.shape[:2]
        key = (int(camera_id), int(width), int(height))
        with self._cache_lock:
            self._latest_safe_scenes[key] = scene.copy()
            self._latest_safe_scenes.move_to_end(key)
            while len(self._latest_safe_scenes) > 6:
                self._latest_safe_scenes.popitem(last=False)

    def _tracking_metadata(self, camera_id: int) -> Dict[str, Any]:
        if self.tracker is None:
            return {"tracking": {"state": "empty", "poses": []}}
        try:
            return dict(self.tracker.latest_metadata(camera_id) or {})
        except Exception:
            return {"tracking": {"state": "empty", "poses": []}}

    def _render_person_blur(self, cv2: Any, frame: Any, metadata: Dict[str, Any]) -> Any:
        output = frame.copy()
        boxes = self._privacy_boxes(metadata, output.shape[1], output.shape[0])
        for x1, y1, x2, y2 in boxes:
            self._obscure_region(cv2, output, x1, y1, x2, y2)
        return output

    def _render_skeleton(
        self,
        cv2: Any,
        camera_id: int,
        frame: Any,
        metadata: Dict[str, Any],
    ) -> Any:
        tracking = dict(metadata.get("tracking") or {})
        state = str(tracking.get("state") or "empty")
        height, width = frame.shape[:2]
        mask = np.zeros((height, width), dtype=np.uint8)
        privacy_boxes = self._privacy_boxes(metadata, width, height)
        for box in privacy_boxes:
            cv2.rectangle(mask, (box[0], box[1]), (box[2] - 1, box[3] - 1), 255, -1)
        canvas = self.background_reconstructor.reconstruct(
            cv2,
            camera_id,
            frame,
            mask,
            clear_token=str(tracking.get("frame_id") or ""),
        )
        self._store_safe_scene(camera_id, canvas)
        if state not in {"observed", "tracked", "coasting"}:
            return canvas

        source_width = max(1, int(metadata.get("image_width") or width))
        source_height = max(1, int(metadata.get("image_height") or height))
        scale_x = width / source_width
        scale_y = height / source_height
        context = dict(metadata.get("analysis_context") or {})
        edges = context.get("pose_skeleton_edges")
        if not isinstance(edges, list) or not edges:
            edges = DEFAULT_SKELETON_EDGES
        line_color = (42, 179, 236)
        joint_color = (248, 248, 245)

        for pose in tracking.get("poses") or []:
            if not isinstance(pose, dict):
                continue
            box = self._target_box(pose, scale_x, scale_y, width, height)
            if box is None:
                continue
            points = {
                str(point.get("name")): point
                for point in (pose.get("keypoints") or [])
                if isinstance(point, dict)
                and point.get("name")
                and point.get("visible")
                and float(point.get("confidence") or 0.0) >= 0.22
            }
            for edge in edges:
                if not isinstance(edge, (list, tuple)) or len(edge) < 2:
                    continue
                start = points.get(str(edge[0]))
                end = points.get(str(edge[1]))
                if start is None or end is None:
                    continue
                p1 = self._point(start, scale_x, scale_y, width, height)
                p2 = self._point(end, scale_x, scale_y, width, height)
                cv2.line(canvas, p1, p2, (8, 8, 8), 6, cv2.LINE_AA)
                cv2.line(canvas, p1, p2, line_color, 3, cv2.LINE_AA)
            for point in points.values():
                center = self._point(point, scale_x, scale_y, width, height)
                cv2.circle(canvas, center, 5, (8, 8, 8), -1, cv2.LINE_AA)
                cv2.circle(canvas, center, 3, joint_color, -1, cv2.LINE_AA)
            self._draw_head(cv2, canvas, points, scale_x, scale_y, width, height, line_color)
        return canvas

    def _privacy_boxes(self, metadata: Dict[str, Any], width: int, height: int) -> list[tuple[int, int, int, int]]:
        tracking = dict(metadata.get("tracking") or {})
        tracking_active = str(tracking.get("state") or "") in {"observed", "tracked", "coasting"}
        source_width = max(1, int(metadata.get("image_width") or width))
        source_height = max(1, int(metadata.get("image_height") or height))
        scale_x = width / source_width
        scale_y = height / source_height
        boxes: list[tuple[int, int, int, int]] = []
        context = dict(metadata.get("analysis_context") or {})
        targets = [
            *((tracking.get("poses") or []) if tracking_active else []),
            *(context.get("people") or []),
        ]
        for target in targets:
            box = self._target_box(target, scale_x, scale_y, width, height)
            if box is None:
                continue
            for index, current in enumerate(boxes):
                if self._box_overlap_ratio(box, current) >= 0.55:
                    boxes[index] = (
                        min(box[0], current[0]),
                        min(box[1], current[1]),
                        max(box[2], current[2]),
                        max(box[3], current[3]),
                    )
                    break
            else:
                boxes.append(box)
        return boxes

    def _target_box(
        self,
        target: Any,
        scale_x: float,
        scale_y: float,
        width: int,
        height: int,
    ) -> tuple[int, int, int, int] | None:
        bbox = target.get("bbox") if isinstance(target, dict) else None
        if not isinstance(bbox, list) or len(bbox) < 4:
            return None
        try:
            raw_x1, raw_y1, raw_x2, raw_y2 = [float(value) for value in bbox[:4]]
        except (TypeError, ValueError):
            return None
        if raw_x2 <= raw_x1 or raw_y2 <= raw_y1:
            return None
        margin_x = max(12.0, (raw_x2 - raw_x1) * 0.18)
        margin_y = max(12.0, (raw_y2 - raw_y1) * 0.16)
        x1 = max(0, min(width - 1, int((raw_x1 - margin_x) * scale_x)))
        y1 = max(0, min(height - 1, int((raw_y1 - margin_y) * scale_y)))
        x2 = max(x1 + 1, min(width, int((raw_x2 + margin_x) * scale_x)))
        y2 = max(y1 + 1, min(height, int((raw_y2 + margin_y) * scale_y)))
        return (x1, y1, x2, y2)

    def _box_overlap_ratio(
        self,
        first: tuple[int, int, int, int],
        second: tuple[int, int, int, int],
    ) -> float:
        intersection_width = max(0, min(first[2], second[2]) - max(first[0], second[0]))
        intersection_height = max(0, min(first[3], second[3]) - max(first[1], second[1]))
        intersection = intersection_width * intersection_height
        first_area = max(1, (first[2] - first[0]) * (first[3] - first[1]))
        second_area = max(1, (second[2] - second[0]) * (second[3] - second[1]))
        return intersection / min(first_area, second_area)

    def _obscure_region(
        self,
        cv2: Any,
        frame: Any,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
    ) -> None:
        region = frame[y1:y2, x1:x2]
        if region.size:
            frame[y1:y2, x1:x2] = self._strong_blur(cv2, region)

    def _strong_blur(self, cv2: Any, frame: Any) -> Any:
        height, width = frame.shape[:2]
        kernel = max(21, min(81, ((min(width, height) // 5) | 1)))
        return cv2.GaussianBlur(frame, (kernel, kernel), 0)

    def _draw_head(
        self,
        cv2: Any,
        frame: Any,
        points: Dict[str, Dict[str, Any]],
        scale_x: float,
        scale_y: float,
        width: int,
        height: int,
        color: tuple[int, int, int],
    ) -> None:
        nose = points.get("nose")
        left_ear = points.get("left_ear")
        right_ear = points.get("right_ear")
        left_shoulder = points.get("left_shoulder")
        right_shoulder = points.get("right_shoulder")
        if nose is None or left_shoulder is None or right_shoulder is None:
            return
        center = self._point(nose, scale_x, scale_y, width, height)
        if left_ear is not None and right_ear is not None:
            left = self._point(left_ear, scale_x, scale_y, width, height)
            right = self._point(right_ear, scale_x, scale_y, width, height)
            radius = int(round(max(7.0, np.hypot(right[0] - left[0], right[1] - left[1]) * 0.62)))
        else:
            left = self._point(left_shoulder, scale_x, scale_y, width, height)
            right = self._point(right_shoulder, scale_x, scale_y, width, height)
            radius = int(round(max(7.0, np.hypot(right[0] - left[0], right[1] - left[1]) * 0.28)))
        radius = min(radius, max(8, int(min(width, height) * 0.09)))
        cv2.circle(frame, center, radius, (8, 8, 8), 5, cv2.LINE_AA)
        cv2.circle(frame, center, radius, color, 2, cv2.LINE_AA)

    def _point(
        self,
        point: Dict[str, Any],
        scale_x: float,
        scale_y: float,
        width: int,
        height: int,
    ) -> tuple[int, int]:
        return (
            max(0, min(width - 1, int(round(float(point.get("x") or 0.0) * scale_x)))),
            max(0, min(height - 1, int(round(float(point.get("y") or 0.0) * scale_y)))),
        )


class PrivacyMjpegStream:
    def __init__(self, camera_agent: Any, renderer: PrivacyFrameRenderer) -> None:
        self.camera_agent = camera_agent
        self.renderer = renderer

    def mjpeg_frames(
        self,
        camera: Dict[str, Any],
        *,
        privacy_mode: str,
        privacy_mode_resolver: Callable[[], str] | None = None,
        fps: int,
        jpeg_quality: int,
        max_width: int,
        max_height: int,
        drop_stale_frames: int,
    ) -> Generator[bytes, None, None]:
        requested_mode = normalize_privacy_mode(privacy_mode)
        for chunk in self.camera_agent.mjpeg_frames(
            camera,
            fps=fps,
            jpeg_quality=jpeg_quality,
            max_width=max_width,
            max_height=max_height,
            drop_stale_frames=drop_stale_frames,
        ):
            jpeg = self._extract_jpeg(chunk)
            if not jpeg:
                continue
            mode = stricter_privacy_mode(
                privacy_mode_resolver() if privacy_mode_resolver is not None else requested_mode,
                requested_mode,
            )
            try:
                rendered = self.renderer.render_jpeg(
                    int(camera["id"]),
                    jpeg,
                    mode,
                    quality=jpeg_quality,
                )
            except Exception:
                if mode == "original":
                    rendered = jpeg
                else:
                    continue
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Cache-Control: no-store\r\n"
                + f"X-GoHome-Privacy-Mode: {mode}\r\n\r\n".encode("ascii")
                + rendered
                + b"\r\n"
            )

    def _extract_jpeg(self, chunk: bytes) -> bytes:
        marker = b"\r\n\r\n"
        if marker not in chunk:
            return chunk
        body = chunk.split(marker, 1)[1]
        return body[:-2] if body.endswith(b"\r\n") else body
