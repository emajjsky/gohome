#!/usr/bin/env python3
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
import sys
import time

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
        return {
            "mask": np.zeros((original_height, original_width), dtype=np.uint8),
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
            anchor_interval_seconds=0.08,
        )
        backend.decoder = DecoderStub()
        frame = np.full((180, 320, 3), 96, dtype=np.uint8)

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

        backend.reset_camera(1)
        assert backend.status()["runtime_count"] == 1
        assert counters["closed"] == 0

        backend.close()
        assert backend.status()["runtime_count"] == 0
        assert counters["closed"] == 1

    print({
        "ok": True,
        "runtime_count_for_two_cameras": counters["created"],
        "maximum_concurrent_device_inferences": counters["maximum_active"],
        "camera_reset_preserves_shared_runtime": True,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
