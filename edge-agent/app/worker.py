from __future__ import annotations

from contextlib import contextmanager
from threading import Event, Lock, RLock, Thread, current_thread
from typing import Any, Callable, Dict
import time
from datetime import datetime, timezone
from pathlib import Path

from .adaptive_inference_scheduler import AdaptiveInferenceScheduler
from .camera_agent import CameraError
from .rule_engine import RuleEngine, RuleEvaluation, build_event_evidence
from .vision.temporal import TemporalObservationEngine
from .vision.pose_factor_graph import PoseFactorGraphEngine
from .vision.continual_pose_tracker import ContinualPoseTracker
from .vision.motion_gate import MotionGate
from .vision.pose_candidate_gate import PoseCandidateValidationGate
from .vision.pose_coordinator import PoseCoordinatorError, PoseInferenceCoordinator
from .observation_coverage import ObservationCoverageTracker


LIFE_OBSERVATION_TYPES = {"no_motion", "no_person"}


class EdgeWorker:
    def __init__(
        self,
        storage: Any,
        camera_agent: Any,
        detect_agent: Any,
        event_agent: Any,
        *,
        snapshot_dir: Path | None = None,
        object_storage_dir: Path | None = None,
        runtime_dir: Path | None = None,
        history_retention_hours: int = 24,
        history_cleanup_interval_seconds: float = 3600,
        history_cleanup_batch_size: int = 5000,
        completed_upload_retention_days: int = 7,
        event_evidence_retention_hours: int = 24,
        local_event_retention_days: int = 30,
        local_runtime_budget_mb: int = 2048,
        activity_log_interval_seconds: float = 600.0,
        activity_posture_stability_seconds: float = 5.0,
        activity_absence_stability_seconds: float = 15.0,
        risk_evidence_interval_seconds: float = 0.5,
        local_storage_high_watermark_percent: float = 70.0,
        local_storage_critical_percent: float = 85.0,
        temporal_engine: TemporalObservationEngine | None = None,
        pose_factor_graph_engine: PoseFactorGraphEngine | None = None,
        inference_scheduler: AdaptiveInferenceScheduler | None = None,
        continual_pose_tracker: Any | None = None,
        motion_gate: Any | None = None,
        pose_candidate_gate: Any | None = None,
        observation_coverage_tracker: ObservationCoverageTracker | None = None,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        self.storage = storage
        self.camera_agent = camera_agent
        self.detect_agent = detect_agent
        self.event_agent = event_agent
        self.snapshot_dir = snapshot_dir
        self.object_storage_dir = object_storage_dir
        self.runtime_dir = runtime_dir
        self.history_retention_hours = max(1, int(history_retention_hours))
        self.history_cleanup_interval_seconds = max(60.0, float(history_cleanup_interval_seconds))
        self.history_cleanup_batch_size = max(100, int(history_cleanup_batch_size))
        self.completed_upload_retention_days = max(1, int(completed_upload_retention_days))
        self.event_evidence_retention_hours = max(1, int(event_evidence_retention_hours))
        self.local_event_retention_days = max(1, int(local_event_retention_days))
        self.local_runtime_budget_bytes = max(256, int(local_runtime_budget_mb)) * 1024 * 1024
        self.activity_log_interval_seconds = max(60.0, float(activity_log_interval_seconds))
        self.activity_posture_stability_seconds = max(1.0, float(activity_posture_stability_seconds))
        self.activity_absence_stability_seconds = max(1.0, float(activity_absence_stability_seconds))
        self.risk_evidence_interval_seconds = max(0.25, float(risk_evidence_interval_seconds))
        self.local_storage_high_watermark_percent = max(50.0, min(95.0, float(local_storage_high_watermark_percent)))
        self.local_storage_critical_percent = max(
            self.local_storage_high_watermark_percent + 1.0,
            min(98.0, float(local_storage_critical_percent)),
        )
        self.temporal_engine = temporal_engine or TemporalObservationEngine()
        self.pose_factor_graph_engine = pose_factor_graph_engine or PoseFactorGraphEngine()
        self.inference_scheduler = inference_scheduler or AdaptiveInferenceScheduler()
        self.continual_pose_tracker = continual_pose_tracker or ContinualPoseTracker()
        self.motion_gate = motion_gate or MotionGate()
        self._monotonic_clock = monotonic_clock or time.monotonic
        self.pose_candidate_gate = pose_candidate_gate or PoseCandidateValidationGate(
            monotonic_clock=self._monotonic_clock,
        )
        self.observation_coverage_tracker = observation_coverage_tracker or ObservationCoverageTracker(
            monotonic_clock=self._monotonic_clock,
        )
        self.last_history_cleanup_at = 0.0
        self.last_history_cleanup_result: Dict[str, Any] = {}
        self.last_error = ""
        self.last_persisted_analysis_at: Dict[int, float] = {}
        self.last_activity_persisted_at: Dict[int, float] = {}
        self.last_activity_signature: Dict[int, tuple[Any, ...]] = {}
        self.pending_activity_posture: Dict[int, tuple[tuple[Any, ...], float]] = {}
        self.pending_activity_absence: Dict[int, float] = {}
        self.persistence_metrics: Dict[str, int] = {
            "analysis_cycles": 0,
            "image_writes": 0,
            "risk_image_writes": 0,
            "candidate_image_writes": 0,
            "structured_activity_writes": 0,
            "activity_intervals_enqueued": 0,
            "routine_image_writes_avoided": 0,
        }
        self.last_persistence_reason: Dict[int, str] = {}
        self._stop = Event()
        self._wake = Event()
        self._thread: Thread | None = None
        self._tracking_thread: Thread | None = None
        self._tracking_camera_threads: Dict[int, Thread] = {}
        self._tracking_camera_stops: Dict[int, Event] = {}
        self._tracking_threads_lock = RLock()
        self._camera_analysis_locks: Dict[int, RLock] = {}
        self._camera_analysis_locks_guard = Lock()
        self.previous_frames: Dict[int, Any] = {}
        self.rule_engine = RuleEngine()
        self.latest_evaluations: Dict[int, Dict[str, Any]] = {}
        self.last_loop_started_at: str | None = None
        self.last_rules_loaded_at: str | None = None
        self.last_rules_snapshot: Dict[str, Any] = {}
        self._known_camera_ids: set[int] = set()
        self._disabled_camera_ids: set[int] = set()
        self._runtime_cameras: Dict[int, Dict[str, Any]] = {}
        self._last_continual_frame_ids: Dict[int, str] = {}
        self.runtime_reconciliation: Dict[str, Any] = {}
        self._runtime_reconciled = False
        self._runtime_config_refreshed_at = 0.0
        self._runtime_config_refresh_seconds = 1.0
        self.last_continual_pose_error = ""
        self.continual_identity_bridge_count = 0
        self.last_continual_identity_bridge: Dict[str, Any] = {}
        self._safety_state_lock = RLock()
        self._safety_state_generation: Dict[int, int] = {}
        self._camera_online_reconciled_ids: set[int] = set()
        self.last_event_state_command: Dict[str, Any] = {}
        pose_service = getattr(self.detect_agent, "pose_inference_service", None)
        self.pose_inference_coordinator = (
            PoseInferenceCoordinator(
                pose_service,
                on_display_result=self._handle_coordinated_display_pose,
                monotonic_clock=self._monotonic_clock,
            )
            if pose_service is not None
            else None
        )

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._wake.clear()
        if self.pose_inference_coordinator is not None:
            self.pose_inference_coordinator.start()
        self._thread = Thread(target=self._run, name="gohome-edge-worker", daemon=True)
        self._tracking_thread = Thread(
            target=self._run_continual_tracking,
            name="gohome-edge-pose-tracker",
            daemon=True,
        )
        self._thread.start()
        self._tracking_thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self._stop_continual_tracking_threads()
        if self.pose_inference_coordinator is not None:
            self.pose_inference_coordinator.stop()
        if self._thread:
            self._thread.join(timeout=5)
        if self._tracking_thread:
            self._tracking_thread.join(timeout=2)
        if self.camera_agent is not None and hasattr(self.camera_agent, "reconcile_managed_streams"):
            self.camera_agent.reconcile_managed_streams([])
        if self.detect_agent is not None and hasattr(self.detect_agent, "close"):
            self.detect_agent.close()

    @contextmanager
    def camera_analysis_guard(self, camera_id: int):
        """Serialize all stateful analysis for one camera across worker and admin calls."""
        resolved_camera_id = int(camera_id)
        if resolved_camera_id <= 0:
            raise ValueError("camera_id must be positive")
        with self._camera_analysis_locks_guard:
            lock = self._camera_analysis_locks.setdefault(resolved_camera_id, RLock())
        with lock:
            yield

    def _run(self) -> None:
        while not self._stop.is_set():
            wait_seconds = 0.25
            try:
                wait_seconds = self._run_iteration()
            except Exception as exc:
                self.last_error = str(exc)
            self._wake.wait(max(0.0, wait_seconds))
            self._wake.clear()

    def _run_iteration(self) -> float:
        now = self._monotonic_clock()
        if not self._runtime_reconciled:
            self.runtime_reconciliation = self.storage.reconcile_camera_runtime_state(close_stale_open=True)
            self.runtime_reconciliation["completed_at"] = datetime.now(timezone.utc).isoformat()
            self._runtime_reconciled = True

        self._refresh_runtime_config(now)
        rules = dict(self.last_rules_snapshot)
        cameras_by_id = dict(self._runtime_cameras)
        current_camera_ids = set(cameras_by_id)
        disabled_camera_ids = set(self._disabled_camera_ids)

        enabled_camera_ids = sorted(current_camera_ids - disabled_camera_ids)
        self.inference_scheduler.reconcile(enabled_camera_ids, now=now)
        camera_id = self.inference_scheduler.next_due_camera(enabled_camera_ids, now=now)
        if camera_id is None:
            self._prune_history_if_due()
            return self.inference_scheduler.wait_seconds(
                enabled_camera_ids,
                now=now,
                maximum=0.25,
            )

        self.last_loop_started_at = datetime.now(timezone.utc).isoformat()
        self.inference_scheduler.mark_started(camera_id, now=now)
        try:
            result = self.process_camera(cameras_by_id[camera_id], rules, adaptive_pose=True)
        except Exception:
            self.pose_candidate_gate.observe_formal_error(
                camera_id,
                analysis_started_at=now,
            )
            self.inference_scheduler.mark_error(camera_id, now=self._monotonic_clock())
            raise

        completed_at = self._monotonic_clock()
        if result.get("ok"):
            analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
            self.pose_candidate_gate.observe_formal(
                camera_id,
                person_present=int(analysis.get("person_count") or 0) > 0,
                analysis_started_at=now,
                now=completed_at,
            )
            self.inference_scheduler.observe(
                camera_id,
                analysis,
                now=completed_at,
                frame_age_seconds=self._snapshot_frame_age_seconds(result.get("snapshot")),
            )
            self.last_error = ""
        else:
            self.pose_candidate_gate.observe_formal_error(
                camera_id,
                analysis_started_at=now,
            )
            self.inference_scheduler.mark_error(camera_id, now=completed_at)
            self.last_error = str(result.get("error") or "camera analysis failed")
        self._prune_history_if_due()
        return 0.0

    def runtime_status(self) -> Dict[str, Any]:
        continual_status = (
            self.continual_pose_tracker.status(sorted(self._runtime_cameras))
            if self.continual_pose_tracker is not None
            else {"schema_version": "disabled", "cameras": []}
        )
        stream_status = (
            self.camera_agent.managed_stream_status()
            if hasattr(self.camera_agent, "managed_stream_status")
            else {"managed_stream_count": 0, "streams": []}
        )
        return {
            "worker_running": self.is_running,
            "last_loop_started_at": self.last_loop_started_at,
            "last_rules_loaded_at": self.last_rules_loaded_at,
            "rules": self.last_rules_snapshot,
            "history_cleanup": self.last_history_cleanup_result,
            "temporal_engine": self.temporal_engine.version,
            "pose_factor_graph_engine": self.pose_factor_graph_engine.version,
            "inference_scheduler": self.inference_scheduler.status(now=self._monotonic_clock()),
            "continual_pose_tracker": getattr(self.continual_pose_tracker, "version", "disabled"),
            "continual_pose_running": self._tracking_thread is not None and self._tracking_thread.is_alive(),
            "continual_pose_camera_threads": self._continual_tracking_thread_status(),
            "continual_pose": continual_status,
            "continual_pose_error": self.last_continual_pose_error,
            "pose_inference_coordinator": (
                self.pose_inference_coordinator.status()
                if self.pose_inference_coordinator is not None
                else {"schema_version": "disabled", "running": False}
            ),
            "pose_candidate_validation": self.pose_candidate_gate.status(),
            "continual_identity_bridge": {
                "count": self.continual_identity_bridge_count,
                "last": dict(self.last_continual_identity_bridge),
            },
            "motion_gate": self.motion_gate.status() if self.motion_gate is not None else {"schema_version": "disabled"},
            "vision_runtime": (
                self.detect_agent.runtime_status()
                if hasattr(self.detect_agent, "runtime_status")
                else {}
            ),
            "camera_streams": stream_status,
            "persistence": {
                "schema_version": "event-driven-persistence-v1",
                "activity_log_interval_seconds": self.activity_log_interval_seconds,
                "activity_posture_stability_seconds": self.activity_posture_stability_seconds,
                "activity_absence_stability_seconds": self.activity_absence_stability_seconds,
                "pending_activity_posture_cameras": sorted(self.pending_activity_posture),
                "pending_activity_absence_cameras": sorted(self.pending_activity_absence),
                "risk_evidence_interval_seconds": self.risk_evidence_interval_seconds,
                "metrics": dict(self.persistence_metrics),
                "last_reason_by_camera": dict(self.last_persistence_reason),
            },
            "runtime_reconciliation": self.runtime_reconciliation,
            "last_event_state_command": dict(self.last_event_state_command),
            "last_error": self.last_error,
        }

    def camera_presence_status(
        self,
        camera_id: int,
        *,
        expected_interval_seconds: float = 5.0,
    ) -> Dict[str, Any]:
        historical = self.storage.camera_presence_status(
            int(camera_id),
            expected_interval_seconds=max(1, int(expected_interval_seconds)),
        )
        return self.observation_coverage_tracker.status(
            int(camera_id),
            expected_interval_seconds=expected_interval_seconds,
            historical=historical,
        )

    def _refresh_runtime_config(self, now: float) -> None:
        if self._runtime_config_refreshed_at and now - self._runtime_config_refreshed_at < self._runtime_config_refresh_seconds:
            return
        rules = self.storage.get_rules()
        cameras = self.storage.list_cameras(include_secret=True)
        cameras_by_id = {int(camera["id"]): camera for camera in cameras}
        self.last_rules_loaded_at = rules.get("updated_at")
        self.last_rules_snapshot = dict(rules)
        if hasattr(self.camera_agent, "reconcile_managed_streams"):
            self.camera_agent.reconcile_managed_streams(list(cameras_by_id.values()))
        self._runtime_cameras = {camera_id: dict(camera) for camera_id, camera in cameras_by_id.items()}
        current_camera_ids = set(cameras_by_id)
        for removed_camera_id in self._known_camera_ids - current_camera_ids:
            self._reset_camera_runtime_memory(removed_camera_id)
        self._known_camera_ids = current_camera_ids

        disabled_camera_ids = {
            camera_id for camera_id, camera in cameras_by_id.items() if not camera.get("enabled")
        }
        for camera_id in disabled_camera_ids - self._disabled_camera_ids:
            self.storage.close_camera_runtime_state(camera_id, reason="camera_disabled")
            self._reset_camera_runtime_memory(camera_id)
        self._disabled_camera_ids = disabled_camera_ids
        self._runtime_config_refreshed_at = float(now)

    def request_rules_reload(self) -> None:
        self._runtime_config_refreshed_at = 0.0
        self.inference_scheduler.wake_all(now=self._monotonic_clock())
        self._wake.set()

    def handle_camera_source_transition(self, transition: Dict[str, Any]) -> None:
        camera_id = int(transition.get("camera_id") or 0)
        if camera_id <= 0:
            return
        self.storage.close_camera_runtime_state(
            camera_id,
            reason=str(transition.get("reason") or "camera_source_transition"),
        )
        self._reset_camera_runtime_memory(camera_id)
        self._runtime_config_refreshed_at = 0.0
        self.inference_scheduler.wake_all(now=self._monotonic_clock())
        self._wake.set()

    def _reset_camera_runtime_memory(
        self,
        camera_id: int,
        *,
        preserve_camera_error_state: bool = False,
    ) -> None:
        camera_id = int(camera_id)
        self.temporal_engine.reset_camera(camera_id)
        self.inference_scheduler.reset_camera(camera_id)
        with self._safety_state_lock:
            self.pose_factor_graph_engine.reset_camera(camera_id)
            self.rule_engine.reset_camera(
                camera_id,
                preserve_camera_error_state=preserve_camera_error_state,
            )
            self._safety_state_generation[camera_id] = self._safety_state_generation.get(camera_id, 0) + 1
        if self.continual_pose_tracker is not None:
            self.continual_pose_tracker.reset_camera(camera_id)
        if self.pose_inference_coordinator is not None:
            self.pose_inference_coordinator.reset_camera(camera_id)
        if self.motion_gate is not None:
            self.motion_gate.reset_camera(camera_id)
        self.previous_frames.pop(camera_id, None)
        self.latest_evaluations.pop(camera_id, None)
        self.last_persisted_analysis_at.pop(camera_id, None)
        self.last_activity_persisted_at.pop(camera_id, None)
        self.last_activity_signature.pop(camera_id, None)
        self.pending_activity_posture.pop(camera_id, None)
        self.pending_activity_absence.pop(camera_id, None)
        self.last_persistence_reason.pop(camera_id, None)
        self._last_continual_frame_ids.pop(camera_id, None)
        self.pose_candidate_gate.reset_camera(camera_id)
        self.observation_coverage_tracker.reset_camera(camera_id)

    def apply_event_state_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        event_id = int(str(command.get("edge_event_id") or "").strip())
        target_state = str(command.get("state") or "").strip().lower()
        if target_state not in {"acknowledged", "resolved", "rejected"}:
            raise ValueError(f"unsupported_event_state:{target_state}")
        resolution = str(command.get("resolution") or "").strip()
        if not resolution:
            resolution = "false_positive" if target_state == "rejected" else "handled"
        with self._safety_state_lock:
            event = self.storage.get_event(event_id)
            if event is None:
                raise RuntimeError(f"edge_event_not_found:{event_id}")
            updated = self.storage.update_event(
                event_id,
                {"acknowledged": True, "resolution": resolution},
            )
            if updated is None:
                raise RuntimeError(f"edge_event_update_failed:{event_id}")
            camera_id = int(updated["camera_id"])
            self.rule_engine.clear_safety_incident(camera_id)
            self.pose_factor_graph_engine.clear_safety_incident(camera_id)
            self._safety_state_generation[camera_id] = self._safety_state_generation.get(camera_id, 0) + 1
            self.latest_evaluations.pop(camera_id, None)
        self.last_event_state_command = {
            "command_id": str(command.get("command_id") or ""),
            "edge_event_id": event_id,
            "camera_id": camera_id,
            "state": target_state,
            "resolution": resolution,
            "applied_at": datetime.now(timezone.utc).isoformat(),
        }
        return dict(self.last_event_state_command)

    def _run_continual_tracking(self) -> None:
        try:
            while not self._stop.is_set():
                self._sync_continual_tracking_threads()
                self._stop.wait(0.25)
        finally:
            self._stop_continual_tracking_threads()

    def _sync_continual_tracking_threads(self) -> None:
        active_ids = {
            int(camera_id)
            for camera_id, camera in self._runtime_cameras.items()
            if camera.get("enabled", True)
        }
        stale_threads: list[Thread] = []
        with self._tracking_threads_lock:
            for camera_id in list(self._tracking_camera_threads):
                thread = self._tracking_camera_threads.get(camera_id)
                if camera_id in active_ids and thread is not None and thread.is_alive():
                    continue
                stop_event = self._tracking_camera_stops.pop(camera_id, None)
                if stop_event is not None:
                    stop_event.set()
                if thread is not None:
                    stale_threads.append(thread)
                self._tracking_camera_threads.pop(camera_id, None)

            for camera_id in sorted(active_ids):
                thread = self._tracking_camera_threads.get(camera_id)
                if thread is not None and thread.is_alive():
                    continue
                stop_event = Event()
                thread = Thread(
                    target=self._run_continual_tracking_camera,
                    args=(camera_id, stop_event),
                    name=f"gohome-edge-pose-tracker-{camera_id}",
                    daemon=True,
                )
                self._tracking_camera_stops[camera_id] = stop_event
                self._tracking_camera_threads[camera_id] = thread
                thread.start()
        for thread in stale_threads:
            thread.join(timeout=1.0)

    def _stop_continual_tracking_threads(self) -> None:
        with self._tracking_threads_lock:
            threads = list(self._tracking_camera_threads.values())
            for stop_event in self._tracking_camera_stops.values():
                stop_event.set()
            self._tracking_camera_threads.clear()
            self._tracking_camera_stops.clear()
        deadline = time.monotonic() + 2.0
        for thread in threads:
            if thread is not current_thread():
                thread.join(timeout=max(0.0, deadline - time.monotonic()))

    def _continual_tracking_thread_status(self) -> Dict[str, Any]:
        with self._tracking_threads_lock:
            return {
                "active_camera_ids": sorted(
                    camera_id
                    for camera_id, thread in self._tracking_camera_threads.items()
                    if thread.is_alive()
                ),
                "thread_count": sum(
                    1 for thread in self._tracking_camera_threads.values() if thread.is_alive()
                ),
            }

    def _run_continual_tracking_camera(self, camera_id: int, stop_event: Event) -> None:
        while not self._stop.is_set() and not stop_event.is_set():
            camera = self._runtime_cameras.get(int(camera_id))
            if camera is None or not camera.get("enabled", True):
                stop_event.wait(0.25)
                continue
            capture = self.camera_agent.latest_cached_frame(camera, max_age_seconds=0.5)
            if capture:
                self._process_continual_capture(camera, capture)
            waiter = getattr(self.camera_agent, "wait_for_frame_update", None)
            if callable(waiter):
                waiter(
                    [camera],
                    {int(camera_id): self._last_continual_frame_ids.get(int(camera_id), "")},
                    timeout=0.25,
                )
            else:
                stop_event.wait(self._continual_tracking_interval_seconds())

    def _continual_tracking_interval_seconds(self) -> float:
        interval = getattr(self.continual_pose_tracker, "minimum_interval_seconds", 0.05)
        try:
            return max(0.05, min(0.25, float(interval)))
        except (TypeError, ValueError):
            return 0.05

    def _continual_tracking_wait_seconds(self, started_at: float) -> float:
        elapsed = max(0.0, self._monotonic_clock() - float(started_at))
        return max(0.0, self._continual_tracking_interval_seconds() - elapsed)

    def _wait_for_continual_frame_update(self, started_at: float) -> None:
        waiter = getattr(self.camera_agent, "wait_for_frame_update", None)
        cameras = list(self._runtime_cameras.values())
        if callable(waiter) and cameras:
            waiter(
                cameras,
                dict(self._last_continual_frame_ids),
                timeout=0.25,
            )
            return
        self._stop.wait(self._continual_tracking_wait_seconds(started_at))

    def _run_continual_tracking_iteration(self) -> None:
        if self.camera_agent is None or self.continual_pose_tracker is None:
            return
        cameras = list(self._runtime_cameras.values())
        for camera in cameras:
            if not camera.get("enabled", True) or not camera.get("id"):
                continue
            capture = self.camera_agent.latest_cached_frame(camera, max_age_seconds=0.5)
            if not capture:
                continue
            self._process_continual_capture(camera, capture)

    def _process_continual_capture(self, camera: Dict[str, Any], capture: Dict[str, Any]) -> None:
        camera_id = int(camera["id"])
        if not self._capture_identity_matches(camera, capture):
            self.last_continual_pose_error = f"camera {camera_id}: frame source identity mismatch"
            return
        frame_id = str(capture.get("frame_id") or "")
        if not frame_id or frame_id == self._last_continual_frame_ids.get(camera_id):
            return
        self._last_continual_frame_ids[camera_id] = frame_id
        if self.motion_gate is not None:
            gate = self.motion_gate.update(camera_id, capture["frame"], frame_id=frame_id)
            if gate.get("detected"):
                self.inference_scheduler.signal_activity(
                    camera_id,
                    now=self._monotonic_clock(),
                )
                self._wake.set()
        self._submit_coordinated_display_pose(camera, capture)
        self.observe_stream_frame(camera, capture["frame"], capture)

    def _submit_coordinated_display_pose(
        self,
        camera: Dict[str, Any],
        capture: Dict[str, Any],
    ) -> None:
        coordinator = self.pose_inference_coordinator
        if coordinator is None or not coordinator.is_running:
            return
        rules = dict(self.last_rules_snapshot)
        if not bool(rules.get("fall_detection_enabled") or rules.get("activity_detection_enabled")):
            return
        camera_id = int(camera["id"])
        now = self._monotonic_clock()
        config = {
            **rules,
            "camera_id": camera_id,
            "force_demo_vision": str(camera.get("stream_url", "")).strip().lower().startswith("demo:"),
            "pose_detection_enabled": True,
            "pose_runtime_reason": "coordinated_display_anchor",
            "pose_allow_internal_detector_fallback": False,
            "eacp_mode": self.inference_scheduler.mode(camera_id, now=now),
        }
        try:
            coordinator.submit_display(
                camera_id=camera_id,
                frame=capture["frame"],
                frame_id=str(capture.get("frame_id") or ""),
                source_key=str(capture.get("source_key") or ""),
                captured_at=str(capture.get("captured_at") or ""),
                captured_monotonic=capture.get("captured_monotonic"),
                config=config,
                minimum_interval_seconds=self.inference_scheduler.pose_interval(camera_id, now=now),
            )
        except (PoseCoordinatorError, ValueError) as exc:
            self.last_continual_pose_error = str(exc)

    def _handle_coordinated_display_pose(self, delivery: Dict[str, Any]) -> None:
        if self.continual_pose_tracker is None:
            return
        camera_id = int(delivery.get("camera_id") or 0)
        camera = self._runtime_cameras.get(camera_id)
        if camera is None or not self._capture_identity_matches(camera, delivery):
            return
        analysis = delivery.get("analysis")
        if not isinstance(analysis, dict):
            return
        poses = [
            pose
            for pose in (analysis.get("poses") or [])
            if isinstance(pose, dict)
        ]
        person_present = bool(poses)
        try:
            validated_context = self._validated_anchor_context(camera_id, delivery, poses)
            if (
                "formal" not in set(delivery.get("roles") or [])
                and poses
                and validated_context is not None
            ):
                context = {
                    **validated_context,
                    **analysis,
                    "inference_backend": "hailo",
                    "display_anchor_runtime": {
                        "schema_version": "eacp-display-anchor-v1",
                        "formal_evidence_eligible": False,
                        "source": "pose_inference_coordinator",
                    },
                }
                self.continual_pose_tracker.observe(
                    camera_id,
                    delivery["frame"],
                    frame_id=str(delivery.get("frame_id") or ""),
                    captured_at=str(delivery.get("captured_at") or ""),
                    captured_monotonic=delivery.get("captured_monotonic"),
                    poses=poses,
                    context=context,
                    source_key=str(delivery.get("source_key") or ""),
                    person_present=True,
                )
            frame = delivery.get("frame")
            frame_height, frame_width = frame.shape[:2] if hasattr(frame, "shape") else (1, 1)
            validation = self.pose_candidate_gate.observe(
                camera_id,
                source_key=str(delivery.get("source_key") or ""),
                poses=poses,
                frame_width=int(frame_width),
                frame_height=int(frame_height),
                now=self._monotonic_clock(),
            )
            if validation.get("validation_requested") and self.inference_scheduler.request_validation(
                camera_id,
                now=self._monotonic_clock(),
                reason=str(validation.get("reason") or "consistent_pose_candidate"),
            ):
                self._wake.set()
            self.last_continual_pose_error = ""
        except Exception as exc:
            self.last_continual_pose_error = str(exc)

    def _validated_anchor_context(
        self,
        camera_id: int,
        delivery: Dict[str, Any],
        poses: list[Dict[str, Any]],
    ) -> Dict[str, Any] | None:
        metadata = self.continual_pose_tracker.latest_metadata(int(camera_id))
        tracking = metadata.get("tracking") if isinstance(metadata.get("tracking"), dict) else {}
        context = metadata.get("analysis_context") if isinstance(metadata.get("analysis_context"), dict) else {}
        if str(tracking.get("state") or "") not in {"observed", "tracked"}:
            return None
        if bool(tracking.get("display_only_stale")):
            return None
        if str(metadata.get("source_key") or "") != str(delivery.get("source_key") or ""):
            return None
        runtime = context.get("inference_runtime") if isinstance(context.get("inference_runtime"), dict) else {}
        if runtime.get("formal_evidence_eligible") is not True:
            return None
        validated = [
            item
            for item in (tracking.get("poses") or [])
            if isinstance(item, dict) and self._valid_bbox(item.get("bbox"))
        ]
        matched = any(
            self._bbox_iou(pose.get("bbox"), anchor.get("bbox")) >= 0.12
            for pose in poses
            if self._valid_bbox(pose.get("bbox"))
            for anchor in validated
        )
        return dict(context) if matched else None

    def _prune_history_if_due(self) -> None:
        if self.snapshot_dir is None:
            return
        now = time.monotonic()
        if now - self.last_history_cleanup_at < self.history_cleanup_interval_seconds:
            return
        self.last_history_cleanup_at = now
        try:
            storage_status = self.storage.runtime_storage_status(
                self.snapshot_dir,
                object_storage_dir=self.object_storage_dir,
                runtime_dir=self.runtime_dir,
                retention_hours=self.history_retention_hours,
            )
            used_percent = float(storage_status.get("disk_used_percent") or 0.0)
            runtime_bytes = int(storage_status.get("runtime_allocated_bytes") or 0)
            effective_retention_hours = self.history_retention_hours
            pressure = "normal"
            if (
                used_percent >= self.local_storage_critical_percent
                or runtime_bytes >= self.local_runtime_budget_bytes
            ):
                effective_retention_hours = 1
                pressure = "critical"
            elif (
                used_percent >= self.local_storage_high_watermark_percent
                or runtime_bytes >= int(self.local_runtime_budget_bytes * 0.8)
            ):
                effective_retention_hours = min(self.history_retention_hours, 2)
                pressure = "high"

            cleanup_batches = []
            max_batches = 20 if pressure == "critical" else 8 if pressure == "high" else 4
            for _ in range(max_batches):
                batch = self.storage.prune_runtime_history(
                    snapshot_dir=self.snapshot_dir,
                    object_storage_dir=self.object_storage_dir,
                    retention_hours=effective_retention_hours,
                    completed_upload_retention_days=self.completed_upload_retention_days,
                    event_evidence_retention_hours=self.event_evidence_retention_hours,
                    local_event_retention_days=self.local_event_retention_days,
                    batch_size=self.history_cleanup_batch_size,
                    discard_live_preview_uploads=True,
                    force_oldest=pressure == "critical",
                )
                cleanup_batches.append(batch)
                if not batch.get("has_more"):
                    break
                if pressure == "critical":
                    current_status = self.storage.runtime_storage_status(
                        self.snapshot_dir,
                        object_storage_dir=self.object_storage_dir,
                        runtime_dir=self.runtime_dir,
                        retention_hours=self.history_retention_hours,
                    )
                    below_disk_watermark = float(current_status.get("disk_used_percent") or 0.0) < self.local_storage_high_watermark_percent
                    below_runtime_budget = int(current_status.get("runtime_allocated_bytes") or 0) < int(self.local_runtime_budget_bytes * 0.8)
                    if below_disk_watermark and below_runtime_budget:
                        break
            deleted: Dict[str, int] = {}
            for batch in cleanup_batches:
                for key, count in (batch.get("deleted") or {}).items():
                    deleted[str(key)] = deleted.get(str(key), 0) + int(count or 0)
            last_batch = cleanup_batches[-1] if cleanup_batches else {}
            compaction = {"compacted": False, "reason": "storage_pressure_normal"}
            if pressure in {"high", "critical"} and any(deleted.values()):
                compaction = self.storage.compact_runtime_database(
                    snapshot_dir=self.snapshot_dir,
                    object_storage_dir=self.object_storage_dir,
                    runtime_dir=self.runtime_dir,
                )
            final_storage_status = self.storage.runtime_storage_status(
                self.snapshot_dir,
                object_storage_dir=self.object_storage_dir,
                runtime_dir=self.runtime_dir,
                retention_hours=self.history_retention_hours,
            )
            self.last_history_cleanup_result = {
                **last_batch,
                "deleted": deleted,
                "deleted_snapshot_files": sum(
                    int(batch.get("deleted_snapshot_files") or 0) for batch in cleanup_batches
                ),
                "skipped_snapshot_files": sum(
                    int(batch.get("skipped_snapshot_files") or 0) for batch in cleanup_batches
                ),
                "batch_count": len(cleanup_batches),
                "storage_pressure": pressure,
                "effective_retention_hours": effective_retention_hours,
                "runtime_budget_bytes": self.local_runtime_budget_bytes,
                "database_compaction": compaction,
                "storage_before": storage_status,
                "storage": final_storage_status,
            }
            self.last_history_cleanup_result["completed_at"] = datetime.now(timezone.utc).isoformat()
            self.last_history_cleanup_result["error"] = ""
        except Exception as exc:
            self.last_history_cleanup_result = {
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error": str(exc),
            }

    def process_camera(
        self,
        camera: Dict[str, Any],
        rules: Dict[str, Any],
        *,
        adaptive_pose: bool = False,
    ) -> Dict[str, Any]:
        with self.camera_analysis_guard(int(camera["id"])):
            return self._process_camera_serialized(camera, rules, adaptive_pose=adaptive_pose)

    def _process_camera_serialized(
        self,
        camera: Dict[str, Any],
        rules: Dict[str, Any],
        *,
        adaptive_pose: bool = False,
    ) -> Dict[str, Any]:
        camera_id = int(camera["id"])
        try:
            self.persistence_metrics["analysis_cycles"] += 1
            capture = self.camera_agent.capture_frame(camera)
            if not self._capture_identity_matches(camera, capture):
                raise RuntimeError(f"camera {camera_id}: frame source identity mismatch")
            frame = capture["frame"]
            pose_runtime_config = self._pose_runtime_config(camera_id, rules, adaptive=adaptive_pose)
            analysis_config = {
                **rules,
                "force_demo_vision": str(camera.get("stream_url", "")).strip().lower().startswith("demo:"),
                "camera_id": camera_id,
                **pose_runtime_config,
            }
            coordinated_pose: Dict[str, Any] | None = None
            if self.pose_inference_coordinator is not None and self.pose_inference_coordinator.is_running:
                coordinated_pose = self.pose_inference_coordinator.infer_for_analysis(
                    camera_id=camera_id,
                    frame=frame,
                    frame_id=str(capture.get("frame_id") or ""),
                    source_key=str(capture.get("source_key") or ""),
                    captured_at=str(capture.get("captured_at") or ""),
                    captured_monotonic=capture.get("captured_monotonic"),
                    config=analysis_config,
                )
                if (
                    coordinated_pose.get("accelerated") is not None
                    and bool(rules.get("fall_detection_enabled") or rules.get("activity_detection_enabled"))
                ):
                    analysis_config["pose_detection_enabled"] = True
                    if not pose_runtime_config.get("pose_detection_enabled"):
                        analysis_config["pose_runtime_reason"] = "coordinated_hailo_pose_probe"
            if coordinated_pose is None:
                analysis = self.detect_agent.analyze_frame_with_config(
                    frame,
                    previous_frame=self.previous_frames.get(camera_id),
                    config=analysis_config,
                )
            else:
                analysis = self.detect_agent.analyze_frame_with_config(
                    frame,
                    previous_frame=self.previous_frames.get(camera_id),
                    config=analysis_config,
                    pose_accelerated=coordinated_pose.get("accelerated"),
                    pose_accelerated_provided=True,
                )
            analysis["inference_runtime"] = self._inference_runtime_payload(
                analysis_config,
                coordinated_pose=coordinated_pose,
            )
            self._attach_continual_identity_hints(camera_id, analysis)
            temporal = self.temporal_engine.update(camera_id, analysis)
            self.observation_coverage_tracker.observe(
                camera_id,
                observed_at=str(capture.get("captured_at") or ""),
                person_present=bool(temporal.get("credible_person_present")),
                valid=not bool(analysis.get("black_screen")),
                now=self._monotonic_clock(),
            )
            self._publish_continual_pose_anchor(camera_id, frame=frame, capture=capture, analysis=analysis)
            with self._safety_state_lock:
                safety_generation = self._safety_state_generation.get(camera_id, 0)
                self.pose_factor_graph_engine.update(camera_id, analysis, config=rules)
            self._attach_temporal_evidence(camera_id, analysis)
            persistence_now = self._monotonic_clock()
            persistence_reason = self._analysis_persistence_reason(
                camera_id,
                analysis,
                temporal,
                now=persistence_now,
            )
            should_persist = bool(persistence_reason)
            snapshot: Dict[str, Any] = self._ephemeral_snapshot(camera_id, capture, analysis)
            detection_result: Dict[str, Any] | None = None
            if should_persist:
                snapshot, detection_result = self._persist_analysis_frame(
                    camera,
                    capture,
                    frame,
                    analysis,
                    temporal,
                    persisted_at=persistence_now,
                    reason=persistence_reason,
                )
            self._attach_temporal_evidence(camera_id, analysis)
            with self._safety_state_lock:
                camera_recovery = self.rule_engine.record_camera_online(camera_id)
            self.storage.update_camera_status(camera_id, "online")
            if camera_recovery and camera_recovery.get("confirmed"):
                self._resolve_recovered_camera_incidents(camera, camera_recovery)
            elif camera_id not in self._camera_online_reconciled_ids:
                self._resolve_recovered_camera_incidents(
                    camera,
                    {
                        "schema_version": "gohome-camera-recovery-v1",
                        "confirmed": True,
                        "failure_count": 0,
                        "duration_seconds": 0.0,
                        "last_error": "",
                        "recovered_at": datetime.now(timezone.utc).isoformat(),
                        "reason": "current_stream_online",
                    },
                )
            self._camera_online_reconciled_ids.add(camera_id)

            with self._safety_state_lock:
                if safety_generation != self._safety_state_generation.get(camera_id, 0):
                    self.pose_factor_graph_engine.update(camera_id, analysis, config=rules)
                    safety_generation = self._safety_state_generation.get(camera_id, 0)
                evaluation = self.rule_engine.evaluate_snapshot(camera, snapshot, analysis, rules)
            if not should_persist and self._requires_durable_candidate(evaluation):
                snapshot, detection_result = self._persist_analysis_frame(
                    camera,
                    capture,
                    frame,
                    analysis,
                    temporal,
                    persisted_at=self._monotonic_clock(),
                    reason="durable_candidate",
                )
                should_persist = True
                persistence_reason = "durable_candidate"
                self._attach_temporal_evidence(camera_id, analysis)
                self._attach_snapshot_to_evaluation(evaluation, snapshot, analysis)

            activity_persisted = self._persist_activity_timeline_if_due(
                camera,
                snapshot,
                temporal,
                now=self._monotonic_clock(),
            )

            evaluation_dict = evaluation.to_dict()
            persisted_evaluation: Dict[str, Any] | None = None
            if should_persist:
                persisted_evaluation = self.storage.create_rule_evaluation(
                    camera_id=camera_id,
                    snapshot_id=int(snapshot["id"]),
                    detection_result_id=int(detection_result["id"]) if detection_result else None,
                    evaluation=evaluation_dict,
                    rule_set_version=str(rules.get("updated_at") or ""),
                )
            self.latest_evaluations[camera_id] = persisted_evaluation or evaluation_dict
            self._close_observation_logs(camera, evaluation)
            with self._safety_state_lock:
                if safety_generation == self._safety_state_generation.get(camera_id, 0):
                    self._resolve_recovered_fall_incident(camera, evaluation)
                    self._emit_candidates(
                        camera,
                        evaluation=evaluation,
                        detection_result_id=int(detection_result["id"]) if detection_result else None,
                        rule_evaluation_id=int(persisted_evaluation["id"]) if persisted_evaluation else None,
                    )
            self.previous_frames[camera_id] = frame.copy()
            return {
                "ok": True,
                "persisted": should_persist,
                "persistence_reason": persistence_reason,
                "activity_persisted": activity_persisted,
                "snapshot": snapshot,
                "analysis": analysis,
                "detection_result": detection_result,
                "evaluation": persisted_evaluation or evaluation_dict,
            }

        except PoseCoordinatorError as exc:
            return {"ok": False, "error": str(exc)}
        except CameraError as exc:
            self.storage.update_camera_status(camera_id, "offline", str(exc))
            self.storage.close_camera_runtime_state(camera_id, reason="camera_offline")
            self._reset_camera_runtime_memory(camera_id, preserve_camera_error_state=True)
            with self._safety_state_lock:
                evaluation = self.rule_engine.evaluate_camera_error(camera, rules, str(exc))
            evaluation_dict = evaluation.to_dict()
            persisted_evaluation = self.storage.create_rule_evaluation(
                camera_id=camera_id,
                snapshot_id=None,
                detection_result_id=None,
                evaluation=evaluation_dict,
                rule_set_version=str(rules.get("updated_at") or ""),
            )
            self.latest_evaluations[camera_id] = persisted_evaluation
            self._emit_candidates(
                camera,
                evaluation=evaluation,
                detection_result_id=None,
                rule_evaluation_id=int(persisted_evaluation["id"]),
            )
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            self.storage.update_camera_status(camera_id, "error", str(exc))
            self.storage.close_camera_runtime_state(camera_id, reason="camera_error")
            self._reset_camera_runtime_memory(camera_id)
            return {"ok": False, "error": str(exc)}

    def observe_stream_frame(
        self,
        camera: Dict[str, Any],
        frame: Any,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        if self.continual_pose_tracker is None or not camera.get("id"):
            return None
        if not self._capture_identity_matches(camera, metadata):
            self.last_continual_pose_error = f"camera {int(camera['id'])}: frame source identity mismatch"
            return None
        try:
            payload = self.continual_pose_tracker.update_frame(
                int(camera["id"]),
                frame,
                frame_id=str(metadata.get("frame_id") or ""),
                captured_at=str(metadata.get("captured_at") or ""),
                captured_monotonic=metadata.get("captured_monotonic"),
                source_key=str(metadata.get("source_key") or ""),
            )
            tracking_state = str(payload.get("state") or "") if isinstance(payload, dict) else ""
            if isinstance(payload, dict) and (
                tracking_state == "coasting" or bool(payload.get("display_only_stale"))
            ):
                self.inference_scheduler.request_refresh(
                    int(camera["id"]),
                    now=self._monotonic_clock(),
                    reason=str(payload.get("reason") or "pose_tracking_stale"),
                )
                self._wake.set()
            risk_hint = payload.get("risk_hint") if isinstance(payload, dict) else None
            if isinstance(risk_hint, dict) and risk_hint.get("detected"):
                self.inference_scheduler.signal_activity(
                    int(camera["id"]),
                    now=self._monotonic_clock(),
                    risk=True,
                    source=str(risk_hint.get("reason") or "klt_risk_hint"),
                )
                self._wake.set()
            self.last_continual_pose_error = ""
            return payload if isinstance(payload, dict) else None
        except Exception as exc:
            self.last_continual_pose_error = str(exc)
            return None

    def _publish_continual_pose_anchor(
        self,
        camera_id: int,
        *,
        frame: Any,
        capture: Dict[str, Any],
        analysis: Dict[str, Any],
    ) -> None:
        if self.continual_pose_tracker is None:
            return
        camera = self._runtime_cameras.get(int(camera_id)) or {"id": int(camera_id)}
        if not self._capture_identity_matches(camera, capture):
            self.last_continual_pose_error = f"camera {int(camera_id)}: anchor source identity mismatch"
            return
        pose_status = str(analysis.get("pose_model_status") or "")
        backend_status = analysis.get("inference_backend_status")
        model_confirmed_empty = (
            pose_status == "disabled"
            and str(analysis.get("inference_backend") or "") == "hailo"
            and isinstance(backend_status, dict)
            and str(backend_status.get("status") or "") == "ready"
            and int(analysis.get("person_count") or 0) == 0
            and not list(analysis.get("people") or [])
        )
        if pose_status not in {"ready", "not_visible"} and not model_confirmed_empty:
            return
        poses = [
            pose
            for pose in (analysis.get("poses") or [])
            if str(pose.get("tracking_state") or "fresh") in {"fresh", "observed"}
        ]
        try:
            payload = self.continual_pose_tracker.observe(
                int(camera_id),
                frame,
                frame_id=str(capture.get("frame_id") or ""),
                captured_at=str(capture.get("captured_at") or ""),
                captured_monotonic=capture.get("captured_monotonic"),
                poses=poses,
                context=analysis,
                source_key=str(capture.get("source_key") or ""),
                person_present=bool(
                    int(analysis.get("person_count") or 0) > 0
                    or list(analysis.get("people") or [])
                    or poses
                ),
            )
            analysis["continual_pose_anchor"] = payload
            self.last_continual_pose_error = ""
        except Exception as exc:
            self.last_continual_pose_error = str(exc)

    def _capture_identity_matches(self, camera: Dict[str, Any], metadata: Dict[str, Any]) -> bool:
        camera_id = int(camera.get("id") or 0)
        if camera_id <= 0:
            return False
        frame_id = str(metadata.get("frame_id") or "")
        if not frame_id.startswith(f"{camera_id}-"):
            return False
        captured_camera_id = metadata.get("camera_id")
        if captured_camera_id not in (None, "") and int(captured_camera_id) != camera_id:
            return False
        source_matcher = getattr(self.camera_agent, "frame_source_matches", None)
        if callable(source_matcher):
            if not source_matcher(camera, metadata.get("source_key")):
                return False
        else:
            source_key_resolver = getattr(self.camera_agent, "frame_source_key", None)
            if callable(source_key_resolver):
                expected_source_key = str(source_key_resolver(camera) or "")
                actual_source_key = str(metadata.get("source_key") or "")
                if not expected_source_key or actual_source_key != expected_source_key:
                    return False
        actual_source_key = str(metadata.get("source_key") or "")
        active_source_resolver = getattr(self.camera_agent, "active_frame_source_key", None)
        if actual_source_key and callable(active_source_resolver):
            active_source_key = str(active_source_resolver(camera) or "")
            if active_source_key and actual_source_key != active_source_key:
                return False
        return True

    def _attach_continual_identity_hints(self, camera_id: int, analysis: Dict[str, Any]) -> None:
        if self.continual_pose_tracker is None:
            return
        tracking = self.continual_pose_tracker.latest(int(camera_id))
        if str(tracking.get("state") or "") != "tracked" or tracking.get("display_only_stale"):
            return
        quality = tracking.get("quality") if isinstance(tracking.get("quality"), dict) else {}
        tracked_points = int(quality.get("tracked_point_count") or 0)
        forward_backward_error = float(quality.get("forward_backward_error") or 999.0)
        geometry_scale = float(quality.get("geometry_scale") or 0.0)
        verified_identity_bridge = bool(
            tracked_points >= 6
            and forward_backward_error <= 1.8
            and 0.65 <= geometry_scale <= 1.45
        )
        if not verified_identity_bridge:
            return
        tracked_poses = [
            pose
            for pose in (tracking.get("poses") or [])
            if isinstance(pose, dict)
            and pose.get("track_id")
            and self._valid_bbox(pose.get("bbox"))
        ]
        if not tracked_poses:
            return
        people = analysis.get("people") if isinstance(analysis.get("people"), list) else []
        poses = analysis.get("poses") if isinstance(analysis.get("poses"), list) else []
        pose_targets = [item for item in poses if isinstance(item, dict) and self._valid_bbox(item.get("bbox"))]
        person_targets = [item for item in people if isinstance(item, dict) and self._valid_bbox(item.get("bbox"))]
        targets = pose_targets or person_targets
        width = max(1.0, float(analysis.get("image_width") or 1.0))
        height = max(1.0, float(analysis.get("image_height") or 1.0))
        candidates = []
        for target_index, target in enumerate(targets):
            for tracked_index, tracked in enumerate(tracked_poses):
                overlap = self._bbox_iou(target["bbox"], tracked["bbox"])
                distance = self._bbox_center_distance(target["bbox"], tracked["bbox"], width, height)
                if overlap < 0.12 and distance > 0.16:
                    continue
                candidates.append((overlap * 2.0 + max(0.0, 1.0 - distance / 0.16), target_index, tracked_index))
        used_targets: set[int] = set()
        used_tracks: set[int] = set()
        for _score, target_index, tracked_index in sorted(candidates, reverse=True):
            if target_index in used_targets or tracked_index in used_tracks:
                continue
            targets[target_index]["_continual_track_id_hint"] = str(tracked_poses[tracked_index]["track_id"])
            targets[target_index]["_continual_track_id_hint_verified"] = True
            if targets is pose_targets:
                matching_person = max(
                    person_targets,
                    key=lambda item: self._bbox_iou(item["bbox"], targets[target_index]["bbox"]),
                    default=None,
                )
                if matching_person is not None and self._bbox_iou(matching_person["bbox"], targets[target_index]["bbox"]) >= 0.12:
                    matching_person["_continual_track_id_hint"] = str(tracked_poses[tracked_index]["track_id"])
                    matching_person["_continual_track_id_hint_verified"] = True
            self.continual_identity_bridge_count += 1
            self.last_continual_identity_bridge = {
                "camera_id": int(camera_id),
                "track_id": str(tracked_poses[tracked_index]["track_id"]),
                "source": "pose" if targets is pose_targets else "person",
            }
            used_targets.add(target_index)
            used_tracks.add(tracked_index)

    def _valid_bbox(self, bbox: Any) -> bool:
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return False
        try:
            x1, y1, x2, y2 = [float(value) for value in bbox]
        except (TypeError, ValueError):
            return False
        return x2 > x1 and y2 > y1

    def _bbox_iou(self, first: Any, second: Any) -> float:
        if not self._valid_bbox(first) or not self._valid_bbox(second):
            return 0.0
        ax1, ay1, ax2, ay2 = [float(value) for value in first]
        bx1, by1, bx2, by2 = [float(value) for value in second]
        intersection = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(0.0, min(ay2, by2) - max(ay1, by1))
        union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - intersection
        return intersection / union if union > 0 else 0.0

    def _bbox_center_distance(self, first: Any, second: Any, width: float, height: float) -> float:
        ax1, ay1, ax2, ay2 = [float(value) for value in first]
        bx1, by1, bx2, by2 = [float(value) for value in second]
        dx = ((ax1 + ax2) - (bx1 + bx2)) / (2.0 * max(1.0, width))
        dy = ((ay1 + ay2) - (by1 + by2)) / (2.0 * max(1.0, height))
        return (dx * dx + dy * dy) ** 0.5

    def _persist_analysis_frame(
        self,
        camera: Dict[str, Any],
        capture: Dict[str, Any],
        frame: Any,
        analysis: Dict[str, Any],
        temporal: Dict[str, Any],
        *,
        persisted_at: float,
        reason: str,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        camera_id = int(camera["id"])
        relative_path = self.camera_agent.snapshot_relative_path(camera_id)
        self.camera_agent.save_frame(frame, relative_path)
        snapshot = self.storage.create_snapshot(
            camera_id=camera_id,
            image_path=relative_path,
            width=capture["width"],
            height=capture["height"],
            brightness=analysis["brightness"],
            motion_score=analysis["motion_score"],
            tags=analysis["tags"],
            person_count=(
                temporal.get("credible_person_count")
                if "credible_person_count" in temporal
                else analysis.get("person_count")
            ),
            analysis=analysis,
        )
        self.temporal_engine.attach_snapshot(camera_id, snapshot)
        self._attach_temporal_evidence(camera_id, analysis)
        detection_result = self.storage.create_detection_result(
            camera_id=camera_id,
            snapshot_id=int(snapshot["id"]),
            captured_at=snapshot["captured_at"],
            width=capture["width"],
            height=capture["height"],
            analysis=analysis,
        )
        self.last_persisted_analysis_at[camera_id] = float(persisted_at)
        self.last_persistence_reason[camera_id] = str(reason or "evidence")
        self.persistence_metrics["image_writes"] += 1
        if reason == "durable_candidate":
            self.persistence_metrics["candidate_image_writes"] += 1
        else:
            self.persistence_metrics["risk_image_writes"] += 1
        return snapshot, detection_result

    def _ephemeral_snapshot(
        self,
        camera_id: int,
        capture: Dict[str, Any],
        analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        captured_at = str(capture.get("captured_at") or datetime.now(timezone.utc).isoformat())
        return {
            "id": None,
            "camera_id": int(camera_id),
            "image_path": "",
            "image_url": "",
            "captured_at": captured_at,
            "created_at": captured_at,
            "width": capture.get("width"),
            "height": capture.get("height"),
            "brightness": analysis.get("brightness"),
            "motion_score": analysis.get("motion_score"),
            "person_count": analysis.get("person_count"),
            "tags": list(analysis.get("tags") or []),
        }

    def _attach_temporal_evidence(self, camera_id: int, analysis: Dict[str, Any]) -> None:
        factor_graph = analysis.get("pose_factor_graph") if isinstance(analysis.get("pose_factor_graph"), dict) else {}
        evidence_track = factor_graph.get("fast_fall_track")
        if not isinstance(evidence_track, dict):
            prolonged_tracks = factor_graph.get("prolonged_floor_lying_tracks") or []
            evidence_track = prolonged_tracks[0] if prolonged_tracks else None
        if not isinstance(evidence_track, dict):
            tracked_poses = [
                pose for pose in (analysis.get("poses") or [])
                if isinstance(pose, dict) and pose.get("track_id")
            ]
            evidence_track = max(
                tracked_poses,
                key=lambda pose: float(pose.get("fall_score") or 0.0),
                default=None,
            )
        analysis["temporal_evidence_bundle"] = self.temporal_engine.evidence_bundle(
            camera_id,
            event_type="pose_safety_candidate",
            track_id=str((evidence_track or {}).get("track_id") or "") or None,
            max_age_seconds=15,
        )

    def _requires_durable_candidate(self, evaluation: RuleEvaluation) -> bool:
        return any(candidate.event_type not in LIFE_OBSERVATION_TYPES for candidate in evaluation.candidates)

    def _attach_snapshot_to_evaluation(
        self,
        evaluation: RuleEvaluation,
        snapshot: Dict[str, Any],
        analysis: Dict[str, Any],
    ) -> None:
        snapshot_id = int(snapshot["id"])
        evaluation.snapshot_id = snapshot_id
        for candidate in evaluation.candidates:
            candidate.snapshot_id = snapshot_id
            payload = {**(candidate.payload or {}), **analysis}
            rule = payload.get("rule") if isinstance(payload.get("rule"), dict) else {}
            payload["evidence"] = build_event_evidence(
                event_type=candidate.event_type,
                summary=candidate.summary,
                level=candidate.level,
                analysis=analysis,
                rule=rule,
            )
            candidate.payload = payload

    def _persist_activity_timeline_if_due(
        self,
        camera: Dict[str, Any],
        snapshot: Dict[str, Any],
        temporal: Dict[str, Any],
        *,
        now: float,
    ) -> bool:
        camera_id = int(camera["id"])
        state = str(temporal.get("presence_persistence_state") or "")
        if not state:
            state = "visible" if temporal.get("credible_person_present") else "absent"
        closures = list(temporal.get("posture_episode_closures") or [])
        if state == "uncertain" and not closures:
            self.pending_activity_absence.pop(camera_id, None)
            return False

        raw_signature = self._activity_signature(temporal, state=state)
        previous_signature = self.last_activity_signature.get(camera_id)
        signature = self._stable_activity_signature(
            camera_id,
            raw_signature,
            previous_signature=previous_signature,
            now=now,
        )
        effective_state = str(signature[0])
        transition_pending = effective_state != state
        last_persisted_at = self.last_activity_persisted_at.get(camera_id)
        interval_due = (
            last_persisted_at is None
            or max(0.0, float(now) - float(last_persisted_at)) >= self.activity_log_interval_seconds
        )
        first_visible_observation = previous_signature is None and effective_state == "visible"
        state_changed = previous_signature is not None and signature[:2] != previous_signature[:2]
        posture_changed = previous_signature is not None and signature[2:] != previous_signature[2:]
        should_write = bool(
            closures
            or first_visible_observation
            or state_changed
            or posture_changed
            or (effective_state == "visible" and interval_due and not transition_pending)
        )
        if not should_write:
            if previous_signature is None and state == "absent":
                jobs = self.storage.advance_activity_export(
                    camera_id=camera_id,
                    room=str(camera.get("room") or ""),
                    observed_at=str(snapshot.get("captured_at") or snapshot.get("created_at") or ""),
                    visible=False,
                    person_count=0,
                    postures=(),
                    confidence=None,
                    flush=True,
                    reason="person_not_visible",
                    max_gap_seconds=self.activity_log_interval_seconds * 2,
                )
                self.persistence_metrics["activity_intervals_enqueued"] += len(jobs)
            self.last_activity_signature[camera_id] = signature
            self.persistence_metrics["routine_image_writes_avoided"] += 1
            return False

        wrote = False
        if effective_state != "uncertain":
            wrote = self._update_presence_session(
                camera,
                snapshot,
                temporal,
                persistence_state=effective_state,
            ) or wrote
        wrote = bool(self._persist_posture_episodes(camera, snapshot, temporal)) or wrote
        export_jobs = [] if effective_state == "uncertain" else self.storage.advance_activity_export(
            camera_id=camera_id,
            room=str(camera.get("room") or ""),
            observed_at=str(snapshot.get("captured_at") or snapshot.get("created_at") or ""),
            visible=effective_state == "visible",
            person_count=int(signature[1]),
            postures=signature[2],
            confidence=self._activity_confidence(temporal),
            flush=bool(previous_signature is not None and (interval_due or state_changed or posture_changed)),
            reason=(
                "person_not_visible" if effective_state == "absent"
                else "posture_changed" if posture_changed
                else "activity_heartbeat" if interval_due
                else "person_visible"
            ),
            max_gap_seconds=self.activity_log_interval_seconds * 2,
        )
        self.persistence_metrics["activity_intervals_enqueued"] += len(export_jobs)
        self.last_activity_signature[camera_id] = signature
        self.last_activity_persisted_at[camera_id] = float(now)
        if wrote:
            self.persistence_metrics["structured_activity_writes"] += 1
        return wrote

    def _stable_activity_signature(
        self,
        camera_id: int,
        signature: tuple[Any, ...],
        *,
        previous_signature: tuple[Any, ...] | None,
        now: float,
    ) -> tuple[Any, ...]:
        state, person_count, postures = signature
        if previous_signature is not None and previous_signature[0] == "visible" and state == "absent":
            pending_since = self.pending_activity_absence.setdefault(camera_id, float(now))
            if max(0.0, float(now) - pending_since) < self.activity_absence_stability_seconds:
                return previous_signature
            self.pending_activity_absence.pop(camera_id, None)
        else:
            self.pending_activity_absence.pop(camera_id, None)
        if previous_signature is None or state != previous_signature[0] or state != "visible":
            self.pending_activity_posture.pop(camera_id, None)
            return signature

        meaningful_postures = tuple(item for item in postures if item and item != "unknown")
        previous_postures = tuple(previous_signature[2])
        if not meaningful_postures and previous_postures:
            self.pending_activity_posture.pop(camera_id, None)
            return previous_signature

        candidate = (state, person_count, meaningful_postures or tuple(postures))
        if candidate == previous_signature:
            self.pending_activity_posture.pop(camera_id, None)
            return candidate
        pending = self.pending_activity_posture.get(camera_id)
        if pending is None or pending[0] != candidate:
            self.pending_activity_posture[camera_id] = (candidate, float(now))
            return previous_signature
        if max(0.0, float(now) - pending[1]) < self.activity_posture_stability_seconds:
            return previous_signature
        self.pending_activity_posture.pop(camera_id, None)
        return candidate

    @staticmethod
    def _activity_signature(temporal: Dict[str, Any], *, state: str) -> tuple[Any, ...]:
        credible_ids = {str(item) for item in (temporal.get("credible_track_ids") or []) if item}
        active_tracks = temporal.get("active_tracks") if isinstance(temporal.get("active_tracks"), list) else []
        postures = sorted(
            str(track.get("posture") or "unknown")
            for track in active_tracks
            if isinstance(track, dict)
            and (not credible_ids or str(track.get("track_id") or "") in credible_ids)
        )
        return (
            str(state),
            int(temporal.get("credible_person_count") or 0),
            tuple(postures),
        )

    @staticmethod
    def _activity_confidence(temporal: Dict[str, Any]) -> float | None:
        credible_ids = {str(item) for item in (temporal.get("credible_track_ids") or []) if item}
        tracks = temporal.get("active_tracks") if isinstance(temporal.get("active_tracks"), list) else []
        values = [
            float(track.get("posture_confidence") or track.get("confidence") or 0.0)
            for track in tracks
            if isinstance(track, dict)
            and (not credible_ids or str(track.get("track_id") or "") in credible_ids)
            and float(track.get("posture_confidence") or track.get("confidence") or 0.0) > 0.0
        ]
        return sum(values) / len(values) if values else None

    def _update_presence_session(
        self,
        camera: Dict[str, Any],
        snapshot: Dict[str, Any],
        temporal: Dict[str, Any],
        *,
        persistence_state: str | None = None,
    ) -> bool:
        camera_id = int(camera["id"])
        observed_at = str(snapshot.get("captured_at") or snapshot.get("created_at") or "")
        snapshot_id = int(snapshot["id"]) if snapshot.get("id") else None
        persistence_state = str(persistence_state or temporal.get("presence_persistence_state") or "")
        if not persistence_state:
            persistence_state = "visible" if temporal.get("person_present") else "absent"
        if persistence_state == "visible":
            self.storage.upsert_presence_session(
                camera_id=camera_id,
                observed_at=observed_at,
                person_count=int(temporal.get("credible_person_count") or temporal.get("person_count") or 1),
                snapshot_id=snapshot_id,
                payload={
                    "schema_version": "gohome-presence-session-v3",
                    "track_ids": temporal.get("credible_track_ids") or temporal.get("current_track_ids") or [],
                    "postures": list(self._activity_signature(temporal, state="visible")[2]),
                    "evidence_source": "structured_activity_timeline",
                },
            )
            return True
        if persistence_state == "uncertain":
            return False
        closed = self.storage.close_presence_session(
            camera_id=camera_id,
            ended_at=observed_at,
            reason="person_not_visible",
        )
        return closed is not None

    def _persist_posture_episodes(
        self,
        camera: Dict[str, Any],
        snapshot: Dict[str, Any],
        temporal: Dict[str, Any],
    ) -> int:
        camera_id = int(camera["id"])
        snapshot_id = int(snapshot["id"]) if snapshot.get("id") else None
        writes = 0
        for closure in temporal.get("posture_episode_closures") or []:
            closed = self.storage.close_posture_episode(
                camera_id=camera_id,
                track_id=str(closure.get("track_id") or "") or None,
                posture=str(closure.get("posture") or "") or None,
                ended_at=str(closure.get("ended_at") or "") or None,
                reason=str(closure.get("reason") or "track_expired"),
            )
            if closed is not None:
                writes += 1
        for episode in temporal.get("posture_episode_updates") or []:
            self.storage.upsert_posture_episode(
                camera_id=camera_id,
                track_id=str(episode.get("track_id") or ""),
                posture=str(episode.get("posture") or "unknown"),
                started_at=str(episode.get("started_at") or snapshot.get("captured_at") or ""),
                confirmed_at=str(episode.get("confirmed_at") or snapshot.get("captured_at") or ""),
                last_seen_at=str(episode.get("last_seen_at") or snapshot.get("captured_at") or ""),
                sample_count=int(episode.get("sample_count") or 1),
                mean_confidence=float(episode.get("mean_confidence") or 0.0),
                max_confidence=float(episode.get("max_confidence") or 0.0),
                normal_lying_zone=bool(episode.get("normal_lying_zone")),
                scene_zone_id=episode.get("scene_zone_id"),
                scene_zone_label=episode.get("scene_zone_label"),
                snapshot_id=snapshot_id,
                payload={
                    "schema_version": "gohome-posture-episode-v2",
                    "evidence_source": "structured_activity_timeline",
                },
            )
            writes += 1
        return writes

    def _pose_runtime_config(
        self,
        camera_id: int,
        rules: Dict[str, Any],
        *,
        adaptive: bool = True,
    ) -> Dict[str, Any]:
        needs_pose = bool(rules.get("fall_detection_enabled") or rules.get("activity_detection_enabled"))
        if not needs_pose:
            return {
                "pose_detection_enabled": False,
                "pose_runtime_reason": "worker_pose_not_required",
                "eacp_mode": "idle",
            }
        if not adaptive:
            return {
                "pose_detection_enabled": True,
                "pose_runtime_reason": "manual_full_pose_analysis",
                "worker_pose_interval_frames": 1,
                "eacp_mode": "manual",
            }
        now = self._monotonic_clock()
        schedule = self.inference_scheduler.camera_state(camera_id, now=now)
        mode = str(schedule.get("mode") or self.inference_scheduler.mode(camera_id, now=now))
        hailo_probe = bool(schedule.get("accelerated"))
        enabled = bool(schedule.get("pose_required") or hailo_probe)
        last_risk_at = schedule.get("last_risk_signal_at_monotonic")
        rapid_descent_age = (
            max(0.0, now - float(last_risk_at))
            if last_risk_at is not None
            and str(schedule.get("last_risk_signal_source") or "") == "rapid_downward_pose_motion"
            else None
        )
        return {
            "pose_detection_enabled": enabled,
            "pose_runtime_reason": (
                f"eacp_{mode}_pose"
                if schedule.get("pose_required")
                else f"eacp_{mode}_hailo_pose_probe"
                if hailo_probe
                else f"eacp_{mode}_person_probe"
            ),
            "worker_pose_interval_frames": 1 if enabled else 0,
            "pose_allow_internal_detector_fallback": False,
            "person_detection_cache_seconds": 0.45 if mode == "risk" else 0.6 if mode == "active" else 0.0,
            "person_detection_cache_max_motion": 0.05,
            "eacp_mode": mode,
            "recent_rapid_descent": rapid_descent_age is not None and rapid_descent_age <= 3.0,
            "rapid_descent_age_seconds": (
                None if rapid_descent_age is None else round(rapid_descent_age, 4)
            ),
            "rapid_descent_source": (
                str(schedule.get("last_risk_signal_source") or "")
                if rapid_descent_age is not None
                else ""
            ),
        }

    def _snapshot_frame_age_seconds(self, snapshot: Any) -> float | None:
        if not isinstance(snapshot, dict):
            return None
        captured_at = str(snapshot.get("captured_at") or snapshot.get("created_at") or "").strip()
        if not captured_at:
            return None
        try:
            parsed = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds())
        except ValueError:
            return None

    def _inference_runtime_payload(
        self,
        pose_runtime_config: Dict[str, Any],
        *,
        coordinated_pose: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        payload = {
            "schema_version": "eacp-analysis-runtime-v1",
            "formal_evidence_eligible": True,
            "scheduler_version": self.inference_scheduler.version,
            "mode": str(pose_runtime_config.get("eacp_mode") or "idle"),
            "pose_requested": bool(pose_runtime_config.get("pose_detection_enabled")),
            "pose_reason": str(pose_runtime_config.get("pose_runtime_reason") or ""),
            "recent_rapid_descent": bool(pose_runtime_config.get("recent_rapid_descent")),
            "rapid_descent_age_seconds": pose_runtime_config.get("rapid_descent_age_seconds"),
            "rapid_descent_source": str(pose_runtime_config.get("rapid_descent_source") or ""),
        }
        if coordinated_pose is not None:
            payload["pose_coordinator"] = {
                "schema_version": self.pose_inference_coordinator.version,
                "frame_id": str(coordinated_pose.get("frame_id") or ""),
                "cache_hit": bool(coordinated_pose.get("cache_hit")),
                "display_delivered": bool(coordinated_pose.get("display_delivered")),
                "queue_wait_ms": coordinated_pose.get("queue_wait_ms"),
                "latency_ms": coordinated_pose.get("coordinator_latency_ms"),
            }
        return payload

    def _analysis_persistence_reason(
        self,
        camera_id: int,
        analysis: Dict[str, Any],
        temporal: Dict[str, Any],
        *,
        now: float,
    ) -> str:
        last_persisted_at = self.last_persisted_analysis_at.get(int(camera_id))
        elapsed = (
            float("inf")
            if last_persisted_at is None
            else max(0.0, float(now) - float(last_persisted_at))
        )
        visual_risk = any(bool(analysis.get(key)) for key in (
            "fall_candidate",
            "pose_fall_candidate",
        ))
        factor_graph = analysis.get("pose_factor_graph")
        graph_risk = isinstance(factor_graph, dict) and (
            factor_graph.get("fast_fall_candidate")
            or factor_graph.get("prolonged_floor_lying_candidate")
        )
        if (visual_risk or graph_risk) and elapsed >= self.risk_evidence_interval_seconds:
            return "formal_risk_evidence"
        runtime = analysis.get("inference_runtime") if isinstance(analysis.get("inference_runtime"), dict) else {}
        if runtime.get("mode") == "risk" and elapsed >= 1.0:
            return "risk_context"
        return ""

    def _should_persist_analysis(
        self,
        camera_id: int,
        analysis: Dict[str, Any],
        temporal: Dict[str, Any],
        rules: Dict[str, Any],
        *,
        now: float,
    ) -> bool:
        return bool(self._analysis_persistence_reason(camera_id, analysis, temporal, now=now))

    def _emit_candidates(
        self,
        camera: Dict[str, Any],
        evaluation: RuleEvaluation,
        detection_result_id: int | None,
        rule_evaluation_id: int | None,
    ) -> None:
        for candidate in evaluation.candidates:
            payload = {
                **(candidate.payload or {}),
                "evaluation": {
                    "camera_id": evaluation.camera_id,
                    "snapshot_id": evaluation.snapshot_id,
                    "evaluated_at": evaluation.evaluated_at,
                    "state": evaluation.state,
                },
                "data_chain": {
                    "detection_result_id": detection_result_id,
                    "rule_evaluation_id": rule_evaluation_id,
                },
            }
            if candidate.event_type in LIFE_OBSERVATION_TYPES:
                self.storage.upsert_observation_log(
                    camera_id=int(camera["id"]),
                    observation_type=candidate.event_type,
                    summary=candidate.summary,
                    evaluated_at=evaluation.evaluated_at,
                    snapshot_id=candidate.snapshot_id,
                    detection_result_id=detection_result_id,
                    rule_evaluation_id=rule_evaluation_id,
                    event_candidate_id=None,
                    payload=payload,
                )
                continue
            candidate_dict = candidate.to_dict()
            candidate_dict["payload"] = payload
            persisted_candidate = self.storage.create_event_candidate(
                camera_id=int(camera["id"]),
                detection_result_id=detection_result_id,
                rule_evaluation_id=rule_evaluation_id,
                candidate=candidate_dict,
                evaluated_at=evaluation.evaluated_at,
            )
            payload["data_chain"]["event_candidate_id"] = int(persisted_candidate["id"])
            self.event_agent.emit(
                event_type=candidate.event_type,
                summary=candidate.summary,
                level=candidate.level,
                camera=camera,
                snapshot_id=candidate.snapshot_id,
                detection_result_id=detection_result_id,
                rule_evaluation_id=rule_evaluation_id,
                candidate_id=int(persisted_candidate["id"]),
                payload=payload,
            )

    def _close_observation_logs(
        self,
        camera: Dict[str, Any],
        evaluation: RuleEvaluation,
    ) -> None:
        state = evaluation.state or {}
        camera_id = int(camera["id"])
        evaluated_at = evaluation.evaluated_at
        if state.get("motion_state") == "moving" or state.get("person_state") == "not_visible":
            self.storage.close_observation_log(
                camera_id=camera_id,
                observation_type="no_motion",
                ended_at=evaluated_at,
            )
        if state.get("person_state") == "visible":
            self.storage.close_observation_log(
                camera_id=camera_id,
                observation_type="no_person",
                ended_at=evaluated_at,
            )

    def _resolve_recovered_fall_incident(
        self,
        camera: Dict[str, Any],
        evaluation: RuleEvaluation,
    ) -> None:
        state = evaluation.state or {}
        recovery = state.get("fall_recovery") if isinstance(state.get("fall_recovery"), dict) else None
        if not recovery or not recovery.get("confirmed"):
            return
        camera_id = int(camera["id"])
        evaluated_at = evaluation.evaluated_at
        event = self.storage.latest_unresolved_event(
            camera_id=camera_id,
            event_types=["fall_candidate", "prolonged_floor_lying"],
            track_id=str(recovery.get("track_id") or ""),
        )
        if not event:
            return
        resolved = self.storage.resolve_event_from_edge(
            int(event["id"]),
            resolution="person_upright_again",
            resolved_at=evaluated_at,
            evidence=recovery,
        )
        if resolved:
            self.storage.enqueue_event_state_upload(
                resolved,
                state="resolved",
                resolution="person_upright_again",
                observed_at=evaluated_at,
                evidence=recovery,
            )

    def _resolve_recovered_camera_incidents(
        self,
        camera: Dict[str, Any],
        recovery: Dict[str, Any],
    ) -> None:
        camera_id = int(camera["id"])
        observed_at = str(recovery.get("recovered_at") or datetime.now(timezone.utc).isoformat())
        for _ in range(20):
            event = self.storage.latest_unresolved_event(
                camera_id=camera_id,
                event_types=["camera_offline"],
            )
            if not event:
                return
            resolved = self.storage.resolve_event_from_edge(
                int(event["id"]),
                resolution="camera_reconnected",
                resolved_at=observed_at,
                evidence=recovery,
            )
            if not resolved:
                return
            self.storage.enqueue_event_state_upload(
                resolved,
                state="resolved",
                resolution="camera_reconnected",
                observed_at=observed_at,
                evidence=recovery,
            )
