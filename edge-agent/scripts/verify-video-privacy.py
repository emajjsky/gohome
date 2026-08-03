#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import time
from unittest.mock import patch

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.camera_agent import _load_cv2
from app.vision.privacy_background import PrivacyBackgroundReconstructor, PrivacyCalibrationRequired
from app.vision.privacy_stream import PrivacyFrameRenderer


PERSON_BOX = [110, 25, 210, 175]
PERSON_SLICE = np.s_[25:176, 110:211]
OUTSIDE_SLICE = np.s_[35:145, 5:75]


def metadata(*, camera_id: int, person: bool, frame_id: str, source_key: str) -> dict:
    poses = []
    people = []
    state = "empty"
    if person:
        state = "observed"
        poses = [{
            "bbox": PERSON_BOX,
            "keypoints": [
                {"name": "nose", "x": 160, "y": 42, "confidence": 0.95, "visible": True},
                {"name": "left_shoulder", "x": 135, "y": 65, "confidence": 0.95, "visible": True},
                {"name": "right_shoulder", "x": 185, "y": 65, "confidence": 0.95, "visible": True},
                {"name": "left_hip", "x": 145, "y": 115, "confidence": 0.95, "visible": True},
                {"name": "right_hip", "x": 175, "y": 115, "confidence": 0.95, "visible": True},
                {"name": "left_knee", "x": 145, "y": 145, "confidence": 0.95, "visible": True},
                {"name": "right_knee", "x": 175, "y": 145, "confidence": 0.95, "visible": True},
            ],
        }]
        people = [{"bbox": PERSON_BOX, "confidence": 0.95}]
    return {
        "image_width": 320,
        "image_height": 180,
        "tracking": {
            "camera_id": camera_id,
            "state": state,
            "frame_id": frame_id,
            "source_key": source_key,
            "captured_monotonic": time.monotonic(),
            "poses": poses,
        },
        "analysis_context": {"people": people},
    }


class MutableTracker:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def latest_metadata(self, _camera_id: int) -> dict:
        return self.payload


class SyntheticSegmentation:
    def __init__(self, backgrounds: dict[str, np.ndarray]) -> None:
        self.backgrounds = {key: value.copy() for key, value in backgrounds.items()}

    def segment(
        self,
        camera_id,
        frame,
        *,
        frame_id,
        source_key,
        captured_monotonic=None,
        person_evidence=False,
    ):
        del captured_monotonic
        configured_source = str(source_key).split(":g", 1)[0]
        background = self.backgrounds.get(configured_source)
        if not person_evidence or background is None or background.shape != frame.shape:
            mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        else:
            delta = np.max(np.abs(frame.astype(np.int16) - background.astype(np.int16)), axis=2)
            mask = np.where(delta >= 24, 255, 0).astype(np.uint8)
        return {
            "camera_id": int(camera_id),
            "frame_id": str(frame_id),
            "source_key": str(source_key),
            "mask": mask,
        }

    def reset_camera(self, _camera_id):
        return None

    def status(self):
        return {"schema_version": "synthetic-segmentation", "status": "ready"}


def scene(seed: int) -> np.ndarray:
    frame = np.zeros((180, 320, 3), dtype=np.uint8)
    for x in range(320):
        frame[:, x] = (
            18 + (x * (seed + 1)) % 105,
            42 + (x * (seed + 3)) % 130,
            65 + (x * (seed + 5)) % 150,
        )
    cv2 = _load_cv2()
    cv2.line(frame, (0, 35 + seed), (319, 145 - seed), (210, 70, 30), 7)
    cv2.rectangle(frame, (8, 58), (72, 128), (30 + seed * 8, 190, 60), -1)
    return frame


def occupied_scene(cv2, clean: np.ndarray) -> np.ndarray:
    frame = clean.copy()
    cv2.rectangle(frame, (110, 25), (210, 175), (244, 244, 244), -1)
    cv2.line(frame, (118, 34), (202, 168), (18, 18, 18), 12)
    return frame


def decode(cv2, payload: bytes) -> np.ndarray:
    frame = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert frame is not None and frame.size
    return frame


def mean_delta(first: np.ndarray, second: np.ndarray, region=...) -> float:
    if region is not ...:
        first = first[region]
        second = second[region]
    return float(np.abs(first.astype(np.float32) - second.astype(np.float32)).mean())


def render(
    renderer: PrivacyFrameRenderer,
    tracker: MutableTracker,
    frame: np.ndarray,
    *,
    camera_id: int,
    source_key: str,
    frame_id: str,
    person: bool,
    mode: str,
) -> np.ndarray:
    captured_monotonic = time.monotonic()
    tracker.payload = metadata(
        camera_id=camera_id,
        person=person,
        frame_id=frame_id,
        source_key=source_key,
    )
    tracker.payload["tracking"]["captured_monotonic"] = captured_monotonic
    return decode(_load_cv2(), renderer.render_frame(
        camera_id,
        frame,
        mode,
        quality=90,
        source_key=source_key,
        frame_id=frame_id,
        captured_monotonic=captured_monotonic,
    ))


def calibrate(
    renderer: PrivacyFrameRenderer,
    tracker: MutableTracker,
    clean: np.ndarray,
    *,
    camera_id: int,
    source_key: str,
) -> dict:
    height, width = clean.shape[:2]
    renderer.begin_calibration(
        camera_id,
        source_key=source_key,
        width=width,
        height=height,
        calibration_id=f"test-{camera_id}",
    )
    result = {}
    for sequence in range(renderer.background_reconstructor.confirmation_frames):
        frame_id = f"{camera_id}-calibration-{sequence}"
        captured_monotonic = time.monotonic()
        tracker.payload = metadata(
            camera_id=camera_id,
            person=False,
            frame_id=frame_id,
            source_key=source_key,
        )
        tracker.payload["tracking"]["captured_monotonic"] = captured_monotonic
        result = renderer.observe_calibration_frame(
            camera_id,
            clean,
            source_key=source_key,
            frame_id=frame_id,
            captured_monotonic=captured_monotonic,
        )
    assert result["ready"] is True
    return result


def assert_calibration_required(callable_value, expected_reason: str | None = None) -> None:
    try:
        callable_value()
    except PrivacyCalibrationRequired as exc:
        if expected_reason is not None:
            assert exc.reason == expected_reason
        return
    raise AssertionError("skeleton rendering must require a valid calibration")


def main() -> int:
    cv2 = _load_cv2()
    clean_a = scene(1)
    clean_b = scene(7)
    occupied_a = occupied_scene(cv2, clean_a)
    source_a_g1 = "camera-a:g1"
    source_a_g2 = "camera-a:g2"
    source_b_g1 = "camera-b:g1"

    with TemporaryDirectory() as temporary_dir:
        tracker = MutableTracker(metadata(
            camera_id=1,
            person=True,
            frame_id="1-person-0",
            source_key=source_a_g1,
        ))
        renderer = PrivacyFrameRenderer(
            tracker,
            PrivacyBackgroundReconstructor(storage_dir=temporary_dir),
            SyntheticSegmentation({"camera-a": clean_a, "camera-b": clean_b}),
        )

        original = render(
            renderer,
            tracker,
            occupied_a,
            camera_id=1,
            source_key=source_a_g1,
            frame_id="1-original",
            person=True,
            mode="original",
        )
        blurred = render(
            renderer,
            tracker,
            occupied_a,
            camera_id=1,
            source_key=source_a_g1,
            frame_id="1-blur",
            person=True,
            mode="person_blur",
        )
        assert mean_delta(original, occupied_a) < 8.0
        assert mean_delta(blurred, occupied_a, PERSON_SLICE) > 18.0
        assert mean_delta(blurred, occupied_a, OUTSIDE_SLICE) < 8.0

        assert_calibration_required(lambda: render(
            renderer,
            tracker,
            occupied_a,
            camera_id=1,
            source_key=source_a_g1,
            frame_id="1-before-calibration",
            person=True,
            mode="skeleton",
        ))

        calibration = calibrate(
            renderer,
            tracker,
            clean_a,
            camera_id=1,
            source_key=source_a_g1,
        )
        assert calibration["calibration_observations"] == renderer.background_reconstructor.confirmation_frames

        started = time.perf_counter()
        skeleton = render(
            renderer,
            tracker,
            occupied_a,
            camera_id=1,
            source_key=source_a_g1,
            frame_id="1-pure-skeleton",
            person=True,
            mode="skeleton",
        )
        render_ms = (time.perf_counter() - started) * 1000.0
        assert mean_delta(skeleton, occupied_a, PERSON_SLICE) > 24.0
        assert mean_delta(skeleton, clean_a, PERSON_SLICE) < mean_delta(blurred, clean_a, PERSON_SLICE)
        assert mean_delta(skeleton, occupied_a, OUTSIDE_SLICE) < 8.0
        assert mean_delta(skeleton, blurred, PERSON_SLICE) > 8.0
        assert render_ms < 80.0

        stale_monotonic = time.monotonic()
        tracker.payload = metadata(
            camera_id=1,
            person=True,
            frame_id="1-stale-coasting",
            source_key=source_a_g1,
        )
        tracker.payload["tracking"]["state"] = "coasting"
        tracker.payload["tracking"]["display_only_stale"] = True
        tracker.payload["tracking"]["captured_monotonic"] = stale_monotonic
        stale_skeleton = decode(cv2, renderer.render_frame(
            1,
            occupied_a,
            "skeleton",
            quality=90,
            source_key=source_a_g1,
            frame_id="1-stale-coasting",
            captured_monotonic=stale_monotonic,
        ))
        assert mean_delta(stale_skeleton, clean_a, PERSON_SLICE) < 8.0

        current_monotonic = time.monotonic()
        tracker.payload = metadata(
            camera_id=1,
            person=True,
            frame_id="1-adjacent-pose",
            source_key=source_a_g1,
        )
        tracker.payload["tracking"]["captured_monotonic"] = current_monotonic + 0.01
        stale_pose_frame = decode(cv2, renderer.render_frame(
            1,
            occupied_a,
            "skeleton",
            quality=90,
            source_key=source_a_g1,
            frame_id="1-current-with-adjacent-pose",
            captured_monotonic=current_monotonic,
        ))
        assert mean_delta(stale_pose_frame, clean_a) < 8.0
        synchronization = renderer.status()["synchronization_rejections"]["1"]
        assert synchronization["reasons"]["pose_frame_superseded"] >= 1

        dropout = render(
            renderer,
            tracker,
            occupied_a,
            camera_id=1,
            source_key=source_a_g1,
            frame_id="1-single-dropout",
            person=False,
            mode="skeleton",
        )
        assert mean_delta(dropout, occupied_a, PERSON_SLICE) > 18.0

        for sequence in range(renderer.background_reconstructor.revalidation_frames - 1):
            assert_calibration_required(lambda sequence=sequence: render(
                renderer,
                tracker,
                clean_a,
                camera_id=1,
                source_key=source_a_g2,
                frame_id=f"1-revalidate-{sequence}",
                person=False,
                mode="skeleton",
            ), "stream_revalidation_required")
        revalidated = render(
            renderer,
            tracker,
            clean_a,
            camera_id=1,
            source_key=source_a_g2,
            frame_id="1-revalidate-complete",
            person=False,
            mode="skeleton",
        )
        assert mean_delta(revalidated, clean_a) < 8.0
        generation_two = render(
            renderer,
            tracker,
            occupied_a,
            camera_id=1,
            source_key=source_a_g2,
            frame_id="1-generation-two-person",
            person=True,
            mode="skeleton",
        )
        assert mean_delta(generation_two, occupied_a, PERSON_SLICE) > 24.0

        tracker_b = MutableTracker(metadata(
            camera_id=2,
            person=True,
            frame_id="2-person-0",
            source_key=source_b_g1,
        ))
        renderer_b = PrivacyFrameRenderer(
            tracker_b,
            PrivacyBackgroundReconstructor(storage_dir=temporary_dir),
            SyntheticSegmentation({"camera-a": clean_a, "camera-b": clean_b}),
        )
        assert_calibration_required(lambda: render(
            renderer_b,
            tracker_b,
            occupied_scene(cv2, clean_b),
            camera_id=2,
            source_key=source_b_g1,
            frame_id="2-isolation",
            person=True,
            mode="skeleton",
        ))

        persisted = PrivacyFrameRenderer(
            tracker,
            PrivacyBackgroundReconstructor(storage_dir=temporary_dir),
            SyntheticSegmentation({"camera-a": clean_a}),
        )
        for sequence in range(persisted.background_reconstructor.revalidation_frames - 1):
            assert_calibration_required(lambda sequence=sequence: render(
                persisted,
                tracker,
                clean_a,
                camera_id=1,
                source_key=source_a_g1,
                frame_id=f"1-persisted-revalidate-{sequence}",
                person=False,
                mode="skeleton",
            ), "stream_revalidation_required")
        render(
            persisted,
            tracker,
            clean_a,
            camera_id=1,
            source_key=source_a_g1,
            frame_id="1-persisted-revalidate-complete",
            person=False,
            mode="skeleton",
        )
        persisted_skeleton = render(
            persisted,
            tracker,
            occupied_a,
            camera_id=1,
            source_key=source_a_g1,
            frame_id="1-persisted-person",
            person=True,
            mode="skeleton",
        )
        assert mean_delta(persisted_skeleton, occupied_a, PERSON_SLICE) > 24.0

        local_change = clean_a.copy()
        cv2.rectangle(local_change, (235, 28), (312, 92), (245, 230, 45), -1)
        local_change_render = render(
            persisted,
            tracker,
            local_change,
            camera_id=1,
            source_key=source_a_g1,
            frame_id="1-local-tv-change",
            person=False,
            mode="skeleton",
        )
        assert mean_delta(local_change_render, local_change) < 8.0
        assert persisted.background_reconstructor.status()["states"][0]["baseline_retained"] is True

        lighting_change = np.clip(clean_a.astype(np.int16) + np.asarray([18, 12, 22]), 0, 255).astype(np.uint8)
        lighting_render = render(
            persisted,
            tracker,
            lighting_change,
            camera_id=1,
            source_key=source_a_g1,
            frame_id="1-lighting-change",
            person=False,
            mode="skeleton",
        )
        assert mean_delta(lighting_render, lighting_change) < 12.0

        moved_scene = np.roll(clean_a, 52, axis=1)
        assert_calibration_required(lambda: render(
            persisted,
            tracker,
            moved_scene,
            camera_id=1,
            source_key=source_a_g1,
            frame_id="1-moved-scene",
            person=False,
            mode="skeleton",
        ), "scene_revalidation_required")
        assert_calibration_required(lambda: render(
            persisted,
            tracker,
            moved_scene,
            camera_id=1,
            source_key=source_a_g1,
            frame_id="1-moved-scene-repeat",
            person=False,
            mode="skeleton",
        ), "scene_revalidation_required")
        moved_status = persisted.background_reconstructor.status()["states"][0]
        assert moved_status["ready"] is False
        assert moved_status["calibrated"] is True
        assert moved_status["baseline_retained"] is True
        assert moved_status["scene_status"] == "scene_review_required"
        retained_baseline_sha256 = moved_status["baseline_sha256"]
        assert len(retained_baseline_sha256) == 64
        assert list(Path(temporary_dir).glob("camera-1-*.npz"))

        restarted_after_move = PrivacyFrameRenderer(
            tracker,
            PrivacyBackgroundReconstructor(storage_dir=temporary_dir),
            SyntheticSegmentation({"camera-a": clean_a}),
        )
        for sequence in range(restarted_after_move.background_reconstructor.revalidation_frames - 1):
            assert_calibration_required(lambda sequence=sequence: render(
                restarted_after_move,
                tracker,
                clean_a,
                camera_id=1,
                source_key=source_a_g1,
                frame_id=f"1-restart-revalidate-{sequence}",
                person=False,
                mode="skeleton",
            ), "stream_revalidation_required")
        render(
            restarted_after_move,
            tracker,
            clean_a,
            camera_id=1,
            source_key=source_a_g1,
            frame_id="1-restart-revalidate-complete",
            person=False,
            mode="skeleton",
        )
        assert restarted_after_move.background_reconstructor.status()["states"][0]["baseline_sha256"] == retained_baseline_sha256

        restarted_after_move.begin_calibration(
            1,
            source_key=source_a_g1,
            width=320,
            height=180,
            calibration_id="failed-recalibration",
        )
        assert_calibration_required(lambda: restarted_after_move.begin_calibration(
            1,
            source_key=source_a_g1,
            width=320,
            height=180,
            calibration_id="concurrent-recalibration",
        ), "calibration_in_progress")
        tracker.payload = metadata(
            camera_id=1,
            person=True,
            frame_id="1-failed-recalibration-person",
            source_key=source_a_g1,
        )
        failed_recalibration = restarted_after_move.observe_calibration_frame(
            1,
            occupied_a,
            source_key=source_a_g1,
            frame_id="1-failed-recalibration-person",
            captured_monotonic=tracker.payload["tracking"]["captured_monotonic"],
        )
        assert failed_recalibration["last_error"] == "person_present"
        cancelled = restarted_after_move.cancel_calibration(
            1,
            source_key=source_a_g1,
            width=320,
            height=180,
            reason="person_present",
        )
        assert cancelled["calibration_active"] is False
        assert cancelled["calibrated"] is True
        assert cancelled["baseline_retained"] is True
        assert cancelled["baseline_sha256"] == retained_baseline_sha256

        restarted_after_move.segmentation_backend.backgrounds["camera-a"] = moved_scene.copy()
        recalibrated = calibrate(
            restarted_after_move,
            tracker,
            moved_scene,
            camera_id=1,
            source_key=source_a_g1,
        )
        assert recalibrated["baseline_revision"] >= 2
        assert recalibrated["baseline_sha256"] != retained_baseline_sha256
        occupied_moved = occupied_scene(cv2, moved_scene)
        replaced_baseline = render(
            restarted_after_move,
            tracker,
            occupied_moved,
            camera_id=1,
            source_key=source_a_g1,
            frame_id="1-recalibrated-person",
            person=True,
            mode="skeleton",
        )
        assert mean_delta(replaced_baseline, occupied_moved, PERSON_SLICE) > 24.0

        failure_dir = Path(temporary_dir) / "persistence-failure"
        failing_background = PrivacyBackgroundReconstructor(storage_dir=failure_dir)
        failing_renderer = PrivacyFrameRenderer(
            tracker,
            failing_background,
            SyntheticSegmentation({"camera-a": clean_a}),
        )
        calibrate(
            failing_renderer,
            tracker,
            clean_a,
            camera_id=1,
            source_key=source_a_g1,
        )
        committed_revision = failing_background.status()["states"][0]["baseline_revision"]
        committed_sha256 = failing_background.status()["states"][0]["baseline_sha256"]
        failing_renderer.begin_calibration(
            1,
            source_key=source_a_g1,
            width=320,
            height=180,
            calibration_id="persistence-failure",
        )
        persistence_failed = False
        for sequence in range(failing_background.confirmation_frames):
            frame_id = f"1-persistence-failure-{sequence}"
            captured_monotonic = time.monotonic()
            tracker.payload = metadata(
                camera_id=1,
                person=False,
                frame_id=frame_id,
                source_key=source_a_g1,
            )
            tracker.payload["tracking"]["captured_monotonic"] = captured_monotonic
            try:
                if sequence == failing_background.confirmation_frames - 1:
                    with patch("app.vision.privacy_background.os.replace", side_effect=OSError("simulated persistence failure")):
                        failing_renderer.observe_calibration_frame(
                            1,
                            moved_scene,
                            source_key=source_a_g1,
                            frame_id=frame_id,
                            captured_monotonic=captured_monotonic,
                        )
                else:
                    failing_renderer.observe_calibration_frame(
                        1,
                        moved_scene,
                        source_key=source_a_g1,
                        frame_id=frame_id,
                        captured_monotonic=captured_monotonic,
                    )
            except OSError:
                persistence_failed = True
                break
        assert persistence_failed is True
        failed_commit = failing_renderer.cancel_calibration(
            1,
            source_key=source_a_g1,
            width=320,
            height=180,
            reason="persistence_failed",
        )
        assert failed_commit["baseline_revision"] == committed_revision
        assert failed_commit["baseline_retained"] is True
        assert failed_commit["baseline_sha256"] == committed_sha256
        assert not list(failure_dir.glob("*.tmp"))

        rejecting = PrivacyFrameRenderer(
            tracker,
            PrivacyBackgroundReconstructor(),
            SyntheticSegmentation({"camera-a": clean_a}),
        )
        rejecting.begin_calibration(
            1,
            source_key=source_a_g1,
            width=320,
            height=180,
            calibration_id="reject-person",
        )
        tracker.payload = metadata(
            camera_id=1,
            person=True,
            frame_id="1-calibration-person",
            source_key=source_a_g1,
        )
        rejected = rejecting.observe_calibration_frame(
            1,
            occupied_a,
            source_key=source_a_g1,
            frame_id="1-calibration-person",
            captured_monotonic=tracker.payload["tracking"]["captured_monotonic"],
        )
        assert rejected["ready"] is False
        assert rejected["calibration_observations"] == 0
        assert rejected["last_error"] == "person_present"

        status = renderer.background_reconstructor.status()
        assert status["strategy"] == "explicit_empty_room_calibration"
        assert status["automatic_background_learning"] is False
        assert status["neutral_fill"] is False
        assert status["state_count"] <= status["max_states"]
        stage_metrics = renderer.status()["cameras"]["1"]["stage_latency_ms"]
        for stage in ("pose_sync_wait", "segmentation", "background_reconstruction", "skeleton_draw", "jpeg_encode", "total"):
            assert stage_metrics[stage]["samples"] > 0
            assert stage_metrics[stage]["p95"] is not None

    print({
        "ok": True,
        "skeleton_base": "calibrated_empty_room",
        "person_blur_is_separate": True,
        "explicit_calibration": True,
        "persistent_calibration": True,
        "transactional_recalibration": True,
        "concurrent_calibration_rejected": True,
        "persistence_failure_preserves_baseline": True,
        "local_scene_change_retained": True,
        "lighting_change_retained": True,
        "camera_move_preserves_baseline": True,
        "stream_generation_revalidation": True,
        "adjacent_pose_rejected": True,
        "camera_isolation": True,
        "neutral_fill": False,
        "automatic_background_learning": False,
        "stale_pose_suppressed": True,
        "stage_latency_metrics": True,
        "render_ms": round(render_ms, 2),
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
