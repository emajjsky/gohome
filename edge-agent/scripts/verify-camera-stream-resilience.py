from __future__ import annotations

from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.camera_agent import CameraAgent
import app.camera_agent as camera_module


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
        FakeCapture([black, recovered, recovered]),
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
        first = decode_part(next(stream))
        second = decode_part(next(stream))
        third = decode_part(next(stream))
        stream.close()
    finally:
        camera_module.time.sleep = original_sleep

    if opens["count"] < 2:
        raise SystemExit("stream did not reopen capture after a read failure")
    if float(first.mean()) < 80:
        raise SystemExit("first valid frame was not emitted")
    if float(second.mean()) < 80:
        raise SystemExit("transient black frame should retain the last valid frame")
    if float(third.mean()) < 120:
        raise SystemExit("stream did not recover to the next valid frame")
    print({"ok": True, "capture_opens": opens["count"], "transient_black_retained": True, "recovered": True})


if __name__ == "__main__":
    main()
