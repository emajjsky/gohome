from __future__ import annotations

from pathlib import Path
import sys
from threading import Barrier, Lock, Thread
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.worker import EdgeWorker


def main() -> None:
    worker = EdgeWorker(
        storage=None,
        camera_agent=None,
        detect_agent=None,
        event_agent=None,
    )
    barrier = Barrier(2)
    state_lock = Lock()
    active = 0
    maximum_active = 0
    calls: list[int] = []

    def serialized(camera, _rules, *, adaptive_pose=False):
        nonlocal active, maximum_active
        if not adaptive_pose:
            raise SystemExit("scheduled/manual analysis lost its explicit pose policy")
        with state_lock:
            active += 1
            maximum_active = max(maximum_active, active)
            calls.append(int(camera["id"]))
        time.sleep(0.03)
        with state_lock:
            active -= 1
        return {"ok": True, "camera_id": int(camera["id"])}

    worker._process_camera_serialized = serialized  # type: ignore[method-assign]
    def invoke() -> None:
        barrier.wait(timeout=2)
        worker.process_camera({"id": 31}, {}, adaptive_pose=True)

    threads = [Thread(target=invoke), Thread(target=invoke)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
        if thread.is_alive():
            raise SystemExit("same-camera analysis did not complete")

    if maximum_active != 1 or calls != [31, 31]:
        raise SystemExit(f"same-camera analysis overlapped: maximum={maximum_active}, calls={calls}")

    source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    worker_source = (ROOT / "app" / "worker.py").read_text(encoding="utf-8")
    if "with self.camera_analysis_guard(int(camera[\"id\"]))" not in worker_source:
        raise SystemExit("formal worker analysis does not use the camera ownership guard")
    if "run_in_threadpool(capture_with_pipeline, camera_id)" not in source:
        raise SystemExit("admin capture does not use the formal worker pipeline")

    print({
        "ok": True,
        "same_camera_analysis_is_serial": True,
        "admin_capture_uses_worker_guard": True,
    })


if __name__ == "__main__":
    main()
