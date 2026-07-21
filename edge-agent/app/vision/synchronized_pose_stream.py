from __future__ import annotations

import re
import time
from typing import Any, Dict, Generator

from ..camera_agent import _load_cv2, next_stream_frame_delay


DEFAULT_SKELETON_EDGES = (
    ("left_shoulder", "right_shoulder"),
    ("left_shoulder", "left_elbow"),
    ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"),
    ("right_elbow", "right_wrist"),
    ("left_shoulder", "left_hip"),
    ("right_shoulder", "right_hip"),
    ("left_hip", "right_hip"),
    ("left_hip", "left_knee"),
    ("left_knee", "left_ankle"),
    ("right_hip", "right_knee"),
    ("right_knee", "right_ankle"),
)


class SynchronizedPoseStream:
    """Encode the exact frame retained alongside each continual-pose result."""

    version = "eacp-synchronized-pose-stream-v1"

    def __init__(self, camera_agent: Any, tracker: Any) -> None:
        self.camera_agent = camera_agent
        self.tracker = tracker

    def mjpeg_frames(
        self,
        camera: Dict[str, Any],
        *,
        fps: int = 8,
        jpeg_quality: int = 72,
        max_width: int = 960,
        max_height: int = 540,
    ) -> Generator[bytes, None, None]:
        cv2 = _load_cv2()
        camera_id = int(camera["id"])
        interval = 1.0 / max(1, min(int(fps), 10))
        deadline = time.monotonic()
        last_frame_id = ""
        encode_params = [
            int(cv2.IMWRITE_JPEG_QUALITY),
            max(40, min(int(jpeg_quality), 90)),
        ]

        while True:
            bundle = self.tracker.latest_frame(camera_id) if self.tracker is not None else None
            tracking: Dict[str, Any] = {}
            context: Dict[str, Any] = {}
            if bundle is not None:
                frame = bundle.get("frame")
                tracking = dict(bundle.get("tracking") or {})
                context = dict(bundle.get("analysis_context") or {})
                frame_id = str(tracking.get("frame_id") or "")
            else:
                capture = self.camera_agent.latest_cached_frame(camera, max_age_seconds=0.75)
                if capture is None:
                    time.sleep(min(0.05, interval))
                    continue
                frame = capture.get("frame")
                frame_id = str(capture.get("frame_id") or "")
                tracking = {
                    "state": "empty",
                    "frame_id": frame_id,
                    "poses": [],
                    "formal_evidence_eligible": False,
                }

            if frame is None or not frame_id or frame_id == last_frame_id:
                time.sleep(min(0.025, interval / 2.0))
                continue

            output = self._render_frame(cv2, frame, tracking, context)
            output = self._resize(cv2, output, max_width=max_width, max_height=max_height)
            ok, encoded = cv2.imencode(".jpg", output, encode_params)
            if not ok:
                time.sleep(min(0.025, interval / 2.0))
                continue

            last_frame_id = frame_id
            safe_frame_id = self._header_value(frame_id)
            safe_state = self._header_value(str(tracking.get("state") or "empty"))
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Cache-Control: no-store\r\n"
                + f"X-GoHome-Frame-ID: {safe_frame_id}\r\n".encode("ascii")
                + f"X-GoHome-Pose-State: {safe_state}\r\n".encode("ascii")
                + b"X-GoHome-Synchronized: 1\r\n\r\n"
                + encoded.tobytes()
                + b"\r\n"
            )
            delay, deadline = next_stream_frame_delay(
                previous_deadline=deadline,
                now=time.monotonic(),
                frame_interval=interval,
            )
            if delay > 0:
                time.sleep(delay)

    def _render_frame(
        self,
        cv2: Any,
        source: Any,
        tracking: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Any:
        frame = source.copy()
        state = str(tracking.get("state") or "empty")
        if state not in {"observed", "tracked", "coasting"}:
            return frame
        poses = tracking.get("poses") if isinstance(tracking.get("poses"), list) else []
        if not poses:
            return frame

        layer = frame.copy()
        height, width = frame.shape[:2]
        edges = context.get("pose_skeleton_edges")
        if not isinstance(edges, list) or not edges:
            edges = DEFAULT_SKELETON_EDGES
        risk = bool(context.get("fall_candidate") or context.get("fire_event_candidate"))
        line_color = (68, 68, 230) if risk else (36, 177, 236)
        joint_color = (245, 245, 242)
        box_color = (68, 68, 230) if risk else (214, 214, 208)

        for pose in poses:
            if not isinstance(pose, dict):
                continue
            bbox = pose.get("bbox")
            if isinstance(bbox, list) and len(bbox) >= 4:
                x1, y1, x2, y2 = self._clamped_bbox(bbox, width, height)
                self._draw_corner_box(cv2, layer, x1, y1, x2, y2, box_color)
                track_label = self._track_label(str(pose.get("track_id") or ""))
                if track_label:
                    position = (x1 + 4, max(16, y1 - 7))
                    cv2.putText(layer, track_label, position, cv2.FONT_HERSHEY_SIMPLEX, 0.42, (24, 24, 24), 3, cv2.LINE_AA)
                    cv2.putText(layer, track_label, position, cv2.FONT_HERSHEY_SIMPLEX, 0.42, joint_color, 1, cv2.LINE_AA)

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
                p1 = self._point(start, width, height)
                p2 = self._point(end, width, height)
                cv2.line(layer, p1, p2, (24, 24, 24), 5, cv2.LINE_AA)
                cv2.line(layer, p1, p2, line_color, 2, cv2.LINE_AA)
            for point in points.values():
                center = self._point(point, width, height)
                cv2.circle(layer, center, 4, (24, 24, 24), -1, cv2.LINE_AA)
                cv2.circle(layer, center, 2, joint_color, -1, cv2.LINE_AA)

        if state == "coasting":
            cv2.addWeighted(layer, 0.46, frame, 0.54, 0.0, frame)
            return frame
        return layer

    def _draw_corner_box(
        self,
        cv2: Any,
        frame: Any,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        color: tuple[int, int, int],
    ) -> None:
        length = max(8, min(22, int(min(x2 - x1, y2 - y1) * 0.18)))
        for start, end in (
            ((x1, y1), (x1 + length, y1)),
            ((x1, y1), (x1, y1 + length)),
            ((x2, y1), (x2 - length, y1)),
            ((x2, y1), (x2, y1 + length)),
            ((x1, y2), (x1 + length, y2)),
            ((x1, y2), (x1, y2 - length)),
            ((x2, y2), (x2 - length, y2)),
            ((x2, y2), (x2, y2 - length)),
        ):
            cv2.line(frame, start, end, (24, 24, 24), 4, cv2.LINE_AA)
            cv2.line(frame, start, end, color, 2, cv2.LINE_AA)

    def _resize(self, cv2: Any, frame: Any, *, max_width: int, max_height: int) -> Any:
        height, width = frame.shape[:2]
        scale = min(
            max(1, int(max_width)) / max(1, width),
            max(1, int(max_height)) / max(1, height),
            1.0,
        )
        if scale >= 0.999:
            return frame
        return cv2.resize(
            frame,
            (max(1, int(width * scale)), max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )

    def _clamped_bbox(self, bbox: list[Any], width: int, height: int) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = [int(round(float(value))) for value in bbox[:4]]
        return (
            max(0, min(width - 1, x1)),
            max(0, min(height - 1, y1)),
            max(0, min(width - 1, x2)),
            max(0, min(height - 1, y2)),
        )

    def _point(self, point: Dict[str, Any], width: int, height: int) -> tuple[int, int]:
        return (
            max(0, min(width - 1, int(round(float(point.get("x") or 0.0))))),
            max(0, min(height - 1, int(round(float(point.get("y") or 0.0))))),
        )

    def _track_label(self, track_id: str) -> str:
        match = re.search(r"p(\d+)$", track_id)
        return f"P{match.group(1)}" if match else ""

    def _header_value(self, value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]", "", value)[:96] or "none"
