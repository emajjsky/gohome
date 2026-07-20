from __future__ import annotations

from pathlib import Path
from threading import Lock, Thread
import sys
import time

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.camera_agent import CameraAgent


class FakeCapture:
    def __init__(self, counters: dict[str, int], counter_lock: Lock) -> None:
        self.counters = counters
        self.counter_lock = counter_lock
        self.released = False
        self.pending = None

    def isOpened(self) -> bool:
        return not self.released

    def read(self):
        if self.released:
            return False, None
        time.sleep(0.01)
        with self.counter_lock:
            self.counters["reads"] += 1
            level = 80 + self.counters["reads"] % 80
        return True, np.full((48, 64, 3), level, dtype=np.uint8)

    def grab(self) -> bool:
        ok, self.pending = self.read()
        return ok

    def retrieve(self):
        frame = self.pending
        self.pending = None
        return frame is not None, frame

    def release(self) -> None:
        self.released = True


def main() -> None:
    counters = {"opens": 0, "reads": 0}
    counter_lock = Lock()
    agent = CameraAgent(Path("/tmp/gohome-shared-stream-test"))
    camera = {"id": 9, "stream_url": "rtsp://example.invalid/live"}

    def open_capture(_cv2, _source, _is_local):
        with counter_lock:
            counters["opens"] += 1
        return FakeCapture(counters, counter_lock)

    agent._open_stream_capture = open_capture  # type: ignore[method-assign]
    agent.reconcile_managed_streams([camera])
    initial = agent.capture_frame(camera, prefer_cache=True, max_cache_age_seconds=1)
    if initial.get("frame_id") is None or counters["opens"] != 1:
        raise SystemExit("initial analysis opened a second capture instead of waiting for the managed reader")

    errors: list[str] = []

    def consume() -> None:
        stream = agent.mjpeg_frames(
            camera,
            fps=8,
            jpeg_quality=70,
            max_width=64,
            max_height=48,
            drop_stale_frames=1,
        )
        try:
            for _ in range(4):
                part = next(stream)
                if b"Content-Type: image/jpeg" not in part:
                    raise RuntimeError("invalid MJPEG part")
        except Exception as exc:
            errors.append(str(exc))
        finally:
            stream.close()

    consumers = [Thread(target=consume), Thread(target=consume)]
    for consumer in consumers:
        consumer.start()
    for consumer in consumers:
        consumer.join(timeout=4)

    if any(consumer.is_alive() for consumer in consumers):
        raise SystemExit("shared stream consumers did not finish")
    if errors:
        raise SystemExit(f"shared stream consumer failed: {errors}")
    if counters["opens"] != 1:
        raise SystemExit(f"same camera opened {counters['opens']} RTSP captures instead of one")
    if counters["reads"] < 16:
        raise SystemExit(f"source was not drained continuously: {counters['reads']} reads")

    cached = agent.latest_cached_frame(camera, max_age_seconds=1)
    if cached is None:
        raise SystemExit("shared reader did not populate the latest-frame cache")
    sequence_before = int(str(cached["frame_id"]).rsplit("-", 1)[-1])
    time.sleep(0.05)
    cached_after_preview = agent.latest_cached_frame(camera, max_age_seconds=1)
    sequence_after = int(str(cached_after_preview["frame_id"]).rsplit("-", 1)[-1])
    if sequence_after <= sequence_before:
        raise SystemExit("managed stream stopped when the preview subscribers disconnected")
    status = agent.managed_stream_status()
    if status.get("managed_stream_count") != 1:
        raise SystemExit(f"managed stream status is incorrect: {status}")
    agent.reconcile_managed_streams([])
    if agent.managed_stream_status().get("managed_stream_count") != 0:
        raise SystemExit("removed camera retained a managed stream reader")

    print({
        "ok": True,
        "capture_opens": counters["opens"],
        "source_reads": counters["reads"],
        "subscribers": len(consumers),
        "managed_stream_survived_preview": True,
    })


if __name__ == "__main__":
    main()
