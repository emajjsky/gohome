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
from app.vision.pose_factor_graph import PoseFactorGraphEngine
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

    presence_quality_engine = RuleEngine()
    weak_presence_analysis = make_upright_analysis()
    weak_presence_analysis["temporal_observation"] = {
        "person_present": True,
        "person_count": 1,
        "credible_person_present": False,
        "credible_person_count": 0,
        "presence_persistence_state": "uncertain",
    }
    weak_presence_eval = presence_quality_engine.evaluate_snapshot(
        camera,
        {"id": 999},
        weak_presence_analysis,
        rules,
    )
    if weak_presence_eval.state.get("person_state") != "not_visible":
        raise SystemExit("weak person evidence must not reset the long-absence clock")

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

    real_graph = PoseFactorGraphEngine(prolonged_lying_seconds=180)
    real_engine = RuleEngine()
    real_upright = make_upright_analysis()
    real_upright["image_height"] = 540
    for item in [*real_upright["people"], *real_upright["poses"]]:
        item["bbox"] = [416.9, 60.4, 478.7, 268.3]
        item["track_id"] = "c24-p758"
        item["confidence"] = 0.768
    real_upright["poses"][0]["posture"] = "standing"
    real_upright["poses"][0]["posture_confidence"] = 0.768
    real_graph.update(24, real_upright, monotonic_at=0.0)
    real_engine.evaluate_snapshot({"id": 24, "name": "冰箱上"}, {"id": 1200}, real_upright, rules)

    real_lying = make_pose_fall_analysis(normal_lying_zone=False)
    real_lying["image_height"] = 540
    real_lying["motion_score"] = 0.0114
    for item in [*real_lying["people"], *real_lying["poses"]]:
        item["bbox"] = [398.0, 279.0, 527.5, 360.0]
        item["track_id"] = "c24-p758"
        item["confidence"] = 0.6552
        item["posture"] = "lying"
        item["normal_lying_zone"] = False
    real_lying["poses"][0]["posture_confidence"] = 0.6552
    real_graph.update(24, real_lying, monotonic_at=1.2)
    real_review = real_engine.evaluate_snapshot(
        {"id": 24, "name": "冰箱上"},
        {"id": 1201},
        real_lying,
        rules,
    )
    if len(real_review.candidates) != 1:
        raise SystemExit(f"real rapid descent must create one cloud-review event immediately: {real_review.state}")
    if real_review.state.get("fall_confirmation_path") != "edge_cloud_review":
        raise SystemExit(f"real rapid descent did not use the auditable cloud-review path: {real_review.state}")
    if "云端复核" not in real_review.candidates[0].summary:
        raise SystemExit(f"product copy must not claim final confirmation before cloud review: {real_review.candidates[0]}")

    clear_eval = engine.evaluate_snapshot(camera, {"id": 1003}, make_analysis(fall_candidate=False, fall_score=0.0), rules)
    if clear_eval.state["fall_stage"] != "confirmed":
        raise SystemExit("first clear frame must keep the confirmed incident open")
    cleared_eval = engine.evaluate_snapshot(camera, {"id": 1004}, make_analysis(fall_candidate=False, fall_score=0.0), rules)
    if cleared_eval.state["fall_stage"] != "candidate_cleared" or cleared_eval.state.get("fall_recovery"):
        raise SystemExit("candidate disappearance must not claim physical recovery")

    squatting_eval = engine.evaluate_snapshot(
        camera,
        {"id": 1005},
        make_recovery_analysis("squatting", "person-1", confirmed=False),
        rules,
    )
    if squatting_eval.state["fall_stage"] != "candidate_cleared" or squatting_eval.state.get("fall_recovery"):
        raise SystemExit("squatting must not resolve a confirmed fall")
    bystander_eval = engine.evaluate_snapshot(
        camera,
        {"id": 1006},
        make_recovery_analysis("standing", "bystander", confirmed=True),
        rules,
    )
    if bystander_eval.state["fall_stage"] != "candidate_cleared" or bystander_eval.state.get("fall_recovery"):
        raise SystemExit("an unrelated standing person must not resolve the fallen track")
    recovered_eval = engine.evaluate_snapshot(
        camera,
        {"id": 1007},
        make_recovery_analysis("standing", "person-1", confirmed=True),
        rules,
    )
    if recovered_eval.state["fall_stage"] != "recovered":
        raise SystemExit("same-track stable standing must recover the confirmed fall")
    recovery = recovered_eval.state.get("fall_recovery") or {}
    if recovery.get("identity_match") != "same_track" or recovery.get("sample_count") != 2:
        raise SystemExit(f"recovery evidence contract mismatch: {recovery}")

    seated_engine = RuleEngine()
    seated_engine.evaluate_snapshot(camera, {"id": 1010}, make_upright_analysis(), rules)
    seated_engine.evaluate_snapshot(camera, {"id": 1011}, make_pose_fall_analysis(normal_lying_zone=False, fast_graph=True), rules)
    seated_engine.evaluate_snapshot(camera, {"id": 1012}, make_pose_fall_analysis(normal_lying_zone=False, fast_graph=True), rules)
    seated_recovery = seated_engine.evaluate_snapshot(
        camera,
        {"id": 1013},
        make_recovery_analysis("sitting", "person-1", confirmed=True),
        rules,
    )
    if seated_recovery.state.get("fall_stage") != "recovered":
        raise SystemExit("same-track stable seated recovery must resolve the fall lifecycle")

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
    if transition_scene_first.candidates or transition_scene_second.candidates:
        raise SystemExit("normal lying zones must suppress pose-only fall transitions")
    if transition_scene_second.state["fall_stage"] != "normal_lying_zone":
        raise SystemExit("pose-only normal lying transition must stay in the scene-suppressed state")
    if not transition_scene_second.state.get("fall_scene_suppressed"):
        raise SystemExit("pose-only normal lying transition must remain scene-suppressed")

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
        fast_uncorroborated = fast_engine.evaluate_snapshot(
            camera,
            {"id": 2202},
            make_pose_fall_analysis(normal_lying_zone=True),
            fast_rules,
        )
        current_time[0] = fast_start + timedelta(seconds=2.50)
        fast_second = fast_engine.evaluate_snapshot(
            camera,
            {"id": 2203},
            make_pose_fall_analysis(normal_lying_zone=True, fast_graph=True),
            fast_rules,
        )
        current_time[0] = fast_start + timedelta(seconds=2.75)
        fast_third = fast_engine.evaluate_snapshot(
            camera,
            {"id": 2204},
            make_pose_fall_analysis(normal_lying_zone=True, fast_graph=True),
            fast_rules,
        )
    finally:
        rule_engine_module.utc_now = original_clock
    if fast_first.candidates:
        raise SystemExit("first graph-confirmed fast-fall frame must remain a suspect")
    if fast_uncorroborated.candidates:
        raise SystemExit("normal lying zone must not inherit a stale graph-confirmed fast-fall path")
    if fast_second.candidates:
        raise SystemExit("first refreshed graph-confirmed frame after scene suppression must remain a suspect")
    if len(fast_third.candidates) != 1 or fast_third.state.get("fall_stage") != "confirmed":
        raise SystemExit("two current factor-graph fall frames must create an event inside a normal lying zone")
    if fast_third.state.get("fall_confirm_seconds", 0) >= fast_rules["fall_confirm_seconds"]:
        raise SystemExit("fast-fall path did not exercise the short dynamic confirmation branch")

    sustained_graph = PoseFactorGraphEngine(prolonged_lying_seconds=180)
    sustained_engine = RuleEngine()
    sustained_start = datetime(2026, 7, 20, 14, 43, 20, tzinfo=timezone.utc)
    try:
        current_time = [sustained_start]
        rule_engine_module.utc_now = lambda: current_time[0]
        sustained_upright = make_upright_analysis()
        sustained_upright["people"][0]["bbox"] = [367.1, 64.5, 463.8, 304.1]
        sustained_upright["poses"][0]["bbox"] = [367.1, 64.5, 463.8, 304.1]
        sustained_upright["people"][0]["track_id"] = "person-1"
        sustained_upright["poses"][0]["track_id"] = "person-1"
        sustained_graph.update(1, sustained_upright, monotonic_at=0.0)
        sustained_engine.evaluate_snapshot(camera, {"id": 2250}, sustained_upright, fast_rules)

        current_time[0] = sustained_start + timedelta(seconds=1.0)
        sustained_first_analysis = make_shallow_floor_lying_analysis()
        sustained_graph.update(1, sustained_first_analysis, monotonic_at=1.0)
        sustained_first = sustained_engine.evaluate_snapshot(
            camera,
            {"id": 2251},
            sustained_first_analysis,
            fast_rules,
        )

        current_time[0] = sustained_start + timedelta(seconds=2.6)
        sustained_second_analysis = make_shallow_floor_lying_analysis()
        sustained_graph.update(1, sustained_second_analysis, monotonic_at=2.6)
        sustained_second = sustained_engine.evaluate_snapshot(
            camera,
            {"id": 2252},
            sustained_second_analysis,
            fast_rules,
        )

        current_time[0] = sustained_start + timedelta(seconds=2.85)
        sustained_third_analysis = make_shallow_floor_lying_analysis()
        sustained_graph.update(1, sustained_third_analysis, monotonic_at=2.85)
        sustained_confirmed = sustained_engine.evaluate_snapshot(
            camera,
            {"id": 2253},
            sustained_third_analysis,
            fast_rules,
        )
    finally:
        rule_engine_module.utc_now = original_clock
    if sustained_first.candidates or sustained_second.candidates:
        raise SystemExit("sustained lying transition must not alert before two formal factor-graph frames")
    if len(sustained_confirmed.candidates) != 1 or sustained_confirmed.state.get("fall_stage") != "confirmed":
        raise SystemExit(f"sustained floor lying after a shallow descent must create an event: {sustained_confirmed.state}")
    if sustained_confirmed.state.get("fall_confirmation_path") != "fast_factor_graph":
        raise SystemExit(f"sustained floor transition path is not auditable: {sustained_confirmed.state}")

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
            make_corroborated_floor_seated_analysis(),
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
            make_corroborated_floor_seated_analysis(),
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

    uncorroborated_engine = RuleEngine()
    try:
        current_time = [dynamic_start]
        rule_engine_module.utc_now = lambda: current_time[0]
        uncorroborated_engine.evaluate_snapshot(camera, {"id": 2350}, make_upright_analysis(), fast_rules)
        uncorroborated_results = []
        for index, seconds in enumerate((1.0, 2.0, 3.2), start=1):
            current_time[0] = dynamic_start + timedelta(seconds=seconds)
            uncorroborated_results.append(uncorroborated_engine.evaluate_snapshot(
                camera,
                {"id": 2350 + index},
                make_floor_seated_analysis(),
                fast_rules,
            ))
    finally:
        rule_engine_module.utc_now = original_clock
    if any(result.candidates for result in uncorroborated_results):
        raise SystemExit("low seated posture without a recent continual descent hint must not create a fall event")

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

    settled_floor_engine = RuleEngine()
    try:
        current_time = [dynamic_start]
        rule_engine_module.utc_now = lambda: current_time[0]
        settled_floor_engine.evaluate_snapshot(camera, {"id": 2420}, make_upright_analysis(), fast_rules)
        settled_floor_results = []
        for index, seconds in enumerate((1.0, 2.0, 3.2), start=1):
            current_time[0] = dynamic_start + timedelta(seconds=seconds)
            settled_floor_results.append(settled_floor_engine.evaluate_snapshot(
                camera,
                {"id": 2420 + index},
                make_settled_floor_seated_analysis(),
                fast_rules,
            ))
    finally:
        rule_engine_module.utc_now = original_clock
    if any(result.candidates for result in settled_floor_results):
        raise SystemExit("settled low sitting without descent motion must not enter the dynamic fall path")

    edge_clipped_engine = RuleEngine()
    try:
        current_time = [dynamic_start]
        rule_engine_module.utc_now = lambda: current_time[0]
        edge_clipped_engine.evaluate_snapshot(camera, {"id": 2430}, make_upright_analysis(), fast_rules)
        edge_clipped_results = []
        for index, seconds in enumerate((1.0, 2.0, 3.2), start=1):
            current_time[0] = dynamic_start + timedelta(seconds=seconds)
            edge_clipped_results.append(edge_clipped_engine.evaluate_snapshot(
                camera,
                {"id": 2430 + index},
                make_edge_clipped_lying_analysis(),
                fast_rules,
            ))
    finally:
        rule_engine_module.utc_now = original_clock
    if any(result.candidates for result in edge_clipped_results):
        raise SystemExit("edge-clipped lying pose must not create a dynamic fall event without direct evidence")

    bottom_clipped_engine = RuleEngine()
    try:
        current_time = [dynamic_start]
        rule_engine_module.utc_now = lambda: current_time[0]
        bottom_clipped_engine.evaluate_snapshot(
            camera,
            {"id": 2435},
            make_bottom_edge_upright_analysis(),
            fast_rules,
        )
        bottom_clipped_results = []
        bottom_clipped_samples = [
            make_bottom_clipped_lying_transition_analysis(),
            make_bottom_clipped_upper_body_analysis(),
            make_bottom_clipped_upper_body_analysis(),
        ]
        for index, (seconds, sample) in enumerate(zip((1.0, 2.0, 3.2), bottom_clipped_samples), start=1):
            current_time[0] = dynamic_start + timedelta(seconds=seconds)
            bottom_clipped_results.append(bottom_clipped_engine.evaluate_snapshot(
                camera,
                {"id": 2435 + index},
                sample,
                fast_rules,
            ))
    finally:
        rule_engine_module.utc_now = original_clock
    if any(result.candidates for result in bottom_clipped_results):
        raise SystemExit("bottom-clipped upper-body pose must not create a dynamic fall event")

    rotation_engine = RuleEngine()
    try:
        current_time = [dynamic_start]
        rule_engine_module.utc_now = lambda: current_time[0]
        rotation_engine.evaluate_snapshot(
            camera,
            {"id": 2440},
            make_rotation_transition_analysis("standing", [398.5, 52.1, 485.3, 307.5], 0.022, 0.08),
            fast_rules,
        )
        current_time[0] = dynamic_start + timedelta(seconds=2.0)
        rotation_engine.evaluate_snapshot(
            camera,
            {"id": 2441},
            make_rotation_transition_analysis("sitting", [342.4, 137.5, 437.4, 282.9], 0.024, 0.18),
            fast_rules,
        )
        current_time[0] = dynamic_start + timedelta(seconds=3.1)
        rotation_engine.evaluate_snapshot(
            camera,
            {"id": 2442},
            make_rotation_transition_analysis("squatting", [361.6, 163.9, 434.6, 248.6], 0.024, 0.36),
            fast_rules,
        )
        rotation_results = []
        for index, seconds in enumerate((3.4, 3.9, 5.6), start=1):
            current_time[0] = dynamic_start + timedelta(seconds=seconds)
            rotation_results.append(rotation_engine.evaluate_snapshot(
                camera,
                {"id": 2442 + index},
                make_rotation_transition_analysis("lying", [373.2, 167.7, 461.9, 235.0], 0.016, 0.82),
                fast_rules,
            ))
    finally:
        rule_engine_module.utc_now = original_clock
    if rotation_results[0].candidates or rotation_results[1].candidates:
        raise SystemExit("body-rotation transition must retain bounded multi-frame confirmation")
    if len(rotation_results[-1].candidates) != 1:
        raise SystemExit(f"standing-to-horizontal rotation must create one fall event: {rotation_results[-1].state}")
    transition = rotation_results[-1].state.get("fall_transition") or {}
    if not transition.get("body_rotation_confirmed"):
        raise SystemExit(f"rotation-based fall transition must remain auditable: {transition}")

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
    worker.inference_scheduler.signal_activity(
        1,
        now=scheduler_now + 0.2,
        risk=True,
        source="rapid_downward_pose_motion",
    )
    corroborated_runtime = worker._pose_runtime_config(1, pose_rules, adaptive=True)
    corroborated_payload = worker._inference_runtime_payload(corroborated_runtime)
    if not corroborated_payload.get("recent_rapid_descent"):
        raise SystemExit("continual descent hint must reach the next formal model anchor")
    if corroborated_payload.get("rapid_descent_source") != "rapid_downward_pose_motion":
        raise SystemExit("continual descent hint source must remain auditable")

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
                "candidate_cleared_stage": cleared_eval.state["fall_stage"],
                "recovered_stage": recovered_eval.state["fall_stage"],
                "clear_confirm_count": recovered_eval.state["fall_confirm_count"],
                "scene_stage": scene_second.state["fall_stage"],
                "scene_suppressed": scene_second.state["fall_scene_suppressed"],
                "transition_scene_stage": transition_scene_second.state["fall_stage"],
                "transition_scene_suppressed": transition_scene_second.state["fall_scene_suppressed"],
                "fast_dynamic_stage": fast_second.state["fall_stage"],
                "fast_dynamic_seconds": fast_second.state["fall_confirm_seconds"],
                "sustained_floor_stage": sustained_confirmed.state["fall_stage"],
                "sustained_floor_action_seconds": 2.85,
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
                "rapid_descent_corroborated": corroborated_payload["recent_rapid_descent"],
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
                "track_id": "person-1",
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
                            "track_id": "person-1",
                            "fall_candidate": fall_candidate,
                            **scene_fields,
                        }
                    ],
                    "single_low_body": {
                        "bbox": [80, 180, 230, 238],
                        "method": "low_body_floor_contact",
                        "source": "fall_single_low_body",
                        "track_id": "person-1",
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
            "track_id": "person-1",
            "aspect_ratio": 0.39,
            "fall_candidate": False,
            "presence_candidate": False,
        }],
        "poses": [{
            "bbox": [100, 20, 190, 250],
            "confidence": 0.78,
            "source": "rtmpose",
            "track_id": "person-1",
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


def make_recovery_analysis(posture: str, track_id: str, *, confirmed: bool) -> dict:
    analysis = make_upright_analysis()
    for item in [*analysis["people"], *analysis["poses"]]:
        item["track_id"] = track_id
    analysis["poses"][0]["posture"] = posture
    analysis["poses"][0]["posture_confidence"] = 0.82
    analysis["pose_factor_graph"] = {
        "fast_fall_candidate": False,
        "fast_fall_score": 0.0,
        "fast_fall_track": None,
        "tracks": [],
        "physical_recoveries": [{
            "schema_version": "gohome-physical-recovery-v1",
            "confirmed": True,
            "reason": "same_track_stable_upright",
            "track_id": track_id,
            "posture": posture,
            "confidence": 0.82,
            "bbox": list(analysis["poses"][0]["bbox"]),
            "sample_count": 2,
            "required_samples": 2,
            "identity_match": "same_track",
        }] if confirmed else [],
    }
    return analysis


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


def make_shallow_floor_lying_analysis() -> dict:
    analysis = make_pose_fall_analysis(normal_lying_zone=False)
    bbox = [301.9, 182.5, 465.9, 268.1]
    analysis["motion_detected"] = False
    analysis["motion_score"] = 0.001
    for target in [*analysis["people"], *analysis["poses"]]:
        target["bbox"] = list(bbox)
        target["track_id"] = "person-1"
        target["confidence"] = 0.7824
        target["posture_confidence"] = 0.7824
        target["normal_lying_zone"] = False
        target["scene_zone_id"] = None
        target["scene_zone_label"] = None
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


def make_corroborated_floor_seated_analysis() -> dict:
    analysis = make_floor_seated_analysis()
    analysis["inference_runtime"] = {
        "schema_version": "eacp-analysis-runtime-v1",
        "recent_rapid_descent": True,
        "rapid_descent_age_seconds": 0.3,
        "rapid_descent_source": "rapid_downward_pose_motion",
    }
    return analysis


def make_settled_floor_seated_analysis() -> dict:
    analysis = make_floor_seated_analysis()
    analysis["motion_detected"] = False
    analysis["motion_score"] = 0.005
    return analysis


def make_edge_clipped_lying_analysis() -> dict:
    analysis = make_settled_floor_seated_analysis()
    bbox = [548, 145, 640, 357]
    for target in [*analysis["people"], *analysis["poses"]]:
        target["bbox"] = list(bbox)
        target["posture"] = "lying"
        target["track_id"] = "person-edge"
        target["fall_score"] = 0.68
    analysis["poses"][0]["posture_confidence"] = 0.64
    analysis["pose_fall_score"] = 0.68
    analysis["fall_score"] = 0.18
    return analysis


def make_bottom_clipped_upper_body_analysis() -> dict:
    analysis = make_floor_seated_analysis()
    bbox = [457.1, 278.0, 570.3, 360.0]
    for target in [*analysis["people"], *analysis["poses"]]:
        target["bbox"] = list(bbox)
        target["track_id"] = "person-1"
        target["fall_score"] = 0.22
    analysis["poses"][0]["posture"] = "upper_body"
    analysis["poses"][0]["posture_confidence"] = 0.55
    analysis["motion_score"] = 0.03
    analysis["pose_fall_score"] = 0.22
    analysis["fall_score"] = 0.16
    return analysis


def make_bottom_clipped_lying_transition_analysis() -> dict:
    analysis = make_bottom_clipped_upper_body_analysis()
    bbox = [430.0, 310.0, 590.0, 360.0]
    for target in [*analysis["people"], *analysis["poses"]]:
        target["bbox"] = list(bbox)
    analysis["poses"][0]["posture"] = "lying"
    analysis["poses"][0]["posture_confidence"] = 0.62
    return analysis


def make_bottom_edge_upright_analysis() -> dict:
    analysis = make_upright_analysis()
    bbox = [472.5, 219.8, 591.1, 360.0]
    for target in [*analysis["people"], *analysis["poses"]]:
        target["bbox"] = list(bbox)
        target["track_id"] = "person-1"
    analysis["poses"][0]["posture"] = "standing"
    return analysis


def make_rotation_transition_analysis(
    posture: str,
    bbox: list[float],
    motion_score: float,
    fall_score: float,
) -> dict:
    analysis = make_upright_analysis()
    track_id = "rotation-person"
    pose = analysis["poses"][0]
    person = analysis["people"][0]
    for target in (pose, person):
        target["bbox"] = list(bbox)
        target["track_id"] = track_id
    pose.update({
        "posture": posture,
        "posture_confidence": 0.82,
        "fall_score": fall_score,
        "fall_evidence_eligible": True,
        "posture_factors": {"body_aspect": (bbox[2] - bbox[0]) / (bbox[3] - bbox[1])},
    })
    person["fall_candidate"] = posture == "lying"
    analysis["fall_candidate"] = posture == "lying"
    analysis["fall_score"] = fall_score
    analysis["pose_fall_candidate"] = posture == "lying"
    analysis["pose_fall_score"] = fall_score
    analysis["motion_detected"] = motion_score >= 0.015
    analysis["motion_score"] = motion_score
    analysis["algorithm_results"]["fall"]["data"] = {
        "fall_candidate": posture == "lying",
        "candidate_count": 1 if posture == "lying" else 0,
        "people": [],
    }
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
