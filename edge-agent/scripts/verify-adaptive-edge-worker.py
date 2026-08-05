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
        self.events = {
            2177: {
                "id": 2177,
                "camera_id": 24,
                "acknowledged": False,
                "payload": {},
            }
        }

    def reconcile_camera_runtime_state(self, *, close_stale_open: bool) -> dict:
        return {"close_stale_open": close_stale_open}

    def get_rules(self) -> dict:
        return dict(self.rules)

    def list_cameras(self, *, include_secret: bool) -> list[dict]:
        return [dict(camera) for camera in self.cameras]

    def close_camera_runtime_state(self, camera_id: int, *, reason: str) -> None:
        raise SystemExit(f"enabled camera {camera_id} was unexpectedly closed: {reason}")

    def get_event(self, event_id: int) -> dict | None:
        event = self.events.get(int(event_id))
        return dict(event) if event else None

    def update_event(self, event_id: int, patch: dict) -> dict | None:
        event = self.events.get(int(event_id))
        if event is None:
            return None
        event["acknowledged"] = bool(patch.get("acknowledged", event["acknowledged"]))
        if patch.get("resolution"):
            event["payload"] = {**event.get("payload", {}), "resolution": patch["resolution"]}
        return dict(event)


class ContinualTracker:
    version = "eacp-continual-pose-test"

    def __init__(self) -> None:
        self.observed = []
        self.frames = []
        self.reset = []
        self.next_state = "tracked"
        self.metadata = {
            "tracking": {"state": "empty", "poses": []},
            "analysis_context": {},
            "source_key": "",
        }

    def observe(
        self,
        camera_id,
        frame,
        *,
        frame_id,
        captured_at,
        captured_monotonic=None,
        poses,
        context=None,
        source_key="",
        person_present=False,
    ):
        self.observed.append({
            "camera_id": camera_id,
            "frame": frame,
            "frame_id": frame_id,
            "captured_at": captured_at,
            "poses": poses,
            "context": context or {},
            "source_key": source_key,
            "person_present": person_present,
        })
        return {"state": "observed", "pose_count": len(poses)}

    def update_frame(
        self,
        camera_id,
        frame,
        *,
        frame_id,
        captured_at,
        captured_monotonic=None,
        source_key="",
    ):
        self.frames.append({
            "camera_id": camera_id,
            "frame_id": frame_id,
            "captured_at": captured_at,
            "source_key": source_key,
        })
        state = self.next_state
        self.next_state = "tracked"
        return {
            "state": state,
            "reason": "forward_backward_error" if state == "coasting" else "",
            "pose_count": 1,
            "formal_evidence_eligible": False,
            "risk_hint": {
                "detected": camera_id == 25,
                "reason": "rapid_downward_pose_motion" if camera_id == 25 else "",
                "formal_evidence_eligible": False,
            },
        }

    def latest(self, camera_id):
        return {"camera_id": camera_id, "state": "tracked", "pose_count": 1}

    def latest_metadata(self, camera_id):
        return dict(self.metadata)

    def status(self, camera_ids=None):
        return {"schema_version": self.version, "camera_ids": sorted(camera_ids or [])}

    def has_anchor(self, camera_id):
        return True

    def reset_camera(self, camera_id):
        self.reset.append(camera_id)


class CameraAgent:
    def __init__(self):
        self.reconciled_camera_ids = []

    def reconcile_managed_streams(self, cameras):
        self.reconciled_camera_ids = sorted(int(camera["id"]) for camera in cameras)

    def latest_cached_frame(self, camera, max_age_seconds=2.0):
        return {
            "frame": "latest-frame",
            "frame_id": f"{camera['id']}-latest",
            "captured_at": "2026-07-17T00:00:00.3+00:00",
            "captured_monotonic": 100.3,
            "source_key": f"camera-{camera['id']}:g1",
        }

    def frame_source_matches(self, camera, source_key):
        return str(source_key or "").startswith(f"camera-{camera['id']}:g")

    def active_frame_source_key(self, camera):
        return f"camera-{camera['id']}:g1"


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
    if worker.camera_agent.reconciled_camera_ids != [24, 25]:
        raise SystemExit("worker did not keep enabled camera streams alive independently of preview pages")

    idle_wait = worker._run_iteration()
    if not 0.0 < idle_wait <= 0.25:
        raise SystemExit(f"worker reused the five-second rule sleep: {idle_wait}")

    if worker._pose_runtime_config(24, worker.storage.rules)["pose_detection_enabled"]:
        raise SystemExit("idle camera should not run RTMPose before person or motion is observed")

    clock.value = 100.5
    scheduler.signal_activity(24, now=clock.value)
    motion_only_config = worker._pose_runtime_config(24, worker.storage.rules)
    if motion_only_config["pose_detection_enabled"]:
        raise SystemExit("motion-only wakeup must run YOLO without enabling RTMPose")

    scheduler.reset_camera(25)
    scheduler.reconcile([24, 25], now=100.5)
    scheduler.mark_started(25, now=100.5)
    clock.value = 100.55
    scheduler.observe(
        25,
        {"inference_backend": "hailo", "person_count": 0, "motion_detected": False},
        now=clock.value,
    )
    hailo_idle_probe_config = worker._pose_runtime_config(25, worker.storage.rules)
    if (
        not hailo_idle_probe_config["pose_detection_enabled"]
        or hailo_idle_probe_config["pose_runtime_reason"] != "eacp_idle_hailo_pose_probe"
    ):
        raise SystemExit(
            f"an already-running Hailo pose result was discarded during idle probing: {hailo_idle_probe_config}"
        )

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
    if analysis_runtime.get("formal_evidence_eligible") is not True:
        raise SystemExit(f"formal analysis did not declare its evidence boundary: {analysis_runtime}")

    persistence_rules = {"capture_interval_seconds": 600}
    if worker._should_persist_analysis(24, {}, {}, persistence_rules, now=200.0):
        raise SystemExit("ordinary analysis must remain memory-only")
    worker.last_persisted_analysis_at[24] = 200.0
    if worker._should_persist_analysis(24, {}, {}, persistence_rules, now=201.0):
        raise SystemExit("ordinary high-frequency anchors must not all be written to disk")
    if worker._should_persist_analysis(24, {"person_count": 1}, {}, persistence_rules, now=201.05):
        raise SystemExit("person activity must use structured persistence instead of JPEG baselines")
    if not worker._should_persist_analysis(
        24,
        {"pose_factor_graph": {"fast_fall_candidate": True}},
        {},
        persistence_rules,
        now=201.1,
    ):
        raise SystemExit("fall-risk anchor must be persisted immediately")
    if worker._should_persist_analysis(24, {}, {}, persistence_rules, now=800.0):
        raise SystemExit("routine analysis interval must not restore periodic JPEG persistence")

    runtime = worker.runtime_status()
    if runtime.get("inference_scheduler", {}).get("schema_version") != "eacp-scheduler-v1":
        raise SystemExit(f"worker runtime omitted EACP metrics: {runtime}")
    if runtime.get("continual_pose_tracker") != continual_tracker.version:
        raise SystemExit(f"worker runtime omitted continual pose tracker: {runtime}")
    if runtime.get("continual_pose", {}).get("schema_version") != continual_tracker.version:
        raise SystemExit(f"worker runtime omitted continual pose metrics: {runtime}")
    persistence = runtime.get("persistence", {})
    if persistence.get("schema_version") != "event-driven-persistence-v1":
        raise SystemExit(f"worker runtime omitted persistence contract: {runtime}")

    observed_analysis = {
        "pose_model_status": "ready",
        "poses": [{"track_id": "c24-p1", "tracking_state": "fresh", "keypoints": []}],
    }
    worker._publish_continual_pose_anchor(
        24,
        frame="observed-frame",
        capture={
            "frame_id": "24-100",
            "captured_at": "2026-07-17T00:00:00+00:00",
            "source_key": "camera-24:g1",
        },
        analysis=observed_analysis,
    )
    if len(continual_tracker.observed) != 1 or continual_tracker.observed[0]["camera_id"] != 24:
        raise SystemExit("fresh worker pose did not become a continual tracking anchor")
    if not continual_tracker.observed[0]["person_present"]:
        raise SystemExit("worker did not preserve model-confirmed person presence")
    worker._publish_continual_pose_anchor(
        24,
        frame="model-confirmed-empty-frame",
        capture={
            "frame_id": "24-empty",
            "captured_at": "2026-07-17T00:00:00.05+00:00",
            "source_key": "camera-24:g1",
        },
        analysis={"pose_model_status": "not_visible", "poses": [], "people": []},
    )
    if len(continual_tracker.observed) != 2 or continual_tracker.observed[-1]["poses"]:
        raise SystemExit("model-confirmed empty frame did not refresh the synchronized privacy scene")
    worker._publish_continual_pose_anchor(
        24,
        frame="hailo-idle-empty-frame",
        capture={
            "frame_id": "24-idle-empty",
            "captured_at": "2026-07-17T00:00:00.06+00:00",
            "source_key": "camera-24:g1",
        },
        analysis={
            "pose_model_status": "disabled",
            "inference_backend": "hailo",
            "inference_backend_status": {"status": "ready"},
            "person_count": 0,
            "people": [],
            "poses": [],
        },
    )
    if len(continual_tracker.observed) != 3 or continual_tracker.observed[-1]["poses"]:
        raise SystemExit("Hailo idle person probe did not refresh the synchronized empty scene")
    worker._publish_continual_pose_anchor(
        24,
        frame="cached-frame",
        capture={
            "frame_id": "24-101",
            "captured_at": "2026-07-17T00:00:00.1+00:00",
            "source_key": "camera-24:g1",
        },
        analysis={"pose_model_status": "cached", "poses": observed_analysis["poses"]},
    )
    if len(continual_tracker.observed) != 3:
        raise SystemExit("cached pose was incorrectly promoted to a fresh model anchor")

    tracked_payload = worker.observe_stream_frame(
        {"id": 25},
        "stream-frame",
        {
            "frame_id": "25-200",
            "captured_at": "2026-07-17T00:00:00.2+00:00",
            "source_key": "camera-25:g1",
        },
    )
    if continual_tracker.frames != [{
        "camera_id": 25,
        "frame_id": "25-200",
        "captured_at": "2026-07-17T00:00:00.2+00:00",
        "source_key": "camera-25:g1",
    }]:
        raise SystemExit("shared stream frame was not sent to the continual tracker")
    if not isinstance(tracked_payload, dict) or not tracked_payload.get("risk_hint", {}).get("detected"):
        raise SystemExit("continual tracking risk hint was not returned to the worker")
    if scheduler.camera_state(25, now=clock.value).get("mode") != "risk":
        raise SystemExit("display-only rapid downward hint did not wake formal risk inference")

    continual_tracker.next_state = "coasting"
    worker.observe_stream_frame(
        {"id": 24},
        "tracking-lost-frame",
        {
            "frame_id": "24-201",
            "captured_at": "2026-07-17T00:00:00.21+00:00",
            "source_key": "camera-24:g1",
        },
    )
    refresh_state = scheduler.camera_state(24, now=clock.value)
    if (
        not refresh_state.get("refresh_requested")
        or refresh_state.get("last_refresh_reason") != "forward_backward_error"
    ):
        raise SystemExit(f"tracking loss did not prioritize a fresh Hailo anchor: {refresh_state}")

    worker._runtime_cameras = {24: {"id": 24, "enabled": True}}
    worker._run_continual_tracking_iteration()
    if continual_tracker.frames[-1]["frame_id"] != "24-latest":
        raise SystemExit("independent continual tracking loop did not consume the latest cached frame")
    if continual_tracker.frames[-1]["source_key"] != "camera-24:g1":
        raise SystemExit("continual tracking lost the active camera source generation")
    if worker._capture_identity_matches(
        {"id": 24},
        {"frame_id": "24-old", "source_key": "camera-24:g0"},
    ):
        raise SystemExit("an old stream generation was accepted after camera reconnect")
    if abs(worker._continual_tracking_interval_seconds() - 0.05) > 0.001:
        raise SystemExit("continual tracking loop did not use the accelerated tracker interval")
    cadence_started = clock.value
    clock.value += 0.02
    if abs(worker._continual_tracking_wait_seconds(cadence_started) - 0.03) > 0.001:
        raise SystemExit("continual tracking cadence did not subtract processing time")
    clock.value += 0.06
    if worker._continual_tracking_wait_seconds(cadence_started) != 0.0:
        raise SystemExit("continual tracking cadence slept after exceeding its frame deadline")

    worker._runtime_cameras = {24: {"id": 24, "enabled": True}}
    continual_tracker.metadata = {
        "tracking": {
            "state": "observed",
            "display_only_stale": False,
            "poses": [{"bbox": [100.0, 40.0, 220.0, 300.0]}],
        },
        "analysis_context": {
            "inference_runtime": {"formal_evidence_eligible": True},
        },
        "source_key": "camera-24:g1",
    }
    observed_before_coordinator = len(continual_tracker.observed)
    worker._handle_coordinated_display_pose({
        "camera_id": 24,
        "frame": "coordinated-frame",
        "frame_id": "24-300",
        "captured_at": "2026-07-17T00:00:00.3+00:00",
        "captured_monotonic": 100.3,
        "source_key": "camera-24:g1",
        "roles": ["display"],
        "analysis": {"poses": [{"bbox": [104.0, 44.0, 224.0, 304.0]}]},
    })
    if len(continual_tracker.observed) != observed_before_coordinator + 1:
        raise SystemExit("validated coordinated Pose did not refresh the existing display anchor")
    if not continual_tracker.observed[-1]["context"].get("inference_runtime", {}).get("formal_evidence_eligible"):
        raise SystemExit("display refresh discarded the validated formal-analysis boundary")
    worker._handle_coordinated_display_pose({
        "camera_id": 24,
        "frame": "unvalidated-frame",
        "frame_id": "24-301",
        "captured_at": "2026-07-17T00:00:00.31+00:00",
        "captured_monotonic": 100.31,
        "source_key": "camera-24:g1",
        "roles": ["display"],
        "analysis": {"poses": [{"bbox": [350.0, 40.0, 470.0, 300.0]}]},
    })
    worker._handle_coordinated_display_pose({
        "camera_id": 24,
        "frame": "formal-frame",
        "frame_id": "24-302",
        "captured_at": "2026-07-17T00:00:00.32+00:00",
        "captured_monotonic": 100.32,
        "source_key": "camera-24:g1",
        "roles": ["display", "formal"],
        "analysis": {"poses": [{"bbox": [104.0, 44.0, 224.0, 304.0]}]},
    })
    if len(continual_tracker.observed) != observed_before_coordinator + 1:
        raise SystemExit("unvalidated or formal coordinator output bypassed the full pipeline")

    worker.pose_candidate_gate.reset_camera(24)
    scheduler.reset_camera(24)
    scheduler.reconcile([24], now=clock.value)
    scheduler.mark_started(24, now=clock.value)
    clock.value += 0.04
    scheduler.observe(
        24,
        {"inference_backend": "hailo", "person_count": 0, "motion_detected": False},
        now=clock.value,
    )
    continual_tracker.metadata = {
        "tracking": {"state": "empty", "poses": []},
        "analysis_context": {},
        "source_key": "camera-24:g1",
    }
    worker._handle_coordinated_display_pose({
        "camera_id": 24,
        "frame": "empty-candidate-frame",
        "frame_id": "24-310",
        "captured_at": "2026-07-17T00:00:00.34+00:00",
        "captured_monotonic": 100.34,
        "source_key": "camera-24:g1",
        "roles": ["display"],
        "analysis": {"poses": []},
    })
    empty_candidate_state = scheduler.camera_state(24, now=clock.value)
    if empty_candidate_state["refresh_requested"] or empty_candidate_state["mode"] != "idle":
        raise SystemExit(f"initial empty coordinated Pose woke formal analysis: {empty_candidate_state}")

    for frame_id, bbox in (
        ("24-311", [100.0, 40.0, 220.0, 300.0]),
        ("24-312", [106.0, 44.0, 226.0, 304.0]),
    ):
        clock.value += 0.2
        worker._handle_coordinated_display_pose({
            "camera_id": 24,
            "frame": "candidate-frame",
            "frame_id": frame_id,
            "captured_at": "2026-07-17T00:00:00.4+00:00",
            "captured_monotonic": clock.value,
            "source_key": "camera-24:g1",
            "roles": ["display"],
            "analysis": {"poses": [{"bbox": bbox}]},
        })
    candidate_state = scheduler.camera_state(24, now=clock.value)
    if (
        candidate_state["mode"] != "idle"
        or not candidate_state["refresh_requested"]
        or candidate_state["validation_request_count"] != 1
        or candidate_state["refresh_request_count"] != 0
        or candidate_state["last_validation_reason"] != "consistent_pose_candidate"
    ):
        raise SystemExit(f"consistent raw Pose did not request one idle validation: {candidate_state}")
    gate_status = worker.pose_candidate_gate.status()["cameras"][0]
    if gate_status["validation_requests"] != 1 or gate_status["consistent_hits"] != 2:
        raise SystemExit(f"Pose candidate temporal gate is incomplete: {gate_status}")
    clock.value += 0.02
    worker._handle_coordinated_display_pose({
        "camera_id": 24,
        "frame": "candidate-empty-before-formal",
        "frame_id": "24-313",
        "captured_at": "2026-07-17T00:00:00.82+00:00",
        "captured_monotonic": clock.value,
        "source_key": "camera-24:g1",
        "roles": ["display"],
        "analysis": {"poses": []},
    })
    pending_gate_status = worker.pose_candidate_gate.status()["cameras"][0]
    if (
        not pending_gate_status["awaiting_formal"]
        or pending_gate_status["validation_requests"] != 1
        or scheduler.camera_state(24, now=clock.value)["validation_request_count"] != 1
    ):
        raise SystemExit(f"empty frame forgot a pending formal validation: {pending_gate_status}")
    worker.pose_candidate_gate.observe_formal(
        24,
        person_present=False,
        analysis_started_at=clock.value + 0.01,
        now=clock.value + 0.05,
    )
    rejected_status = worker.pose_candidate_gate.status()["cameras"][0]
    first_cooldown = float(rejected_status["cooldown_remaining_seconds"])
    if (
        rejected_status["formal_rejections"] != 1
        or rejected_status["rejection_streak"] != 1
        or first_cooldown <= 0.0
    ):
        raise SystemExit(f"formal rejection did not cool down raw Pose candidates: {rejected_status}")
    clock.value += first_cooldown + 0.1
    for offset in (0.1, 0.2):
        second_decision = worker.pose_candidate_gate.observe(
            24,
            source_key="camera-24:g1",
            poses=[{"bbox": [100.0, 40.0, 220.0, 300.0]}],
            frame_width=640,
            frame_height=360,
            now=clock.value + offset,
        )
    if not second_decision["validation_requested"]:
        raise SystemExit(f"post-cooldown candidate did not request validation: {second_decision}")
    worker.pose_candidate_gate.observe_formal(
        24,
        person_present=False,
        analysis_started_at=clock.value + 0.21,
        now=clock.value + 0.25,
    )
    backed_off_status = worker.pose_candidate_gate.status()["cameras"][0]
    if (
        backed_off_status["formal_rejections"] != 2
        or backed_off_status["rejection_streak"] != 2
        or float(backed_off_status["cooldown_remaining_seconds"]) <= first_cooldown
    ):
        raise SystemExit(f"repeated formal rejection did not back off: {backed_off_status}")
    worker.pose_candidate_gate.reset_camera(24)
    for offset in (0.1, 0.2):
        decision = worker.pose_candidate_gate.observe(
            24,
            source_key="camera-24:g1",
            poses=[{"bbox": [100.0, 40.0, 220.0, 300.0]}],
            frame_width=640,
            frame_height=360,
            now=clock.value + offset,
        )
    if not decision["validation_requested"]:
        raise SystemExit(f"formal-error probe did not request validation: {decision}")
    worker.pose_candidate_gate.observe_formal_error(
        24,
        analysis_started_at=clock.value + 0.21,
    )
    error_status = worker.pose_candidate_gate.status()["cameras"][0]
    if error_status["formal_errors"] != 1 or error_status["awaiting_formal"]:
        raise SystemExit(f"formal analysis error left candidate validation stuck: {error_status}")

    worker._reset_camera_runtime_memory(24)
    if continual_tracker.reset != [24]:
        raise SystemExit("camera lifecycle reset left continual pose state behind")

    worker.rule_engine.fall_tracks[24] = {
        "stage": "confirmed",
        "alert_emitted": True,
        "target": {"track_id": "c24-p68"},
    }
    worker.pose_factor_graph_engine._states[24] = {
        "c24-p68": {"lying_started_monotonic": 100.0}
    }
    command_result = worker.apply_event_state_command({
        "command_id": "event-state-test-2177",
        "edge_event_id": "2177",
        "state": "resolved",
        "resolution": "handled",
    })
    if command_result.get("camera_id") != 24:
        raise SystemExit(f"event state command returned the wrong camera: {command_result}")
    if not worker.storage.get_event(2177).get("acknowledged"):
        raise SystemExit("event state command did not acknowledge the local event")
    if 24 in worker.rule_engine.fall_tracks or 24 in worker.pose_factor_graph_engine._states:
        raise SystemExit("event state command left stale fall safety state in memory")

    print({
        "ok": True,
        "processed": processed,
        "maximum_idle_wait": idle_wait,
        "fixed_five_second_sleep_removed": True,
        "hailo_idle_pose_result_reused": True,
        "active_pose_enabled": True,
        "coordinated_pose_requires_validated_anchor": True,
    })


if __name__ == "__main__":
    main()
