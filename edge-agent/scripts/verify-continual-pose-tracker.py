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
        max_display_age_seconds=0.6,
        minimum_interval_seconds=0.05,
        tracking_scale=0.5,
        min_tracked_points=6,
        monotonic_clock=lambda: clock["now"],
    )
    frame, pose = synthetic_anchor()
    clock["now"] = 99.9
    empty = tracker.update_frame(
        25,
        frame,
        frame_id="25-1",
        captured_at="2026-07-17T01:59:59+00:00",
    )
    if empty["state"] != "empty" or empty["reason"] != "no_anchor":
        raise SystemExit("person-free source frames did not enter the synchronized display stream")
    synchronized_empty = tracker.latest_synchronized_frame(25)
    if synchronized_empty is None or synchronized_empty["tracking"]["frame_id"] != "25-1":
        raise SystemExit("person-free synchronized display dropped the current source frame")
    clock["now"] = 99.91
    tracker.update_frame(
        25,
        frame,
        frame_id="25-1",
        captured_at="2026-07-17T01:59:59+00:00",
    )
    if len(tracker._display_updates.get(25) or ()) != 1:
        raise SystemExit("display FPS counted the same frame more than once")
    same_frame_model = tracker.observe(
        25,
        frame,
        frame_id="25-1",
        captured_at="2026-07-17T01:59:59+00:00",
        poses=[pose],
        source_key="camera-25:g1",
    )
    if (
        same_frame_model.get("state") != "observed"
        or not same_frame_model.get("display_published")
        or tracker.status([25])["cameras"][0].get("late_anchor_count") != 0
        or len(tracker._display_updates.get(25) or ()) != 1
    ):
        raise SystemExit("same-frame model result was incorrectly treated as a late anchor")

    rate_clock = {"now": 600.2}
    rate_tracker = ContinualPoseTracker(monotonic_clock=lambda: rate_clock["now"])
    rate_tracker.update_frame(
        28,
        frame,
        frame_id="28-1",
        captured_at="2026-07-17T02:00:00+00:00",
        captured_monotonic=600.0,
    )
    rate_clock["now"] = 600.21
    rate_tracker.update_frame(
        28,
        frame,
        frame_id="28-2",
        captured_at="2026-07-17T02:00:00.100000+00:00",
        captured_monotonic=600.1,
    )
    source_timed_rate = rate_tracker.status([28])["cameras"][0]["display_output_fps"]
    if abs(float(source_timed_rate) - 10.0) > 0.01:
        raise SystemExit(
            "display FPS used compressed processing time instead of source-frame time: "
            f"{source_timed_rate}"
        )
    rate_clock["now"] = 600.22
    late_frame = rate_tracker.update_frame(
        28,
        frame,
        frame_id="28-late",
        captured_at="2026-07-17T02:00:00.050000+00:00",
        captured_monotonic=600.05,
    )
    rate_runtime = rate_tracker.status([28])["cameras"][0]
    if late_frame.get("frame_id") != "28-2" or rate_runtime.get("late_frame_drop_count") != 1:
        raise SystemExit(f"late source frame replaced the current display frame: {late_frame}, {rate_runtime}")

    ordering_clock = {"now": 700.2}
    ordering_tracker = ContinualPoseTracker(monotonic_clock=lambda: ordering_clock["now"])
    current_ordering_frame = translate(frame, dx=4, dy=2)
    ordering_tracker.update_frame(
        29,
        current_ordering_frame,
        frame_id="29-300",
        captured_at="2026-07-17T02:00:00.200000+00:00",
        captured_monotonic=700.2,
        source_key="camera-29:g1",
    )
    ordering_clock["now"] = 700.25
    late_anchor = ordering_tracker.observe(
        29,
        frame,
        frame_id="29-299",
        captured_at="2026-07-17T02:00:00.100000+00:00",
        captured_monotonic=700.1,
        poses=[pose],
        source_key="camera-29:g1",
    )
    if (
        not late_anchor.get("display_published")
        or late_anchor.get("frame_id") != "29-300"
        or late_anchor.get("reason") != "late_anchor_rebased"
        or (late_anchor.get("poses") or [{}])[0].get("tracking_source") != "model_anchor_rebased"
    ):
        raise SystemExit(f"late model anchor was not rebased onto the current display frame: {late_anchor}")
    rebased_frame = ordering_tracker.latest_frame(29)
    if rebased_frame is None or not np.array_equal(rebased_frame["frame"], current_ordering_frame):
        raise SystemExit("rebased model anchor replaced the current display pixels")
    if not ordering_tracker.has_anchor(29):
        raise SystemExit("late model result was not retained as a tracking anchor")
    ordering_clock["now"] = 700.31
    ordered_track = ordering_tracker.update_frame(
        29,
        translate(frame, dx=5, dy=3),
        frame_id="29-301",
        captured_at="2026-07-17T02:00:00.300000+00:00",
        captured_monotonic=700.3,
        source_key="camera-29:g1",
    )
    if ordered_track.get("frame_id") != "29-301" or not ordered_track.get("display_published"):
        raise SystemExit(f"late anchor did not resume on the next current source frame: {ordered_track}")

    empty_rebase_clock = {"now": 800.0}
    empty_rebase_tracker = ContinualPoseTracker(monotonic_clock=lambda: empty_rebase_clock["now"])
    empty_rebase_tracker.observe(
        30,
        frame,
        frame_id="30-100",
        captured_at="2026-07-17T02:00:00+00:00",
        captured_monotonic=800.0,
        poses=[pose],
        source_key="camera-30:g1",
    )
    empty_rebase_clock["now"] = 800.1
    current_empty_frame = translate(frame, dx=3, dy=1)
    empty_rebase_tracker.update_frame(
        30,
        current_empty_frame,
        frame_id="30-101",
        captured_at="2026-07-17T02:00:00.100000+00:00",
        captured_monotonic=800.1,
        source_key="camera-30:g1",
    )
    empty_rebase_clock["now"] = 800.15
    rebased_empty = empty_rebase_tracker.observe(
        30,
        np.zeros_like(frame),
        frame_id="30-model-empty",
        captured_at="2026-07-17T02:00:00.050000+00:00",
        captured_monotonic=800.05,
        poses=[],
        context={"pose_model_status": "ready", "people": []},
        source_key="camera-30:g1",
    )
    if (
        rebased_empty.get("state") != "empty"
        or rebased_empty.get("frame_id") != "30-101"
        or rebased_empty.get("reason") != "no_observed_pose"
        or empty_rebase_tracker.has_anchor(30)
    ):
        raise SystemExit(f"late authoritative empty result did not clear the current pose: {rebased_empty}")
    synchronized_rebased_empty = empty_rebase_tracker.latest_synchronized_frame(30)
    if synchronized_rebased_empty is None or not np.array_equal(
        synchronized_rebased_empty["frame"], current_empty_frame
    ):
        raise SystemExit("late authoritative empty result replaced the current display pixels")

    rejected_late_tracker = ContinualPoseTracker(monotonic_clock=lambda: empty_rebase_clock["now"])
    rejected_late_tracker.update_frame(
        31,
        current_empty_frame,
        frame_id="31-200",
        captured_at="2026-07-17T02:00:00.200000+00:00",
        captured_monotonic=800.2,
        source_key="camera-31:g2",
    )
    empty_rebase_clock["now"] = 800.25
    rejected_cross_source = rejected_late_tracker.observe(
        31,
        frame,
        frame_id="31-old-source",
        captured_at="2026-07-17T02:00:00.100000+00:00",
        captured_monotonic=800.1,
        poses=[pose],
        source_key="camera-31:g1",
    )
    rejected_runtime = rejected_late_tracker.status([31])["cameras"][0]
    if (
        rejected_cross_source.get("display_published")
        or rejected_late_tracker.latest(31).get("frame_id") != "31-200"
        or rejected_late_tracker.has_anchor(31)
        or rejected_runtime.get("late_model_source_rejection_count") != 1
    ):
        raise SystemExit("cross-source late model result changed current display state")
    clock["now"] = 100.0
    observed = tracker.observe(
        24,
        frame,
        frame_id="24-100",
        captured_at="2026-07-17T02:00:00+00:00",
        poses=[pose],
        context={
            "detector_backend": "yolo",
            "pose_model_status": "ready",
            "scene_zones": [{"id": "sofa-1", "label": "couch", "bbox": [0, 120, 250, 230]}],
            "algorithm_results": {"pose": {"data": {"poses": [pose]}}},
            "temporal_evidence_bundle": {"snapshots": list(range(50))},
        },
    )
    if observed["state"] != "observed" or observed["pose_count"] != 1:
        raise SystemExit("fresh model anchor was not recorded as observed")
    if not tracker.has_anchor(24):
        raise SystemExit("fresh observed pose did not open the short tracking window")
    observed_frame = tracker.latest_frame(24)
    if observed_frame is None or observed_frame["tracking"]["frame_id"] != "24-100":
        raise SystemExit("observed pose did not retain its exact color frame")
    if not np.array_equal(observed_frame["frame"], frame):
        raise SystemExit("observed pose frame pixels do not match its frame_id")
    if observed_frame["analysis_context"].get("detector_backend") != "yolo":
        raise SystemExit("observed frame lost its matching analysis context")
    synchronized_observed = tracker.latest_synchronized_frame(24)
    if synchronized_observed is None or not np.array_equal(synchronized_observed["frame"], frame):
        raise SystemExit("privacy synchronization did not retain the observed frame")
    observed_metadata = tracker.latest_metadata(24)
    if observed_metadata.get("image_width") != 320 or observed_metadata.get("image_height") != 240:
        raise SystemExit(f"continual pose metadata lost source dimensions: {observed_metadata}")
    if "frame" in observed_metadata:
        raise SystemExit("continual pose metadata copied frame pixels")
    display_context = observed_metadata.get("analysis_context") or {}
    if not display_context.get("scene_zones") or display_context.get("algorithm_results"):
        raise SystemExit(f"continual pose metadata did not filter heavy analysis context: {display_context}")
    if display_context.get("temporal_evidence_bundle"):
        raise SystemExit("continual pose metadata exposed historical evidence bundles")

    shifted = translate(frame, dx=5, dy=3)
    clock["now"] = 100.03
    throttled = tracker.update_frame(
        24,
        shifted,
        frame_id="24-100-fast",
        captured_at="2026-07-17T02:00:00.030000+00:00",
    )
    if throttled["state"] != "observed" or throttled["frame_id"] != "24-100":
        raise SystemExit("KLT ignored its bounded processing interval")

    clock["now"] = 100.08
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
    tracked_frame = tracker.latest_frame(24)
    if tracked_frame is None or tracked_frame["tracking"]["frame_id"] != "24-101":
        raise SystemExit("tracked pose did not retain its exact color frame")
    if not np.array_equal(tracked_frame["frame"], shifted):
        raise SystemExit("tracked pose frame pixels do not match its frame_id")
    retained_anchor_metadata = tracker.metadata_for_frame(24, frame_id="24-100")
    if (
        retained_anchor_metadata is None
        or retained_anchor_metadata.get("tracking", {}).get("frame_id") != "24-100"
        or "frame" in retained_anchor_metadata
    ):
        raise SystemExit("bounded metadata history did not retain the exact earlier pose frame")
    if tracker.metadata_for_frame(24, frame_id="24-100", source_key="wrong-source") is not None:
        raise SystemExit("pose metadata history crossed source identity")
    visible = [point for point in tracked_pose.get("keypoints") or [] if point.get("visible")]
    dx = np.median([point["x"] - source["x"] for point, source in zip(visible, pose["keypoints"])])
    dy = np.median([point["y"] - source["y"] for point, source in zip(visible, pose["keypoints"])])
    if abs(float(dx) - 5.0) > 1.0 or abs(float(dy) - 3.0) > 1.0:
        raise SystemExit(f"tracked keypoints drifted from the synthetic translation: dx={dx}, dy={dy}")
    if tracked.get("risk_hint", {}).get("detected"):
        raise SystemExit("ordinary small pose motion incorrectly triggered risk scheduling")

    risk_clock = {"now": 300.0}
    risk_tracker = ContinualPoseTracker(
        max_age_seconds=0.6,
        max_display_age_seconds=1.2,
        min_tracked_points=6,
        monotonic_clock=lambda: risk_clock["now"],
    )
    risk_tracker.observe(
        26,
        frame,
        frame_id="26-100",
        captured_at="2026-07-17T02:00:00+00:00",
        poses=[pose],
    )
    risk_clock["now"] = 300.11
    downward = risk_tracker.update_frame(
        26,
        translate(frame, dx=0, dy=20),
        frame_id="26-101",
        captured_at="2026-07-17T02:00:00.110000+00:00",
    )
    risk_hint = downward.get("risk_hint") or {}
    if (
        downward.get("state") != "tracked"
        or not risk_hint.get("detected")
        or risk_hint.get("reason") != "rapid_downward_pose_motion"
    ):
        raise SystemExit(f"rapid downward KLT motion did not request risk scheduling: {downward}")
    if downward.get("formal_evidence_eligible") or risk_hint.get("formal_evidence_eligible"):
        raise SystemExit("KLT risk scheduling hint leaked into formal event evidence")
    risk_runtime = risk_tracker.status([26])["cameras"][0]
    if (
        risk_runtime.get("risk_hint_count") != 1
        or abs(float(risk_runtime.get("last_risk_hint_at_monotonic") or 0.0) - 300.11) > 0.0001
    ):
        raise SystemExit(f"KLT risk hint diagnostics are incomplete: {risk_runtime}")

    grace_clock = {"now": 200.0}
    grace_tracker = ContinualPoseTracker(
        max_age_seconds=0.6,
        max_display_age_seconds=1.2,
        min_tracked_points=6,
        monotonic_clock=lambda: grace_clock["now"],
    )
    grace_tracker.observe(24, frame, frame_id="grace-100", captured_at="2026-07-17T02:00:00+00:00", poses=[pose])
    grace_clock["now"] = 200.7
    grace = grace_tracker.update_frame(
        24,
        shifted,
        frame_id="grace-101",
        captured_at="2026-07-17T02:00:00.700000+00:00",
    )
    if grace["state"] != "tracked" or not grace.get("display_only_stale"):
        raise SystemExit("display grace did not retain a stale tracked overlay")
    if grace.get("formal_evidence_eligible") or grace["poses"][0].get("fall_evidence_eligible"):
        raise SystemExit("display grace leaked into formal evidence")
    grace_clock["now"] = 201.3
    if grace_tracker.update_frame(
        24,
        shifted,
        frame_id="grace-102",
        captured_at="2026-07-17T02:00:01.300000+00:00",
    )["state"] != "expired":
        raise SystemExit("display grace did not expire after its bounded window")

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
    if tracker.latest_frame(24) is not None:
        raise SystemExit("expired tracking window retained stale display pixels")
    if tracker.latest_synchronized_frame(24) is not None:
        raise SystemExit("expired tracking window leaked stale privacy pixels")

    empty_frame = np.full_like(frame, 57)
    tracker.observe(
        24,
        empty_frame,
        frame_id="24-empty-1",
        captured_at="2026-07-17T02:00:00.800000+00:00",
        poses=[],
        context={"pose_model_status": "ready", "people": []},
    )
    synchronized_empty = tracker.latest_synchronized_frame(24)
    if synchronized_empty is None or not np.array_equal(synchronized_empty["frame"], empty_frame):
        raise SystemExit("model-confirmed empty frame was not retained for privacy rendering")
    if synchronized_empty["tracking"].get("reason") != "no_observed_pose":
        raise SystemExit("privacy empty frame lost its model-confirmed reason")

    person_without_pose = tracker.observe(
        27,
        empty_frame,
        frame_id="27-person-1",
        captured_at="2026-07-17T02:00:00.900000+00:00",
        poses=[],
        context={"pose_model_status": "not_visible", "people": [{"bbox": [80, 30, 180, 220]}]},
        person_present=True,
        source_key="camera-27:g1",
    )
    if person_without_pose.get("state") != "untracked":
        raise SystemExit(f"person without a complete pose was incorrectly marked empty: {person_without_pose}")
    synchronized_untracked = tracker.latest_synchronized_frame(27)
    if (
        synchronized_untracked is None
        or synchronized_untracked["tracking"].get("reason") != "person_without_trackable_pose"
        or not synchronized_untracked["analysis_context"].get("people")
    ):
        raise SystemExit("untracked person lost its privacy boxes or synchronized frame")
    untracked_metadata = tracker.latest_metadata(27)
    if untracked_metadata.get("image_width") != 320 or not untracked_metadata.get("analysis_context", {}).get("people"):
        raise SystemExit("untracked person metadata is incomplete for privacy rendering")

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
    if rejected["state"] != "coasting" or rejected.get("reason") not in {
        "insufficient_points",
        "forward_backward_error",
        "optical_flow_failed",
    }:
        raise SystemExit(f"invalid optical flow did not enter bounded display coasting: {rejected}")
    rejected_pose = (rejected.get("poses") or [{}])[0]
    if (
        rejected.get("formal_evidence_eligible")
        or rejected_pose.get("fall_evidence_eligible")
        or rejected_pose.get("person_evidence_eligible")
        or rejected_pose.get("tracking_state") != "coasting"
        or rejected_pose.get("tracking_source") != "last_good_overlay"
    ):
        raise SystemExit(f"coasting pose leaked into formal evidence: {rejected}")
    clock["now"] = 102.3
    coast_expired = tracker.update_frame(
        24,
        np.zeros_like(frame),
        frame_id="24-202",
        captured_at="2026-07-17T02:00:02.300000+00:00",
    )
    if coast_expired["state"] != "expired" or coast_expired.get("reason") != "anchor_expired":
        raise SystemExit(f"bounded coasting did not expire: {coast_expired}")

    runtime = tracker.status([24, 25])
    if runtime.get("tracking_scale") != 0.5:
        raise SystemExit(f"continual pose runtime did not expose reduced-resolution tracking: {runtime}")
    camera_24_runtime = next(item for item in runtime["cameras"] if item["camera_id"] == 24)
    if camera_24_runtime["observed_count"] != 2 or camera_24_runtime["tracked_count"] < 1:
        raise SystemExit(f"continual pose runtime counters are incomplete: {runtime}")
    if camera_24_runtime["coasting_count"] < 1 or camera_24_runtime["expired_count"] < 2:
        raise SystemExit(f"continual pose expiry metrics are incomplete: {runtime}")

    tracker.reset_camera(25)
    if tracker.latest(25)["state"] != "empty":
        raise SystemExit("camera reset did not clear continual pose state")
    if tracker.metadata_for_frame(25, frame_id="25-100") is not None:
        raise SystemExit("camera reset retained pose metadata history")

    worker_source = (ROOT / "app" / "worker.py").read_text(encoding="utf-8")
    for contract in ("ContinualPoseTracker()", "_run_continual_tracking", "latest_cached_frame"):
        if contract not in worker_source:
            raise SystemExit(f"production continual pose loop is missing: {contract}")
    deploy_source = (ROOT / "scripts" / "deploy-to-pi.sh").read_text(encoding="utf-8")
    if (
        "--include '/scripts/verify-vision-runtime.py'" not in deploy_source
        or "--exclude '/scripts/verify-*.py'" not in deploy_source
    ):
        raise SystemExit("production deployment does not enforce the single runtime-check whitelist")

    print({
        "ok": True,
        "translation": [round(float(dx), 2), round(float(dy), 2)],
        "tracked_points": tracked["quality"]["tracked_point_count"],
        "risk_hint": risk_hint,
        "display_grace_stale_tracked": True,
        "bounded_display_coasting": True,
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
