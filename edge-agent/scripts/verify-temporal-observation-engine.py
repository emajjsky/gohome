from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.temporal import TemporalObservationEngine
from app.worker import EdgeWorker


def analysis(*people: dict) -> dict:
    return {
        "image_width": 640,
        "image_height": 360,
        "people": list(people),
        "poses": [],
        "motion_score": 0.02,
        "fall_candidate": False,
        "fire_candidate": False,
    }


def person(bbox: list[float], confidence: float = 0.9, posture: str = "standing") -> dict:
    return {
        "bbox": bbox,
        "confidence": confidence,
        "posture": posture,
        "posture_confidence": confidence,
    }


def assert_track(payload: dict, index: int, expected: str, message: str) -> None:
    actual = str(payload["people"][index].get("track_id") or "")
    if actual != expected:
        raise SystemExit(f"{message}: expected {expected}, got {actual}")


def main() -> None:
    engine = TemporalObservationEngine(history_size=8, track_ttl_seconds=10)
    first = analysis({"bbox": [100, 60, 220, 330], "confidence": 0.91})
    first_result = engine.update(1, first, observed_at="2026-07-11T10:00:00+00:00", monotonic_at=1.0)
    track_id = first_result["current_track_ids"][0]

    second = analysis({"bbox": [108, 62, 228, 332], "confidence": 0.90})
    second_result = engine.update(1, second, observed_at="2026-07-11T10:00:01+00:00", monotonic_at=2.0)
    if second_result["current_track_ids"] != [track_id]:
        raise SystemExit("nearby detections must keep the same track id")
    if second["people"][0].get("track_id") != track_id:
        raise SystemExit("analysis person must be annotated with track id")
    if second_result.get("presence_persistence_state") != "visible":
        raise SystemExit(f"credible person must be eligible for durable presence: {second_result}")
    engine.attach_snapshot(1, {"id": 12, "image_path": "snapshots/camera-1/12.jpg"})
    bundle = engine.evidence_bundle(1, event_type="fall_candidate", track_id=track_id)
    if bundle["snapshots"][-1]["snapshot_id"] != 12 or bundle["track_id"] != track_id:
        raise SystemExit("temporal evidence bundle must preserve representative snapshot and track")

    third = analysis(
        {"bbox": [115, 64, 235, 334], "confidence": 0.89},
        {"bbox": [400, 80, 510, 338], "confidence": 0.87},
    )
    third_result = engine.update(1, third, observed_at="2026-07-11T10:00:02+00:00", monotonic_at=3.0)
    if len(set(third_result["current_track_ids"])) != 2 or track_id not in third_result["current_track_ids"]:
        raise SystemExit("second person must get a distinct stable track")

    for index in range(12):
        engine.update(1, analysis(), observed_at=f"2026-07-11T10:01:{index:02d}+00:00", monotonic_at=20.0 + index)
    history = engine.recent_history(1)
    if len(history) != 8:
        raise SystemExit(f"ring buffer must remain bounded, got {len(history)}")
    if engine.update(1, analysis(), monotonic_at=40.0)["active_tracks"]:
        raise SystemExit("expired tracks must be removed")

    weak_presence = TemporalObservationEngine(history_size=8, track_ttl_seconds=10)
    weak_first = weak_presence.update(
        25,
        analysis(person([610, 100, 640, 250], confidence=0.22, posture="unknown")),
        monotonic_at=1.0,
    )
    if weak_first.get("presence_persistence_state") != "uncertain" or weak_first.get("credible_person_present"):
        raise SystemExit(f"one-frame weak edge detection must stay out of durable presence: {weak_first}")
    weak_second_payload = analysis(person([608, 101, 640, 252], confidence=0.30, posture="unknown"))
    weak_second = weak_presence.update(25, weak_second_payload, monotonic_at=2.0)
    if weak_second.get("presence_persistence_state") != "visible":
        raise SystemExit(f"repeated model evidence above the tracked floor should become credible: {weak_second}")
    weak_absent = weak_presence.update(25, analysis(), monotonic_at=3.0)
    if weak_absent.get("presence_persistence_state") != "absent":
        raise SystemExit(f"empty frame must close durable presence: {weak_absent}")

    evidence_engine = TemporalObservationEngine(
        history_size=12,
        track_ttl_seconds=30,
        max_match_age_seconds=10,
    )
    evidence_track = ""
    for index, seconds in enumerate((0, 5, 10, 15), start=1):
        payload = analysis(person([100, 50, 200, 330]))
        evidence_engine.update(
            12,
            payload,
            observed_at=f"2026-07-11T10:02:{seconds:02d}+00:00",
            monotonic_at=float(seconds),
        )
        evidence_track = str(payload["people"][0]["track_id"])
        evidence_engine.attach_snapshot(12, {"id": index, "image_path": f"camera-12/{index}.jpg"})
    recent_bundle = evidence_engine.evidence_bundle(
        12,
        event_type="fall_candidate",
        track_id=evidence_track,
        max_age_seconds=10,
    )
    if [item["snapshot_id"] for item in recent_bundle["snapshots"]] != [2, 3, 4]:
        raise SystemExit(f"event evidence must use the recent action window: {recent_bundle}")

    role_engine = TemporalObservationEngine(
        history_size=12,
        track_ttl_seconds=20,
        max_match_age_seconds=5,
    )
    role_track = ""
    role_samples = [
        (101, 0.0, "standing", [240, 30, 340, 330], 0.01),
        (102, 0.6, "bending", [230, 100, 360, 335], 0.08),
        (103, 1.2, "lying", [210, 220, 520, 350], 0.05),
    ]
    for snapshot_id, seconds, posture, bbox, motion in role_samples:
        payload = analysis(person(bbox, posture=posture))
        payload["motion_score"] = motion
        role_engine.update(
            13,
            payload,
            observed_at=f"2026-07-11T10:03:0{int(seconds)}+00:00",
            monotonic_at=seconds,
        )
        role_track = str(payload["people"][0]["track_id"])
        role_engine.attach_snapshot(
            13,
            {"id": snapshot_id, "image_path": f"camera-13/{snapshot_id}.jpg"},
        )
    role_bundle = role_engine.evidence_bundle(
        13,
        event_type="pose_safety_candidate",
        track_id=role_track,
        max_age_seconds=15,
    )
    role_sequence = [
        (item["snapshot_id"], item["role"])
        for item in role_bundle["snapshots"]
    ]
    if role_sequence != [(101, "before"), (102, "transition"), (103, "current")]:
        raise SystemExit(f"fall evidence must preserve before/transition/current roles: {role_bundle}")
    current_only = role_engine.evidence_bundle(
        13,
        event_type="pose_safety_candidate",
        track_id=role_track,
        limit=1,
        max_age_seconds=15,
    )
    if [(item["snapshot_id"], item["role"]) for item in current_only["snapshots"]] != [(103, "current")]:
        raise SystemExit(f"single-frame evidence must keep the current frame: {current_only}")

    class RecordingTemporalEngine:
        def __init__(self) -> None:
            self.track_id = None

        def evidence_bundle(self, camera_id, *, event_type, track_id=None, limit=3, max_age_seconds=None):
            self.track_id = track_id
            return {"snapshots": []}

    worker = EdgeWorker(None, None, None, None)
    recorder = RecordingTemporalEngine()
    worker.temporal_engine = recorder
    worker._attach_temporal_evidence(12, {
        "poses": [
            {"track_id": "lower-risk", "fall_score": 0.18},
            {"track_id": "event-target", "fall_score": 0.24},
        ],
        "pose_factor_graph": {},
    })
    if recorder.track_id != "event-target":
        raise SystemExit(f"dynamic event evidence must follow the highest-risk pose track: {recorder.track_id}")
    dynamic_evidence_track = recorder.track_id
    worker._attach_temporal_evidence(12, {
        "poses": [{"track_id": "near-fire", "fall_score": 0.24}],
        "pose_factor_graph": {},
        "fire_event_candidate": True,
    })
    if recorder.track_id is not None:
        raise SystemExit(f"fire evidence must remain scene-wide instead of following a person: {recorder.track_id}")

    engine.reset_camera(1)
    if engine.recent_history(1):
        raise SystemExit("camera reset must clear temporal history")

    # Observation-centric motion must preserve identities while two people cross.
    crossing = TemporalObservationEngine(history_size=16, track_ttl_seconds=10)
    crossing_frames = [
        ([50, 50, 150, 330], [480, 50, 580, 330]),
        ([140, 50, 240, 330], [390, 50, 490, 330]),
        ([250, 50, 350, 330], [280, 50, 380, 330]),
        ([360, 50, 460, 330], [170, 50, 270, 330]),
    ]
    first_crossing = analysis(
        person(crossing_frames[0][0], 0.95),
        person(crossing_frames[0][1], 0.90),
    )
    crossing.update(7, first_crossing, monotonic_at=1.0)
    left_track = str(first_crossing["people"][0]["track_id"])
    right_track = str(first_crossing["people"][1]["track_id"])
    for frame_index, (left_bbox, right_bbox) in enumerate(crossing_frames[1:], start=2):
        payload = analysis(person(left_bbox, 0.95), person(right_bbox, 0.90))
        crossing.update(7, payload, monotonic_at=float(frame_index))
        assert_track(payload, 0, left_track, "left-to-right person changed identity during crossing")
        assert_track(payload, 1, right_track, "right-to-left person changed identity during crossing")

    # A short detector miss may be bridged, but the bridge remains model-to-model identity only.
    occlusion = TemporalObservationEngine(history_size=12, track_ttl_seconds=10)
    before = analysis(person([80, 50, 180, 330]))
    occlusion.update(8, before, monotonic_at=1.0)
    occluded_track = str(before["people"][0]["track_id"])
    moving = analysis(person([130, 50, 230, 330]))
    occlusion.update(8, moving, monotonic_at=1.5)
    occlusion.update(8, analysis(), monotonic_at=2.0)
    restored = analysis(person([230, 50, 330, 330]))
    occlusion.update(8, restored, monotonic_at=2.5)
    assert_track(restored, 0, occluded_track, "short occlusion must restore the same model track")

    # A partially occluded floor-lying person may return with a much larger box.
    lying_occlusion = TemporalObservationEngine(history_size=12, track_ttl_seconds=10)
    lying_before = analysis(person([396.0, 185.6, 458.1, 259.3], posture="lying"))
    lying_occlusion.update(18, lying_before, monotonic_at=1.0)
    lying_track = str(lying_before["people"][0]["track_id"])
    lying_occlusion.update(18, analysis(), monotonic_at=1.8)
    lying_restored = analysis(person([323.8, 189.1, 465.1, 316.7], posture="lying"))
    lying_occlusion.update(18, lying_restored, monotonic_at=2.58)
    assert_track(
        lying_restored,
        0,
        lying_track,
        "short floor-lying occlusion with box expansion must preserve identity",
    )

    # A fast upright-to-low movement can travel farther than the old fixed center gate.
    fast_move = TemporalObservationEngine(history_size=12, track_ttl_seconds=10)
    upright = analysis(person([80, 40, 180, 330], posture="standing"))
    fast_move.update(9, upright, monotonic_at=1.0)
    fast_track = str(upright["people"][0]["track_id"])
    low = analysis(person([140, 190, 390, 345], posture="lying"))
    fast_move.update(9, low, monotonic_at=1.35)
    assert_track(low, 0, fast_track, "fast posture transition must not create a new track")

    # A body rotation can contract the observed box against the prior velocity
    # while still overlapping the same person clearly.
    rotating = TemporalObservationEngine(history_size=16, track_ttl_seconds=10)
    rotation_frames = [
        (1.00, [342.4, 137.5, 437.4, 282.9], "sitting"),
        (1.34, [339.2, 167.4, 431.4, 283.0], "sitting"),
        (1.55, [352.2, 166.8, 432.6, 276.8], "sitting"),
        (1.77, [343.9, 167.1, 433.2, 287.4], "squatting"),
        (2.09, [373.0, 162.2, 450.3, 233.5], "sitting"),
    ]
    rotation_track = ""
    for index, (seconds, bbox, posture) in enumerate(rotation_frames):
        payload = analysis(person(bbox, posture=posture))
        rotating.update(24, payload, monotonic_at=seconds)
        if index == 0:
            rotation_track = str(payload["people"][0]["track_id"])
        assert_track(payload, 0, rotation_track, "body rotation must preserve the overlapping model track")

    scheduling_jitter = TemporalObservationEngine(history_size=8, track_ttl_seconds=10)
    jitter_before = analysis(person([398.5, 52.1, 485.3, 307.5], posture="standing"))
    scheduling_jitter.update(25, jitter_before, monotonic_at=1.0)
    jitter_track = str(jitter_before["people"][0]["track_id"])
    jitter_after = analysis(person([342.4, 137.5, 437.4, 282.9], posture="sitting"))
    scheduling_jitter.update(25, jitter_after, monotonic_at=3.01)
    assert_track(
        jitter_after,
        0,
        jitter_track,
        "normal inference scheduling jitter must not split a continuous person track",
    )

    # A detector box and its pose-refined box describe one person even when
    # their overlap is below the old duplicate-suppression threshold.
    pose_box_shift = TemporalObservationEngine(history_size=12, track_ttl_seconds=10)
    before_shift = analysis(person([396.5, 71.3, 510.2, 359.0], posture="standing"))
    pose_box_shift.update(24, before_shift, monotonic_at=1.0)
    shifted_track = str(before_shift["people"][0]["track_id"])
    shifted = analysis(person([396.5, 71.3, 510.2, 359.0], posture="unknown"))
    shifted["poses"] = [{
        "bbox": [352.1, 145.9, 451.3, 332.2],
        "confidence": 0.688,
        "posture": "sitting",
        "posture_confidence": 0.7384,
    }]
    shifted_result = pose_box_shift.update(24, shifted, monotonic_at=1.4)
    if shifted_result["current_track_ids"] != [shifted_track]:
        raise SystemExit(
            "one person with a shifted pose box must produce one continuous temporal track"
        )
    if shifted["poses"][0].get("track_id") != shifted_track:
        raise SystemExit("matched pose must inherit the detector person's track identity")
    shifted_low = analysis(person([367.0, 196.6, 454.2, 293.9], posture="unknown"))
    shifted_low["poses"] = [{
        "bbox": [367.0, 196.6, 454.2, 293.9],
        "confidence": 0.5902,
        "posture": "squatting",
        "posture_confidence": 0.6959,
    }]
    pose_box_shift.update(24, shifted_low, monotonic_at=2.7)
    if shifted_low["people"][0].get("track_id") != shifted_track:
        raise SystemExit("sitting-to-squatting box deformation must preserve the same identity")

    # A new person after a long absence must never inherit the previous safety history.
    replacement = TemporalObservationEngine(
        history_size=12,
        track_ttl_seconds=10,
        max_match_age_seconds=2.0,
    )
    original = analysis(person([120, 50, 220, 330]))
    replacement.update(10, original, monotonic_at=1.0)
    original_track = str(original["people"][0]["track_id"])
    replacement.update(10, analysis(), monotonic_at=3.1)
    newcomer = analysis(person([122, 52, 222, 332]))
    replacement.update(10, newcomer, monotonic_at=3.2)
    newcomer_track = str(newcomer["people"][0]["track_id"])
    if newcomer_track == original_track:
        raise SystemExit("a replacement person must not inherit an expired model track")

    # Camera-local state is a hard safety boundary.
    other_camera = analysis(person([120, 50, 220, 330]))
    replacement.update(11, other_camera, monotonic_at=3.2)
    if not str(other_camera["people"][0].get("track_id") or "").startswith("c11-"):
        raise SystemExit("track identity must remain isolated per camera")

    print(json.dumps({
        "ok": True,
        "stable_track_id": track_id,
        "crossing_tracks": [left_track, right_track],
        "occlusion_track": occluded_track,
        "lying_occlusion_track": lying_track,
        "fast_transition_track": fast_track,
        "body_rotation_track": rotation_track,
        "scheduling_jitter_track": jitter_track,
        "shifted_pose_box_track": shifted_track,
        "replacement_track": newcomer_track,
        "history_capacity": 8,
        "recent_evidence_snapshot_ids": [2, 3, 4],
        "role_aware_evidence": role_sequence,
        "dynamic_evidence_track": dynamic_evidence_track,
        "weak_presence_first_state": weak_first.get("presence_persistence_state"),
        "weak_presence_second_state": weak_second.get("presence_persistence_state"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
