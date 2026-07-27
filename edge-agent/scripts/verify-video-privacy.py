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
    assert blurred_person_delta > blurred_background_delta * 2.0
    assert skeleton_person_delta > skeleton_background_delta * 2.0
    assert blurred_background_delta < 12.0
    assert skeleton_background_delta < 12.0
    assert float(skeleton.mean()) > float(reference.mean()) * 0.75
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
    assert float(np.abs(person_only_skeleton[outside_slice].astype(float) - reference[outside_slice]).mean()) < 12.0
    assert normalize_privacy_mode("invalid") == "original"

    try:
        renderer.render_jpeg(1, b"not-a-jpeg", "person_blur")
        raise AssertionError("privacy decode failure must not return the original bytes")
    except RuntimeError:
        pass

    print("video privacy renderer verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
