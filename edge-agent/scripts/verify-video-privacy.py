#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from hashlib import sha256
import sys
import time
from unittest.mock import patch

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.camera_agent import _load_cv2
from app.vision.privacy_background import PrivacyBackgroundReconstructor, PrivacyCalibrationRequired
from app.vision.privacy_scene_geometry import SceneGeometryVerifier
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


class ManualClock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = float(value)

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += float(seconds)


class ScriptedGeometryVerifier:
    def __init__(self, outcomes: list[dict]) -> None:
        self.outcomes = [dict(outcome) for outcome in outcomes]
        self.call_count = 0

    def signature(self, frame, *, excluded_mask=None):
        del frame, excluded_mask
        return self.call_count

    def signatures_match(self, previous, current) -> bool:
        del previous, current
        return False

    def assess(self, background, frame, *, excluded_mask=None):
        del background, frame, excluded_mask
        index = min(self.call_count, len(self.outcomes) - 1)
        self.call_count += 1
        return dict(self.outcomes[index])


def geometry_outcome(status: str, *, confidence: str = "strong") -> dict:
    return {
        "accepted": status == "same_view",
        "geometry_status": status,
        "geometry_reason": "" if status == "same_view" else status,
        "geometry_confidence": confidence,
        "geometry_good_matches": 24 if confidence == "strong" else 8,
        "geometry_inliers": 18 if confidence == "strong" else 5,
        "geometry_inlier_ratio": 0.75 if confidence == "strong" else 0.5,
        "geometry_median_corner_displacement_ratio": 0.002 if status == "same_view" else None,
        "geometry_max_corner_displacement_ratio": 0.004 if status == "same_view" else None,
        "geometry_cached": False,
    }


class SyntheticSegmentation:
    def __init__(self, backgrounds: dict[str, np.ndarray]) -> None:
        self.backgrounds = {key: value.copy() for key, value in backgrounds.items()}
        self.call_count = 0

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
        self.call_count += 1
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
    local_texture = np.random.default_rng(7).integers(
        0,
        256,
        size=(100, 100),
        dtype=np.uint8,
    )
    local_texture = cv2.cvtColor(local_texture, cv2.COLOR_GRAY2BGR)
    clustered_baseline = np.full((360, 640, 3), 30, dtype=np.uint8)
    clustered_current = np.full((360, 640, 3), 190, dtype=np.uint8)
    clustered_baseline[100:200, 100:200] = local_texture
    clustered_current[100:200, 160:260] = local_texture
    clustered_assessment = SceneGeometryVerifier().assess(
        clustered_baseline,
        clustered_current,
        excluded_mask=None,
    )
    assert clustered_assessment["geometry_status"] == "unverifiable"
    assert clustered_assessment["geometry_reason"] == "geometry_models_inconclusive"
    assert (
        clustered_assessment["geometry_spatial_coverage_ratio"] < 0.12
        or clustered_assessment["geometry_grid_coverage_ratio"] < 0.25
    )

    broad_baseline = np.random.default_rng(17).integers(
        0,
        256,
        size=(360, 640, 3),
        dtype=np.uint8,
    )
    broad_current = cv2.warpAffine(
        broad_baseline,
        np.float32([[1.0, 0.0, 9.0], [0.0, 1.0, 0.0]]),
        (640, 360),
        borderMode=cv2.BORDER_REFLECT,
    )

    def unstable_homography(current_coordinates, baseline_coordinates, *args, **kwargs):
        del baseline_coordinates, args, kwargs
        return (
            np.float64([
                [1.0, 0.0, -9.0],
                [0.0, 1.0, 0.0],
                [0.0003, 0.0, 1.0],
            ]),
            np.ones((len(current_coordinates), 1), dtype=np.uint8),
        )

    with patch.object(cv2, "findHomography", side_effect=unstable_homography):
        broad_conflict_assessment = SceneGeometryVerifier().assess(
            broad_baseline,
            broad_current,
            excluded_mask=None,
        )
    assert broad_conflict_assessment["geometry_status"] == "same_view"
    assert broad_conflict_assessment["geometry_model_agreement"] == "conflict"
    assert broad_conflict_assessment["geometry_model_resolution"] == "affine_phase_consensus"
    assert broad_conflict_assessment["geometry_affine_grid_coverage_ratio"] >= 0.75
    assert broad_conflict_assessment["geometry_phase_response"] >= 0.9
    assert broad_conflict_assessment["geometry_phase_displacement_ratio"] <= 0.015
    assert broad_conflict_assessment.get(
        "geometry_phase_affine_vector_residual_ratio",
        float("inf"),
    ) <= 0.002

    def near_limit_affine(current_coordinates, baseline_coordinates, *args, **kwargs):
        del baseline_coordinates, args, kwargs
        return (
            np.float64([
                [1.0, 0.0, -11.2],
                [0.0, 1.0, 0.0],
            ]),
            np.ones((len(current_coordinates), 1), dtype=np.uint8),
        )

    with (
        patch.object(cv2, "findHomography", side_effect=unstable_homography),
        patch.object(cv2, "estimateAffinePartial2D", side_effect=near_limit_affine),
    ):
        near_limit_conflict = SceneGeometryVerifier().assess(
            broad_baseline,
            broad_current,
            excluded_mask=None,
        )
    assert near_limit_conflict["geometry_status"] == "same_view"
    assert near_limit_conflict["geometry_model_agreement"] == "camera_view_changed"
    assert near_limit_conflict["geometry_model_resolution"] == "affine_phase_consensus"

    low_feature_baseline = np.random.default_rng(9).integers(
        0,
        256,
        size=(360, 640, 3),
        dtype=np.uint8,
    )
    low_feature_lighting = np.clip(
        low_feature_baseline.astype(np.int16) + 20,
        0,
        255,
    ).astype(np.uint8)
    phase_only_verifier = SceneGeometryVerifier(minimum_features=1000)
    low_feature_assessment = phase_only_verifier.assess(
        low_feature_baseline,
        low_feature_lighting,
        excluded_mask=None,
    )
    assert low_feature_assessment["geometry_status"] == "same_view"
    assert low_feature_assessment["geometry_phase_status"] == "same_view"
    assert low_feature_assessment["geometry_phase_displacement_ratio"] == 0.0
    low_feature_moved = phase_only_verifier.assess(
        low_feature_baseline,
        np.roll(low_feature_baseline, 50, axis=1),
        excluded_mask=None,
    )
    assert low_feature_moved["geometry_status"] == "unverifiable"
    assert low_feature_moved["geometry_phase_status"] == "unverifiable"

    clean_a = scene(1)
    clean_b = scene(7)
    occupied_a = occupied_scene(cv2, clean_a)
    source_a_g1 = "camera-a:g1"
    source_a_g2 = "camera-a:g2"
    source_b_g1 = "camera-b:g1"
    revalidation_clock = ManualClock()

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
            revalidation_interval_seconds=1.0,
            monotonic_clock=revalidation_clock,
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

        blur_image_frame_id = "1-blur-image"
        blur_image_monotonic = time.monotonic()
        tracker.payload = metadata(
            camera_id=1,
            person=True,
            frame_id=blur_image_frame_id,
            source_key=source_a_g1,
        )
        tracker.payload["tracking"]["captured_monotonic"] = blur_image_monotonic
        blurred_image = renderer.render_image(
            1,
            occupied_a,
            "person_blur",
            source_key=source_a_g1,
            frame_id=blur_image_frame_id,
            captured_monotonic=blur_image_monotonic,
        )
        assert np.array_equal(blurred_image[OUTSIDE_SLICE], occupied_a[OUTSIDE_SLICE])
        assert mean_delta(blurred_image, occupied_a, PERSON_SLICE) > 18.0

        segmentation_calls_before_block = renderer.segmentation_backend.call_count
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
        assert renderer.segmentation_backend.call_count == segmentation_calls_before_block

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

        image_frame_id = "1-composed-image"
        image_monotonic = time.monotonic()
        tracker.payload = metadata(
            camera_id=1,
            person=True,
            frame_id=image_frame_id,
            source_key=source_a_g1,
        )
        tracker.payload["tracking"]["captured_monotonic"] = image_monotonic
        stages_before = renderer.status()["cameras"]["1"]["stage_latency_ms"]
        jpeg_samples_before = int(stages_before["jpeg_encode"]["samples"])
        composed = renderer.render_image(
            1,
            occupied_a,
            "skeleton",
            source_key=source_a_g1,
            frame_id=image_frame_id,
            captured_monotonic=image_monotonic,
        )
        assert isinstance(composed, np.ndarray)
        assert composed.shape == occupied_a.shape
        assert composed.dtype == np.uint8
        assert mean_delta(composed, occupied_a, PERSON_SLICE) > 24.0
        stages_after = renderer.status()["cameras"]["1"]["stage_latency_ms"]
        assert stages_after["jpeg_encode"]["samples"] == jpeg_samples_before
        assert stages_after["composition_total"]["samples"] >= 1

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

        # An empty current segmentation anchor is sufficient to continue room
        # revalidation even when the pose worker has no matching-frame result.
        tracker.payload = metadata(
            camera_id=1,
            person=False,
            frame_id="1-stale-empty-pose",
            source_key=source_a_g2,
        )
        assert_calibration_required(lambda: renderer.render_frame(
            1,
            clean_a,
            "skeleton",
            quality=90,
            source_key=source_a_g2,
            frame_id="1-empty-without-pose",
            captured_monotonic=time.monotonic(),
        ), "stream_revalidation_required")
        empty_without_pose_status = renderer.background_reconstructor.status()["states"][0]
        assert empty_without_pose_status["revalidation_observations"] == 1
        revalidation_clock.advance(1.0)

        for sequence in range(1, renderer.background_reconstructor.revalidation_frames - 1):
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
            revalidation_clock.advance(1.0)
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

        persisted_path = next(Path(temporary_dir).glob("camera-1-*.npz"))
        persisted_file_sha256 = sha256(persisted_path.read_bytes()).hexdigest()
        persisted = PrivacyFrameRenderer(
            tracker,
            PrivacyBackgroundReconstructor(
                storage_dir=temporary_dir,
                monotonic_clock=revalidation_clock,
            ),
            SyntheticSegmentation({"camera-a": clean_a}),
            revalidation_interval_seconds=1.0,
            monotonic_clock=revalidation_clock,
        )
        discovered = persisted.discover_calibrations(1, source_key=source_a_g1)
        assert len(discovered) == 1
        assert discovered[0]["calibrated"] is True
        assert discovered[0]["baseline_retained"] is True
        assert discovered[0]["ready"] is False
        assert discovered[0]["status"] == "revalidating"

        moved_endpoint = PrivacyFrameRenderer(
            tracker,
            PrivacyBackgroundReconstructor(
                storage_dir=temporary_dir,
                monotonic_clock=revalidation_clock,
            ),
            SyntheticSegmentation({"camera-a-moved": clean_a}),
            revalidation_interval_seconds=1.0,
            monotonic_clock=revalidation_clock,
        )
        moved_source = "camera-a-moved:g1"
        moved_discovery = moved_endpoint.discover_calibrations(1, source_key=moved_source)
        assert len(moved_discovery) == 1
        assert moved_discovery[0]["baseline_retained"] is True
        assert moved_discovery[0]["ready"] is False
        for sequence in range(moved_endpoint.background_reconstructor.revalidation_frames):
            revalidation_clock.advance(1.0)
            render(
                moved_endpoint,
                tracker,
                clean_a,
                camera_id=1,
                source_key=moved_source,
                frame_id=f"1-moved-endpoint-revalidate-{sequence}",
                person=False,
                mode="original",
            )
        moved_status = moved_endpoint.background_reconstructor.inspect(
            1,
            source_key=moved_source,
            width=320,
            height=180,
        )
        assert moved_status["ready"] is True
        assert moved_status["baseline_retained"] is True

        occupied_original = render(
            persisted,
            tracker,
            occupied_a,
            camera_id=1,
            source_key=source_a_g1,
            frame_id="1-persisted-person-present",
            person=True,
            mode="original",
        )
        assert mean_delta(occupied_original, occupied_a) < 8.0
        person_blocked = persisted.background_reconstructor.status()["states"][0]
        assert person_blocked["ready"] is False
        assert person_blocked["revalidation_observations"] == 0
        assert person_blocked["last_error"] == "person_present"

        calls_after_person_anchor = persisted.segmentation_backend.call_count
        for sequence in range(12):
            render(
                persisted,
                tracker,
                occupied_a,
                camera_id=1,
                source_key=source_a_g1,
                frame_id=f"1-person-cadence-{sequence}",
                person=True,
                mode="original",
            )
        assert persisted.segmentation_backend.call_count == calls_after_person_anchor
        revalidation_clock.advance(0.99)
        render(
            persisted,
            tracker,
            occupied_a,
            camera_id=1,
            source_key=source_a_g1,
            frame_id="1-person-before-cadence",
            person=True,
            mode="original",
        )
        assert persisted.segmentation_backend.call_count == calls_after_person_anchor
        revalidation_clock.advance(0.01)
        render(
            persisted,
            tracker,
            occupied_a,
            camera_id=1,
            source_key=source_a_g1,
            frame_id="1-person-next-anchor",
            person=True,
            mode="original",
        )
        assert persisted.segmentation_backend.call_count == calls_after_person_anchor + 1
        scheduler = persisted.status()["revalidation_scheduler"]
        assert scheduler["interval_seconds"] == 1.0
        assert scheduler["active_streams"] == 1

        for sequence in range(persisted.background_reconstructor.revalidation_frames):
            revalidation_clock.advance(1.0)
            original_during_revalidation = render(
                persisted,
                tracker,
                clean_a,
                camera_id=1,
                source_key=source_a_g1,
                frame_id=f"1-persisted-revalidate-{sequence}",
                person=False,
                mode="original",
            )
            assert mean_delta(original_during_revalidation, clean_a) < 8.0
            current_status = persisted.background_reconstructor.status()["states"][0]
            assert current_status["revalidation_observations"] == sequence + 1
            assert current_status["ready"] is (
                sequence + 1 == persisted.background_reconstructor.revalidation_frames
            )
        assert sha256(persisted_path.read_bytes()).hexdigest() == persisted_file_sha256
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

        revalidation_clock.advance(2.0)
        household_change = clean_a.copy()
        cv2.rectangle(household_change, (0, 0), (80, 179), (38, 92, 210), -1)
        cv2.rectangle(household_change, (245, 0), (319, 179), (215, 210, 205), -1)
        household_change_render = render(
            persisted,
            tracker,
            household_change,
            camera_id=1,
            source_key=source_a_g1,
            frame_id="1-household-layout-change",
            person=False,
            mode="skeleton",
        )
        assert mean_delta(household_change_render, household_change) < 8.0
        household_status = persisted.background_reconstructor.status()["states"][0]
        assert household_status["last_geometry_status"] == "same_view"
        assert household_status["last_geometry_inliers"] >= 10

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

        tri_state_dir = Path(temporary_dir) / "tri-state"
        tri_state_seed = PrivacyFrameRenderer(
            tracker,
            PrivacyBackgroundReconstructor(storage_dir=tri_state_dir),
            SyntheticSegmentation({"camera-a": clean_a, "camera-b": clean_b}),
        )
        calibrate(
            tri_state_seed,
            tracker,
            clean_a,
            camera_id=1,
            source_key=source_a_g1,
        )
        calibrate(
            tri_state_seed,
            tracker,
            clean_b,
            camera_id=2,
            source_key=source_b_g1,
        )
        scripted_geometry = ScriptedGeometryVerifier(
            [geometry_outcome("unverifiable", confidence="none")] * 4
            + [geometry_outcome("same_view", confidence="moderate")] * 3
        )
        tri_state = PrivacyFrameRenderer(
            tracker,
            PrivacyBackgroundReconstructor(
                storage_dir=tri_state_dir,
                geometry_verifier=scripted_geometry,
                monotonic_clock=revalidation_clock,
            ),
            SyntheticSegmentation({"camera-a": clean_a, "camera-b": clean_b}),
            revalidation_interval_seconds=1.0,
            monotonic_clock=revalidation_clock,
        )
        low_feature_same_view = np.full_like(clean_a, 210)
        for sequence in range(4):
            revalidation_clock.advance(1.0)
            render(
                tri_state,
                tracker,
                low_feature_same_view,
                camera_id=1,
                source_key=source_a_g1,
                frame_id=f"1-unverifiable-{sequence}",
                person=False,
                mode="original",
            )
        uncertain_status = tri_state.background_reconstructor.inspect(
            1,
            source_key=source_a_g1,
            width=320,
            height=180,
        )
        assert uncertain_status["ready"] is False
        assert uncertain_status["status"] == "revalidating"
        assert uncertain_status["scene_status"] == "revalidation_uncertain"
        assert uncertain_status["scene_mismatch_observations"] == 0
        assert uncertain_status["scene_unverifiable_observations"] == 4
        assert uncertain_status["baseline_retained"] is True

        for sequence in range(tri_state.background_reconstructor.revalidation_frames):
            revalidation_clock.advance(1.0)
            render(
                tri_state,
                tracker,
                clean_b,
                camera_id=2,
                source_key=source_b_g1,
                frame_id=f"2-independent-revalidate-{sequence}",
                person=False,
                mode="original",
            )
        independent_status = tri_state.background_reconstructor.inspect(
            2,
            source_key=source_b_g1,
            width=320,
            height=180,
        )
        assert independent_status["ready"] is True
        assert tri_state.background_reconstructor.inspect(
            1,
            source_key=source_a_g1,
            width=320,
            height=180,
        )["ready"] is False

        for sequence in range(tri_state.background_reconstructor.revalidation_frames):
            revalidation_clock.advance(1.0)
            render(
                tri_state,
                tracker,
                low_feature_same_view,
                camera_id=1,
                source_key=source_a_g1,
                frame_id=f"1-reliable-recovery-{sequence}",
                person=False,
                mode="original",
            )
        recovered_status = tri_state.background_reconstructor.inspect(
            1,
            source_key=source_a_g1,
            width=320,
            height=180,
        )
        assert recovered_status["ready"] is True
        assert recovered_status["last_geometry_status"] == "same_view"
        assert recovered_status["last_geometry_confidence"] == "moderate"
        assert recovered_status["scene_unverifiable_observations"] == 0

        changed_restart = PrivacyFrameRenderer(
            tracker,
            PrivacyBackgroundReconstructor(
                storage_dir=temporary_dir,
                monotonic_clock=revalidation_clock,
            ),
            SyntheticSegmentation({"camera-a": clean_a}),
            revalidation_interval_seconds=1.0,
            monotonic_clock=revalidation_clock,
        )
        for sequence in range(changed_restart.background_reconstructor.revalidation_frames - 1):
            assert_calibration_required(lambda sequence=sequence: render(
                changed_restart,
                tracker,
                household_change,
                camera_id=1,
                source_key=source_a_g1,
                frame_id=f"1-household-revalidate-{sequence}",
                person=False,
                mode="skeleton",
            ), "stream_revalidation_required")
            revalidation_clock.advance(1.0)
        changed_revalidated = render(
            changed_restart,
            tracker,
            household_change,
            camera_id=1,
            source_key=source_a_g1,
            frame_id="1-household-revalidate-complete",
            person=False,
            mode="skeleton",
        )
        assert mean_delta(changed_revalidated, household_change) < 8.0
        changed_restart_status = changed_restart.background_reconstructor.status()["states"][0]
        assert changed_restart_status["ready"] is True
        assert changed_restart_status["last_geometry_status"] == "same_view"

        moved_scene = np.roll(clean_a, 52, axis=1)
        first_move_candidate = render(
            persisted,
            tracker,
            moved_scene,
            camera_id=1,
            source_key=source_a_g1,
            frame_id="1-moved-scene",
            person=False,
            mode="skeleton",
        )
        assert mean_delta(first_move_candidate, moved_scene) < 8.0
        revalidation_clock.advance(1.0)
        second_move_candidate = render(
            persisted,
            tracker,
            moved_scene,
            camera_id=1,
            source_key=source_a_g1,
            frame_id="1-moved-scene-repeat",
            person=False,
            mode="skeleton",
        )
        assert mean_delta(second_move_candidate, moved_scene) < 8.0
        revalidation_clock.advance(1.0)
        assert_calibration_required(lambda: render(
            persisted,
            tracker,
            moved_scene,
            camera_id=1,
            source_key=source_a_g1,
            frame_id="1-moved-scene-confirmed",
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
            revalidation_interval_seconds=1.0,
            monotonic_clock=revalidation_clock,
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
            revalidation_clock.advance(1.0)
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
        multi_view_status = restarted_after_move.background_reconstructor.status()["states"][0]
        assert multi_view_status["known_view_count"] == 2
        assert len(list(Path(temporary_dir).glob("*-view-*.npz"))) == 1

        # A restart must recognize either previously confirmed camera angle.
        multi_view_restart = PrivacyFrameRenderer(
            tracker,
            PrivacyBackgroundReconstructor(storage_dir=temporary_dir),
            SyntheticSegmentation({"camera-a": moved_scene}),
            revalidation_interval_seconds=1.0,
            monotonic_clock=revalidation_clock,
        )
        assert_calibration_required(lambda: render(
            multi_view_restart,
            tracker,
            moved_scene,
            camera_id=1,
            source_key=source_a_g1,
            frame_id="1-known-view-switch",
            person=False,
            mode="skeleton",
        ), "stream_revalidation_required")
        for sequence in range(multi_view_restart.background_reconstructor.revalidation_frames):
            revalidation_clock.advance(1.0)
            try:
                render(
                    multi_view_restart,
                    tracker,
                    moved_scene,
                    camera_id=1,
                    source_key=source_a_g1,
                    frame_id=f"1-known-view-revalidate-{sequence}",
                    person=False,
                    mode="skeleton",
                )
            except PrivacyCalibrationRequired as exc:
                assert exc.reason == "stream_revalidation_required"
        recovered_known_view = multi_view_restart.background_reconstructor.status()["states"][0]
        assert recovered_known_view["ready"] is True
        assert recovered_known_view["known_view_count"] == 2
        assert recovered_known_view["active_view_id"] != "legacy"

        # Returning to the original angle selects the retained legacy baseline.
        multi_view_restart.segmentation_backend.backgrounds["camera-a"] = clean_a.copy()
        assert_calibration_required(lambda: render(
            multi_view_restart,
            tracker,
            clean_a,
            camera_id=1,
            source_key=source_a_g1,
            frame_id="1-return-to-original-view",
            person=False,
            mode="skeleton",
        ), "stream_revalidation_required")
        for sequence in range(multi_view_restart.background_reconstructor.revalidation_frames):
            revalidation_clock.advance(1.0)
            try:
                render(
                    multi_view_restart,
                    tracker,
                    clean_a,
                    camera_id=1,
                    source_key=source_a_g1,
                    frame_id=f"1-original-view-revalidate-{sequence}",
                    person=False,
                    mode="skeleton",
                )
            except PrivacyCalibrationRequired as exc:
                assert exc.reason == "stream_revalidation_required"
        returned_view = multi_view_restart.background_reconstructor.status()["states"][0]
        assert returned_view["ready"] is True
        assert returned_view["active_view_id"] == "legacy"
        assert returned_view["known_view_count"] == 2

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
        "missing_baseline_skips_segmentation": True,
        "persistent_calibration": True,
        "persisted_baseline_discovery": True,
        "mode_independent_revalidation": True,
        "person_present_revalidation_blocked": True,
        "revalidation_anchor_cadence_bounded": True,
        "revalidation_preserves_baseline_file": True,
        "transactional_recalibration": True,
        "concurrent_calibration_rejected": True,
        "persistence_failure_preserves_baseline": True,
        "local_scene_change_retained": True,
        "large_household_change_retained": True,
        "large_household_change_restart_revalidated": True,
        "lighting_change_retained": True,
        "clustered_features_do_not_confirm_camera_move": True,
        "affine_phase_consensus_rejects_homography_extrapolation": True,
        "low_feature_phase_revalidation": True,
        "unverifiable_scene_retains_baseline": True,
        "unverifiable_scene_recovers": True,
        "revalidation_camera_isolation": True,
        "camera_move_requires_reliable_sequence": True,
        "camera_move_preserves_baseline": True,
        "known_camera_views_restore_after_restart": True,
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
