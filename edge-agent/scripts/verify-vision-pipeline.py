from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.detect_agent import DetectAgent
from app.vision.fall import FallAnalyzer
from app.vision.person_yolo import PersonDetector
from app.vision.pipeline import VisionPipeline
from app.vision.pose_rtmpose import RtmposeAnalyzer


def main() -> None:
    agent = DetectAgent(
        black_brightness_threshold=18,
        black_contrast_threshold=4,
        motion_threshold=0.015,
        detector_backend="basic",
    )
    black = np.zeros((240, 320, 3), dtype=np.uint8)
    gradient = np.tile(np.linspace(60, 132, 320, dtype=np.uint8), (240, 1))
    normal = np.dstack([gradient, np.roll(gradient, 24, axis=1), np.full_like(gradient, 96)])
    fire = normal.copy()
    fire_patch_y, fire_patch_x = np.indices((80, 80))
    fire_block = ((fire_patch_x // 8 + fire_patch_y // 8) % 3)
    fire_r = np.choose(fire_block, [255, 220, 185]).astype(np.uint8)
    fire_g = np.choose(fire_block, [210, 150, 95]).astype(np.uint8)
    fire_b = np.choose(fire_block, [16, 24, 8]).astype(np.uint8)
    fire[40:120, 180:260] = np.dstack([fire_b, fire_g, fire_r])
    red_light = normal.copy()
    red_light[40:120, 180:260] = [20, 30, 230]
    seated_half_body = synthetic_seated_half_body_frame()

    black_result = agent.analyze_frame_with_config(black)
    fire_result = agent.analyze_frame_with_config(fire)
    shifted_fire = normal.copy()
    shifted_fire[38:118, 184:264] = np.dstack([fire_b, np.roll(fire_g, 2, axis=1), np.roll(fire_r, 3, axis=0)])
    dynamic_fire_result = agent.analyze_frame_with_config(
        shifted_fire,
        previous_frame=fire,
        config={
            "fire_event_score_threshold": 0.02,
            "fire_motion_threshold": 0.001,
            "fire_temporal_threshold": 0.001,
        },
    )
    red_light_result = agent.analyze_frame_with_config(red_light)
    demo_result = agent.analyze_frame_with_config(normal, config={"force_demo_vision": True})
    presence_result = analyze_with_mocked_yolo_miss(seated_half_body)
    blank_presence_result = analyze_with_mocked_yolo_miss(black)
    weak_fall_result = FallAnalyzer().analyze(synthetic_weak_fall_people(), {})
    pose_refine_result = verify_pose_refines_presence_candidates()
    pose_cache_result = verify_pose_cache_stabilizes_tracking()
    activity_temporal_result = verify_activity_temporal_candidates()
    pose_runtime_config = verify_pose_runtime_config()

    checks = {
        "black_screen": bool(black_result["black_screen"]),
        "fire_candidate": bool(fire_result["fire_candidate"]),
        "fire_event_candidate_without_previous": bool(fire_result.get("fire_event_candidate")),
        "dynamic_fire_event_candidate": bool(dynamic_fire_result.get("fire_event_candidate")),
        "dynamic_fire_temporal_score": dynamic_fire_result.get("fire_temporal_score"),
        "red_light_fire_candidate": bool(red_light_result["fire_candidate"]),
        "demo_person_count": demo_result.get("person_count"),
        "presence_person_count": presence_result.get("person_count"),
        "presence_enhanced": bool(presence_result.get("presence_enhanced")),
        "blank_presence_person_count": blank_presence_result.get("person_count"),
        "weak_fall_candidate": bool(weak_fall_result.get("fall_candidate")),
        "weak_fall_score": weak_fall_result.get("fall_score"),
        "pose_refine_person_count": pose_refine_result["person_count"],
        "pose_refine_filtered_count": pose_refine_result["filtered_count"],
        "pose_refine_pose_added": pose_refine_result["pose_added"],
        "pose_cache_state": pose_cache_result["tracking_state"],
        "pose_cache_model_status": pose_cache_result["model_status"],
        "pose_cache_person_count": pose_cache_result["person_count"],
        "pose_cache_fall_candidate": pose_cache_result["fall_candidate"],
        "activity_temporal_meal_candidate": activity_temporal_result["meal_candidate"],
        "activity_temporal_daze_candidate": activity_temporal_result["daze_candidate"],
        "activity_temporal_samples": activity_temporal_result["sample_count"],
        "pose_det_frequency_without_tracking": pose_runtime_config["without_tracking"],
        "pose_det_frequency_with_tracking": pose_runtime_config["with_tracking"],
        "pose_result_status": fire_result.get("algorithm_results", {}).get("pose", {}).get("status"),
        "pipeline_version": fire_result.get("pipeline_version"),
        "algorithm_results": sorted((fire_result.get("algorithm_results") or {}).keys()),
    }
    expected_algorithms = ["activity", "fall", "fire", "person", "pose", "quality"]
    if not checks["black_screen"]:
        raise SystemExit("black screen check failed")
    if not checks["fire_candidate"]:
        raise SystemExit("fire candidate check failed")
    if checks["fire_event_candidate_without_previous"]:
        raise SystemExit("static fire visual candidate should not become formal event candidate")
    if not checks["dynamic_fire_event_candidate"]:
        raise SystemExit("dynamic fire event candidate check failed")
    if checks["red_light_fire_candidate"]:
        raise SystemExit("red light false-positive check failed")
    if checks["algorithm_results"] != expected_algorithms:
        raise SystemExit(f"algorithm result keys mismatch: {checks['algorithm_results']}")
    if not isinstance(checks["demo_person_count"], int) or checks["demo_person_count"] < 1:
        raise SystemExit("demo person check failed")
    if not isinstance(checks["presence_person_count"], int) or checks["presence_person_count"] < 1:
        raise SystemExit("seated half-body presence enhancement check failed")
    if not checks["presence_enhanced"]:
        raise SystemExit("presence enhancement flag check failed")
    if checks["blank_presence_person_count"] != 0:
        raise SystemExit("blank presence false-positive check failed")
    if checks["weak_fall_candidate"]:
        raise SystemExit("weak low-confidence fall box should not become fall candidate")
    if checks["pose_refine_person_count"] != 1 or checks["pose_refine_filtered_count"] < 2:
        raise SystemExit("pose refinement should filter weak non-overlapping presence candidates")
    if not checks["pose_refine_pose_added"]:
        raise SystemExit("pose refinement should add a pose-confirmed person when YOLO boxes are unusable")
    if checks["pose_cache_state"] != "cached" or checks["pose_cache_person_count"] != 1:
        raise SystemExit("pose cache should stabilize a short RTMPose miss")
    if checks["pose_cache_model_status"] != "cached":
        raise SystemExit("pose cache should report cached runtime status")
    if checks["pose_cache_fall_candidate"]:
        raise SystemExit("cached pose should not become a fall candidate")
    if not checks["activity_temporal_meal_candidate"]:
        raise SystemExit("temporal meal candidate check failed")
    if not checks["activity_temporal_daze_candidate"]:
        raise SystemExit("temporal daze candidate check failed")
    if checks["pose_det_frequency_without_tracking"] != 1:
        raise SystemExit("RTMPose without tracking must run person detection on every sampled pose frame")
    if checks["pose_det_frequency_with_tracking"] != 8:
        raise SystemExit("RTMPose tracking mode should preserve configured detector frequency")
    if checks["pose_result_status"] != "disabled":
        raise SystemExit("pose disabled status check failed")

    print(json.dumps({"ok": True, **checks}, ensure_ascii=False, indent=2))


def synthetic_seated_half_body_frame() -> np.ndarray:
    try:
        import cv2  # type: ignore
    except ModuleNotFoundError:
        cv2 = None

    frame = np.full((480, 640, 3), [118, 124, 119], dtype=np.uint8)
    frame[:, :260] = [105, 113, 112]
    frame[320:480, :] = [86, 91, 86]
    if cv2 is None:
        frame[116:196, 380:460] = [86, 150, 214]
        frame[198:390, 330:525] = [62, 95, 150]
        frame[250:292, 288:440] = [84, 146, 205]
        return frame

    cv2.rectangle(frame, (300, 250), (560, 430), (58, 62, 66), -1)
    cv2.ellipse(frame, (420, 148), (43, 52), -8, 0, 360, (82, 148, 214), -1)
    cv2.rectangle(frame, (392, 190), (444, 224), (78, 142, 204), -1)
    cv2.ellipse(frame, (425, 312), (104, 122), 2, 0, 360, (62, 96, 158), -1)
    cv2.ellipse(frame, (343, 270), (35, 82), 22, 0, 360, (82, 148, 214), -1)
    cv2.circle(frame, (407, 143), 5, (35, 45, 55), -1)
    cv2.circle(frame, (434, 145), 5, (35, 45, 55), -1)
    return frame


def analyze_with_mocked_yolo_miss(frame: np.ndarray) -> dict:
    detector = PersonDetector(detector_backend="yolo", yolo_confidence=0.35)
    detector._detect_people_with_yolo = lambda frame, confidence=None: []  # type: ignore[method-assign]
    return detector.analyze(frame, {})


def synthetic_weak_fall_people() -> list[dict]:
    return [
        {
            "bbox": [272.1, 127.5, 444.3, 350.6],
            "confidence": 0.7309,
            "source": "yolo",
            "presence_candidate": False,
            "aspect_ratio": 0.772,
            "area_ratio": 0.1668,
            "height_ratio": 0.62,
            "center_y_ratio": 0.664,
            "frame_width": 640,
            "frame_height": 360,
            "fall_candidate": False,
        },
        {
            "bbox": [345.3, 186.8, 638.4, 355.3],
            "confidence": 0.2096,
            "source": "yolo",
            "presence_candidate": False,
            "aspect_ratio": 1.739,
            "area_ratio": 0.2143,
            "height_ratio": 0.468,
            "center_y_ratio": 0.753,
            "frame_width": 640,
            "frame_height": 360,
            "fall_candidate": True,
        },
    ]


def verify_pose_refines_presence_candidates() -> dict:
    pipeline = VisionPipeline(
        black_brightness_threshold=18,
        black_contrast_threshold=4,
        motion_threshold=0.015,
        detector_backend="basic",
    )
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    pose = {
        "bbox": [310.0, 86.0, 454.0, 330.0],
        "confidence": 0.83,
        "keypoints": [],
    }
    raw_people = [
        {
            "bbox": [308.0, 92.0, 456.0, 336.0],
            "confidence": 0.5,
            "source": "presence_skin",
            "label": "人体存在",
            "presence_candidate": True,
            "frame_width": 640,
            "frame_height": 360,
            "fall_candidate": False,
        },
        {
            "bbox": [120.0, 95.0, 220.0, 310.0],
            "confidence": 0.5,
            "source": "presence_skin",
            "label": "人体存在",
            "presence_candidate": True,
            "frame_width": 640,
            "frame_height": 360,
            "fall_candidate": False,
        },
        {
            "bbox": [480.0, 162.0, 628.0, 320.0],
            "confidence": 0.74,
            "source": "yolo",
            "label": "人形命中",
            "presence_candidate": False,
            "frame_width": 640,
            "frame_height": 360,
            "fall_candidate": True,
        },
    ]
    refined = pipeline._refine_people_with_pose(raw_people, [pose], frame, {})
    pose_added = pipeline._refine_people_with_pose([], [pose], frame, {})
    return {
        "person_count": len(refined),
        "filtered_count": len(raw_people) - len(refined),
        "pose_added": len(pose_added) == 1 and pose_added[0].get("source") == "pose_person",
    }


def verify_pose_cache_stabilizes_tracking() -> dict:
    pipeline = VisionPipeline(
        black_brightness_threshold=18,
        black_contrast_threshold=4,
        motion_threshold=0.015,
        detector_backend="basic",
        pose_cache_seconds=2.0,
    )
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    pose = {
        "bbox": [310.0, 86.0, 454.0, 330.0],
        "confidence": 0.83,
        "keypoints": [],
        "fall_score": 0.92,
        "action_hints": ["fall_candidate"],
    }
    first_pose = {
        "poses": [pose],
        "pose_count": 1,
        "pose_fall_score": 0.92,
        "pose_fall_candidate": True,
        "pose_model_status": "ready",
        "pose_action_hints": ["fall_candidate"],
        "tags": ["pose_detected", "pose_fall_candidate"],
        "result": None,
    }
    empty_pose = {
        "poses": [],
        "pose_count": 0,
        "pose_fall_score": 0.0,
        "pose_fall_candidate": False,
        "pose_model_status": "ready",
        "pose_action_hints": [],
        "tags": [],
        "result": None,
    }
    quality = {"black_screen": False, "motion_score": 0.01}
    pipeline._pose_with_short_cache(first_pose, {"camera_id": 1, "pose_cache_seconds": 2.0}, quality)
    cached_pose = pipeline._pose_with_short_cache(empty_pose, {"camera_id": 1, "pose_cache_seconds": 2.0}, quality)
    refined = pipeline._refine_people_with_pose([], cached_pose.get("poses") or [], frame, {})
    alert_people = pipeline._fresh_people_for_alerts(refined)
    fall = pipeline.fall.analyze(alert_people, {})
    return {
        "tracking_state": cached_pose.get("pose_tracking_state"),
        "model_status": cached_pose.get("pose_model_status"),
        "person_count": len(refined),
        "fall_candidate": bool(fall.get("fall_candidate") or cached_pose.get("pose_fall_candidate")),
    }


def verify_pose_runtime_config() -> dict:
    without_tracking = RtmposeAnalyzer(enabled=True, det_frequency=8, tracking=False)
    with_tracking = RtmposeAnalyzer(enabled=True, det_frequency=8, tracking=True)
    return {
        "without_tracking": without_tracking.det_frequency,
        "with_tracking": with_tracking.det_frequency,
    }


def verify_activity_temporal_candidates() -> dict:
    pipeline = VisionPipeline(
        black_brightness_threshold=18,
        black_contrast_threshold=4,
        motion_threshold=0.015,
        detector_backend="basic",
        activity_window_seconds=30,
    )
    people = [
        {
            "bbox": [260.0, 80.0, 430.0, 330.0],
            "confidence": 0.88,
            "source": "pose_person",
            "pose_validated": True,
        }
    ]
    meal_pose = [
        {
            "bbox": [260.0, 80.0, 430.0, 330.0],
            "confidence": 0.82,
            "posture": "upper_body",
            "action_hints": ["hand_near_face", "seated_or_upper_body"],
            "tracking_state": "fresh",
        }
    ]
    daze_pose = [
        {
            "bbox": [260.0, 80.0, 430.0, 330.0],
            "confidence": 0.82,
            "posture": "upper_body",
            "action_hints": ["seated_or_upper_body"],
            "tracking_state": "fresh",
        }
    ]

    meal_temporal = {}
    for _ in range(4):
        meal_temporal = pipeline._activity_temporal_features(
            people,
            meal_pose,
            {"black_screen": False, "motion_score": 0.018},
            {"pose_tracking_state": "fresh"},
            {"camera_id": "meal-test", "activity_temporal_min_samples": 3},
        )
    meal = pipeline.activity.analyze(
        people,
        meal_pose,
        0.018,
        {"activity_temporal_min_samples": 3},
        temporal=meal_temporal,
    )

    daze_temporal = {}
    for _ in range(4):
        daze_temporal = pipeline._activity_temporal_features(
            people,
            daze_pose,
            {"black_screen": False, "motion_score": 0.002},
            {"pose_tracking_state": "fresh"},
            {"camera_id": "daze-test", "activity_temporal_min_samples": 3},
        )
    daze = pipeline.activity.analyze(
        people,
        daze_pose,
        0.002,
        {"activity_temporal_min_samples": 3},
        temporal=daze_temporal,
    )
    return {
        "meal_candidate": bool(meal.get("meal_candidate")),
        "daze_candidate": bool(daze.get("daze_candidate")),
        "sample_count": min(int(meal_temporal.get("sample_count") or 0), int(daze_temporal.get("sample_count") or 0)),
    }


if __name__ == "__main__":
    main()
