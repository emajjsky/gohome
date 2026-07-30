from __future__ import annotations

from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.camera_agent import CameraAgent
from app.rule_engine import RuleEngine
import app.camera_agent as camera_module
import app.rule_engine as rule_engine_module


class FakeCapture:
    def __init__(self, frames: list[np.ndarray | None]) -> None:
        self.frames = list(frames)
        self.released = False

    def isOpened(self) -> bool:
        return not self.released

    def read(self):
        if not self.frames:
            return False, None
        frame = self.frames.pop(0)
        return (frame is not None), frame

    def release(self) -> None:
        self.released = True


def decode_part(part: bytes) -> np.ndarray:
    import cv2  # type: ignore

    start = part.index(b"\r\n\r\n") + 4
    end = part.rindex(b"\r\n")
    encoded = np.frombuffer(part[start:end], dtype=np.uint8)
    frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if frame is None:
        raise SystemExit("failed to decode generated MJPEG frame")
    return frame


def main() -> None:
    normal = np.full((48, 64, 3), 96, dtype=np.uint8)
    recovered = np.full((48, 64, 3), 144, dtype=np.uint8)
    black = np.zeros((48, 64, 3), dtype=np.uint8)
    captures = [
        FakeCapture([normal, None]),
        FakeCapture([black, black, black, black, black]),
        FakeCapture([recovered, recovered]),
    ]
    opens = {"count": 0}
    agent = CameraAgent(Path("/tmp/gohome-stream-test"))

    def open_capture(_cv2, _source, _is_local):
        opens["count"] += 1
        return captures.pop(0) if captures else FakeCapture([recovered, recovered])

    agent._open_stream_capture = open_capture  # type: ignore[method-assign]
    original_sleep = camera_module.time.sleep
    camera_module.time.sleep = lambda _seconds: None
    try:
        stream = agent.mjpeg_frames(
            {"id": 1, "stream_url": "rtsp://example.invalid/live"},
            fps=5,
            jpeg_quality=90,
            max_width=64,
            max_height=48,
            drop_stale_frames=0,
        )
        frames = [decode_part(next(stream)) for _ in range(7)]
        stream.close()
    finally:
        camera_module.time.sleep = original_sleep

    if opens["count"] < 3:
        raise SystemExit("stream did not reopen capture after read failure and sustained black frames")
    if float(frames[0].mean()) < 80:
        raise SystemExit("first valid frame was not emitted")
    if any(float(frame.mean()) < 80 for frame in frames[1:6]):
        raise SystemExit("black decoder frames must never replace the last valid preview frame")
    if float(frames[-1].mean()) < 120:
        raise SystemExit("stream did not recover to the next valid frame")

    camera = {"id": 7, "name": "客厅摄像头"}
    rules = {"offline_enabled": True}
    engine = RuleEngine()
    original_clock = rule_engine_module.utc_now
    try:
        from datetime import datetime, timedelta, timezone

        started_at = datetime(2026, 7, 30, 14, 8, 0, tzinfo=timezone.utc)
        current_time = [started_at]
        rule_engine_module.utc_now = lambda: current_time[0]
        first = engine.evaluate_camera_error(camera, rules, "timeout")
        recovered = engine.record_camera_online(7)
        if first.candidates or not recovered or recovered.get("confirmed"):
            raise SystemExit("one transient stream timeout must remain a reconnect diagnostic")

        current_time[0] = started_at + timedelta(minutes=1)
        first = engine.evaluate_camera_error(camera, rules, "timeout")
        current_time[0] += timedelta(seconds=8)
        second = engine.evaluate_camera_error(camera, rules, "timeout")
        current_time[0] += timedelta(seconds=8)
        third = engine.evaluate_camera_error(camera, rules, "timeout")
        current_time[0] += timedelta(seconds=8)
        repeated = engine.evaluate_camera_error(camera, rules, "timeout")
        if first.candidates or second.candidates or len(third.candidates) != 1 or repeated.candidates:
            raise SystemExit("only the first sustained camera outage must create one event candidate")
        recovered = engine.record_camera_online(7)
        if not recovered or not recovered.get("confirmed") or recovered.get("failure_count") != 4:
            raise SystemExit(f"confirmed outage recovery is not auditable: {recovered}")
    finally:
        rule_engine_module.utc_now = original_clock
    print({
        "ok": True,
        "capture_opens": opens["count"],
        "black_frames_suppressed": 5,
        "sustained_black_reconnected": True,
        "recovered": True,
        "transient_timeout_suppressed": True,
        "sustained_outage_confirmed_once": True,
    })


if __name__ == "__main__":
    main()
