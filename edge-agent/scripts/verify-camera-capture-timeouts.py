from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.camera_agent import CameraAgent


class FakeCapture:
    def isOpened(self) -> bool:
        return True

    def set(self, _key, _value) -> bool:
        return True


class FakeCv2:
    CAP_FFMPEG = 1900
    CAP_PROP_BUFFERSIZE = 38
    CAP_PROP_OPEN_TIMEOUT_MSEC = 53
    CAP_PROP_READ_TIMEOUT_MSEC = 54

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def VideoCapture(self, *args):
        self.calls.append(args)
        return FakeCapture()


def main() -> None:
    cv2 = FakeCv2()
    agent = CameraAgent(Path("/tmp/gohome-capture-timeout-test"))
    capture = agent._open_stream_capture(cv2, "rtsp://example.invalid/live", False)
    if not capture.isOpened():
        raise SystemExit("fake capture did not open")
    if not cv2.calls or len(cv2.calls[0]) != 3:
        raise SystemExit(f"network timeouts were not passed at open time: {cv2.calls}")
    params = list(cv2.calls[0][2])
    expected = {
        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC: 8000,
        cv2.CAP_PROP_READ_TIMEOUT_MSEC: 5000,
    }
    actual = dict(zip(params[::2], params[1::2]))
    if any(actual.get(key) != value for key, value in expected.items()):
        raise SystemExit(f"capture timeout params are wrong: {actual}")
    print({"ok": True, "open_timeout_ms": 8000, "read_timeout_ms": 5000})


if __name__ == "__main__":
    main()
