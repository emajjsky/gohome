#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
import os
import sys
import time

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.h264_publisher import (
    H264PublisherError,
    H264StreamPublisher,
    build_rtsps_publish_url,
    redact_publish_url,
)
from app.live_relay_agent import LiveRelayAgent
from app.vision.privacy_background import PrivacyCalibrationRequired


def wait_until(predicate, *, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition was not satisfied before timeout")


class FakeStdin:
    def __init__(self, descriptor: int, lifecycle: list[str]) -> None:
        self._descriptor = int(descriptor)
        self._lifecycle = lifecycle
        self.closed = False

    def fileno(self) -> int:
        return self._descriptor

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._lifecycle.append("stdin_close")
        os.close(self._descriptor)


class FakeProcess:
    next_pid = 4100

    def __init__(self, command: list[str]) -> None:
        read_fd, write_fd = os.pipe()
        self.command = list(command)
        self.lifecycle: list[str] = []
        self.stdin = FakeStdin(write_fd, self.lifecycle)
        self.stderr = None
        self._read_fd = read_fd
        self.returncode = None
        self.pid = FakeProcess.next_pid
        FakeProcess.next_pid += 1

    def poll(self):
        return self.returncode

    def terminate(self) -> None:
        self.lifecycle.append("terminate")
        self._finish(-15)

    def kill(self) -> None:
        self.lifecycle.append("kill")
        self._finish(-9)

    def wait(self, timeout=None):
        del timeout
        if self.returncode is None:
            self._finish(0)
        return self.returncode

    def _finish(self, returncode: int) -> None:
        if self.returncode is not None:
            return
        self.returncode = int(returncode)
        try:
            os.close(self._read_fd)
        except OSError:
            pass


class DelayedReaderProcess(FakeProcess):
    def __init__(self, command: list[str], *, delay_seconds: float) -> None:
        super().__init__(command)
        self._reader = Thread(
            target=self._drain_after_delay,
            args=(float(delay_seconds),),
            daemon=True,
        )
        self._reader.start()

    def _drain_after_delay(self, delay_seconds: float) -> None:
        time.sleep(delay_seconds)
        while self.returncode is None:
            try:
                if not os.read(self._read_fd, 65536):
                    return
            except OSError:
                return


class ProcessFactory:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.processes: list[FakeProcess] = []

    def __call__(self, command: list[str]) -> FakeProcess:
        process = FakeProcess(command)
        self.commands.append(list(command))
        self.processes.append(process)
        return process


class SettingsStub:
    live_relay_enabled = True
    live_relay_fps = 15
    live_relay_width = 640
    live_relay_height = 360
    media_publish_base_url = "rtsps://media.example.invalid:8322"
    media_publish_ffmpeg_path = sys.executable
    media_publish_bitrate_kbps = 1200
    media_publish_write_timeout_seconds = 0.2
    media_publish_startup_timeout_seconds = 0.5
    device_api_token = "device-token"
    require_issued_device_token = False


class CameraAgentStub:
    def __init__(self, stop_event: Event, *, frame_count: int = 8) -> None:
        self.stop_event = stop_event
        self.frame_count = int(frame_count)

    def raw_frames(self, camera, **options):
        assert options == {"fps": 15, "max_width": 640, "max_height": 360}
        for index in range(self.frame_count):
            yield {
                "frame": np.full((36, 64, 3), index, dtype=np.uint8),
                "frame_id": f"{camera['id']}-{index + 1}",
                "source_key": f"camera-{camera['id']}-source",
                "captured_at": "2026-08-03T08:00:00+00:00",
                "captured_monotonic": time.monotonic(),
            }
        self.stop_event.set()


class PrivacyRendererStub:
    def __init__(self, blocked_frames: int = 0) -> None:
        self.render_calls = 0
        self.blocked_frames = max(0, int(blocked_frames))

    def render_image(
        self,
        camera_id,
        frame,
        mode,
        *,
        source_key,
        frame_id,
        captured_at,
        captured_monotonic=None,
    ):
        assert source_key == f"camera-{camera_id}-source"
        assert frame_id.startswith(f"{camera_id}-")
        assert captured_at == "2026-08-03T08:00:00+00:00"
        assert captured_monotonic is not None
        assert mode == "skeleton"
        self.render_calls += 1
        if self.render_calls <= self.blocked_frames:
            raise PrivacyCalibrationRequired(camera_id, "stream_revalidation_required")
        return frame


class PublisherRecorder:
    def __init__(self, **configuration) -> None:
        self.configuration = dict(configuration)
        self.submissions = []
        self.pauses = []
        self.closed = False

    def submit(self, frame, **metadata) -> None:
        self.submissions.append((frame.copy(), dict(metadata)))

    def pause(self, reason: str) -> None:
        self.pauses.append(str(reason))

    def close(self) -> None:
        self.closed = True

    def status(self):
        return {"frames_written": len(self.submissions), "closed": self.closed}


class PublisherRecorderFactory:
    def __init__(self) -> None:
        self.instances: list[PublisherRecorder] = []

    def __call__(self, **configuration) -> PublisherRecorder:
        instance = PublisherRecorder(**configuration)
        self.instances.append(instance)
        return instance


def verify_url_and_command_contract() -> None:
    secret = "token with / reserved?characters"
    url = build_rtsps_publish_url(
        "rtsps://media.example.invalid:8322/root",
        device_id="edge/alpha",
        device_token=secret,
        camera_id="camera 2",
    )
    assert url.startswith("rtsps://edge%2Falpha:token%20with%20%2F%20reserved%3Fcharacters@")
    assert url.endswith("/root/live/edge%2Falpha/camera%202")
    assert secret not in redact_publish_url(url)
    for invalid in (
        "rtsp://media.example.invalid:8322",
        "https://media.example.invalid",
        "rtsps://user:pass@media.example.invalid",
        "rtsps://media.example.invalid?token=secret",
    ):
        try:
            build_rtsps_publish_url(invalid, device_id="edge", device_token="token", camera_id="2")
        except H264PublisherError:
            pass
        else:
            raise AssertionError(f"invalid publish URL was accepted: {invalid}")

    publisher = H264StreamPublisher(
        camera_id=2,
        publish_url=url,
        ffmpeg_path="/usr/bin/ffmpeg",
        fps=15,
        bitrate_kbps=1200,
        write_timeout_seconds=0.2,
        process_factory=ProcessFactory(),
    )
    command = publisher.command(width=641, height=359)
    joined = " ".join(command)
    for required in (
        "-c:v libx264",
        "-preset ultrafast",
        "-tune zerolatency",
        "-pix_fmt yuv420p",
        "-bf 0",
        "-g 15",
        "-rtsp_transport tcp",
        "-fflags +genpts",
        "-fps_mode passthrough",
        "-progress pipe:2",
        "-stats_period 0.25",
        "pad=ceil(iw/2)*2:ceil(ih/2)*2",
    ):
        assert required in joined, required
    assert "use_wallclock_as_timestamps" not in joined
    assert "mjpeg" not in joined
    publisher.close()


def verify_latest_frame_and_context_restart() -> None:
    factory = ProcessFactory()
    publisher = H264StreamPublisher(
        camera_id=2,
        publish_url="rtsps://edge:secret-token@media.example.invalid:8322/live/edge/2",
        ffmpeg_path="ffmpeg",
        fps=15,
        bitrate_kbps=1200,
        write_timeout_seconds=0.2,
        process_factory=factory,
    )
    first_write_started = Event()
    release_first_write = Event()
    payload_first_bytes = []

    def controlled_write(_process, payload, *, control_revision):
        assert not publisher._control_changed(control_revision)
        payload_first_bytes.append(int(payload[0]))
        if len(payload_first_bytes) == 1:
            first_write_started.set()
            assert release_first_write.wait(1.0)

    publisher._write_all = controlled_write
    base = np.zeros((36, 64, 3), dtype=np.uint8)
    publisher.submit(
        base,
        frame_id="2-1",
        captured_monotonic=time.monotonic(),
        privacy_mode="original",
        source_key="source-a",
    )
    wait_until(first_write_started.is_set)
    for index in range(2, 21):
        frame = np.full((36, 64, 3), index, dtype=np.uint8)
        if index == 20:
            frame = frame[:, ::-1]
            assert not frame.flags.c_contiguous
        publisher.submit(
            frame,
            frame_id=f"2-{index}",
            captured_monotonic=time.monotonic(),
            privacy_mode="original",
            source_key="source-a",
        )
    release_first_write.set()
    wait_until(lambda: publisher.status()["frames_written"] == 2)
    status = publisher.status()
    assert status["replaced_pending"] == 18
    assert status["last_written_frame_id"] == "2-20"
    assert payload_first_bytes == [0, 20]
    assert status["process_starts"] == 1
    assert status["raw_input_bytes_written"] == base.nbytes * 2
    assert "bytes_written" not in status
    active_process = factory.processes[0]
    assert publisher._consume_progress_line(active_process, "frame=2")
    assert publisher._consume_progress_line(active_process, "fps=14.92")
    assert publisher._consume_progress_line(active_process, "stream_0_0_q=9.0")
    assert publisher._consume_progress_line(active_process, "out_time=00:00:00.133333")
    assert not publisher._consume_progress_line(active_process, "Packet corrupt")
    progress_status = publisher.status()
    assert progress_status["publish_ready"]
    assert progress_status["encoded_frames_reported"] == 2
    assert progress_status["stderr_tail"] == []

    publisher.submit(
        np.full((36, 64, 3), 21, dtype=np.uint8),
        frame_id="2-21",
        captured_monotonic=time.monotonic(),
        privacy_mode="skeleton",
        source_key="source-a",
    )
    wait_until(lambda: publisher.status()["frames_written"] == 3)
    assert publisher.status()["process_starts"] == 2
    assert publisher.status()["process_stop_reasons"] == {"context_changed": 1}
    assert factory.processes[0].returncode is not None
    assert publisher.status()["context"]["source_generation"] != "source-a"

    factory.processes[-1].terminate()
    publisher.submit(
        np.full((36, 64, 3), 22, dtype=np.uint8),
        frame_id="2-22",
        captured_monotonic=time.monotonic(),
        privacy_mode="skeleton",
        source_key="source-a",
    )
    wait_until(lambda: publisher.status()["process_failures"] == 1)
    assert publisher.status()["last_error"] == "FFmpeg exited with code -15"
    time.sleep(0.55)
    publisher.submit(
        np.full((36, 64, 3), 23, dtype=np.uint8),
        frame_id="2-23",
        captured_monotonic=time.monotonic(),
        privacy_mode="skeleton",
        source_key="source-a",
    )
    wait_until(lambda: publisher.status()["frames_written"] == 4)
    assert publisher.status()["process_starts"] == 3
    recovered = publisher.status()
    assert recovered["last_recovered_error"] == "FFmpeg exited with code -15"
    assert recovered["last_recovered_at_monotonic"] is not None

    publisher.pause(f"publisher failed at {publisher.publish_url}")
    wait_until(lambda: not publisher.status()["running"])
    publisher._read_stderr(SimpleNamespace(stderr=[f"failed {publisher.publish_url}".encode()]))
    serialized_status = repr(publisher.status())
    assert "secret-token" not in serialized_status
    publisher.close()
    publisher.close()


def verify_blocked_pipe_timeout_and_restart() -> None:
    factory = ProcessFactory()
    publisher = H264StreamPublisher(
        camera_id=3,
        publish_url="rtsps://edge:token@media.example.invalid:8322/live/edge/3",
        ffmpeg_path="ffmpeg",
        fps=15,
        bitrate_kbps=1200,
        write_timeout_seconds=0.1,
        startup_timeout_seconds=0.1,
        process_factory=factory,
    )
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    publisher.submit(
        frame,
        frame_id="3-1",
        captured_monotonic=time.monotonic(),
        privacy_mode="original",
        source_key="source-a",
    )
    wait_until(lambda: publisher.status()["process_failures"] == 1)
    first_failure = publisher.status()
    assert first_failure["last_error"] == "FFmpeg frame write timed out"
    assert first_failure["partial_frame_aborts"] == 1
    assert 0 < first_failure["last_partial_frame_bytes"] < frame.nbytes
    assert first_failure["last_partial_frame_size"] == frame.nbytes
    assert factory.processes[0].lifecycle[:2] == ["kill", "stdin_close"]
    time.sleep(0.55)
    publisher.submit(
        frame,
        frame_id="3-2",
        captured_monotonic=time.monotonic(),
        privacy_mode="original",
        source_key="source-a",
    )
    wait_until(lambda: publisher.status()["process_failures"] == 2)
    assert publisher.status()["process_starts"] == 2
    publisher.close()


def verify_cold_start_uses_handshake_deadline() -> None:
    processes = []

    def process_factory(command: list[str]) -> DelayedReaderProcess:
        process = DelayedReaderProcess(command, delay_seconds=0.2)
        processes.append(process)
        return process

    publisher = H264StreamPublisher(
        camera_id=4,
        publish_url="rtsps://edge:token@media.example.invalid:8322/live/edge/4",
        ffmpeg_path="ffmpeg",
        fps=15,
        bitrate_kbps=1200,
        write_timeout_seconds=0.1,
        startup_timeout_seconds=0.5,
        process_factory=process_factory,
    )
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    publisher.submit(
        frame,
        frame_id="4-1",
        captured_monotonic=time.monotonic(),
        privacy_mode="original",
        source_key="source-a",
    )
    wait_until(lambda: publisher.status()["frames_written"] == 1, timeout=1.0)
    status = publisher.status()
    assert status["process_failures"] == 0
    assert status["startup_timeout_seconds"] == 0.5
    assert processes[0].lifecycle == []
    publisher.close()


def verify_shutdown_aborts_partial_frame_before_closing_input() -> None:
    factory = ProcessFactory()
    publisher = H264StreamPublisher(
        camera_id=5,
        publish_url="rtsps://edge:token@media.example.invalid:8322/live/edge/5",
        ffmpeg_path="ffmpeg",
        fps=15,
        bitrate_kbps=1200,
        write_timeout_seconds=1.0,
        startup_timeout_seconds=1.0,
        process_factory=factory,
    )
    publisher.submit(
        np.zeros((720, 1280, 3), dtype=np.uint8),
        frame_id="5-1",
        captured_monotonic=time.monotonic(),
        privacy_mode="original",
        source_key="source-a",
    )
    wait_until(lambda: bool(factory.processes), timeout=0.5)
    time.sleep(0.05)
    publisher.close()
    process = factory.processes[0]
    assert process.lifecycle[:2] == ["kill", "stdin_close"]
    status = publisher.status()
    assert status["process_stop_reasons"] == {"control_changed": 1}
    assert status["partial_frame_aborts"] == 1
    assert 0 < status["last_partial_frame_bytes"] < status["last_partial_frame_size"]


def verify_relay_uses_single_composed_h264_publisher() -> None:
    stop_event = Event()
    renderer = PrivacyRendererStub(blocked_frames=2)
    publisher_factory = PublisherRecorderFactory()
    relay = LiveRelayAgent(
        storage=None,
        settings=SettingsStub(),
        camera_agent=CameraAgentStub(stop_event),
        device_id_resolver=lambda: "edge-test",
        token_resolver=lambda: "issued-token",
        remote_camera_id_resolver=lambda camera_id: camera_id + 100,
        privacy_mode_resolver=lambda: "skeleton",
        privacy_renderer=renderer,
        publisher_factory=publisher_factory,
    )
    relay._run_camera({"id": 2}, stop_event)
    assert len(publisher_factory.instances) == 1
    publisher = publisher_factory.instances[0]
    assert publisher.closed
    assert renderer.render_calls == 8
    assert len(publisher.submissions) == 6
    assert publisher.submissions[-1][1]["frame_id"] == "2-8"
    assert publisher.submissions[-1][1]["privacy_mode"] == "skeleton"
    assert publisher.configuration["camera_id"] == 2
    assert publisher.configuration["publish_url"].endswith("/live/edge-test/102")
    assert publisher.configuration["fps"] == 15
    assert "stream_revalidation_required" in publisher.pauses
    assert relay.status()["camera_privacy_states"]["2"]["status"] == "ready"
    assert relay.status()["last_error"] == ""
    assert LiveRelayAgent._privacy_block_status("calibration_in_progress") == "calibrating"
    assert LiveRelayAgent._privacy_block_status("stream_revalidation_required") == "revalidating"
    assert LiveRelayAgent._privacy_block_status("scene_revalidation_required") == "scene_review_required"

    relay._set_camera_error(2, "capture thread did not stop within 5 seconds")
    active_error = relay.status()
    assert active_error["last_error"] == "camera 2: capture thread did not stop within 5 seconds"
    assert active_error["camera_errors"]["2"]["message"] == "capture thread did not stop within 5 seconds"
    relay._clear_camera_error(2)
    recovered_error = relay.status()
    assert recovered_error["last_error"] == ""
    assert recovered_error["recovered_camera_errors"]["2"]["recovered_at"]

    source = (ROOT / "app" / "live_relay_agent.py").read_text(encoding="utf-8")
    for retired in ("cv2.imencode", "image/jpeg", "_post_frame", "HTTPConnection"):
        assert retired not in source


def main() -> int:
    verify_url_and_command_contract()
    verify_latest_frame_and_context_restart()
    verify_blocked_pipe_timeout_and_restart()
    verify_cold_start_uses_handshake_deadline()
    verify_shutdown_aborts_partial_frame_before_closing_input()
    verify_relay_uses_single_composed_h264_publisher()
    print({
        "ok": True,
        "transport": "h264-rtsps",
        "single_persistent_process_per_camera": True,
        "latest_pending_frame_only": True,
        "context_restart": True,
        "bounded_write_timeout": True,
        "bounded_startup_handshake": True,
        "partial_frame_abort_order": True,
        "credentials_redacted": True,
        "jpeg_relay_removed": True,
        "calibration_pauses_publication": True,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
