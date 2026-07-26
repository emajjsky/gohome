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
            "analysis_context": {},
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
    assert renderer.render_jpeg(1, original, "original") == original
    blurred = decode(cv2, renderer.render_jpeg(1, original, "person_blur", quality=70))
    skeleton = decode(cv2, renderer.render_jpeg(1, original, "skeleton", quality=70))

    person_region = blurred[20:178, 90:230]
    outside_region = blurred[20:160, 5:70]
    assert float(person_region.var()) < float(source[20:178, 90:230].var())
    assert float(outside_region.var()) > 20.0
    assert float(skeleton.mean()) < float(source.mean()) * 0.55
    assert int((skeleton[:, :, 2] > 180).sum()) > 10
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
