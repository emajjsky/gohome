from __future__ import annotations

from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.camera_agent import CameraAgent, stream_reconnect_delay
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


class AheadOfNotificationReader:
    """Expose the cache-ahead race without depending on thread scheduling."""

    is_stopped = False

    def __init__(self) -> None:
        self.sequence = 0

    def wait_for_update(self, _after_sequence: int, timeout: float = 3.5):
        del timeout
        self.sequence += 1
        return self.sequence, ""


def main() -> None:
    delays = [stream_reconnect_delay(index) for index in range(1, 8)]
    if delays != [0.5, 1.0, 2.0, 4.0, 8.0, 8.0, 8.0]:
        raise SystemExit(f"stream reconnect backoff is not bounded: {delays}")
    normal = np.full((48, 64, 3), 96, dtype=np.uint8)
    status_agent = CameraAgent(Path("/tmp/gohome-near-black-status-test"))
    status_reader = camera_module._SharedStreamReader(
        agent=status_agent,
        camera={"id": 2, "stream_url": "rtsp://example.invalid/status"},
        source="rtsp://example.invalid/status",
        is_local_source=False,
        source_label="status stream",
        stream_generation=1,
    )
    cv2 = camera_module._load_cv2()
    now = camera_module.time.monotonic()
    for index, level in enumerate((96, 104)):
        disposition = status_reader._record_frame(
            cv2,
            np.full((48, 64, 3), level, dtype=np.uint8),
            now - 0.2 + index * 0.1,
            1.0,
        )
        if disposition != "unique":
            raise SystemExit(f"valid status probe frame was rejected: {disposition}")
        status_reader._sequence += 1
    if status_reader.status().get("effective_fps", 0) <= 0:
        raise SystemExit("status probe did not establish a nonzero effective FPS")
    disposition = status_reader._record_frame(cv2, np.zeros((48, 64, 3), dtype=np.uint8), now, 1.0)
    near_black_status = status_reader.status()
    if (
        disposition != "near_black"
        or near_black_status.get("state") != "stale"
        or near_black_status.get("effective_fps") != 0.0
        or near_black_status.get("near_black_frames") != 1
    ):
        raise SystemExit(f"first near-black frame did not invalidate live status: {near_black_status}")
    recovered = [
        np.full((48, 64, 3), 140 + index % 40, dtype=np.uint8)
        for index in range(256)
    ]
    black = [np.full((48, 64, 3), index % 3, dtype=np.uint8) for index in range(5)]
    captures = [
        FakeCapture([normal, None]),
        FakeCapture(black),
        FakeCapture(recovered),
    ]
    opens = {"count": 0}
    agent = CameraAgent(Path("/tmp/gohome-stream-test"))

    def open_capture(_cv2, _source, _is_local):
        opens["count"] += 1
        return captures.pop(0) if captures else FakeCapture([
            np.full((48, 64, 3), 150 + index % 40, dtype=np.uint8)
            for index in range(512)
        ])

    agent._open_stream_capture = open_capture  # type: ignore[method-assign]
    stored_means: list[float] = []
    original_store = agent._store_latest_frame

    def record_store(camera, frame, source_label, *, stream_generation=0):
        stored_means.append(float(frame.mean()))
        return original_store(
            camera,
            frame,
            source_label,
            stream_generation=stream_generation,
        )

    agent._store_latest_frame = record_store  # type: ignore[method-assign]
    original_sleep = camera_module.time.sleep
    original_near_black_seconds = camera_module.STREAM_NEAR_BLACK_RECONNECT_SECONDS
    camera_module.time.sleep = lambda _seconds: None
    camera_module.STREAM_NEAR_BLACK_RECONNECT_SECONDS = 0.0
    try:
        stream = agent.raw_frames(
            {"id": 1, "stream_url": "rtsp://example.invalid/live"},
            fps=5,
            max_width=64,
            max_height=48,
        )
        captures_out = [next(stream) for _ in range(7)]
        stream.close()
    finally:
        camera_module.time.sleep = original_sleep
        camera_module.STREAM_NEAR_BLACK_RECONNECT_SECONDS = original_near_black_seconds

    if opens["count"] < 3:
        raise SystemExit("stream did not reopen capture after read failure and sustained black frames")
    frames = [capture["frame"] for capture in captures_out]
    if float(frames[0].mean()) < 80:
        raise SystemExit("first valid frame was not emitted")
    if any(float(frame.mean()) < 120 for frame in frames[1:]):
        raise SystemExit("near-black decoder frames entered the effective live stream")
    if float(frames[-1].mean()) < 120:
        raise SystemExit("stream did not recover to the next valid frame")
    frame_ids = [str(capture.get("frame_id") or "") for capture in captures_out]
    if len(set(frame_ids)) != len(frame_ids) or any(not frame_id for frame_id in frame_ids):
        raise SystemExit(f"effective frames do not have unique source-owned identities: {frame_ids}")
    if int(captures_out[1].get("stream_generation") or 0) <= int(captures_out[0].get("stream_generation") or 0):
        raise SystemExit("near-black recovery did not advance the stream generation")
    if any(mean < 80 for mean in stored_means):
        raise SystemExit(f"near-black frames entered the shared effective-frame cache: {stored_means}")
    if agent._frame_sequences.get("1") != len(stored_means):
        raise SystemExit("effective frame identity advanced without a source-owned cache write")

    race_agent = CameraAgent(Path("/tmp/gohome-stream-cache-ahead-test"))
    race_reader = AheadOfNotificationReader()
    cached_frames = [
        {"frame": normal, "frame_id": "9-1"},
        {"frame": normal, "frame_id": "9-1"},
        {"frame": np.full_like(normal, 112), "frame_id": "9-2"},
    ]
    race_agent._acquire_shared_stream = lambda *args, **kwargs: race_reader  # type: ignore[method-assign]
    race_agent._release_shared_stream = lambda *args, **kwargs: None  # type: ignore[method-assign]
    race_agent.latest_cached_frame = (  # type: ignore[method-assign]
        lambda *args, **kwargs: cached_frames.pop(0)
    )
    race_stream = race_agent.raw_frames(
        {"id": 9, "stream_url": "rtsp://example.invalid/cache-ahead"},
        fps=30,
        max_width=64,
        max_height=48,
    )
    race_frame_ids = [str(next(race_stream)["frame_id"]) for _ in range(2)]
    race_stream.close()
    if race_frame_ids != ["9-1", "9-2"]:
        raise SystemExit(f"cache-ahead notification emitted a duplicate frame: {race_frame_ids}")

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
        "near_black_frames_suppressed": 5,
        "near_black_effective_fps": near_black_status["effective_fps"],
        "old_pixels_republished": False,
        "effective_frame_ids": frame_ids,
        "cache_ahead_duplicate_suppressed": True,
        "sustained_black_reconnected": True,
        "recovered": True,
        "transient_timeout_suppressed": True,
        "sustained_outage_confirmed_once": True,
        "reconnect_delays": delays,
    })


if __name__ == "__main__":
    main()
