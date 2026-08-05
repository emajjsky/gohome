#!/usr/bin/env python3
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
import sys
import time

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.hailo_segmentation import HailoPersonSegmentationBackend


class RuntimeStub:
    input_shape = (640, 640, 3)

    def __init__(self, counters: dict[str, int], lock: Lock) -> None:
        self.counters = counters
        self.lock = lock

    def infer(self, _model_input):
        with self.lock:
            self.counters["inferences"] += 1
            self.counters["active"] += 1
            self.counters["maximum_active"] = max(
                self.counters["maximum_active"],
                self.counters["active"],
            )
        time.sleep(0.03)
        with self.lock:
            self.counters["active"] -= 1
        return {}

    def close(self) -> None:
        with self.lock:
            self.counters["closed"] += 1


class DecoderStub:
    def decode(self, _outputs, *, original_width, original_height, confidence):
        del confidence
        mask = np.zeros((original_height, original_width), dtype=np.uint8)
        x1 = max(0, original_width // 3)
        x2 = min(original_width, x1 + max(12, original_width // 5))
        y1 = max(0, original_height // 4)
        y2 = min(original_height, y1 + max(12, original_height // 2))
        mask[y1:y2, x1:x2] = 255
        return {
            "mask": mask,
            "boxes": np.empty((0, 4), dtype=np.float32),
            "scores": np.empty((0,), dtype=np.float32),
            "person_count": 0,
            "architecture": "runtime-ownership-test",
        }


def main() -> int:
    counters = {
        "created": 0,
        "closed": 0,
        "active": 0,
        "maximum_active": 0,
        "inferences": 0,
    }
    lock = Lock()

    def runtime_factory(_model_path: Path):
        with lock:
            counters["created"] += 1
        return RuntimeStub(counters, lock)

    with TemporaryDirectory() as temporary_dir:
        model_path = Path(temporary_dir) / "person-seg.hef"
        model_path.write_bytes(b"test-hef-placeholder")
        backend = HailoPersonSegmentationBackend(
            model_path=str(model_path),
            runtime_factory=runtime_factory,
            anchor_interval_seconds=0.5,
        )
        backend.decoder = DecoderStub()
        rng = np.random.default_rng(20260805)
        frame = cv2.GaussianBlur(
            rng.integers(0, 256, size=(180, 320, 3), dtype=np.uint8),
            (9, 9),
            0,
        )

        def segment(camera_id: int):
            return backend.segment(
                camera_id,
                frame,
                frame_id=f"{camera_id}-frame-1",
                source_key=f"camera-{camera_id}:g1",
                captured_monotonic=time.monotonic(),
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(segment, (1, 2)))

        assert all(result["backend"] == "hailo" for result in results)
        assert counters["created"] == 1
        assert counters["maximum_active"] == 1
        assert backend.status()["runtime_count"] == 1
        assert backend.status()["runtime_ownership"] == "shared_per_hef"

        propagated = backend.segment(
            1,
            frame,
            frame_id="1-frame-2",
            source_key="camera-1:g1",
            captured_monotonic=time.monotonic(),
        )
        inferences_before_anchor = counters["inferences"]
        anchored = backend.segment_anchor(
            1,
            frame,
            frame_id="1-frame-3",
            source_key="camera-1:g1",
            captured_monotonic=time.monotonic(),
        )
        assert propagated["temporal_mode"] == "propagated"
        assert anchored["temporal_mode"] == "anchor"
        assert counters["inferences"] == inferences_before_anchor + 1

        shift = np.float32([[1, 0, 8], [0, 1, 3]])
        shifted_frame = cv2.warpAffine(
            frame,
            shift,
            (frame.shape[1], frame.shape[0]),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT,
        )
        propagated_motion = backend.segment(
            1,
            shifted_frame,
            frame_id="1-frame-4",
            source_key="camera-1:g1",
            captured_monotonic=time.monotonic(),
        )
        expected_mask = cv2.warpAffine(
            np.asarray(anchored["mask"], dtype=np.uint8),
            shift,
            (frame.shape[1], frame.shape[0]),
            flags=cv2.INTER_NEAREST,
        )
        actual_pixels = propagated_motion["mask"] > 0
        expected_pixels = expected_mask > 0
        intersection = np.count_nonzero(actual_pixels & expected_pixels)
        union = np.count_nonzero(actual_pixels | expected_pixels)
        translated_mask_iou = intersection / max(1, union)
        assert propagated_motion["temporal_mode"] == "propagated"
        assert translated_mask_iou >= 0.90, translated_mask_iou
        flow_status = backend.status()
        assert flow_status["flow_algorithm"] == "dis_ultrafast"
        assert flow_status["flow_estimator_count"] == 1
        assert flow_status["flow_grid_cache_entries"] == 1

        backend.reset_camera(1)
        assert backend.status()["runtime_count"] == 1
        assert backend.status()["flow_estimator_count"] == 0
        assert counters["closed"] == 0

        backend.close()
        assert backend.status()["runtime_count"] == 0
        assert counters["closed"] == 1

    print({
        "ok": True,
        "runtime_count_for_two_cameras": counters["created"],
        "maximum_concurrent_device_inferences": counters["maximum_active"],
        "camera_reset_preserves_shared_runtime": True,
        "forced_anchor_bypasses_propagation": True,
        "flow_algorithm": "dis_ultrafast",
        "translated_mask_iou": round(translated_mask_iou, 4),
        "flow_resources_reused": True,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
