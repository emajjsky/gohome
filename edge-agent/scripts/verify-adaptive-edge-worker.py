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


def main() -> None:
    clock = Clock(100.0)
    scheduler = AdaptiveInferenceScheduler(
        idle_interval_seconds=1.0,
        active_interval_seconds=0.5,
        risk_interval_seconds=0.2,
    )
    worker = EdgeWorker(
        Storage(),
        camera_agent=None,
        detect_agent=None,
        event_agent=None,
        inference_scheduler=scheduler,
        monotonic_clock=clock,
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

    print({
        "ok": True,
        "processed": processed,
        "maximum_idle_wait": idle_wait,
        "fixed_five_second_sleep_removed": True,
        "active_pose_enabled": True,
    })


if __name__ == "__main__":
    main()
