from __future__ import annotations

from pathlib import Path
from threading import Lock, Thread
from typing import Any
import sys
import time

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.camera_agent import CameraAgent, CameraError
import app.camera_agent as camera_module


class FakeCapture:
    def __init__(self, counters: dict[str, Any], counter_lock: Lock) -> None:
        self.counters = counters
        self.counter_lock = counter_lock
        self.released = False
        self.pending = None

    def isOpened(self) -> bool:
        return not self.released

    def get(self, _property: int) -> float:
        return 15.0

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


class FrozenCapture:
    def __init__(self) -> None:
        self.released = False
        self.frame = np.full((48, 64, 3), 112, dtype=np.uint8)

    def isOpened(self) -> bool:
        return not self.released

    def get(self, _property: int) -> float:
        return 15.0

    def read(self):
        if self.released:
            return False, None
        time.sleep(0.005)
        return True, self.frame.copy()

    def release(self) -> None:
        self.released = True


def main() -> None:
    class UnavailableReader:
        source_label = "network stream"

        def status(self):
            return {
                "state": "retrying",
                "decoded_frames": 0,
                "last_error": "stream open failed",
            }

        def wait_for_update(self, _after_sequence: int, timeout: float = 0.0):
            raise RuntimeError(f"offline managed reader unexpectedly waited for {timeout}")

    unavailable_agent = CameraAgent(Path("/tmp/gohome-shared-stream-unavailable-test"))
    unavailable_camera = {"id": 8, "stream_url": "rtsp://example.invalid/offline"}
    unavailable_agent._managed_streams[8] = (unavailable_camera, UnavailableReader())  # type: ignore[assignment]
    fallback_opened = {"value": False}

    def forbidden_fallback(_camera):
        fallback_opened["value"] = True
        raise RuntimeError("offline managed camera opened a second capture")

    unavailable_agent._capture_frame_unlocked = forbidden_fallback  # type: ignore[method-assign]
    try:
        unavailable_agent.capture_frame(unavailable_camera)
    except CameraError as exc:
        if "stream open failed" not in str(exc):
            raise SystemExit(f"managed stream error lost its root cause: {exc}")
    else:
        raise SystemExit("offline managed stream did not report a camera error")
    if fallback_opened["value"]:
        raise SystemExit("offline managed stream opened an unowned fallback capture")

    counters: dict[str, Any] = {"opens": 0, "reads": 0, "opened_sources": []}
    counter_lock = Lock()
    agent = CameraAgent(Path("/tmp/gohome-shared-stream-test"))
    camera = {"id": 9, "stream_url": "rtsp://example.invalid/live"}

    def open_capture(_cv2, source, _is_local):
        with counter_lock:
            counters["opens"] += 1
            counters["opened_sources"].append(str(source))
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
    if not isinstance(cached.get("captured_monotonic"), float):
        raise SystemExit("shared reader did not preserve the source-frame monotonic timestamp")
    if not agent.wait_for_frame_update([camera], {9: str(cached["frame_id"])}, timeout=0.5):
        raise SystemExit("shared reader did not notify the continual tracker about a new frame")
    notified = agent.latest_cached_frame(camera, max_age_seconds=1)
    if notified is None or notified.get("frame_id") == cached.get("frame_id"):
        raise SystemExit("new-frame notification fired without advancing the camera frame")
    cached = notified
    sequence_before = int(str(cached["frame_id"]).rsplit("-", 1)[-1])
    time.sleep(0.05)
    cached_after_preview = agent.latest_cached_frame(camera, max_age_seconds=1)
    sequence_after = int(str(cached_after_preview["frame_id"]).rsplit("-", 1)[-1])
    if sequence_after <= sequence_before:
        raise SystemExit("managed stream stopped when the preview subscribers disconnected")
    if sequence_after > counters["reads"]:
        raise SystemExit(
            "preview subscribers rewrote the shared camera cache and created synthetic frame ids: "
            f"frame_sequence={sequence_after}, source_reads={counters['reads']}"
        )
    status = agent.managed_stream_status()
    if status.get("managed_stream_count") != 1:
        raise SystemExit(f"managed stream status is incorrect: {status}")
    stream_status = status["streams"][0]
    if stream_status.get("source_fps", 0) <= 0 or stream_status.get("decoded_frames", 0) <= 0:
        raise SystemExit(f"shared stream capture metrics are missing: {stream_status}")
    if stream_status.get("latest_frame_age_ms") is None or stream_status.get("advertised_fps") != 15.0:
        raise SystemExit(f"shared stream freshness metrics are incorrect: {stream_status}")
    managed_reader = agent._managed_reader(camera)
    if managed_reader is None or hasattr(managed_reader, "_frame"):
        raise SystemExit("shared reader must publish sequence updates without retaining a duplicate frame")

    transitions: list[dict[str, Any]] = []
    agent.add_source_change_listener(transitions.append)
    previous_source_key = str(cached["source_key"])
    previous_frame_sequence = int(str(cached["frame_id"]).rsplit("-", 1)[-1])
    old_reader = managed_reader
    updated_camera = {**camera, "stream_url": "rtsp://example.invalid/reassigned"}
    agent.reconcile_managed_streams([updated_camera])
    switched = agent.capture_frame(updated_camera, prefer_cache=True, max_cache_age_seconds=1)
    if not old_reader.is_stopped:
        raise SystemExit("source transition did not retire the old camera reader")
    if len(transitions) != 1 or transitions[0].get("reason") != "source_changed":
        raise SystemExit(f"source transition was not published exactly once: {transitions}")
    if counters["opened_sources"][-2:] != [
        "rtsp://example.invalid/live",
        "rtsp://example.invalid/reassigned",
    ]:
        raise SystemExit(f"camera source was not switched in place: {counters['opened_sources']}")
    if str(switched.get("source_key")) == previous_source_key:
        raise SystemExit("source transition reused stale source identity")
    if int(switched.get("stream_generation") or 0) <= int(cached.get("stream_generation") or 0):
        raise SystemExit("source transition did not advance the independent stream generation")
    if int(str(switched["frame_id"]).rsplit("-", 1)[-1]) <= previous_frame_sequence:
        raise SystemExit("source transition reused an old frame id")
    if agent.latest_cached_frame(camera, max_age_seconds=1) is not None:
        raise SystemExit("old camera configuration can still read a stale cached frame")
    managed_reader = agent._managed_reader(updated_camera)
    if managed_reader is None or managed_reader is old_reader:
        raise SystemExit("updated camera did not receive a new managed reader")
    agent.reconcile_managed_streams([])
    if agent.managed_stream_status().get("managed_stream_count") != 0:
        raise SystemExit("removed camera retained a managed stream reader")

    class StuckReader:
        is_stopped = False

        def stop(self):
            return False

    blocked_agent = CameraAgent(Path("/tmp/gohome-source-transition-stop-test"))
    blocked_camera = {"id": 12, "stream_url": "rtsp://example.invalid/old"}
    replacement_camera = {"id": 12, "stream_url": "rtsp://example.invalid/new"}
    stuck_reader = StuckReader()
    blocked_agent._managed_streams[12] = (blocked_camera, stuck_reader)  # type: ignore[assignment]
    blocked_agent._shared_streams[blocked_agent._frame_cache_key(blocked_camera)] = stuck_reader  # type: ignore[assignment]
    replacement_attempted = {"value": False}

    def forbidden_replacement(*_args, **_kwargs):
        replacement_attempted["value"] = True
        raise AssertionError("source transition started a replacement before old reader stopped")

    blocked_agent._acquire_shared_stream = forbidden_replacement  # type: ignore[method-assign]
    try:
        blocked_agent.reconcile_managed_streams([replacement_camera])
    except CameraError as exc:
        if "did not stop" not in str(exc):
            raise SystemExit(f"reader stop failure lost its root cause: {exc}")
    except Exception as exc:
        raise SystemExit(f"source transition did not fail at the stop boundary: {exc}") from exc
    else:
        raise SystemExit("source transition reported success while the old reader was still active")
    if replacement_attempted["value"]:
        raise SystemExit("source transition created a replacement reader after stop failure")
    if blocked_agent._managed_streams.get(12, (None, None))[1] is not stuck_reader:
        raise SystemExit("failed source transition lost the still-active reader ownership")
    if blocked_agent._shared_streams.get(blocked_agent._frame_cache_key(blocked_camera)) is not stuck_reader:
        raise SystemExit("failed source transition removed the active reader from the shared registry")
    try:
        blocked_agent.capture_frame(replacement_camera)
    except CameraError as exc:
        if "still waiting" not in str(exc):
            raise SystemExit(f"pending source transition was not exposed to capture consumers: {exc}")
    else:
        raise SystemExit("pending source transition opened a fallback capture")

    semantic_agent = CameraAgent(Path("/tmp/gohome-frame-semantics-test"))
    semantic_camera = {"id": 11, "stream_url": "rtsp://example.invalid/semantics"}
    semantic_frame = np.full((48, 64, 3), 126, dtype=np.uint8)
    content_identity = semantic_agent._store_latest_frame(
        semantic_camera,
        semantic_frame,
        "semantic stream",
        stream_generation=1,
    )
    if content_identity is None:
        raise SystemExit("content frame identity was not created")
    first_delivery = semantic_agent._store_latest_live_frame(
        semantic_camera,
        semantic_frame,
        "semantic stream",
        stream_generation=1,
        content_identity=content_identity,
    )
    content_before_repeat = semantic_agent.latest_cached_frame(semantic_camera, max_age_seconds=1)
    repeated_delivery = semantic_agent._store_latest_live_frame(
        semantic_camera,
        semantic_frame.copy(),
        "semantic stream",
        stream_generation=1,
    )
    content_after_repeat = semantic_agent.latest_cached_frame(semantic_camera, max_age_seconds=1)
    live_after_repeat = semantic_agent.latest_live_frame(semantic_camera, max_age_seconds=1)
    if not all((first_delivery, repeated_delivery, content_before_repeat, content_after_repeat, live_after_repeat)):
        raise SystemExit("content/live frame semantic fixture is incomplete")
    if content_after_repeat["frame_id"] != content_before_repeat["frame_id"]:
        raise SystemExit("repeated live delivery advanced the analysis frame identity")
    if content_after_repeat["captured_monotonic"] != content_before_repeat["captured_monotonic"]:
        raise SystemExit("repeated live delivery changed the analysis capture timestamp")
    if live_after_repeat["delivery_frame_id"] == first_delivery["delivery_frame_id"]:
        raise SystemExit("repeated decoded frame did not advance the live delivery identity")
    if not live_after_repeat.get("content_repeated"):
        raise SystemExit("repeated live delivery lost its content classification")
    if semantic_agent.wait_for_frame_update(
        [semantic_camera],
        {11: str(content_before_repeat["frame_id"])},
        timeout=0.01,
    ):
        raise SystemExit("repeated live delivery woke the analysis-frame consumer")
    semantic_agent._clear_camera_cache(11)
    if (
        semantic_agent.latest_cached_frame(semantic_camera, max_age_seconds=1) is not None
        or semantic_agent.latest_live_frame(semantic_camera, max_age_seconds=1) is not None
    ):
        raise SystemExit("camera invalidation did not clear both frame semantics")

    frozen_agent = CameraAgent(Path("/tmp/gohome-frozen-stream-test"))
    fingerprint_base = np.zeros((48, 64, 3), dtype=np.uint8)
    fingerprint_local_change = fingerprint_base.copy()
    fingerprint_local_change[7:12, 7:12] = 255
    if frozen_agent.frame_content_fingerprint(fingerprint_base) == frozen_agent.frame_content_fingerprint(fingerprint_local_change):
        raise SystemExit("content fingerprint missed a localized frame change between the old 16-pixel samples")
    frozen_agent._open_stream_capture = lambda *_args: FrozenCapture()  # type: ignore[method-assign]
    frozen_camera = {"id": 10, "stream_url": "rtsp://example.invalid/frozen"}
    frozen_transitions: list[dict[str, Any]] = []
    stale_pose_state = {"present": True}

    def clear_stale_pose(transition: dict[str, Any]) -> None:
        frozen_transitions.append(transition)
        stale_pose_state["present"] = False

    frozen_agent.add_source_change_listener(clear_stale_pose)
    original_frozen_seconds = camera_module.STREAM_FROZEN_RECONNECT_SECONDS
    camera_module.STREAM_FROZEN_RECONNECT_SECONDS = 0.03
    try:
        frozen_agent.reconcile_managed_streams([frozen_camera])
        deadline = time.monotonic() + 0.5
        while not frozen_transitions and time.monotonic() < deadline:
            time.sleep(0.01)
        frozen_status = frozen_agent.managed_stream_status()["streams"][0]
        if frozen_status.get("decoded_frames", 0) <= 1:
            raise SystemExit(f"frozen stream test did not decode repeated frames: {frozen_status}")
        if frozen_status.get("unique_frames") != 1 or frozen_status.get("repeated_frames", 0) <= 0:
            raise SystemExit(f"repeated pixels were counted as content frames: {frozen_status}")
        if frozen_status.get("live_deliveries", 0) <= frozen_status.get("unique_frames", 0):
            raise SystemExit(f"valid repeated frames did not maintain live delivery cadence: {frozen_status}")
        if frozen_status.get("effective_fps") != 0.0:
            raise SystemExit(f"frozen stream still reports an effective FPS: {frozen_status}")
        if len(frozen_transitions) != 1 or frozen_transitions[0].get("reason") != "stream_pixels_frozen":
            raise SystemExit(f"frozen stream did not publish one lifecycle invalidation: {frozen_transitions}")
        if stale_pose_state["present"]:
            raise SystemExit("frozen stream lifecycle invalidation did not clear stale pose state")
        if frozen_agent.latest_cached_frame(frozen_camera, max_age_seconds=1) is not None:
            raise SystemExit("frozen stream retained its last unique frame after invalidation")
        if frozen_agent.latest_live_frame(frozen_camera, max_age_seconds=1) is not None:
            raise SystemExit("frozen stream retained its last live delivery after invalidation")
        if int(frozen_status.get("stream_generation") or 0) < 2:
            raise SystemExit(f"frozen stream did not advance its generation: {frozen_status}")
    finally:
        camera_module.STREAM_FROZEN_RECONNECT_SECONDS = original_frozen_seconds
        frozen_agent.reconcile_managed_streams([])

    print({
        "ok": True,
        "capture_opens": counters["opens"],
        "source_reads": counters["reads"],
        "subscribers": len(consumers),
        "managed_stream_survived_preview": True,
        "new_frame_notification": True,
        "reader_retains_duplicate_frame": False,
        "bounded_content_and_live_caches": True,
        "offline_fallback_capture": False,
        "capture_metrics": stream_status,
        "source_transition": transitions[0],
        "old_reader_retired": True,
        "stale_cache_rejected": True,
        "repeated_pixels_counted_as_content": False,
        "repeated_pixels_delivered_before_freeze": True,
        "localized_frame_change_detected": True,
        "analysis_and_live_frame_semantics_separated": True,
        "frozen_stream_invalidated_stale_pose": True,
        "frozen_stream_invalidated_live_delivery": True,
    })


if __name__ == "__main__":
    main()
