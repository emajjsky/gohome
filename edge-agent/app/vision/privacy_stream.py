from __future__ import annotations

from typing import Any, Callable, Dict, Generator

import numpy as np

from ..camera_agent import _load_cv2
from ..video_privacy import normalize_privacy_mode, stricter_privacy_mode
from .synchronized_pose_stream import DEFAULT_SKELETON_EDGES


class PrivacyFrameRenderer:
    """Render privacy-safe relay frames without changing safety inference inputs."""

    version = "privacy-frame-renderer-v2"

    def __init__(self, tracker: Any) -> None:
        self.tracker = tracker

    def render_jpeg(self, camera_id: int, jpeg: bytes, mode: str, *, quality: int = 55) -> bytes:
        resolved_mode = normalize_privacy_mode(mode)
        if resolved_mode == "original":
            return jpeg

        cv2 = _load_cv2()
        encoded = np.frombuffer(jpeg, dtype=np.uint8)
        frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if frame is None or frame.size == 0:
            raise RuntimeError("privacy frame decode failed")

        metadata = self._tracking_metadata(int(camera_id))
        if resolved_mode == "person_blur":
            output = self._render_person_blur(cv2, frame, metadata)
        else:
            output = self._render_skeleton(cv2, frame, metadata)

        encode_params = [
            int(cv2.IMWRITE_JPEG_QUALITY),
            max(40, min(int(quality), 85)),
        ]
        ok, rendered = cv2.imencode(".jpg", output, encode_params)
        if not ok:
            raise RuntimeError("privacy frame encode failed")
        return rendered.tobytes()

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

    def _render_skeleton(self, cv2: Any, frame: Any, metadata: Dict[str, Any]) -> Any:
        canvas = frame.copy()
        tracking = dict(metadata.get("tracking") or {})
        state = str(tracking.get("state") or "empty")
        if state not in {"observed", "tracked", "coasting"}:
            return canvas

        height, width = canvas.shape[:2]
        source_width = max(1, int(metadata.get("image_width") or width))
        source_height = max(1, int(metadata.get("image_height") or height))
        scale_x = width / source_width
        scale_y = height / source_height
        context = dict(metadata.get("analysis_context") or {})
        edges = context.get("pose_skeleton_edges")
        if not isinstance(edges, list) or not edges:
            edges = DEFAULT_SKELETON_EDGES
        line_color = (54, 186, 238)
        joint_color = (242, 242, 238)

        for box in self._privacy_boxes(metadata, width, height):
            self._obscure_region(cv2, canvas, *box)

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
        return canvas

    def _privacy_boxes(self, metadata: Dict[str, Any], width: int, height: int) -> list[tuple[int, int, int, int]]:
        tracking = dict(metadata.get("tracking") or {})
        if str(tracking.get("state") or "") not in {"observed", "tracked", "coasting"}:
            return []
        source_width = max(1, int(metadata.get("image_width") or width))
        source_height = max(1, int(metadata.get("image_height") or height))
        scale_x = width / source_width
        scale_y = height / source_height
        boxes: list[tuple[int, int, int, int]] = []
        context = dict(metadata.get("analysis_context") or {})
        targets = [*(tracking.get("poses") or []), *(context.get("people") or [])]
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
        small_width = max(12, width // 20)
        small_height = max(8, height // 20)
        reduced = cv2.resize(frame, (small_width, small_height), interpolation=cv2.INTER_AREA)
        pixelated = cv2.resize(reduced, (width, height), interpolation=cv2.INTER_NEAREST)
        return cv2.GaussianBlur(pixelated, (21, 21), 0)

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
