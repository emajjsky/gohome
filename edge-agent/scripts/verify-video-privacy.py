#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.camera_agent import _load_cv2
from app.video_privacy import normalize_privacy_mode
from app.vision.privacy_stream import PrivacyFrameRenderer


class TrackerStub:
    def latest_metadata(self, _camera_id: int):
        return {
            "image_width": 320,
            "image_height": 180,
            "tracking": {
                "state": "observed",
                "poses": [{
                    "bbox": [110, 25, 210, 175],
                    "keypoints": [
                        {"name": "left_shoulder", "x": 135, "y": 65, "confidence": 0.9, "visible": True},
                        {"name": "right_shoulder", "x": 185, "y": 65, "confidence": 0.9, "visible": True},
                        {"name": "left_hip", "x": 145, "y": 115, "confidence": 0.9, "visible": True},
                        {"name": "right_hip", "x": 175, "y": 115, "confidence": 0.9, "visible": True},
                    ],
                }],
            },
            "analysis_context": {
                "people": [{"bbox": [112, 27, 208, 173], "confidence": 0.93}],
            },
        }


class EmptyTrackerStub:
    def latest_metadata(self, _camera_id: int):
        return {
            "image_width": 320,
            "image_height": 180,
            "tracking": {"state": "empty", "poses": []},
        }


class PersonWithoutPoseTrackerStub:
    def latest_metadata(self, _camera_id: int):
        return {
            "image_width": 320,
            "image_height": 180,
            "tracking": {"state": "observed", "poses": []},
            "analysis_context": {
                "people": [{"bbox": [110, 25, 210, 175], "confidence": 0.91}],
            },
        }


class MutableTrackerStub:
    def __init__(self, metadata):
        self.metadata = metadata

    def latest_metadata(self, _camera_id: int):
        return self.metadata


class SynchronizedTrackerStub:
    def __init__(self, frame, metadata):
        self.frame = frame
        self.metadata = metadata

    def latest_synchronized_frame(self, _camera_id: int):
        return {
            "frame": self.frame.copy(),
            "tracking": dict(self.metadata.get("tracking") or {}),
            "analysis_context": dict(self.metadata.get("analysis_context") or {}),
        }


def decode(cv2, payload: bytes):
    frame = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert frame is not None and frame.size > 0
    return frame


def main() -> int:
    cv2 = _load_cv2()
    source = np.zeros((180, 320, 3), dtype=np.uint8)
    for x in range(320):
        source[:, x] = (x % 255, (x * 3) % 255, (x * 7) % 255)
    cv2.rectangle(source, (110, 25), (210, 175), (245, 245, 245), -1)
    for y in range(30, 175, 12):
        cv2.line(source, (112, y), (208, y), (30, 70 + (y % 120), 210), 5)
    ok, encoded = cv2.imencode(".jpg", source, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    assert ok
    original = encoded.tobytes()

    renderer = PrivacyFrameRenderer(TrackerStub())
    assert len(renderer._privacy_boxes(TrackerStub().latest_metadata(1), 320, 180)) == 1
    assert renderer.render_jpeg(1, original, "original") == original
    blurred = decode(cv2, renderer.render_jpeg(1, original, "person_blur", quality=70))
    skeleton = decode(cv2, renderer.render_jpeg(1, original, "skeleton", quality=70))

    reference = decode(cv2, original)
    person_slice = np.s_[20:178, 90:230]
    outside_slice = np.s_[20:160, 5:70]
    blurred_person_delta = float(np.abs(blurred[person_slice].astype(float) - reference[person_slice]).mean())
    blurred_background_delta = float(np.abs(blurred[outside_slice].astype(float) - reference[outside_slice]).mean())
    skeleton_person_delta = float(np.abs(skeleton[person_slice].astype(float) - reference[person_slice]).mean())
    skeleton_background_delta = float(np.abs(skeleton[outside_slice].astype(float) - reference[outside_slice]).mean())
    blur_skeleton_delta = float(np.abs(blurred[person_slice].astype(float) - skeleton[person_slice].astype(float)).mean())
    assert blurred_person_delta > blurred_background_delta * 2.0
    assert skeleton_person_delta > skeleton_background_delta * 2.0
    assert blur_skeleton_delta > 20.0
    assert blurred_background_delta < 12.0
    assert skeleton_background_delta < 12.0
    assert int((skeleton[:, :, 2] > 180).sum()) > 10

    empty_renderer = PrivacyFrameRenderer(EmptyTrackerStub())
    empty_blur = decode(cv2, empty_renderer.render_jpeg(1, original, "person_blur", quality=70))
    empty_skeleton = decode(cv2, empty_renderer.render_jpeg(1, original, "skeleton", quality=70))
    assert float(np.abs(empty_blur.astype(float) - reference.astype(float)).mean()) < 12.0
    assert float(np.abs(empty_skeleton.astype(float) - reference.astype(float)).mean()) < 12.0

    person_only_renderer = PrivacyFrameRenderer(PersonWithoutPoseTrackerStub())
    person_only_blur = decode(cv2, person_only_renderer.render_jpeg(1, original, "person_blur", quality=70))
    person_only_skeleton = decode(cv2, person_only_renderer.render_jpeg(1, original, "skeleton", quality=70))
    assert float(np.abs(person_only_blur[person_slice].astype(float) - reference[person_slice]).mean()) > 12.0
    assert float(np.abs(person_only_skeleton[person_slice].astype(float) - reference[person_slice]).mean()) > 12.0
    assert float(np.abs(person_only_blur[person_slice].astype(float) - person_only_skeleton[person_slice].astype(float)).mean()) > 20.0
    assert float(np.abs(person_only_skeleton[outside_slice].astype(float) - reference[outside_slice]).mean()) < 12.0
    assert normalize_privacy_mode("invalid") == "original"

    clean = np.zeros((180, 320, 3), dtype=np.uint8)
    for x in range(320):
        clean[:, x] = (25 + x % 90, 50 + (x * 2) % 110, 80 + (x * 3) % 120)
    cv2.line(clean, (0, 40), (319, 150), (210, 80, 35), 8)
    occupied = clean.copy()
    cv2.rectangle(occupied, (110, 25), (210, 175), (245, 245, 245), -1)
    cv2.line(occupied, (115, 35), (205, 165), (20, 20, 20), 12)
    ok, clean_jpeg = cv2.imencode(".jpg", clean, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    assert ok
    ok, occupied_jpeg = cv2.imencode(".jpg", occupied, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    assert ok
    mutable = MutableTrackerStub(EmptyTrackerStub().latest_metadata(1))
    reconstructed_renderer = PrivacyFrameRenderer(mutable)
    for _ in range(3):
        reconstructed_renderer.render_jpeg(1, clean_jpeg.tobytes(), "skeleton", quality=85)
    mutable.metadata = TrackerStub().latest_metadata(1)
    reconstructed = decode(
        cv2,
        reconstructed_renderer.render_jpeg(1, occupied_jpeg.tobytes(), "skeleton", quality=85),
    )
    safe_scene = decode(
        cv2,
        reconstructed_renderer.safe_scene_jpeg(1, occupied_jpeg.tobytes(), quality=85),
    )
    clean_reference = decode(cv2, clean_jpeg.tobytes())
    reconstructed_region = reconstructed[20:178, 90:230]
    clean_region = clean_reference[20:178, 90:230]
    occupied_region = decode(cv2, occupied_jpeg.tobytes())[20:178, 90:230]
    assert float(np.abs(reconstructed_region.astype(float) - clean_region.astype(float)).mean()) < 24.0
    assert float(np.abs(reconstructed_region.astype(float) - occupied_region.astype(float)).mean()) > 35.0
    assert float(np.std(reconstructed_region.astype(float))) > 20.0
    assert float(np.abs(safe_scene.astype(float) - clean_reference.astype(float)).mean()) < 24.0
    assert float(np.abs(safe_scene[person_slice].astype(float) - occupied_region.astype(float)).mean()) > 35.0

    changed_scene = occupied.copy()
    cv2.rectangle(changed_scene, (10, 55), (70, 120), (30, 220, 40), -1)
    ok, changed_jpeg = cv2.imencode(".jpg", changed_scene, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    assert ok
    changed_safe_scene = decode(
        cv2,
        reconstructed_renderer.safe_scene_jpeg(1, changed_jpeg.tobytes(), quality=85),
    )
    changed_reference = decode(cv2, changed_jpeg.tobytes())
    changed_region = np.s_[58:118, 12:68]
    assert float(
        np.abs(changed_safe_scene[changed_region].astype(float) - changed_reference[changed_region]).mean()
    ) < 18.0
    assert float(
        np.abs(changed_safe_scene[person_slice].astype(float) - changed_reference[person_slice]).mean()
    ) > 35.0

    deduplicated_renderer = PrivacyFrameRenderer(EmptyTrackerStub())
    zero_mask = np.zeros(clean.shape[:2], dtype=np.uint8)
    for _ in range(5):
        deduplicated_renderer.background_reconstructor.reconstruct(
            cv2,
            1,
            clean,
            zero_mask,
            clear_token="empty-anchor-1",
        )
    deduplicated_status = deduplicated_renderer.background_reconstructor.status()["states"][0]
    assert deduplicated_status["candidate_observations"] == 1

    fallback_renderer = PrivacyFrameRenderer(PersonWithoutPoseTrackerStub())
    fallback = decode(cv2, fallback_renderer.render_jpeg(7, occupied_jpeg.tobytes(), "skeleton", quality=85))
    assert float(np.abs(fallback[person_slice].astype(float) - occupied_region).mean()) > 18.0
    fallback_status = fallback_renderer.background_reconstructor.status()
    assert fallback_status["state_count"] == 1
    assert fallback_status["states"][0]["clean"] is False

    bounded_renderer = PrivacyFrameRenderer(EmptyTrackerStub())
    for camera_id in range(10):
        bounded_renderer.render_jpeg(camera_id, clean_jpeg.tobytes(), "skeleton", quality=60)
    assert bounded_renderer.background_reconstructor.status()["state_count"] == 6
    bounded_renderer.background_reconstructor.reset_camera(9)
    assert all(
        state["camera_id"] != 9
        for state in bounded_renderer.background_reconstructor.status()["states"]
    )

    supplied_wrong_frame = clean.copy()
    cv2.rectangle(supplied_wrong_frame, (225, 25), (315, 175), (245, 245, 245), -1)
    exact_frame = clean.copy()
    cv2.rectangle(exact_frame, (110, 25), (210, 175), (245, 245, 245), -1)
    exact_metadata = TrackerStub().latest_metadata(1)
    exact_metadata["tracking"]["frame_id"] = "camera-1-exact-7"
    synchronized_renderer = PrivacyFrameRenderer(SynchronizedTrackerStub(exact_frame, exact_metadata))
    synchronized_renderer.background_reconstructor._observe_clear_frame((1, 320, 180), clean)
    synchronized_renderer.background_reconstructor._observe_clear_frame((1, 320, 180), clean)
    synchronized_renderer.background_reconstructor._observe_clear_frame((1, 320, 180), clean)
    ok, wrong_jpeg = cv2.imencode(".jpg", supplied_wrong_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    assert ok
    synchronized_output = decode(
        cv2,
        synchronized_renderer.render_jpeg(1, wrong_jpeg.tobytes(), "skeleton", quality=85),
    )
    wrong_person_region = synchronized_output[25:175, 225:315]
    clean_wrong_region = clean[25:175, 225:315]
    assert float(np.abs(wrong_person_region.astype(float) - clean_wrong_region.astype(float)).mean()) < 18.0

    unavailable_renderer = PrivacyFrameRenderer(SynchronizedTrackerStub(exact_frame, exact_metadata))
    unavailable_renderer.tracker.latest_synchronized_frame = lambda _camera_id: None
    unavailable = decode(cv2, unavailable_renderer.render_jpeg(1, wrong_jpeg.tobytes(), "skeleton", quality=85))
    assert float(np.max(np.std(unavailable.astype(float), axis=(0, 1)))) < 2.0

    current_scene = exact_frame.copy()
    cv2.rectangle(current_scene, (8, 8), (72, 20), (12, 220, 35), -1)
    recent_renderer = PrivacyFrameRenderer(SynchronizedTrackerStub(current_scene, exact_metadata))
    for _ in range(3):
        recent_renderer.background_reconstructor._observe_clear_frame((1, 320, 180), clean)
    recent_renderer.render_jpeg(1, wrong_jpeg.tobytes(), "skeleton", quality=85)
    recent_renderer.tracker.latest_synchronized_frame = lambda _camera_id: None
    recent_fallback = decode(
        cv2,
        recent_renderer.render_jpeg(1, wrong_jpeg.tobytes(), "skeleton", quality=85),
    )
    assert float(np.abs(recent_fallback[8:20, 8:72].astype(float) - current_scene[8:20, 8:72]).mean()) < 18.0
    assert float(np.abs(recent_fallback[person_slice].astype(float) - clean_reference[person_slice]).mean()) < 18.0

    try:
        renderer.render_jpeg(1, b"not-a-jpeg", "person_blur")
        raise AssertionError("privacy decode failure must not return the original bytes")
    except RuntimeError:
        pass

    print("video privacy renderer verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
