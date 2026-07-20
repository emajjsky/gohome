from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.rule_engine as rule_engine_module
from app.rule_engine import RuleEngine
from app.worker import EdgeWorker


def main() -> None:
    engine = RuleEngine()
    camera = {"id": 1, "name": "客厅摄像头"}
    snapshot = {"id": 1001}
    rules = {
        "black_screen_enabled": False,
        "person_detection_enabled": True,
        "fall_detection_enabled": True,
        "fall_score_threshold": 0.50,
        "fall_confirm_frames": 2,
        "fall_confirm_seconds": 0,
        "fall_recover_frames": 2,
        "fire_detection_enabled": False,
        "activity_detection_enabled": True,
        "no_motion_enabled": False,
        "no_person_seconds": 300,
    }

    low_score = make_analysis(fall_score=0.32)
    low_eval = engine.evaluate_snapshot(camera, snapshot, low_score, rules)
    if low_eval.candidates:
        raise SystemExit("low-score fall candidate must not create a formal event")
    if low_eval.state["fall_state"] != "visual_only":
        raise SystemExit(f"unexpected low-score state: {low_eval.state['fall_state']}")

    engine = RuleEngine()
    no_transition_eval = engine.evaluate_snapshot(camera, snapshot, make_analysis(fall_score=0.62), rules)
    if no_transition_eval.candidates or no_transition_eval.state["fall_stage"] != "awaiting_transition":
        raise SystemExit("strong single-frame fall without prior upright state must wait for transition evidence")

    engine = RuleEngine()
    engine.evaluate_snapshot(camera, {"id": 1000}, make_upright_analysis(), rules)
    first_eval = engine.evaluate_snapshot(camera, snapshot, make_analysis(fall_score=0.62), rules)
    if first_eval.candidates:
        raise SystemExit("first strong fall frame must only confirm, not alert")
    if first_eval.state["fall_confirm_count"] != 1:
        raise SystemExit(f"first frame confirm count mismatch: {first_eval.state['fall_confirm_count']}")

    engine.fall_upright_states.clear()
    second_eval = engine.evaluate_snapshot(camera, {"id": 1002}, make_analysis(fall_score=0.64), rules)
    if len(second_eval.candidates) != 1:
        raise SystemExit("second consecutive strong fall frame must create one formal event")
    candidate = second_eval.candidates[0]
    if candidate.event_type != "fall_candidate" or candidate.level != "critical":
        raise SystemExit(f"unexpected candidate: {candidate}")
    evidence = (candidate.payload or {}).get("evidence") or {}
    rule = evidence.get("rule") or {}
    if (rule.get("threshold") or {}).get("confirm_frames") != 2:
        raise SystemExit("fall evidence must include confirm frame threshold")
    if second_eval.state["fall_stage"] != "confirmed":
        raise SystemExit(f"fall must enter confirmed stage: {second_eval.state['fall_stage']}")
    if not second_eval.state.get("fall_transition_confirmed"):
        raise SystemExit("formal fall must retain confirmed standing-to-low transition evidence")

    history_engine = RuleEngine()
    history_engine.evaluate_snapshot(camera, {"id": 1100}, make_upright_analysis(), rules)
    history_engine.evaluate_snapshot(camera, {"id": 1101}, make_bending_analysis(), rules)
    history_first = history_engine.evaluate_snapshot(camera, {"id": 1102}, make_analysis(fall_score=0.88), rules)
    if not history_first.state.get("fall_transition_confirmed") or history_first.state.get("fall_stage") != "suspect":
        raise SystemExit("bending transition frames must not overwrite the recent standing/sitting baseline")

    clear_eval = engine.evaluate_snapshot(camera, {"id": 1003}, make_analysis(fall_candidate=False, fall_score=0.0), rules)
    if clear_eval.state["fall_stage"] != "confirmed":
        raise SystemExit("first clear frame keeps incident open until recovery threshold")
    recovered_eval = engine.evaluate_snapshot(camera, {"id": 1004}, make_analysis(fall_candidate=False, fall_score=0.0), rules)
    if recovered_eval.state["fall_confirm_count"] != 0 or recovered_eval.state["fall_stage"] != "recovered":
        raise SystemExit("second clear frame must recover fall state")

    scene_engine = RuleEngine()
    scene_first = scene_engine.evaluate_snapshot(
        camera,
        {"id": 2001},
        make_analysis(fall_score=0.88, normal_lying_zone=True),
        rules,
    )
    scene_second = scene_engine.evaluate_snapshot(
        camera,
        {"id": 2002},
        make_analysis(fall_score=0.90, normal_lying_zone=True),
        rules,
    )
    if scene_first.candidates or scene_second.candidates:
        raise SystemExit("stable bed/couch overlap must suppress formal fall events")
    if scene_second.state["fall_stage"] != "normal_lying_zone" or not scene_second.state.get("fall_scene_suppressed"):
        raise SystemExit("normal lying scene state mismatch")

    transition_scene_engine = RuleEngine()
    transition_scene_engine.evaluate_snapshot(camera, {"id": 2100}, make_upright_analysis(), rules)
    transition_scene_first = transition_scene_engine.evaluate_snapshot(
        camera,
        {"id": 2101},
        make_pose_fall_analysis(normal_lying_zone=True),
        rules,
    )
    transition_scene_second = transition_scene_engine.evaluate_snapshot(
        camera,
        {"id": 2102},
        make_pose_fall_analysis(normal_lying_zone=True),
        rules,
    )
    if transition_scene_first.candidates:
        raise SystemExit("first transitioned pose-fall frame must remain a suspect")
    if len(transition_scene_second.candidates) != 1:
        raise SystemExit("confirmed pose fall must override static couch/bed suppression")
    if transition_scene_second.state["fall_stage"] != "confirmed":
        raise SystemExit("transitioned pose fall in a normal lying zone must be confirmed")
    if transition_scene_second.state.get("fall_scene_suppressed"):
        raise SystemExit("dynamic pose fall must not remain scene-suppressed")

    fast_rules = {**rules, "fall_confirm_seconds": 4}
    fast_engine = RuleEngine()
    fast_start = datetime(2026, 7, 20, tzinfo=timezone.utc)
    original_clock = rule_engine_module.utc_now
    try:
        current_time = [fast_start]
        rule_engine_module.utc_now = lambda: current_time[0]
        fast_engine.evaluate_snapshot(camera, {"id": 2200}, make_upright_analysis(), fast_rules)
        current_time[0] = fast_start + timedelta(seconds=2)
        fast_first = fast_engine.evaluate_snapshot(
            camera,
            {"id": 2201},
            make_pose_fall_analysis(normal_lying_zone=True, fast_graph=True),
            fast_rules,
        )
        current_time[0] = fast_start + timedelta(seconds=2.25)
        fast_second = fast_engine.evaluate_snapshot(
            camera,
            {"id": 2202},
            make_pose_fall_analysis(normal_lying_zone=True),
            fast_rules,
        )
    finally:
        rule_engine_module.utc_now = original_clock
    if fast_first.candidates:
        raise SystemExit("first graph-confirmed fast-fall frame must remain a suspect")
    if len(fast_second.candidates) != 1 or fast_second.state.get("fall_stage") != "confirmed":
        raise SystemExit("two formal pose frames after a graph-confirmed fast fall must create an event without cached evidence")
    if fast_second.state.get("fall_confirm_seconds", 0) >= fast_rules["fall_confirm_seconds"]:
        raise SystemExit("fast-fall path did not exercise the short dynamic confirmation branch")

    dynamic_engine = RuleEngine()
    dynamic_start = datetime(2026, 7, 20, 12, 43, 0, tzinfo=timezone.utc)
    try:
        current_time = [dynamic_start]
        rule_engine_module.utc_now = lambda: current_time[0]
        dynamic_engine.evaluate_snapshot(camera, {"id": 2300}, make_upright_analysis(), fast_rules)
        current_time[0] = dynamic_start + timedelta(seconds=1.0)
        dynamic_first = dynamic_engine.evaluate_snapshot(
            camera,
            {"id": 2301},
            make_floor_seated_analysis(),
            fast_rules,
        )
        current_time[0] = dynamic_start + timedelta(seconds=1.8)
        dynamic_jitter = dynamic_engine.evaluate_snapshot(
            camera,
            {"id": 2302},
            make_pose_fall_analysis(normal_lying_zone=False),
            fast_rules,
        )
        current_time[0] = dynamic_start + timedelta(seconds=3.1)
        dynamic_confirmed = dynamic_engine.evaluate_snapshot(
            camera,
            {"id": 2303},
            make_floor_seated_analysis(),
            fast_rules,
        )
    finally:
        rule_engine_module.utc_now = original_clock
    if dynamic_first.candidates or dynamic_jitter.candidates:
        raise SystemExit("dynamic low-position evidence must not alert before the bounded confirmation window")
    if dynamic_jitter.state.get("fall_stage") not in {"suspect", "confirming"}:
        raise SystemExit(f"same-track posture jitter reset dynamic fall evidence: {dynamic_jitter.state}")
    if len(dynamic_confirmed.candidates) != 1 or dynamic_confirmed.state.get("fall_stage") != "confirmed":
        raise SystemExit(f"sustained post-descent floor sitting must create one event: {dynamic_confirmed.state}")
    if dynamic_confirmed.state.get("fall_confirmation_path") != "dynamic_low_position":
        raise SystemExit(f"dynamic fall path is not auditable: {dynamic_confirmed.state}")
    if not 1.5 <= float(dynamic_confirmed.state.get("fall_confirm_seconds") or 0.0) <= 3.0:
        raise SystemExit(f"dynamic fall confirmation missed the 1.5-3 second target: {dynamic_confirmed.state}")

    chair_engine = RuleEngine()
    try:
        current_time = [dynamic_start]
        rule_engine_module.utc_now = lambda: current_time[0]
        chair_engine.evaluate_snapshot(camera, {"id": 2400}, make_upright_analysis(), fast_rules)
        chair_results = []
        for index, seconds in enumerate((1.0, 2.0, 3.2), start=1):
            current_time[0] = dynamic_start + timedelta(seconds=seconds)
            chair_results.append(chair_engine.evaluate_snapshot(
                camera,
                {"id": 2400 + index},
                make_chair_seated_analysis(),
                fast_rules,
            ))
    finally:
        rule_engine_module.utc_now = original_clock
    if any(result.candidates for result in chair_results):
        raise SystemExit("ordinary chair-height sitting must not enter the floor-impact path")

    unmapped_sofa_engine = RuleEngine()
    try:
        current_time = [dynamic_start]
        rule_engine_module.utc_now = lambda: current_time[0]
        unmapped_sofa_engine.evaluate_snapshot(camera, {"id": 2450}, make_upright_analysis(), fast_rules)
        unmapped_sofa_results = []
        for index, seconds in enumerate((1.0, 2.0, 3.2), start=1):
            current_time[0] = dynamic_start + timedelta(seconds=seconds)
            unmapped_sofa_results.append(unmapped_sofa_engine.evaluate_snapshot(
                camera,
                {"id": 2450 + index},
                make_unmapped_sofa_seated_analysis(),
                fast_rules,
            ))
    finally:
        rule_engine_module.utc_now = original_clock
    if any(result.candidates for result in unmapped_sofa_results):
        raise SystemExit("normal sofa-height sitting must not alert when furniture mapping is missing")

    no_upright_engine = RuleEngine()
    try:
        current_time = [dynamic_start]
        rule_engine_module.utc_now = lambda: current_time[0]
        no_upright_results = []
        for index, seconds in enumerate((0.0, 1.0, 2.2), start=1):
            current_time[0] = dynamic_start + timedelta(seconds=seconds)
            no_upright_results.append(no_upright_engine.evaluate_snapshot(
                camera,
                {"id": 2500 + index},
                make_floor_seated_analysis(),
                fast_rules,
            ))
    finally:
        rule_engine_module.utc_now = original_clock
    if any(result.candidates for result in no_upright_results):
        raise SystemExit("floor sitting without a recent upright-to-low transition must not alert")

    squat_engine = RuleEngine()
    try:
        current_time = [dynamic_start]
        rule_engine_module.utc_now = lambda: current_time[0]
        squat_engine.evaluate_snapshot(camera, {"id": 2600}, make_upright_analysis(), fast_rules)
        squat_results = []
        for index, seconds in enumerate((1.0, 2.0, 3.2), start=1):
            current_time[0] = dynamic_start + timedelta(seconds=seconds)
            squat_results.append(squat_engine.evaluate_snapshot(
                camera,
                {"id": 2600 + index},
                make_floor_squatting_analysis(),
                fast_rules,
            ))
    finally:
        rule_engine_module.utc_now = original_clock
    if any(result.candidates for result in squat_results):
        raise SystemExit("rapid squatting must not enter the floor-seated fall path")

    multi_person_engine = RuleEngine()
    try:
        current_time = [dynamic_start]
        rule_engine_module.utc_now = lambda: current_time[0]
        multi_person_engine.evaluate_snapshot(
            camera,
            {"id": 2700},
            make_multi_person_upright_analysis(),
            fast_rules,
        )
        multi_person_results = []
        for index, seconds in enumerate((1.0, 2.0, 3.2), start=1):
            current_time[0] = dynamic_start + timedelta(seconds=seconds)
            multi_person_results.append(multi_person_engine.evaluate_snapshot(
                camera,
                {"id": 2700 + index},
                make_multi_person_seated_analysis(),
                fast_rules,
            ))
    finally:
        rule_engine_module.utc_now = original_clock
    if any(result.candidates for result in multi_person_results):
        raise SystemExit("an upright bystander must not confirm another person's seated posture as a fall")

    track_jump_engine = RuleEngine()
    try:
        current_time = [dynamic_start]
        rule_engine_module.utc_now = lambda: current_time[0]
        tracked_upright = make_upright_analysis()
        tracked_upright["people"][0]["track_id"] = "person-1"
        tracked_upright["poses"][0]["track_id"] = "person-1"
        track_jump_engine.evaluate_snapshot(camera, {"id": 2800}, tracked_upright, fast_rules)
        current_time[0] = dynamic_start + timedelta(seconds=1.0)
        track_jump_engine.evaluate_snapshot(camera, {"id": 2801}, make_floor_seated_analysis(), fast_rules)
        track_jump_results = []
        for index, seconds in enumerate((1.8, 3.2), start=2):
            current_time[0] = dynamic_start + timedelta(seconds=seconds)
            track_jump_results.append(track_jump_engine.evaluate_snapshot(
                camera,
                {"id": 2800 + index},
                make_edge_track_jump_analysis(),
                fast_rules,
            ))
    finally:
        rule_engine_module.utc_now = original_clock
    if any(result.candidates for result in track_jump_results):
        raise SystemExit("an impossible same-id jump across the frame must break fall-state inheritance")

    worker = EdgeWorker(None, None, None, None)
    pose_rules = {"fall_detection_enabled": True, "activity_detection_enabled": True}
    manual_pose_runtime = worker._pose_runtime_config(1, pose_rules, adaptive=False)
    if not manual_pose_runtime.get("pose_detection_enabled"):
        raise SystemExit("manual full analysis must keep pose enabled")
    scheduler_now = worker._monotonic_clock()
    worker.inference_scheduler.reconcile([1], now=scheduler_now)
    idle_pose_runtime = worker._pose_runtime_config(1, pose_rules, adaptive=True)
    if idle_pose_runtime.get("pose_detection_enabled") or idle_pose_runtime.get("eacp_mode") != "idle":
        raise SystemExit("idle EACP sampling must begin with a person anchor instead of duplicate pose detection")
    worker.inference_scheduler.mark_started(1, now=scheduler_now)
    worker.inference_scheduler.observe(1, {"person_count": 1, "motion_detected": True}, now=scheduler_now + 0.1)
    fall_pose_runtime = worker._pose_runtime_config(1, pose_rules, adaptive=True)
    if not fall_pose_runtime.get("pose_detection_enabled") or fall_pose_runtime.get("worker_pose_interval_frames") != 1:
        raise SystemExit("active fall observation must sample pose on every scheduled model anchor")

    print(
        json.dumps(
            {
                "ok": True,
                "low_score_state": low_eval.state["fall_state"],
                "no_transition_state": no_transition_eval.state["fall_stage"],
                "first_frame_candidates": len(first_eval.candidates),
                "second_frame_candidates": len(second_eval.candidates),
                "second_frame_confirm_count": second_eval.state["fall_confirm_count"],
                "clear_stage": clear_eval.state["fall_stage"],
                "recovered_stage": recovered_eval.state["fall_stage"],
                "clear_confirm_count": recovered_eval.state["fall_confirm_count"],
                "scene_stage": scene_second.state["fall_stage"],
                "scene_suppressed": scene_second.state["fall_scene_suppressed"],
                "transition_scene_stage": transition_scene_second.state["fall_stage"],
                "transition_scene_suppressed": transition_scene_second.state["fall_scene_suppressed"],
                "fast_dynamic_stage": fast_second.state["fall_stage"],
                "fast_dynamic_seconds": fast_second.state["fall_confirm_seconds"],
                "dynamic_floor_stage": dynamic_confirmed.state["fall_stage"],
                "dynamic_floor_seconds": dynamic_confirmed.state["fall_confirm_seconds"],
                "chair_sitting_suppressed": True,
                "unmapped_sofa_sitting_suppressed": True,
                "floor_sitting_without_transition_suppressed": True,
                "rapid_squatting_suppressed": True,
                "multi_person_track_switch_suppressed": True,
                "impossible_track_jump_suppressed": True,
                "idle_pose_enabled": idle_pose_runtime["pose_detection_enabled"],
                "fall_pose_interval": fall_pose_runtime["worker_pose_interval_frames"],
                "history_baseline_stage": history_first.state["fall_stage"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def make_analysis(*, fall_candidate: bool = True, fall_score: float, normal_lying_zone: bool = False) -> dict:
    scene_fields = {
        "normal_lying_zone": normal_lying_zone,
        "scene_zone_id": "couch-1" if normal_lying_zone else None,
        "scene_zone_label": "couch" if normal_lying_zone else None,
        "scene_zone_label_zh": "沙发" if normal_lying_zone else None,
        "scene_zone_overlap": 0.82 if normal_lying_zone else None,
    }
    return {
        "pipeline_version": "vision-pipeline-v1",
        "detector_backend": "yolo",
        "model_name": "yolo11n.pt",
        "image_width": 640,
        "image_height": 360,
        "person_count": 1,
        "people": [
            {
                "bbox": [80, 180, 230, 238],
                "confidence": 0.74,
                "source": "fall_single_low_body",
                "method": "low_body_floor_contact",
                "fall_candidate": fall_candidate,
                "presence_candidate": False,
                **scene_fields,
            }
        ],
        "poses": [],
        "pose_count": 0,
        "fall_candidate": fall_candidate,
        "fall_score": fall_score,
        "pose_fall_candidate": False,
        "pose_fall_score": 0.0,
        "black_screen": False,
        "motion_detected": True,
        "motion_score": 0.08,
        "meal_candidate": False,
        "meal_score": 0.0,
        "stillness_candidate": False,
        "fire_candidate": False,
        "fire_score": 0.0,
        "fire_event_candidate": False,
        "thresholds": {
            "pose_fall_threshold": 0.78,
        },
        "algorithm_results": {
            "fall": {
                "data": {
                    "fall_candidate": fall_candidate,
                    "candidate_count": 1 if fall_candidate else 0,
                    "people": [
                        {
                            "method": "low_body_floor_contact",
                            "source": "fall_single_low_body",
                            "fall_candidate": fall_candidate,
                            **scene_fields,
                        }
                    ],
                    "single_low_body": {
                        "bbox": [80, 180, 230, 238],
                        "method": "low_body_floor_contact",
                        "source": "fall_single_low_body",
                        "fall_candidate": True,
                        **scene_fields,
                    } if fall_candidate else None,
                    "floor_cluster": None,
                }
            },
            "person": {"data": {}},
            "pose": {"data": {}},
        },
        "tags": ["fall_candidate"] if fall_candidate else [],
    }


def make_upright_analysis() -> dict:
    return {
        "pipeline_version": "vision-pipeline-v1",
        "detector_backend": "yolo",
        "model_name": "yolo11n.pt",
        "image_width": 640,
        "image_height": 360,
        "person_count": 1,
        "people": [{
            "bbox": [100, 20, 190, 250],
            "confidence": 0.82,
            "source": "yolo",
            "aspect_ratio": 0.39,
            "fall_candidate": False,
            "presence_candidate": False,
        }],
        "poses": [{
            "bbox": [100, 20, 190, 250],
            "confidence": 0.78,
            "source": "rtmpose",
            "posture": "standing_or_sitting",
            "person_evidence_eligible": True,
            "fall_score": 0.10,
        }],
        "pose_count": 1,
        "fall_candidate": False,
        "fall_score": 0.10,
        "pose_fall_candidate": False,
        "pose_fall_score": 0.10,
        "black_screen": False,
        "motion_detected": True,
        "motion_score": 0.04,
        "meal_candidate": False,
        "meal_score": 0.0,
        "stillness_candidate": False,
        "fire_candidate": False,
        "fire_score": 0.0,
        "fire_event_candidate": False,
        "thresholds": {"pose_fall_threshold": 0.78},
        "algorithm_results": {
            "fall": {"data": {"fall_candidate": False, "candidate_count": 0, "people": []}},
            "person": {"data": {}},
            "pose": {"data": {}},
        },
        "tags": ["person_detected", "pose_detected"],
    }


def make_bending_analysis() -> dict:
    analysis = make_upright_analysis()
    analysis["people"][0]["bbox"] = [105, 90, 225, 285]
    analysis["people"][0]["aspect_ratio"] = 0.62
    analysis["poses"][0]["bbox"] = [105, 90, 225, 285]
    analysis["poses"][0]["posture"] = "bending"
    analysis["motion_score"] = 0.06
    return analysis


def make_pose_fall_analysis(*, normal_lying_zone: bool, fast_graph: bool = False) -> dict:
    analysis = make_analysis(fall_candidate=False, fall_score=0.96, normal_lying_zone=normal_lying_zone)
    scene_fields = {
        "normal_lying_zone": normal_lying_zone,
        "scene_zone_id": "couch-1" if normal_lying_zone else None,
        "scene_zone_label": "couch" if normal_lying_zone else None,
        "scene_zone_label_zh": "沙发" if normal_lying_zone else None,
        "scene_zone_overlap": 0.82 if normal_lying_zone else None,
    }
    analysis["fall_candidate"] = True
    analysis["pose_fall_candidate"] = True
    analysis["pose_fall_score"] = 0.96
    analysis["poses"] = [{
        "bbox": [80, 180, 230, 238],
        "confidence": 0.88,
        "posture_confidence": 0.91,
        "source": "rtmpose",
        "posture": "lying",
        "track_id": "person-1",
        "person_evidence_eligible": True,
        "fall_evidence_eligible": True,
        "fall_score": 0.96,
        **scene_fields,
    }]
    analysis["pose_count"] = 1
    if fast_graph:
        analysis["pose_factor_graph"] = {
            "fast_fall_candidate": True,
            "fast_fall_score": 0.82,
            "fast_fall_track": {
                **analysis["poses"][0],
                "fast_fall_candidate": True,
                "fast_fall_score": 0.82,
            },
            "tracks": [],
        }
    return analysis


def make_floor_seated_analysis() -> dict:
    analysis = make_upright_analysis()
    bbox = [80, 200, 240, 350]
    analysis["people"] = [{
        "bbox": bbox,
        "confidence": 0.82,
        "source": "yolo",
        "track_id": "person-1",
        "aspect_ratio": 1.07,
        "fall_candidate": False,
        "presence_candidate": False,
        "normal_lying_zone": False,
    }]
    analysis["poses"] = [{
        "bbox": bbox,
        "confidence": 0.78,
        "posture_confidence": 0.78,
        "source": "rtmpose",
        "posture": "sitting",
        "track_id": "person-1",
        "person_evidence_eligible": True,
        "fall_evidence_eligible": True,
        "fall_score": 0.24,
        "normal_lying_zone": False,
    }]
    analysis["fall_candidate"] = False
    analysis["fall_score"] = 0.24
    analysis["pose_fall_candidate"] = False
    analysis["pose_fall_score"] = 0.24
    analysis["motion_detected"] = True
    analysis["motion_score"] = 0.06
    analysis["algorithm_results"]["fall"]["data"] = {
        "fall_candidate": False,
        "candidate_count": 0,
        "people": [],
    }
    analysis["tags"] = ["person_detected", "pose_detected"]
    return analysis


def make_chair_seated_analysis() -> dict:
    analysis = make_floor_seated_analysis()
    bbox = [90, 105, 215, 270]
    for target in [*analysis["people"], *analysis["poses"]]:
        target["bbox"] = bbox
        target["scene_zone_id"] = "chair-1"
        target["scene_zone_label"] = "chair"
    return analysis


def make_unmapped_sofa_seated_analysis() -> dict:
    analysis = make_floor_seated_analysis()
    bbox = [30, 176, 103, 271]
    for target in [*analysis["people"], *analysis["poses"]]:
        target["bbox"] = bbox
        target["scene_zone_id"] = None
        target["scene_zone_label"] = None
        target["normal_lying_zone"] = False
    analysis["motion_score"] = 0.03
    return analysis


def make_floor_squatting_analysis() -> dict:
    analysis = make_floor_seated_analysis()
    analysis["poses"][0]["posture"] = "squatting"
    analysis["poses"][0]["fall_score"] = 0.36
    analysis["fall_score"] = 0.36
    analysis["pose_fall_score"] = 0.36
    return analysis


def make_multi_person_upright_analysis() -> dict:
    analysis = make_upright_analysis()
    analysis["person_count"] = 2
    analysis["people"] = [
        {
            "bbox": [16, 90, 73, 214],
            "confidence": 0.82,
            "source": "yolo",
            "track_id": "bystander",
            "aspect_ratio": 0.46,
            "fall_candidate": False,
            "presence_candidate": False,
        },
        {
            "bbox": [91, 184, 166, 274],
            "confidence": 0.78,
            "source": "yolo",
            "track_id": "seated-person",
            "aspect_ratio": 0.83,
            "fall_candidate": False,
            "presence_candidate": False,
        },
    ]
    analysis["poses"] = [
        {
            "bbox": [16, 90, 73, 214],
            "confidence": 0.82,
            "source": "rtmpose",
            "track_id": "bystander",
            "posture": "standing",
            "person_evidence_eligible": True,
            "fall_score": 0.08,
        },
        {
            "bbox": [91, 184, 166, 274],
            "confidence": 0.78,
            "source": "rtmpose",
            "track_id": "seated-person",
            "posture": "sitting",
            "person_evidence_eligible": True,
            "fall_score": 0.24,
        },
    ]
    analysis["pose_count"] = 2
    return analysis


def make_multi_person_seated_analysis() -> dict:
    analysis = make_multi_person_upright_analysis()
    analysis["poses"][0]["bbox"] = [74, 125, 138, 238]
    analysis["poses"][0]["posture"] = "sitting"
    analysis["poses"][0]["fall_score"] = 0.18
    analysis["people"][0]["bbox"] = [74, 125, 138, 238]
    analysis["motion_score"] = 0.01
    return analysis


def make_edge_track_jump_analysis() -> dict:
    analysis = make_floor_seated_analysis()
    bbox = [565, 126, 640, 360]
    for target in [*analysis["people"], *analysis["poses"]]:
        target["bbox"] = bbox
    analysis["motion_score"] = 0.05
    return analysis


if __name__ == "__main__":
    main()
