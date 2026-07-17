from __future__ import annotations

from pathlib import Path
import sys

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.continual_pose_tracker import ContinualPoseTracker


def main() -> None:
    clock = {"now": 100.0}
    tracker = ContinualPoseTracker(
        max_age_seconds=0.6,
        min_tracked_points=6,
        monotonic_clock=lambda: clock["now"],
    )
    frame, pose = synthetic_anchor()
    observed = tracker.observe(
        24,
        frame,
        frame_id="24-100",
        captured_at="2026-07-17T02:00:00+00:00",
        poses=[pose],
    )
    if observed["state"] != "observed" or observed["pose_count"] != 1:
        raise SystemExit("fresh model anchor was not recorded as observed")
    if not tracker.has_anchor(24):
        raise SystemExit("fresh observed pose did not open the short tracking window")

    shifted = translate(frame, dx=5, dy=3)
    clock["now"] = 100.05
    throttled = tracker.update_frame(
        24,
        shifted,
        frame_id="24-100-fast",
        captured_at="2026-07-17T02:00:00.050000+00:00",
    )
    if throttled["state"] != "observed" or throttled["frame_id"] != "24-100":
        raise SystemExit("KLT ignored its 6-8 FPS processing limit")

    clock["now"] = 100.11
    tracked = tracker.update_frame(
        24,
        shifted,
        frame_id="24-101",
        captured_at="2026-07-17T02:00:00.100000+00:00",
    )
    if tracked["state"] != "tracked" or tracked["pose_count"] != 1:
        raise SystemExit("KLT did not produce a tracked pose between model anchors")
    tracked_pose = tracked["poses"][0]
    if tracked_pose.get("tracking_state") != "tracked":
        raise SystemExit("tracked pose did not expose its evidence state")
    if tracked_pose.get("fall_evidence_eligible") or tracked_pose.get("person_evidence_eligible"):
        raise SystemExit("tracked-only pose entered formal person or fall evidence")
    visible = [point for point in tracked_pose.get("keypoints") or [] if point.get("visible")]
    dx = np.median([point["x"] - source["x"] for point, source in zip(visible, pose["keypoints"])])
    dy = np.median([point["y"] - source["y"] for point, source in zip(visible, pose["keypoints"])])
    if abs(float(dx) - 5.0) > 1.0 or abs(float(dy) - 3.0) > 1.0:
        raise SystemExit(f"tracked keypoints drifted from the synthetic translation: dx={dx}, dy={dy}")

    camera_25_frame, camera_25_pose = synthetic_anchor(offset_x=120)
    tracker.observe(
        25,
        camera_25_frame,
        frame_id="25-100",
        captured_at="2026-07-17T02:00:00+00:00",
        poses=[camera_25_pose],
    )
    if tracker.latest(24)["poses"][0]["track_id"] == tracker.latest(25)["poses"][0]["track_id"]:
        raise SystemExit("camera-local pose states were mixed")

    clock["now"] = 100.7
    expired = tracker.update_frame(
        24,
        shifted,
        frame_id="24-107",
        captured_at="2026-07-17T02:00:00.700000+00:00",
    )
    if expired["state"] != "expired" or expired["pose_count"] != 0:
        raise SystemExit("tracked pose remained visible beyond the 600ms freshness gate")
    if tracker.has_anchor(24):
        raise SystemExit("expired tracking window still requested camera frame copies")

    clock["now"] = 101.0
    tracker.observe(
        24,
        frame,
        frame_id="24-200",
        captured_at="2026-07-17T02:00:01+00:00",
        poses=[pose],
    )
    clock["now"] = 101.11
    rejected = tracker.update_frame(
        24,
        np.zeros_like(frame),
        frame_id="24-201",
        captured_at="2026-07-17T02:00:01.100000+00:00",
    )
    if rejected["state"] != "expired" or rejected.get("reason") not in {
        "insufficient_points",
        "forward_backward_error",
        "optical_flow_failed",
    }:
        raise SystemExit(f"invalid optical flow was not rejected: {rejected}")

    runtime = tracker.status([24, 25])
    camera_24_runtime = next(item for item in runtime["cameras"] if item["camera_id"] == 24)
    if camera_24_runtime["observed_count"] != 2 or camera_24_runtime["tracked_count"] < 1:
        raise SystemExit(f"continual pose runtime counters are incomplete: {runtime}")
    if camera_24_runtime["expired_count"] < 2:
        raise SystemExit(f"continual pose expiry metrics are incomplete: {runtime}")

    tracker.reset_camera(25)
    if tracker.latest(25)["state"] != "empty":
        raise SystemExit("camera reset did not clear continual pose state")

    worker_source = (ROOT / "app" / "worker.py").read_text(encoding="utf-8")
    for contract in ("ContinualPoseTracker()", "_run_continual_tracking", "latest_cached_frame"):
        if contract not in worker_source:
            raise SystemExit(f"production continual pose loop is missing: {contract}")
    deploy_source = (ROOT / "scripts" / "deploy-to-pi.sh").read_text(encoding="utf-8")
    if "scripts/verify-continual-pose-tracker.py" not in deploy_source:
        raise SystemExit("continual pose QA script would be deployed into the production box")

    print({
        "ok": True,
        "translation": [round(float(dx), 2), round(float(dy), 2)],
        "tracked_points": tracked["quality"]["tracked_point_count"],
        "tracked_age_seconds": tracked["age_seconds"],
        "expired_state": expired["state"],
        "drift_rejection": rejected.get("reason"),
        "camera_isolation": True,
        "runtime_metrics": camera_24_runtime,
        "production_wiring": True,
    })


def synthetic_anchor(offset_x: int = 0) -> tuple[np.ndarray, dict]:
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    coordinates = [
        (100, 45),
        (88, 62),
        (112, 62),
        (80, 92),
        (120, 92),
        (78, 130),
        (122, 130),
        (82, 175),
        (118, 175),
    ]
    keypoints = []
    for index, (x, y) in enumerate(coordinates):
        x += offset_x
        cv2.circle(frame, (x, y), 5, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.line(frame, (x - 7, y), (x + 7, y), (90, 210, 250), 2, cv2.LINE_AA)
        cv2.line(frame, (x, y - 7), (x, y + 7), (90, 210, 250), 2, cv2.LINE_AA)
        keypoints.append({
            "name": f"point_{index}",
            "x": float(x),
            "y": float(y),
            "confidence": 0.92,
            "visible": True,
        })
    return frame, {
        "track_id": f"c{24 if offset_x == 0 else 25}-p1",
        "bbox": [70.0 + offset_x, 30.0, 130.0 + offset_x, 190.0],
        "confidence": 0.91,
        "posture": "standing",
        "fall_score": 0.08,
        "fall_evidence_eligible": True,
        "person_evidence_eligible": True,
        "keypoints": keypoints,
    }


def translate(frame: np.ndarray, *, dx: int, dy: int) -> np.ndarray:
    matrix = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(frame, matrix, (frame.shape[1], frame.shape[0]))


if __name__ == "__main__":
    main()
