from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.pipeline import VisionPipeline
from app.vision.pose_factor_graph import PoseFactorGraphEngine
from app.vision.pose_rtmpose import RtmposeAnalyzer


def pose_payload(*, confidence: float, names: list[str], bbox: list[float]) -> dict:
    return {
        "bbox": bbox,
        "confidence": confidence,
        "posture": "lying",
        "posture_confidence": confidence,
        "posture_factors": {"body_aspect": 2.0},
        "fall_score": 0.90,
        "action_hints": ["fall_candidate", "lying"],
        "keypoints": [
            {
                "name": name,
                "x": 20.0 + index * 12.0,
                "y": 60.0 + index * 4.0,
                "confidence": confidence,
                "visible": True,
            }
            for index, name in enumerate(names)
        ],
    }


def analyze(analyzer: RtmposeAnalyzer, pose: dict) -> dict:
    return analyzer._result_from_raw_poses(
        [pose],
        {},
        model_name="boundary-test",
        model_label="Boundary Test",
        model_message="ready",
        backend="test",
        detection_source="test",
        external_box_count=1,
        inference_retried=False,
    )


def main() -> None:
    analyzer = RtmposeAnalyzer(enabled=True)
    half_body = analyze(analyzer, pose_payload(
        confidence=0.55,
        names=[
            "nose", "left_shoulder", "right_shoulder",
            "left_elbow", "right_elbow", "left_wrist",
        ],
        bbox=[100.0, 40.0, 260.0, 240.0],
    ))
    visible_pose = (half_body.get("poses") or [{}])[0]
    if half_body.get("display_pose_count") != 1 or not visible_pose.get("display_evidence_eligible"):
        raise SystemExit("half-body pose was incorrectly removed from the display stream")
    if (
        half_body.get("fall_evidence_pose_count") != 0
        or half_body.get("pose_fall_candidate")
        or half_body.get("pose_fall_score") != 0.0
        or visible_pose.get("fall_evidence_eligible")
        or "fall_candidate" in (visible_pose.get("action_hints") or [])
    ):
        raise SystemExit("half-body display pose leaked into formal fall evidence")

    full_body = analyze(analyzer, pose_payload(
        confidence=0.72,
        names=[
            "nose", "left_shoulder", "right_shoulder", "left_hip", "right_hip",
            "left_knee", "right_knee", "left_ankle", "right_ankle",
        ],
        bbox=[120.0, 30.0, 300.0, 330.0],
    ))
    if (
        full_body.get("display_pose_count") != 1
        or full_body.get("fall_evidence_pose_count") != 1
        or not full_body.get("pose_fall_candidate")
    ):
        raise SystemExit("full-quality pose lost display or formal fall eligibility")

    invalid = analyze(analyzer, pose_payload(
        confidence=0.10,
        names=["nose", "left_shoulder", "right_shoulder", "left_hip"],
        bbox=[100.0, 100.0, 104.0, 104.0],
    ))
    if invalid.get("display_pose_count") != 0 or len(invalid.get("rejected_poses") or []) != 1:
        raise SystemExit("invalid pose geometry entered the display stream")

    pipeline = VisionPipeline(
        black_brightness_threshold=18,
        black_contrast_threshold=4,
        motion_threshold=0.015,
        detector_backend="basic",
    )
    display_only_pose = dict(visible_pose)
    display_only_pose["track_id"] = "c1-display-only"
    scene_result = pipeline._pose_with_scene_context(
        half_body,
        [display_only_pose],
        {"pose_fall_threshold": 0.78},
    )
    if scene_result.get("pose_fall_candidate") or scene_result.get("pose_fall_score") != 0.0:
        raise SystemExit("scene annotation recreated fall evidence from a display-only pose")

    factor_result = PoseFactorGraphEngine().update(
        1,
        {
            "image_width": 640,
            "image_height": 360,
            "motion_score": 0.08,
            "people": [{"track_id": "c1-display-only", "bbox": display_only_pose["bbox"]}],
            "poses": [display_only_pose],
        },
        monotonic_at=1.0,
    )
    if factor_result.get("tracks"):
        raise SystemExit("display-only pose entered the temporal fall factor graph")

    print({
        "ok": True,
        "half_body_visible": True,
        "half_body_fall_suppressed": True,
        "full_body_fall_eligible": True,
        "invalid_geometry_rejected": True,
        "pipeline_risk_isolated": True,
        "factor_graph_risk_isolated": True,
    })


if __name__ == "__main__":
    main()
