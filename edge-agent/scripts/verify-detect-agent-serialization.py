from __future__ import annotations

from pathlib import Path
from threading import Lock, Thread
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.detect_agent import DetectAgent


class ConcurrentProbePipeline:
    def __init__(self) -> None:
        self.lock = Lock()
        self.active = 0
        self.max_active = 0

    def analyze(self, frame, previous_frame=None, config=None):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.08)
        with self.lock:
            self.active -= 1
        return {"ok": True}


def main() -> None:
    agent = DetectAgent.__new__(DetectAgent)
    agent.pipeline = ConcurrentProbePipeline()
    agent._initialize_inference_lock()

    threads = [
        Thread(target=agent.analyze_frame_with_config, args=(object(),), kwargs={"config": {}}),
        Thread(target=agent.analyze_frame_with_config, args=(object(),), kwargs={"config": {}}),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    if any(thread.is_alive() for thread in threads):
        raise SystemExit("serialized inference threads did not finish")
    if agent.pipeline.max_active != 1:
        raise SystemExit(f"inference overlapped across requests: {agent.pipeline.max_active}")

    print({"ok": True, "max_concurrent_inference": agent.pipeline.max_active})


if __name__ == "__main__":
    main()
