from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.rule_engine import RuleEngine


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
    first_eval = engine.evaluate_snapshot(camera, snapshot, make_analysis(fall_score=0.62), rules)
    if first_eval.candidates:
        raise SystemExit("first strong fall frame must only confirm, not alert")
    if first_eval.state["fall_confirm_count"] != 1:
        raise SystemExit(f"first frame confirm count mismatch: {first_eval.state['fall_confirm_count']}")

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

    clear_eval = engine.evaluate_snapshot(camera, {"id": 1003}, make_analysis(fall_candidate=False, fall_score=0.0), rules)
    if clear_eval.state["fall_stage"] != "confirmed":
        raise SystemExit("first clear frame keeps incident open until recovery threshold")
    recovered_eval = engine.evaluate_snapshot(camera, {"id": 1004}, make_analysis(fall_candidate=False, fall_score=0.0), rules)
    if recovered_eval.state["fall_confirm_count"] != 0 or recovered_eval.state["fall_stage"] != "recovered":
        raise SystemExit("second clear frame must recover fall state")

    print(
        json.dumps(
            {
                "ok": True,
                "low_score_state": low_eval.state["fall_state"],
                "first_frame_candidates": len(first_eval.candidates),
                "second_frame_candidates": len(second_eval.candidates),
                "second_frame_confirm_count": second_eval.state["fall_confirm_count"],
                "clear_stage": clear_eval.state["fall_stage"],
                "recovered_stage": recovered_eval.state["fall_stage"],
                "clear_confirm_count": recovered_eval.state["fall_confirm_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def make_analysis(*, fall_candidate: bool = True, fall_score: float) -> dict:
    return {
        "pipeline_version": "vision-pipeline-v1",
        "detector_backend": "yolo",
        "model_name": "yolo11n.pt",
        "person_count": 1,
        "people": [
            {
                "bbox": [80, 180, 230, 238],
                "confidence": 0.74,
                "source": "fall_single_low_body",
                "method": "low_body_floor_contact",
                "fall_candidate": fall_candidate,
                "presence_candidate": False,
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
                        }
                    ],
                    "single_low_body": {"method": "low_body_floor_contact"} if fall_candidate else None,
                    "floor_cluster": None,
                }
            },
            "person": {"data": {}},
            "pose": {"data": {}},
        },
        "tags": ["fall_candidate"] if fall_candidate else [],
    }


if __name__ == "__main__":
    main()
