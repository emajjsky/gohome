from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
    scene_engine.evaluate_snapshot(camera, {"id": 2000}, make_upright_analysis(), rules)
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


if __name__ == "__main__":
    main()
