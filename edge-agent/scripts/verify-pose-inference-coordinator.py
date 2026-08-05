from __future__ import annotations

from pathlib import Path
from threading import Event, Lock, Thread
import sys
import time

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.pose_coordinator import PoseInferenceCoordinator


class ProbePoseService:
    def __init__(self) -> None:
        self.first_started = Event()
        self.release_first = Event()
        self._lock = Lock()
        self.calls: list[int] = []
        self.concurrent = 0
        self.max_concurrent = 0

    def analyze_accelerated_frame(self, frame, config):
        marker = int(frame[0, 0, 0])
        with self._lock:
            self.calls.append(marker)
            self.concurrent += 1
            self.max_concurrent = max(self.max_concurrent, self.concurrent)
            first = len(self.calls) == 1
        try:
            if first:
                self.first_started.set()
                if not self.release_first.wait(2.0):
                    raise RuntimeError("probe release timed out")
            time.sleep(0.01)
            return {
                "accelerated": {"marker": marker},
                "analysis": {
                    "pose_model_status": "ready",
                    "poses": [],
                },
            }
        finally:
            with self._lock:
                self.concurrent -= 1


def frame(marker: int):
    return np.full((12, 16, 3), marker, dtype=np.uint8)


def main() -> None:
    service = ProbePoseService()
    deliveries: list[tuple[int, str, int]] = []
    coordinator = PoseInferenceCoordinator(
        service,  # type: ignore[arg-type]
        on_display_result=lambda payload: deliveries.append((
            int(payload["camera_id"]),
            str(payload["frame_id"]),
            int(payload["frame"][0, 0, 0]),
        )),
    )
    coordinator.start()

    coordinator.submit_display(
        camera_id=31,
        frame=frame(1),
        frame_id="31-1",
        source_key="source-31",
        captured_at="2026-08-05T00:00:00Z",
        captured_monotonic=1.0,
        config={"pose_detection_enabled": True},
        minimum_interval_seconds=0.0,
    )
    if not service.first_started.wait(1.0):
        raise SystemExit("coordinator did not start the first request")

    coordinator.submit_display(
        camera_id=31,
        frame=frame(2),
        frame_id="31-2",
        source_key="source-31",
        captured_at="2026-08-05T00:00:00.067Z",
        captured_monotonic=1.067,
        config={"pose_detection_enabled": True},
        minimum_interval_seconds=0.0,
    )
    coordinator.submit_display(
        camera_id=31,
        frame=frame(3),
        frame_id="31-3",
        source_key="source-31",
        captured_at="2026-08-05T00:00:00.134Z",
        captured_monotonic=1.134,
        config={"pose_detection_enabled": True},
        minimum_interval_seconds=0.0,
    )
    coordinator.submit_display(
        camera_id=32,
        frame=frame(4),
        frame_id="32-1",
        source_key="source-32",
        captured_at="2026-08-05T00:00:00.100Z",
        captured_monotonic=1.1,
        config={"pose_detection_enabled": True},
        minimum_interval_seconds=0.0,
    )

    formal_result: dict = {}
    formal_error: list[Exception] = []

    def request_formal() -> None:
        try:
            formal_result.update(coordinator.infer_for_analysis(
                camera_id=31,
                frame=frame(3),
                frame_id="31-3",
                source_key="source-31",
                captured_at="2026-08-05T00:00:00.134Z",
                captured_monotonic=1.134,
                config={"pose_detection_enabled": True},
                timeout=2.0,
            ))
        except Exception as exc:
            formal_error.append(exc)

    formal_thread = Thread(target=request_formal)
    formal_thread.start()
    time.sleep(0.02)
    service.release_first.set()
    formal_thread.join(timeout=3.0)
    if formal_thread.is_alive() or formal_error:
        raise SystemExit(f"formal request failed: {formal_error}")

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and len(service.calls) < 3:
        time.sleep(0.01)
    coordinator.stop()

    if service.calls != [1, 3, 4]:
        raise SystemExit(f"latest-frame replacement or fairness failed: {service.calls}")
    if service.max_concurrent != 1:
        raise SystemExit(f"Pose runtime concurrency exceeded one: {service.max_concurrent}")
    if int((formal_result.get("accelerated") or {}).get("marker") or 0) != 3:
        raise SystemExit(f"formal result did not reuse the exact display frame: {formal_result}")
    if sorted(formal_result.get("roles") or []) != ["display", "formal"]:
        raise SystemExit(f"display/formal request was not coalesced: {formal_result}")
    if (31, "31-2", 2) in deliveries or (31, "31-3", 3) not in deliveries:
        raise SystemExit(f"display delivery did not keep only the latest pending frame: {deliveries}")

    status = coordinator.status()
    camera31 = next(item for item in status["cameras"] if item["camera_id"] == 31)
    if camera31["display_replaced"] != 1 or camera31["formal_coalesced"] != 1:
        raise SystemExit(f"coordinator metrics are incomplete: {camera31}")
    if status["queue_depth"] != 0 or status["in_flight"] is not None:
        raise SystemExit(f"coordinator did not drain cleanly: {status}")

    cadence_service = ProbePoseService()
    cadence_service.release_first.set()
    cadence = PoseInferenceCoordinator(cadence_service)  # type: ignore[arg-type]
    cadence.start()
    cadence.submit_display(
        camera_id=31,
        frame=frame(5),
        frame_id="31-5",
        source_key="source-31",
        captured_at="2026-08-05T00:00:01Z",
        captured_monotonic=2.0,
        config={"pose_detection_enabled": True},
        minimum_interval_seconds=0.5,
    )
    if not cadence_service.first_started.wait(0.1) or cadence_service.calls != [5]:
        raise SystemExit(f"first frame was incorrectly delayed by cadence: {cadence_service.calls}")
    cadence.submit_display(
        camera_id=31,
        frame=frame(6),
        frame_id="31-6",
        source_key="source-31",
        captured_at="2026-08-05T00:00:01.020Z",
        captured_monotonic=2.02,
        config={"pose_detection_enabled": True},
        minimum_interval_seconds=0.08,
    )
    cadence.submit_display(
        camera_id=31,
        frame=frame(7),
        frame_id="31-7",
        source_key="source-31",
        captured_at="2026-08-05T00:00:01.040Z",
        captured_monotonic=2.04,
        config={"pose_detection_enabled": True},
        minimum_interval_seconds=0.08,
    )
    time.sleep(0.03)
    if cadence_service.calls != [5]:
        raise SystemExit(f"deferred cadence ran before its deadline: {cadence_service.calls}")
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and cadence_service.calls != [5, 7]:
        time.sleep(0.005)
    cadence_status = cadence.status()
    cadence.stop()
    if cadence_service.calls != [5, 7]:
        raise SystemExit(f"deferred cadence did not retain the latest frame: {cadence_service.calls}")
    cadence_camera = cadence_status["cameras"][0]
    if cadence_camera["display_deferred"] < 2 or cadence_camera["display_replaced"] != 1:
        raise SystemExit(f"deferred cadence metrics are incomplete: {cadence_camera}")

    print({
        "ok": True,
        "calls": service.calls,
        "deliveries": deliveries,
        "max_concurrent": service.max_concurrent,
        "latest_frame_replacement": True,
        "display_formal_coalescing": True,
        "dual_camera_progress": True,
        "deadline_keeps_latest_frame": True,
    })


if __name__ == "__main__":
    main()
