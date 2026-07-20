from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.detect_agent import DetectAgent
from app.rule_engine import build_event_evidence
from app.vision.fall import FallAnalyzer
from app.vision.person_yolo import PersonDetector
from app.vision.pipeline import VisionPipeline
from app.vision.pose_rtmpose import RtmposeAnalyzer
from app.vision.scene_context import SceneContextTracker


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
    default_presence_result = analyze_with_mocked_yolo_miss(seated_half_body)
    presence_result = analyze_with_mocked_yolo_miss(
        seated_half_body,
        {"presence_classical_enhancement_enabled": True},
    )
    blank_presence_result = analyze_with_mocked_yolo_miss(
        black,
        {"presence_classical_enhancement_enabled": True},
    )
    weak_fall_result = FallAnalyzer().analyze(synthetic_weak_fall_people(), {})
    pose_refine_result = verify_pose_refines_presence_candidates()
    pose_cache_result = verify_pose_cache_stabilizes_tracking()
    activity_temporal_result = verify_activity_temporal_candidates()
    pose_runtime_config = verify_pose_runtime_config()
    pose_fall_quality = verify_pose_fall_quality_gate()
    pose_candidate_partition = verify_pose_candidate_partition()
    pose_human_consistency = verify_pose_human_consistency_gate()
    pose_external_boxes = verify_pose_reuses_external_person_boxes()
    pose_detector_fallback = verify_pose_uses_detector_fallback_without_external_boxes()
    pose_empty_fallback = verify_pose_skips_estimator_when_fallback_detector_is_empty()
    pipeline_pose_source = verify_pipeline_reports_pose_detection_source()
    pose_retry = verify_pose_transient_retry()
    pose_posture = verify_pose_posture_direction()
    pose_partial_shoulders = verify_pose_action_hints_with_partial_shoulders()
    scene_context = verify_scene_context_stabilizes_normal_lying_zone()
    scene_human_filter = verify_scene_context_rejects_human_shaped_furniture()
    display_suppression = verify_display_content_suppression()
    display_pose_bypass = verify_display_pose_cannot_recreate_suppressed_person()
    scene_merge = verify_scene_context_survives_pose_merge()
    pet_isolation = verify_pet_detection_isolated_from_people_and_fall(normal)
    detector_cache = verify_person_detector_cache_is_motion_aware()
    pose_requires_person_box = verify_pose_requires_person_box()

    checks = {
        "black_screen": bool(black_result["black_screen"]),
        "fire_candidate": bool(fire_result["fire_candidate"]),
        "fire_event_candidate_without_previous": bool(fire_result.get("fire_event_candidate")),
        "dynamic_fire_event_candidate": bool(dynamic_fire_result.get("fire_event_candidate")),
        "dynamic_fire_temporal_score": dynamic_fire_result.get("fire_temporal_score"),
        "red_light_fire_candidate": bool(red_light_result["fire_candidate"]),
        "demo_person_count": demo_result.get("person_count"),
        "default_classical_presence_person_count": default_presence_result.get("person_count"),
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
        "pose_fall_low_quality_eligible": pose_fall_quality["low_quality_eligible"],
        "pose_fall_valid_quality_eligible": pose_fall_quality["valid_quality_eligible"],
        "pose_low_quality_visible_count": pose_candidate_partition["visible_count"],
        "pose_low_quality_rejected_count": pose_candidate_partition["rejected_count"],
        "pose_furniture_hallucination_count": pose_human_consistency["furniture_count"],
        "pose_furniture_rejected_count": pose_human_consistency["furniture_rejected"],
        "pose_real_lying_retained_count": pose_human_consistency["real_lying_retained"],
        "pose_occluded_seated_retained_count": pose_human_consistency["occluded_seated_retained"],
        "pose_unmatched_low_confidence_rejected_count": pose_human_consistency["unmatched_low_confidence_rejected"],
        "pose_external_box_count": pose_external_boxes["box_count"],
        "pose_external_detection_source": pose_external_boxes["detection_source"],
        "pose_external_fallback_calls": pose_external_boxes["fallback_calls"],
        "pose_external_source_bbox": pose_external_boxes["source_bbox"],
        "pose_detector_fallback_calls": pose_detector_fallback["fallback_calls"],
        "pose_detector_fallback_source": pose_detector_fallback["detection_source"],
        "pose_empty_fallback_estimator_calls": pose_empty_fallback["estimator_calls"],
        "pose_empty_fallback_status": pose_empty_fallback["status"],
        "pipeline_pose_detection_source": pipeline_pose_source["detection_source"],
        "pipeline_pose_external_box_count": pipeline_pose_source["box_count"],
        "pose_transient_retry_count": pose_retry["call_count"],
        "pose_transient_retry_used": pose_retry["retried"],
        "pose_front_seated_posture": pose_posture["front_seated"],
        "pose_horizontal_fall_posture": pose_posture["horizontal_fall"],
        "pose_partial_shoulders_hints": pose_partial_shoulders,
        "scene_status": scene_context["status"],
        "scene_zone_count": scene_context["zone_count"],
        "scene_normal_lying": scene_context["normal_lying"],
        "scene_human_filter_count": scene_human_filter,
        "display_suppressed_people": display_suppression["suppressed_people"],
        "display_suppressed_poses": display_suppression["suppressed_poses"],
        "display_real_people_retained": display_suppression["real_people_retained"],
        "display_pose_bypass_suppressed": display_pose_bypass["suppressed_pose_count"],
        "display_pose_bypass_people": display_pose_bypass["refined_person_count"],
        "scene_merge_normal_lying": scene_merge["normal_lying_zone"],
        "scene_merge_label": scene_merge["scene_zone_label"],
        "pet_count": pet_isolation["pet_count"],
        "pet_person_count": pet_isolation["person_count"],
        "pet_fall_candidate": pet_isolation["fall_candidate"],
        "pet_event_evidence_count": pet_isolation["event_evidence_count"],
        "pet_screen_suppressed": pet_isolation["screen_suppressed"],
        "pet_default_confidence": pet_isolation["default_confidence"],
        "detector_cache_calls": detector_cache["calls"],
        "detector_cache_motion_refresh": detector_cache["motion_refresh"],
        "pose_requires_person_box": pose_requires_person_box["fallback_calls"],
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
    if checks["default_classical_presence_person_count"] != 0:
        raise SystemExit("classical skin/Haar presence enhancement must be disabled by default")
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
    if checks["scene_status"] != "stable" or checks["scene_zone_count"] != 1:
        raise SystemExit("scene context should stabilize a repeated couch detection")
    if not checks["scene_normal_lying"]:
        raise SystemExit("lying pose overlapping a stable couch must be marked as normal lying zone")
    if checks["scene_human_filter_count"] != 1:
        raise SystemExit("scene context must reject furniture boxes mostly covered by a person")
    if checks["display_suppressed_people"] != 1 or checks["display_suppressed_poses"] != 1:
        raise SystemExit("stable TV zones must suppress people and poses contained inside screen content")
    if checks["display_real_people_retained"] != 1:
        raise SystemExit("a real person extending outside the TV zone must remain visible")
    if checks["display_pose_bypass_suppressed"] != 1 or checks["display_pose_bypass_people"] != 0:
        raise SystemExit("a pose derived from suppressed TV content must not recreate a person")
    if not checks["scene_merge_normal_lying"] or checks["scene_merge_label"] != "couch":
        raise SystemExit("pose refinement must not erase a person box already matched to a couch or bed")
    if checks["pet_count"] != 1 or checks["pet_person_count"] != 0:
        raise SystemExit("cat/dog detections must remain independent from person_count")
    if checks["detector_cache_calls"] != 2 or not checks["detector_cache_motion_refresh"]:
        raise SystemExit("person detector cache did not refresh on meaningful motion")
    if checks["pose_requires_person_box"] != 0:
        raise SystemExit("worker pose mode must not run a whole-frame fallback without a person box")
    if checks["pet_fall_candidate"]:
        raise SystemExit("cat/dog detections must never enter fall analysis")
    if checks["pet_event_evidence_count"] != 1:
        raise SystemExit("event evidence must preserve independent pet metadata")
    if checks["pet_screen_suppressed"] != 1:
        raise SystemExit("pets displayed inside a stable TV zone must be suppressed")
    if checks["pet_default_confidence"] != 0.40:
        raise SystemExit("pet detections must use an independent conservative confidence threshold")
    if checks["pose_det_frequency_with_tracking"] != 8:
        raise SystemExit("RTMPose tracking mode should preserve configured detector frequency")
    if checks["pose_fall_low_quality_eligible"]:
        raise SystemExit("low-confidence sofa-like skeleton must not become fall evidence")
    if not checks["pose_fall_valid_quality_eligible"]:
        raise SystemExit("valid pose must remain eligible as fall evidence")
    if checks["pose_low_quality_visible_count"] != 0 or checks["pose_low_quality_rejected_count"] != 1:
        raise SystemExit("low-quality sofa-like skeleton must remain diagnostic-only")
    if checks["pose_furniture_hallucination_count"] != 0 or checks["pose_furniture_rejected_count"] != 1:
        raise SystemExit("wide unmatched skeleton on stable furniture must be rejected")
    if checks["pose_unmatched_low_confidence_rejected_count"] != 1:
        raise SystemExit("low-confidence pose without YOLO human evidence must be rejected")
    if checks["pose_external_box_count"] != 1:
        raise SystemExit("RTMPose did not receive the existing YOLO person box")
    if checks["pose_external_detection_source"] != "external_person_boxes":
        raise SystemExit("RTMPose did not report external-box inference")
    if checks["pose_external_fallback_calls"] != 0:
        raise SystemExit("RTMPose called its internal detector despite a reusable YOLO person box")
    if checks["pose_external_source_bbox"] != [100.0, 60.0, 240.0, 340.0]:
        raise SystemExit("RTMPose poses must retain their source person box")
    if checks["pose_detector_fallback_calls"] != 1:
        raise SystemExit("RTMPose did not use its detector fallback when no reusable YOLO box existed")
    if checks["pose_detector_fallback_source"] != "rtmlib_detector_fallback":
        raise SystemExit("RTMPose did not report detector fallback inference")
    if checks["pose_empty_fallback_estimator_calls"] != 0:
        raise SystemExit("RTMPose ran whole-frame pose inference after the fallback detector found no person")
    if checks["pose_empty_fallback_status"] != "not_visible":
        raise SystemExit("an empty fallback detector result must be reported as not visible")
    if checks["pipeline_pose_detection_source"] != "external_person_boxes":
        raise SystemExit("top-level analysis did not expose the RTMPose detection source")
    if checks["pipeline_pose_external_box_count"] != 1:
        raise SystemExit("top-level analysis did not expose the reused person box count")
    if checks["pose_real_lying_retained_count"] != 1:
        raise SystemExit("a genuine lying person matched by YOLO must remain visible")
    if checks["pose_occluded_seated_retained_count"] != 1:
        raise SystemExit("a coherent high-confidence occluded seated pose must remain visible")
    if checks["pose_transient_retry_count"] != 2 or not checks["pose_transient_retry_used"]:
        raise SystemExit("RTMPose transient NoneType failure should retry exactly once")
    if checks["pose_front_seated_posture"] != "sitting":
        raise SystemExit("front-facing seated skeleton must be classified as sitting")
    if checks["pose_horizontal_fall_posture"] != "lying":
        raise SystemExit("horizontal shoulder-to-hip direction should remain a lying pose")
    if not isinstance(checks["pose_partial_shoulders_hints"], list):
        raise SystemExit("partial shoulder keypoints did not produce stable action hints")
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


def analyze_with_mocked_yolo_miss(frame: np.ndarray, config: dict | None = None) -> dict:
    detector = PersonDetector(detector_backend="yolo", yolo_confidence=0.35)
    detector._detect_yolo_entities = lambda frame, **kwargs: ([], [])  # type: ignore[method-assign]
    return detector.analyze(frame, config or {})


def verify_scene_context_stabilizes_normal_lying_zone() -> dict:
    tracker = SceneContextTracker()
    config = {"camera_id": 9, "scene_stable_min_hits": 2}
    objects = [{
        "bbox": [80.0, 190.0, 560.0, 355.0],
        "confidence": 0.72,
        "class_id": 57,
        "label": "couch",
        "source": "yolo_scene",
    }, {
        "bbox": [300.0, 198.0, 550.0, 350.0],
        "confidence": 0.61,
        "class_id": 57,
        "label": "couch",
        "source": "yolo_scene",
    }]
    tracker.update(objects, config)
    scene = tracker.update(objects, config)
    _, poses = tracker.annotate(
        [],
        [{"bbox": [350.0, 200.0, 540.0, 350.0], "posture": "lying", "fall_candidate": True}],
        scene["scene_zones"],
    )
    return {
        "status": scene["scene_map_status"],
        "zone_count": len(scene["normal_lying_zones"]),
        "normal_lying": bool(poses and poses[0].get("normal_lying_zone")),
    }


def verify_scene_context_rejects_human_shaped_furniture() -> int:
    pipeline = VisionPipeline(
        black_brightness_threshold=18,
        black_contrast_threshold=4,
        motion_threshold=0.015,
        detector_backend="basic",
    )
    scene_objects = [
        {"bbox": [300.0, 190.0, 540.0, 350.0], "label": "couch", "confidence": 0.51},
        {"bbox": [60.0, 180.0, 590.0, 355.0], "label": "couch", "confidence": 0.68},
    ]
    people = [{"bbox": [320.0, 195.0, 535.0, 350.0]}]
    return len(pipeline._scene_objects_without_human_overlap(scene_objects, people, []))


def verify_display_content_suppression() -> dict:
    pipeline = VisionPipeline(
        black_brightness_threshold=18,
        black_contrast_threshold=4,
        motion_threshold=0.015,
        detector_backend="basic",
    )
    zones = [{
        "id": "tv-1",
        "bbox": [200.0, 40.0, 500.0, 260.0],
        "label": "tv",
        "label_zh": "电视",
        "stable": True,
    }]
    screen_person = {"bbox": [245.0, 70.0, 390.0, 245.0], "confidence": 0.72}
    real_person = {"bbox": [150.0, 55.0, 310.0, 350.0], "confidence": 0.84}
    screen_pose = {"bbox": [260.0, 82.0, 382.0, 238.0], "confidence": 0.77, "posture": "standing"}
    people, poses, suppressed = pipeline._suppress_display_content(
        [screen_person, real_person],
        [screen_pose],
        zones,
        {},
    )
    return {
        "suppressed_people": len([item for item in suppressed if item.get("kind") == "person"]),
        "suppressed_poses": len([item for item in suppressed if item.get("kind") == "pose"]),
        "real_people_retained": len(people),
        "remaining_poses": len(poses),
    }


def verify_display_pose_cannot_recreate_suppressed_person() -> dict:
    pipeline = VisionPipeline(
        black_brightness_threshold=18,
        black_contrast_threshold=4,
        motion_threshold=0.015,
        detector_backend="basic",
    )
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    zones = [{
        "id": "tv-bypass",
        "bbox": [200.0, 40.0, 500.0, 260.0],
        "label": "tv",
        "label_zh": "电视",
        "stable": True,
    }]
    screen_person = {
        "bbox": [245.0, 70.0, 390.0, 245.0],
        "confidence": 0.72,
    }
    expanded_screen_pose = {
        "bbox": [170.0, 60.0, 430.0, 285.0],
        "source_person_bbox": list(screen_person["bbox"]),
        "confidence": 0.77,
        "posture": "standing",
    }
    people, poses, suppressed = pipeline._suppress_display_content(
        [screen_person],
        [expanded_screen_pose],
        zones,
        {},
    )
    refined = pipeline._refine_people_with_pose(people, poses, frame, {})
    return {
        "suppressed_pose_count": len([item for item in suppressed if item.get("kind") == "pose"]),
        "refined_person_count": len(refined),
    }


def verify_pet_detection_isolated_from_people_and_fall(frame: np.ndarray) -> dict:
    pipeline = VisionPipeline(
        black_brightness_threshold=18,
        black_contrast_threshold=4,
        motion_threshold=0.015,
        detector_backend="yolo",
    )
    pet = pipeline.person.pet_box(
        120.0,
        190.0,
        260.0,
        330.0,
        frame.shape[1],
        frame.shape[0],
        confidence=0.84,
        class_id=15,
        pet_type="cat",
        label_zh="猫",
    )
    detector_config = {}

    def detect_pet(current_frame, **kwargs):
        detector_config.update(kwargs)
        return [], [pet], []

    pipeline.person._detect_yolo_entities = detect_pet  # type: ignore[method-assign]
    analysis = pipeline.analyze(frame, config={"pet_detection_enabled": True})
    evidence = build_event_evidence(
        event_type="no_person",
        summary="未检测到人物",
        level="warning",
        analysis=analysis,
        rule={"rule_type": "no_person"},
    )
    tv_zone = [{
        "id": "tv-pet",
        "bbox": [80.0, 120.0, 300.0, 350.0],
        "label": "tv",
        "label_zh": "电视",
        "stable": True,
    }]
    _, suppressed = pipeline._suppress_pet_display_content([pet], tv_zone, {})
    return {
        "pet_count": analysis.get("pet_count"),
        "person_count": analysis.get("person_count"),
        "fall_candidate": bool(analysis.get("fall_candidate")),
        "event_evidence_count": len(evidence.get("objects", {}).get("pets") or []),
        "screen_suppressed": len(suppressed),
        "default_confidence": detector_config.get("pet_confidence"),
    }


def verify_person_detector_cache_is_motion_aware() -> dict:
    detector = PersonDetector(detector_backend="yolo")
    calls = {"count": 0}
    people = [{"bbox": [40.0, 20.0, 120.0, 220.0], "confidence": 0.8}]

    def detect_entities(*args, **kwargs):
        calls["count"] += 1
        return people, [], []

    detector._detect_yolo_entities = detect_entities  # type: ignore[method-assign]
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    config = {
        "camera_id": "cache-test",
        "person_detection_cache_seconds": 2.0,
        "person_detection_cache_max_motion": 0.05,
        "frame_motion_score": 0.01,
    }
    detector.analyze(frame, config)
    detector.analyze(frame, config)
    refreshed_config = {**config, "frame_motion_score": 0.20}
    detector.analyze(frame, refreshed_config)
    return {"calls": calls["count"], "motion_refresh": calls["count"] == 2}


def verify_pose_requires_person_box() -> dict:
    analyzer = RtmposeAnalyzer(enabled=True)
    calls = {"fallback": 0}

    def fallback_detector(frame):
        calls["fallback"] += 1
        return [[20.0, 20.0, 200.0, 230.0]]

    analyzer._pose_detector = fallback_detector
    analyzer._pose_tracker = analyzer._infer_with_internal_detector
    result = analyzer.analyze(
        np.zeros((240, 320, 3), dtype=np.uint8),
        {
            "pose_detection_enabled": True,
            "pose_allow_internal_detector_fallback": False,
        },
        people=[],
    )
    return {"fallback_calls": calls["fallback"], "status": result.get("pose_model_status")}


def verify_scene_context_survives_pose_merge() -> dict:
    pipeline = VisionPipeline(
        black_brightness_threshold=18,
        black_contrast_threshold=4,
        motion_threshold=0.015,
        detector_backend="basic",
    )
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    people = [{
        "bbox": [120.0, 170.0, 400.0, 280.0],
        "confidence": 0.56,
        "fall_candidate": True,
        "normal_lying_zone": True,
        "scene_zone_id": "couch-1",
        "scene_zone_label": "couch",
        "scene_zone_label_zh": "沙发",
        "scene_zone_bbox": [0.0, 200.0, 410.0, 358.0],
        "scene_zone_overlap": 0.68,
    }]
    poses = [{
        "bbox": [125.0, 168.0, 220.0, 270.0],
        "confidence": 0.62,
        "posture": "standing",
        "normal_lying_zone": False,
    }]
    refined = pipeline._refine_people_with_pose(people, poses, frame, {})
    return {
        "normal_lying_zone": bool(refined and refined[0].get("normal_lying_zone")),
        "scene_zone_label": refined[0].get("scene_zone_label") if refined else None,
    }


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


def verify_pose_fall_quality_gate() -> dict:
    analyzer = RtmposeAnalyzer(enabled=True)
    keypoints = [
        {
            "name": name,
            "confidence": 0.34,
            "visible": True,
        }
        for name in [
            "nose",
            "left_eye",
            "right_eye",
            "left_shoulder",
            "right_shoulder",
            "left_hip",
            "right_hip",
            "left_knee",
            "right_knee",
        ]
    ]
    low_quality = analyzer._fall_evidence_quality(
        {"confidence": 0.34, "keypoints": keypoints},
        {},
    )
    valid_quality = analyzer._fall_evidence_quality(
        {"confidence": 0.52, "keypoints": keypoints},
        {},
    )
    return {
        "low_quality_eligible": low_quality["eligible"],
        "valid_quality_eligible": valid_quality["eligible"],
    }


def verify_pose_candidate_partition() -> dict:
    analyzer = RtmposeAnalyzer(enabled=True)
    low_quality_pose = synthetic_pose_candidate(
        bbox=[99.3, 147.2, 544.8, 271.2],
        confidence=0.329,
        posture="lying",
        body_aspect=3.375,
    )
    analyzer._ensure_ready = lambda: (True, "ready")  # type: ignore[method-assign]
    analyzer._infer_pose = lambda frame: (None, None, False)  # type: ignore[method-assign]
    analyzer._extract_poses = lambda keypoints, scores, frame, **kwargs: [low_quality_pose]  # type: ignore[method-assign]
    result = analyzer.analyze(np.zeros((360, 640, 3), dtype=np.uint8), {})
    return {
        "visible_count": int(result.get("pose_count") or 0),
        "rejected_count": len(result.get("rejected_poses") or []),
    }


def verify_pose_human_consistency_gate() -> dict:
    pipeline = VisionPipeline(
        black_brightness_threshold=18,
        black_contrast_threshold=4,
        motion_threshold=0.015,
        detector_backend="basic",
    )
    furniture = [{
        "id": "couch-1",
        "bbox": [204.4, 200.3, 570.1, 350.2],
        "label": "couch",
        "stable": True,
    }]
    sofa_pose = synthetic_pose_candidate(
        bbox=[99.3, 147.2, 544.8, 271.2],
        confidence=0.44,
        posture="lying",
        body_aspect=3.375,
    )
    kept, rejected = pipeline._filter_pose_human_consistency([sofa_pose], [], furniture, {})
    real_lying, _ = pipeline._filter_pose_human_consistency(
        [sofa_pose],
        [{"bbox": [115.0, 140.0, 540.0, 286.0], "confidence": 0.81}],
        furniture,
        {},
    )
    seated_pose = synthetic_pose_candidate(
        bbox=[320.0, 105.0, 465.0, 338.0],
        confidence=0.61,
        posture="sitting",
        body_aspect=0.62,
    )
    occluded_seated, _ = pipeline._filter_pose_human_consistency([seated_pose], [], furniture, {})
    low_confidence_pose = synthetic_pose_candidate(
        bbox=[258.0, 180.0, 475.0, 320.0],
        confidence=0.38,
        posture="lying",
        body_aspect=1.55,
    )
    _, low_confidence_rejected = pipeline._filter_pose_human_consistency(
        [low_confidence_pose],
        [],
        furniture,
        {},
    )
    return {
        "furniture_count": len(kept),
        "furniture_rejected": len(rejected),
        "real_lying_retained": len(real_lying),
        "occluded_seated_retained": len(occluded_seated),
        "unmatched_low_confidence_rejected": len(low_confidence_rejected),
    }


def synthetic_pose_candidate(
    *,
    bbox: list[float],
    confidence: float,
    posture: str,
    body_aspect: float,
) -> dict:
    names = [
        "nose",
        "left_eye",
        "right_eye",
        "left_shoulder",
        "right_shoulder",
        "left_hip",
        "right_hip",
        "left_knee",
        "right_knee",
        "left_ankle",
        "right_ankle",
    ]
    return {
        "bbox": bbox,
        "confidence": confidence,
        "posture": posture,
        "posture_factors": {"body_aspect": body_aspect},
        "fall_score": 0.90 if posture == "lying" else 0.18,
        "action_hints": ["fall_candidate", "lying"] if posture == "lying" else ["seated_or_upper_body"],
        "keypoints": [
            {"name": name, "confidence": confidence, "visible": True, "x": 0.0, "y": 0.0}
            for name in names
        ],
    }


def verify_pose_transient_retry() -> dict:
    analyzer = RtmposeAnalyzer(enabled=True)
    calls = {"count": 0}

    def transient_tracker(frame):
        calls["count"] += 1
        if calls["count"] == 1:
            raise TypeError("'NoneType' object is not subscriptable")
        return np.array([]), np.array([])

    analyzer._pose_tracker = transient_tracker
    _, _, retried = analyzer._infer_pose(np.zeros((8, 8, 3), dtype=np.uint8))
    return {"call_count": calls["count"], "retried": retried}


def verify_pose_reuses_external_person_boxes() -> dict:
    analyzer = RtmposeAnalyzer(enabled=True)
    captured = {"boxes": [], "fallback_calls": 0}
    keypoints = np.array([[[120.0 + index * 2.0, 80.0 + index * 8.0] for index in range(17)]])
    scores = np.full((1, 17), 0.92, dtype=np.float32)

    def pose_estimator(frame, *, bboxes):
        captured["boxes"] = [list(box) for box in bboxes]
        return keypoints, scores

    def fallback_tracker(frame):
        captured["fallback_calls"] += 1
        raise SystemExit("internal detector fallback must not run when YOLO boxes are available")

    analyzer._pose_estimator = pose_estimator
    analyzer._pose_tracker = fallback_tracker
    result = analyzer.analyze(
        np.zeros((360, 640, 3), dtype=np.uint8),
        {"pose_detection_enabled": True},
        people=[{"bbox": [100.0, 60.0, 240.0, 340.0], "confidence": 0.91, "source": "yolo"}],
    )
    return {
        "box_count": len(captured["boxes"]),
        "detection_source": result.get("pose_detection_source"),
        "fallback_calls": captured["fallback_calls"],
        "source_bbox": (result.get("poses") or [{}])[0].get("source_person_bbox"),
    }


def verify_pose_uses_detector_fallback_without_external_boxes() -> dict:
    analyzer = RtmposeAnalyzer(enabled=True)
    captured = {"fallback_calls": 0, "pose_calls": 0, "boxes": []}

    def fallback_detector(frame):
        captured["fallback_calls"] += 1
        return [[80.0, 50.0, 260.0, 340.0]]

    def pose_estimator(frame, *, bboxes):
        captured["pose_calls"] += 1
        captured["boxes"] = [list(box) for box in bboxes]
        return np.array([]), np.array([])

    analyzer._pose_detector = fallback_detector
    analyzer._pose_estimator = pose_estimator
    analyzer._pose_tracker = analyzer._infer_with_internal_detector
    result = analyzer.analyze(
        np.zeros((360, 640, 3), dtype=np.uint8),
        {"pose_detection_enabled": True},
        people=[],
    )
    if captured["pose_calls"] != 1 or captured["boxes"] != [[80.0, 50.0, 260.0, 340.0]]:
        raise SystemExit("detector fallback did not reuse the shared RTMPose estimator")
    return {
        "fallback_calls": captured["fallback_calls"],
        "detection_source": result.get("pose_detection_source"),
    }


def verify_pose_skips_estimator_when_fallback_detector_is_empty() -> dict:
    analyzer = RtmposeAnalyzer(enabled=True)
    captured = {"estimator_calls": 0}

    def pose_estimator(frame, *, bboxes):
        captured["estimator_calls"] += 1
        raise SystemExit("whole-frame RTMPose must not run after an empty person detection")

    analyzer._pose_detector = lambda frame: np.empty((0, 4), dtype=np.float32)
    analyzer._pose_estimator = pose_estimator
    analyzer._pose_tracker = analyzer._infer_with_internal_detector
    result = analyzer.analyze(
        np.zeros((360, 640, 3), dtype=np.uint8),
        {"pose_detection_enabled": True},
        people=[],
    )
    return {
        "estimator_calls": captured["estimator_calls"],
        "status": result.get("result").status,
    }


def verify_pipeline_reports_pose_detection_source() -> dict:
    pipeline = VisionPipeline(
        black_brightness_threshold=18,
        black_contrast_threshold=4,
        motion_threshold=0.015,
        detector_backend="basic",
        pose_enabled=True,
    )
    gradient = np.tile(np.linspace(60, 132, 640, dtype=np.uint8), (360, 1))
    frame = np.dstack([gradient, np.roll(gradient, 24, axis=1), np.full_like(gradient, 96)])
    keypoints = np.array([[[120.0 + index * 2.0, 80.0 + index * 8.0] for index in range(17)]])
    scores = np.full((1, 17), 0.92, dtype=np.float32)
    pipeline.pose._pose_estimator = lambda image, *, bboxes: (keypoints, scores)
    analysis = pipeline.analyze(
        frame,
        config={"force_demo_vision": True, "pose_detection_enabled": True},
    )
    return {
        "detection_source": analysis.get("pose_detection_source"),
        "box_count": analysis.get("pose_external_box_count"),
    }


def verify_pose_posture_direction() -> dict:
    analyzer = RtmposeAnalyzer(enabled=True)

    def point(name: str, x: float, y: float) -> dict:
        return {"name": name, "x": x, "y": y, "confidence": 0.8, "visible": True}

    front_seated = [
        point("left_shoulder", 380, 238),
        point("right_shoulder", 333, 235),
        point("left_hip", 370, 264),
        point("right_hip", 338, 267),
        point("left_knee", 370, 261),
        point("right_knee", 334, 262),
        point("left_ankle", 385, 299),
        point("right_ankle", 315, 294),
    ]
    horizontal_fall = [
        point("left_shoulder", 220, 140),
        point("right_shoulder", 224, 180),
        point("left_hip", 310, 144),
        point("right_hip", 314, 184),
        point("left_knee", 380, 150),
        point("right_knee", 382, 188),
    ]
    return {
        "front_seated": analyzer._estimate_posture(front_seated),
        "horizontal_fall": analyzer._estimate_posture(horizontal_fall),
    }


def verify_pose_action_hints_with_partial_shoulders() -> list[str]:
    analyzer = RtmposeAnalyzer(enabled=True)
    keypoints = [
        {"name": "nose", "x": 120.0, "y": 72.0, "confidence": 0.9, "visible": True},
        {"name": "left_shoulder", "x": 110.0, "y": 130.0, "confidence": 0.8, "visible": True},
        {"name": "left_wrist", "x": 112.0, "y": 92.0, "confidence": 0.8, "visible": True},
    ]
    return analyzer._action_hints(keypoints, "upper_body", False)


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
