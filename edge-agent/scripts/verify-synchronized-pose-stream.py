from __future__ import annotations

from pathlib import Path
import sys

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.synchronized_pose_stream import SynchronizedPoseStream


class Tracker:
    def latest_frame(self, _camera_id: int) -> dict:
        raise SystemExit("diagnostic stream used tracker-retained pixels instead of the current camera frame")

    def metadata_for_frame(self, camera_id: int, *, frame_id: str, source_key: str) -> dict:
        assert camera_id == 24
        assert frame_id == "24-101"
        assert source_key == "camera-24:g3"
        return {
            "tracking": {
                "camera_id": 24,
                "state": "tracked",
                "frame_id": "24-101",
                "source_key": "camera-24:g3",
                "captured_at": "2026-07-21T04:00:00.100000+00:00",
                "formal_evidence_eligible": False,
                "poses": [{
                    "track_id": "c24-p7",
                    "bbox": [42.0, 20.0, 118.0, 132.0],
                    "confidence": 0.91,
                    "posture": "standing",
                    "tracking_state": "tracked",
                    "formal_evidence_eligible": False,
                    "keypoints": [
                        {"name": "left_shoulder", "x": 62.0, "y": 46.0, "confidence": 0.92, "visible": True},
                        {"name": "right_shoulder", "x": 96.0, "y": 46.0, "confidence": 0.93, "visible": True},
                        {"name": "left_hip", "x": 68.0, "y": 86.0, "confidence": 0.90, "visible": True},
                        {"name": "right_hip", "x": 91.0, "y": 86.0, "confidence": 0.91, "visible": True},
                        {"name": "left_knee", "x": 66.0, "y": 111.0, "confidence": 0.88, "visible": True},
                        {"name": "right_knee", "x": 94.0, "y": 111.0, "confidence": 0.89, "visible": True},
                    ],
                }],
                "quality": {"tracked_point_count": 6, "forward_backward_error": 0.12},
            },
            "analysis_context": {
                "pose_skeleton_edges": [
                    ["left_shoulder", "right_shoulder"],
                    ["left_shoulder", "left_hip"],
                    ["right_shoulder", "right_hip"],
                    ["left_hip", "right_hip"],
                    ["left_hip", "left_knee"],
                    ["right_hip", "right_knee"],
                ],
                "fall_candidate": False,
            },
        }


class CameraAgent:
    def __init__(self, frame: np.ndarray) -> None:
        self.frame = frame

    def latest_cached_frame(self, camera: dict, max_age_seconds: float) -> dict:
        assert camera["id"] == 24
        assert max_age_seconds == 0.75
        return {
            "frame": self.frame.copy(),
            "frame_id": "24-101",
            "source_key": "camera-24:g3",
        }


def main() -> None:
    frame = np.full((150, 180, 3), 34, dtype=np.uint8)
    source_copy = frame.copy()
    tracking = Tracker()
    stream = SynchronizedPoseStream(CameraAgent(frame), tracking).mjpeg_frames(
        {"id": 24},
        fps=8,
        jpeg_quality=85,
        max_width=180,
        max_height=150,
    )
    part = next(stream)
    stream.close()

    if b"X-GoHome-Frame-ID: 24-101" not in part:
        raise SystemExit("annotated stream did not expose the exact source frame id")
    if b"X-GoHome-Pose-State: tracked" not in part:
        raise SystemExit("annotated stream did not expose the tracking state")
    if b"X-GoHome-Synchronized: 1" not in part:
        raise SystemExit("annotated stream is not marked as synchronized")

    jpeg = part.split(b"\r\n\r\n", 1)[1].rsplit(b"\r\n", 1)[0]
    decoded = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if decoded is None or decoded.shape[:2] != frame.shape[:2]:
        raise SystemExit("annotated stream did not return a valid JPEG frame")
    if int(np.count_nonzero(np.abs(decoded.astype(np.int16) - frame.astype(np.int16)) > 18)) < 120:
        raise SystemExit("pose skeleton was not rendered into the synchronized frame")
    if not np.array_equal(frame, source_copy):
        raise SystemExit("pose rendering mutated the tracker's retained evidence frame")

    stale_tracking = tracking.metadata_for_frame(24, frame_id="24-101", source_key="camera-24:g3")
    stale_tracking["tracking"]["state"] = "coasting"
    stale_tracking["tracking"]["display_only_stale"] = True
    stale = SynchronizedPoseStream(CameraAgent(frame), tracking)._render_frame(
        cv2,
        frame,
        stale_tracking["tracking"],
        stale_tracking["analysis_context"],
    )
    if not np.array_equal(stale, frame):
        raise SystemExit("stale coasting pose was rendered over the current diagnostic frame")
    print({
        "ok": True,
        "same_frame_id": True,
        "server_side_pose_overlay": True,
        "source_frame_immutable": True,
        "current_camera_pixels": True,
        "stale_pose_suppressed": True,
    })


if __name__ == "__main__":
    main()
