from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.pose_factor_graph import PoseFactorGraphEngine


def frame(
    posture: str,
    bbox: list[float],
    *,
    normal_zone: bool = False,
    motion: float = 0.03,
    track_id: str = "c1-p1",
    confidence: float = 0.92,
    image_height: int = 360,
    frame_edge_clipped: bool = False,
) -> dict:
    pose = {
        "track_id": track_id,
        "bbox": bbox,
        "confidence": confidence,
        "posture": posture,
        "posture_confidence": confidence,
        "posture_factors": {"body_aspect": (bbox[2] - bbox[0]) / (bbox[3] - bbox[1])},
        "normal_lying_zone": normal_zone,
        "scene_zone_id": "couch-1" if normal_zone else None,
        "scene_zone_label": "沙发" if normal_zone else None,
        "frame_edge_clipped": frame_edge_clipped,
    }
    return {
        "image_width": 640,
        "image_height": image_height,
        "motion_score": motion,
        "people": [],
        "poses": [pose],
    }


def main() -> None:
    engine = PoseFactorGraphEngine(prolonged_lying_seconds=180)
    engine.update(1, frame("standing", [250, 20, 340, 320]), monotonic_at=0.0)
    fall = frame("lying", [220, 220, 540, 350])
    result = engine.update(1, fall, monotonic_at=2.0)
    if not result["fast_fall_candidate"]:
        raise SystemExit(f"upright-to-floor transition must create a fast-fall factor candidate: {result}")
    track = result["fast_fall_track"] or {}
    if track.get("vertical_drop", 0) < 0.12 or track.get("normal_lying_zone"):
        raise SystemExit("fast-fall graph must preserve displacement and scene factors")

    sustained_engine = PoseFactorGraphEngine(prolonged_lying_seconds=180)
    sustained_engine.update(1, frame("standing", [250, 20, 340, 320], confidence=0.78), monotonic_at=10.0)
    shallow_floor_lying = frame(
        "lying",
        [220, 150, 540, 300],
        motion=0.001,
        confidence=0.78,
    )
    sustained_engine.update(1, shallow_floor_lying, monotonic_at=11.0)
    sustained_floor = sustained_engine.update(1, shallow_floor_lying, monotonic_at=12.6)
    if not sustained_floor["fast_fall_candidate"]:
        raise SystemExit(
            "same-track high-confidence floor lying must preserve recent descent evidence "
            f"after motion stops: {sustained_floor}"
        )

    borderline_engine = PoseFactorGraphEngine(prolonged_lying_seconds=180)
    borderline_engine.update(
        1,
        frame("standing", [367.1, 64.5, 463.8, 304.1], confidence=0.78, track_id="c24-p30"),
        monotonic_at=30.0,
    )
    borderline_floor = frame(
        "lying",
        [301.9, 182.5, 465.9, 268.1],
        motion=0.002,
        confidence=0.7824,
        track_id="c24-p30",
    )
    borderline_engine.update(1, borderline_floor, monotonic_at=31.0)
    sustained_borderline = borderline_engine.update(1, borderline_floor, monotonic_at=32.58)
    if not sustained_borderline["fast_fall_candidate"]:
        raise SystemExit(
            "sustained same-track floor lying must tolerate bounded pose-box jitter near the descent threshold: "
            f"{sustained_borderline}"
        )

    configured_engine = PoseFactorGraphEngine(prolonged_lying_seconds=180)
    configured_rules = {"fall_min_vertical_drop": 0.16, "fall_transition_motion_score": 0.03}
    configured_engine.update(
        1,
        frame("standing", [367.1, 64.5, 463.8, 304.1], confidence=0.78, track_id="configured-track"),
        monotonic_at=40.0,
        config=configured_rules,
    )
    configured_floor = frame(
        "lying",
        [301.9, 182.5, 465.9, 268.1],
        motion=0.002,
        confidence=0.7824,
        track_id="configured-track",
    )
    configured_engine.update(
        1,
        configured_floor,
        monotonic_at=41.0,
        config=configured_rules,
    )
    configured_result = configured_engine.update(
        1,
        configured_floor,
        monotonic_at=42.58,
        config=configured_rules,
    )
    configured_track = configured_result["tracks"][0]
    if configured_result["fast_fall_candidate"] or configured_track.get("fall_min_vertical_drop") != 0.16:
        raise SystemExit(f"pose factor graph must use the shared runtime fall thresholds: {configured_result}")

    sustained_engine.reset_camera(1)
    sustained_engine.update(1, frame("standing", [250, 20, 340, 320], confidence=0.78), monotonic_at=20.0)
    shallow_couch_lying = frame(
        "lying",
        [220, 150, 540, 300],
        normal_zone=True,
        motion=0.001,
        confidence=0.78,
    )
    sustained_engine.update(1, shallow_couch_lying, monotonic_at=21.0)
    sustained_couch = sustained_engine.update(1, shallow_couch_lying, monotonic_at=22.6)
    if sustained_couch["fast_fall_candidate"]:
        raise SystemExit("sustained couch or bed lying must not synthesize descent motion evidence")

    prolonged = engine.update(1, frame("lying", [220, 220, 540, 350], motion=0.0), monotonic_at=183.0)
    if not prolonged["prolonged_floor_lying_candidate"]:
        raise SystemExit("continuous non-normal-zone lying must trigger after 180 seconds")

    engine.reset_camera(1)
    engine.update(1, frame("standing", [250, 20, 340, 320]), monotonic_at=100.0)
    suppressed = engine.update(1, frame("lying", [220, 220, 540, 350], normal_zone=True), monotonic_at=300.0)
    if suppressed["fast_fall_candidate"] or suppressed["prolonged_floor_lying_candidate"]:
        raise SystemExit("static bed/couch lying without a recent descent must remain suppressed")

    engine.reset_camera(1)
    engine.update(1, frame("standing", [250, 20, 340, 320]), monotonic_at=100.0)
    couch_fall = engine.update(1, frame("lying", [220, 220, 540, 350], normal_zone=True), monotonic_at=102.0)
    if not couch_fall["fast_fall_candidate"]:
        raise SystemExit("recent rapid descent must remain a fast-fall candidate inside a couch/bed zone")
    if couch_fall["prolonged_floor_lying_candidate"]:
        raise SystemExit("normal lying surfaces must still suppress prolonged-floor-lying alerts")

    engine.reset_camera(1)
    engine.update(1, frame("standing", [504, 80, 637, 357]), monotonic_at=100.0)
    traversed_fall = engine.update(
        1,
        frame("lying", [3, 249, 209, 357], normal_zone=True, motion=0.056, confidence=0.81),
        monotonic_at=114.0,
    )
    if not traversed_fall["fast_fall_candidate"]:
        raise SystemExit("same-track continuity must survive a large in-frame traversal before a fall")

    engine.reset_camera(1)
    engine.update(1, frame("standing", [504, 80, 637, 357], track_id="c1-p1"), monotonic_at=100.0)
    different_track = engine.update(
        1,
        frame("lying", [3, 249, 209, 357], normal_zone=True, motion=0.056, track_id="c1-p2", confidence=0.81),
        monotonic_at=114.0,
    )
    if different_track["fast_fall_candidate"]:
        raise SystemExit("a distant replacement track must not inherit another person's upright history")

    # Production miss from camera 24 on 2026-07-22: geometry and track continuity
    # were strong, but the 0.6552 posture confidence previously capped the score.
    real_sequence = PoseFactorGraphEngine(prolonged_lying_seconds=180)
    real_sequence.update(
        24,
        frame(
            "standing",
            [416.9, 60.4, 478.7, 268.3],
            track_id="c24-p758",
            confidence=0.768,
            image_height=540,
        ),
        monotonic_at=0.0,
    )
    real_fall = real_sequence.update(
        24,
        frame(
            "lying",
            [398.0, 279.0, 527.5, 360.0],
            motion=0.0114,
            track_id="c24-p758",
            confidence=0.6552,
            image_height=540,
        ),
        monotonic_at=1.2,
    )
    if not real_fall["fast_fall_candidate"]:
        raise SystemExit(f"real rapid-descent sequence must enter cloud review: {real_fall}")
    real_track = real_fall["fast_fall_track"] or {}
    if not real_track.get("review_ready") or real_track.get("posture_reliability", 0) < 0.55:
        raise SystemExit(f"real sequence must expose auditable review quality: {real_track}")

    # Camera 24 live validation on 2026-07-22: the final horizontal posture
    # followed the descent frame by two seconds, so the transition evidence
    # must remain available to the factor graph.
    live_transition = PoseFactorGraphEngine(prolonged_lying_seconds=180)
    live_track_id = "c24-live-transition"
    live_transition.update(
        24,
        frame(
            "standing",
            [345.4, 59.7, 432.7, 326.0],
            motion=0.0054,
            track_id=live_track_id,
            confidence=0.7853,
        ),
        monotonic_at=0.0,
    )
    live_transition.update(
        24,
        frame(
            "sitting",
            [352.1, 145.9, 451.3, 332.2],
            motion=0.0204,
            track_id=live_track_id,
            confidence=0.7384,
        ),
        monotonic_at=8.6,
    )
    live_transition.update(
        24,
        frame(
            "squatting",
            [367.0, 196.6, 454.2, 293.9],
            motion=0.0197,
            track_id=live_track_id,
            confidence=0.6959,
        ),
        monotonic_at=9.9,
    )
    live_review = live_transition.update(
        24,
        frame(
            "squatting",
            [361.6, 210.9, 481.8, 299.2],
            motion=0.009,
            track_id=live_track_id,
            confidence=0.6581,
        ),
        monotonic_at=10.95,
    )
    live_review_track = live_review["fast_fall_track"] or {}
    if not live_review_track.get("review_ready"):
        raise SystemExit(f"live descent-to-horizontal sequence must enter cloud review: {live_review}")
    if live_review_track.get("motion_evidence_source") != "recent_descent":
        raise SystemExit(f"live sequence must explain its retained descent evidence: {live_review_track}")

    sit_engine = PoseFactorGraphEngine()
    sit_engine.update(1, frame("standing", [250, 20, 340, 320]), monotonic_at=0.0)
    deliberate_sit = sit_engine.update(
        1,
        frame("sitting", [220, 150, 360, 340], motion=0.04, confidence=0.88),
        monotonic_at=1.0,
    )
    if deliberate_sit["fast_fall_candidate"]:
        raise SystemExit("ordinary sitting must not enter fall review")

    squat_engine = PoseFactorGraphEngine()
    squat_engine.update(1, frame("standing", [250, 20, 340, 320]), monotonic_at=0.0)
    crouch = squat_engine.update(
        1,
        frame("squatting", [250, 170, 350, 350], motion=0.04, confidence=0.86),
        monotonic_at=1.0,
    )
    if crouch["fast_fall_candidate"]:
        raise SystemExit("upright-to-squat movement without a horizontal body must not enter fall review")

    clipped_engine = PoseFactorGraphEngine()
    clipped_engine.update(1, frame("standing", [520, 30, 620, 320]), monotonic_at=0.0)
    clipped = clipped_engine.update(
        1,
        frame(
            "lying",
            [500, 260, 640, 360],
            motion=0.05,
            confidence=0.32,
            frame_edge_clipped=True,
        ),
        monotonic_at=1.0,
    )
    if clipped["fast_fall_candidate"]:
        raise SystemExit("edge-clipped low-confidence person must not enter fall review")

    closeup_engine = PoseFactorGraphEngine()
    closeup_engine.update(
        1,
        frame("standing", [52.0, 50.0, 155.0, 320.0], track_id="c24-p23"),
        monotonic_at=0.0,
    )
    closeup = closeup_engine.update(
        1,
        frame(
            "lying",
            [0.0, 239.0, 313.1, 360.0],
            motion=0.0911,
            confidence=0.8154,
            track_id="c24-p23",
        ),
        monotonic_at=1.2,
    )
    closeup_track = closeup["tracks"][0]
    if closeup["fast_fall_candidate"]:
        raise SystemExit("high-confidence close-up crop must not enter fall review")
    if not closeup_track.get("frame_edge_clipped") or closeup_track.get("quality_gate"):
        raise SystemExit(f"close-up crop must fail the edge quality gate: {closeup_track}")

    occluded_lying_engine = PoseFactorGraphEngine(prolonged_lying_seconds=180)
    floor_lying = frame("lying", [220, 220, 540, 350], motion=0.0, track_id="c1-floor")
    occluded_lying_engine.update(1, floor_lying, monotonic_at=0.0)
    clipped_floor = frame(
        "lying",
        [0.0, 250.0, 320.0, 360.0],
        motion=0.0,
        track_id="c1-floor",
    )
    occluded_lying_engine.update(1, clipped_floor, monotonic_at=60.0)
    occluded_lying_engine.update(1, clipped_floor, monotonic_at=120.0)
    resumed_floor = occluded_lying_engine.update(1, floor_lying, monotonic_at=181.0)
    if not resumed_floor["prolonged_floor_lying_candidate"]:
        raise SystemExit("temporary edge clipping must not erase an established floor-lying state")

    slow_lie_engine = PoseFactorGraphEngine()
    slow_lie_engine.update(1, frame("standing", [250, 20, 340, 320]), monotonic_at=0.0)
    slow_lie = slow_lie_engine.update(
        1,
        frame("lying", [220, 220, 540, 350], motion=0.001, confidence=0.88),
        monotonic_at=10.0,
    )
    slow_lie_track = slow_lie["fast_fall_track"] or slow_lie["tracks"][0]
    if slow_lie_track.get("review_ready"):
        raise SystemExit("slow intentional lying without current motion must require temporal confirmation")

    engine.reset_camera(1)
    engine.update(1, frame("lying", [220, 220, 540, 350], motion=0.0), monotonic_at=0.0)
    squatting = engine.update(1, frame("squatting", [250, 170, 350, 350], motion=0.02), monotonic_at=181.0)
    bending = engine.update(1, frame("bending", [245, 130, 365, 345], motion=0.02), monotonic_at=182.0)
    resumed_after_low_postures = engine.update(1, frame("lying", [220, 220, 540, 350], motion=0.0), monotonic_at=183.0)
    if squatting["physical_recoveries"] or bending["physical_recoveries"]:
        raise SystemExit("transitional low postures must not produce physical recovery evidence")
    if not resumed_after_low_postures["prolonged_floor_lying_candidate"]:
        raise SystemExit("squatting and bending must not clear the active floor episode")

    bystander = engine.update(
        1,
        frame("standing", [40, 20, 130, 320], track_id="c1-bystander"),
        monotonic_at=184.0,
    )
    if bystander["physical_recoveries"]:
        raise SystemExit("an unrelated standing track must not recover the floor episode")
    resumed_after_bystander = engine.update(1, frame("lying", [220, 220, 540, 350], motion=0.0), monotonic_at=185.0)
    if not resumed_after_bystander["prolonged_floor_lying_candidate"]:
        raise SystemExit("a standing bystander must not clear another track's floor episode")

    engine.update(1, frame("standing", [250, 20, 340, 320], motion=0.02), monotonic_at=186.0)
    recovered = engine.update(1, frame("standing", [252, 20, 342, 320], motion=0.01), monotonic_at=187.0)
    if recovered["prolonged_floor_lying_candidate"]:
        raise SystemExit("two upright recovery samples must close prolonged lying state")
    recovery = recovered["physical_recoveries"][0] if recovered["physical_recoveries"] else {}
    if recovery.get("track_id") != "c1-p1" or recovery.get("sample_count") != 2:
        raise SystemExit(f"stable standing must emit same-track recovery evidence: {recovery}")

    seated_recovery_engine = PoseFactorGraphEngine(prolonged_lying_seconds=180)
    seated_recovery_engine.update(1, frame("lying", [220, 220, 540, 350]), monotonic_at=0.0)
    seated_recovery_engine.update(1, frame("sitting", [250, 120, 360, 340]), monotonic_at=181.0)
    seated_recovered = seated_recovery_engine.update(1, frame("sitting", [252, 120, 362, 340]), monotonic_at=182.0)
    if not seated_recovered["physical_recoveries"]:
        raise SystemExit("stable same-track seated posture must emit recovery evidence")

    print(json.dumps({
        "ok": True,
        "fast_fall_score": track.get("fast_fall_score"),
        "prolonged_seconds": prolonged["prolonged_floor_lying_tracks"][0]["lying_duration_seconds"],
        "normal_zone_suppressed": True,
        "normal_zone_fast_fall": couch_fall["fast_fall_candidate"],
        "sustained_floor_fast_fall": sustained_floor["fast_fall_candidate"],
        "sustained_borderline_fast_fall": sustained_borderline["fast_fall_candidate"],
        "shared_runtime_threshold": configured_track["fall_min_vertical_drop"],
        "sustained_couch_suppressed": not sustained_couch["fast_fall_candidate"],
        "traversed_fast_fall": traversed_fall["fast_fall_candidate"],
        "different_track_suppressed": not different_track["fast_fall_candidate"],
        "real_sequence_review_ready": real_track.get("review_ready"),
        "live_transition_review_ready": live_review_track.get("review_ready"),
        "deliberate_sit_suppressed": not deliberate_sit["fast_fall_candidate"],
        "crouch_suppressed": not crouch["fast_fall_candidate"],
        "edge_clipped_suppressed": not clipped["fast_fall_candidate"],
        "closeup_crop_suppressed": not closeup["fast_fall_candidate"],
        "edge_occlusion_preserves_lying_state": resumed_floor["prolonged_floor_lying_candidate"],
        "slow_lying_requires_confirmation": not slow_lie_track.get("review_ready"),
        "recovery_verified": True,
        "transitional_postures_preserve_floor_episode": True,
        "bystander_recovery_suppressed": True,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
