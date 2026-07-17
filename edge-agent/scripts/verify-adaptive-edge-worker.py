from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.adaptive_inference_scheduler import AdaptiveInferenceScheduler
from app.worker import EdgeWorker


class Clock:
    def __init__(self, value: float) -> None:
        self.value = float(value)

    def __call__(self) -> float:
        return self.value


class Storage:
    def __init__(self) -> None:
        self.cameras = [
            {"id": 24, "name": "客厅", "enabled": True},
            {"id": 25, "name": "书房", "enabled": True},
        ]
        self.rules = {
            "updated_at": "2026-07-17T00:00:00+00:00",
            "capture_interval_seconds": 5,
            "fall_detection_enabled": True,
            "activity_detection_enabled": True,
        }

    def reconcile_camera_runtime_state(self, *, close_stale_open: bool) -> dict:
        return {"close_stale_open": close_stale_open}

    def get_rules(self) -> dict:
        return dict(self.rules)

    def list_cameras(self, *, include_secret: bool) -> list[dict]:
        return [dict(camera) for camera in self.cameras]

    def close_camera_runtime_state(self, camera_id: int, *, reason: str) -> None:
        raise SystemExit(f"enabled camera {camera_id} was unexpectedly closed: {reason}")


class ContinualTracker:
    version = "eacp-continual-pose-test"

    def __init__(self) -> None:
        self.observed = []
        self.frames = []
        self.reset = []

    def observe(self, camera_id, frame, *, frame_id, captured_at, poses):
        self.observed.append({
            "camera_id": camera_id,
            "frame": frame,
            "frame_id": frame_id,
            "captured_at": captured_at,
            "poses": poses,
        })
        return {"state": "observed", "pose_count": len(poses)}

    def update_frame(self, camera_id, frame, *, frame_id, captured_at):
        self.frames.append({"camera_id": camera_id, "frame_id": frame_id, "captured_at": captured_at})
        return {"state": "tracked", "pose_count": 1}

    def latest(self, camera_id):
        return {"camera_id": camera_id, "state": "tracked", "pose_count": 1}

    def status(self, camera_ids=None):
        return {"schema_version": self.version, "camera_ids": sorted(camera_ids or [])}

    def has_anchor(self, camera_id):
        return True

    def reset_camera(self, camera_id):
        self.reset.append(camera_id)


class CameraAgent:
    def latest_cached_frame(self, camera, max_age_seconds=2.0):
        return {
            "frame": "latest-frame",
            "frame_id": f"{camera['id']}-latest",
            "captured_at": "2026-07-17T00:00:00.3+00:00",
        }


def main() -> None:
    clock = Clock(100.0)
    scheduler = AdaptiveInferenceScheduler(
        idle_interval_seconds=1.0,
        active_interval_seconds=0.5,
        risk_interval_seconds=0.2,
    )
    continual_tracker = ContinualTracker()
    worker = EdgeWorker(
        Storage(),
        camera_agent=CameraAgent(),
        detect_agent=None,
        event_agent=None,
        inference_scheduler=scheduler,
        monotonic_clock=clock,
        continual_pose_tracker=continual_tracker,
    )
    processed: list[int] = []

    def process(camera: dict, rules: dict, *, adaptive_pose: bool = False) -> dict:
        if not adaptive_pose:
            raise SystemExit("scheduled worker did not request adaptive pose policy")
        processed.append(int(camera["id"]))
        clock.value += 0.1
        return {
            "ok": True,
            "analysis": {"person_count": 0, "motion_detected": False},
            "snapshot": {"captured_at": "2026-07-17T00:00:00+00:00"},
        }

    worker.process_camera = process  # type: ignore[method-assign]

    first_wait = worker._run_iteration()
    if processed != [24] or first_wait != 0.0:
        raise SystemExit(f"first iteration did not process one due camera: {processed}, {first_wait}")
    second_wait = worker._run_iteration()
    if processed != [24, 25] or second_wait != 0.0:
        raise SystemExit(f"second camera was not independently scheduled: {processed}, {second_wait}")

    idle_wait = worker._run_iteration()
    if not 0.0 < idle_wait <= 0.25:
        raise SystemExit(f"worker reused the five-second rule sleep: {idle_wait}")

    if worker._pose_runtime_config(24, worker.storage.rules)["pose_detection_enabled"]:
        raise SystemExit("idle camera should not run RTMPose before person or motion is observed")

    clock.value = 101.0
    scheduler.mark_started(24, now=clock.value)
    clock.value = 101.1
    scheduler.observe(24, {"person_count": 1, "motion_detected": True}, now=clock.value)
    pose_config = worker._pose_runtime_config(24, worker.storage.rules)
    if not pose_config["pose_detection_enabled"] or pose_config["eacp_mode"] != "active":
        raise SystemExit(f"active camera did not enable RTMPose: {pose_config}")
    analysis_runtime = worker._inference_runtime_payload(pose_config)
    if analysis_runtime.get("schema_version") != "eacp-analysis-runtime-v1":
        raise SystemExit(f"persisted analysis runtime metadata is missing: {analysis_runtime}")
    if analysis_runtime.get("mode") != "active" or not analysis_runtime.get("pose_requested"):
        raise SystemExit(f"persisted analysis mode does not match scheduler state: {analysis_runtime}")

    persistence_rules = {"capture_interval_seconds": 5}
    if not worker._should_persist_analysis(24, {}, {}, persistence_rules, now=200.0):
        raise SystemExit("first analysis frame must establish a durable baseline")
    worker.last_persisted_analysis_at[24] = 200.0
    worker.last_persisted_person_state[24] = False
    if worker._should_persist_analysis(24, {}, {}, persistence_rules, now=201.0):
        raise SystemExit("ordinary high-frequency anchors must not all be written to disk")
    if not worker._should_persist_analysis(24, {"person_count": 1}, {}, persistence_rules, now=201.05):
        raise SystemExit("no-person to person transition must be persisted immediately")
    if not worker._should_persist_analysis(
        24,
        {"pose_factor_graph": {"fast_fall_candidate": True}},
        {},
        persistence_rules,
        now=201.1,
    ):
        raise SystemExit("fall-risk anchor must be persisted immediately")
    if not worker._should_persist_analysis(24, {}, {}, persistence_rules, now=205.0):
        raise SystemExit("durable baseline was not refreshed at the persistence interval")

    runtime = worker.runtime_status()
    if runtime.get("inference_scheduler", {}).get("schema_version") != "eacp-scheduler-v1":
        raise SystemExit(f"worker runtime omitted EACP metrics: {runtime}")
    if runtime.get("continual_pose_tracker") != continual_tracker.version:
        raise SystemExit(f"worker runtime omitted continual pose tracker: {runtime}")
    if runtime.get("continual_pose", {}).get("schema_version") != continual_tracker.version:
        raise SystemExit(f"worker runtime omitted continual pose metrics: {runtime}")

    observed_analysis = {
        "pose_model_status": "ready",
        "poses": [{"track_id": "c24-p1", "tracking_state": "fresh", "keypoints": []}],
    }
    worker._publish_continual_pose_anchor(
        24,
        frame="observed-frame",
        capture={"frame_id": "24-100", "captured_at": "2026-07-17T00:00:00+00:00"},
        analysis=observed_analysis,
    )
    if len(continual_tracker.observed) != 1 or continual_tracker.observed[0]["camera_id"] != 24:
        raise SystemExit("fresh worker pose did not become a continual tracking anchor")
    worker._publish_continual_pose_anchor(
        24,
        frame="cached-frame",
        capture={"frame_id": "24-101", "captured_at": "2026-07-17T00:00:00.1+00:00"},
        analysis={"pose_model_status": "cached", "poses": observed_analysis["poses"]},
    )
    if len(continual_tracker.observed) != 1:
        raise SystemExit("cached pose was incorrectly promoted to a fresh model anchor")

    worker.observe_stream_frame(
        {"id": 25},
        "stream-frame",
        {"frame_id": "25-200", "captured_at": "2026-07-17T00:00:00.2+00:00"},
    )
    if continual_tracker.frames != [{
        "camera_id": 25,
        "frame_id": "25-200",
        "captured_at": "2026-07-17T00:00:00.2+00:00",
    }]:
        raise SystemExit("shared stream frame was not sent to the continual tracker")

    worker._runtime_cameras = {24: {"id": 24, "enabled": True}}
    worker._run_continual_tracking_iteration()
    if continual_tracker.frames[-1]["frame_id"] != "24-latest":
        raise SystemExit("independent continual tracking loop did not consume the latest cached frame")

    worker._reset_camera_runtime_memory(24)
    if continual_tracker.reset != [24]:
        raise SystemExit("camera lifecycle reset left continual pose state behind")

    print({
        "ok": True,
        "processed": processed,
        "maximum_idle_wait": idle_wait,
        "fixed_five_second_sleep_removed": True,
        "active_pose_enabled": True,
    })


if __name__ == "__main__":
    main()
