from __future__ import annotations

from threading import Event, Thread
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


LIFE_OBSERVATION_TYPES = {"no_motion", "no_person"}


class EdgeWorker:
    def __init__(
        self,
        storage: Any,
        camera_agent: Any,
        detect_agent: Any,
        event_agent: Any,
        *,
        live_frame_upload_enabled: bool = False,
        live_frame_upload_interval_seconds: float = 12.0,
        remote_camera_id_resolver: Callable[[int], Any] | None = None,
        snapshot_dir: Path | None = None,
        history_retention_hours: int = 24,
        history_cleanup_interval_seconds: float = 3600,
        history_cleanup_batch_size: int = 5000,
        completed_upload_retention_days: int = 7,
        temporal_engine: TemporalObservationEngine | None = None,
        pose_factor_graph_engine: PoseFactorGraphEngine | None = None,
        inference_scheduler: AdaptiveInferenceScheduler | None = None,
        continual_pose_tracker: Any | None = None,
        motion_gate: Any | None = None,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        self.storage = storage
        self.camera_agent = camera_agent
        self.detect_agent = detect_agent
        self.event_agent = event_agent
        self.live_frame_upload_enabled = live_frame_upload_enabled
        self.live_frame_upload_interval_seconds = max(1.0, float(live_frame_upload_interval_seconds or 12.0))
        self.remote_camera_id_resolver = remote_camera_id_resolver or (lambda camera_id: camera_id)
        self.snapshot_dir = snapshot_dir
        self.history_retention_hours = max(1, int(history_retention_hours))
        self.history_cleanup_interval_seconds = max(60.0, float(history_cleanup_interval_seconds))
        self.history_cleanup_batch_size = max(100, int(history_cleanup_batch_size))
        self.completed_upload_retention_days = max(1, int(completed_upload_retention_days))
        self.temporal_engine = temporal_engine or TemporalObservationEngine()
        self.pose_factor_graph_engine = pose_factor_graph_engine or PoseFactorGraphEngine()
        self.inference_scheduler = inference_scheduler or AdaptiveInferenceScheduler()
        self.continual_pose_tracker = continual_pose_tracker or ContinualPoseTracker()
        self.motion_gate = motion_gate or MotionGate()
        self._monotonic_clock = monotonic_clock or time.monotonic
        self.last_history_cleanup_at = time.monotonic()
        self.last_history_cleanup_result: Dict[str, Any] = {}
        self.last_error = ""
        self.last_live_upload_at: Dict[int, float] = {}
        self.last_persisted_analysis_at: Dict[int, float] = {}
        self.last_persisted_person_state: Dict[int, bool] = {}
        self._stop = Event()
        self._wake = Event()
        self._thread: Thread | None = None
        self._tracking_thread: Thread | None = None
        self.previous_frames: Dict[int, Any] = {}
        self.rule_engine = RuleEngine()
        self.latest_evaluations: Dict[int, Dict[str, Any]] = {}
        self.last_loop_started_at: str | None = None
        self.last_rules_loaded_at: str | None = None
        self.last_rules_snapshot: Dict[str, Any] = {}
        self._known_camera_ids: set[int] = set()
        self._disabled_camera_ids: set[int] = set()
        self._runtime_cameras: Dict[int, Dict[str, Any]] = {}
        self._last_tracked_frame_ids: Dict[int, str] = {}
        self.runtime_reconciliation: Dict[str, Any] = {}
        self._runtime_reconciled = False
        self.last_continual_pose_error = ""
        self.continual_identity_bridge_count = 0
        self.last_continual_identity_bridge: Dict[str, Any] = {}

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._wake.clear()
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
        if self._thread:
            self._thread.join(timeout=5)
        if self._tracking_thread:
            self._tracking_thread.join(timeout=2)
        if self.camera_agent is not None and hasattr(self.camera_agent, "reconcile_managed_streams"):
            self.camera_agent.reconcile_managed_streams([])

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

        rules = self.storage.get_rules()
        self.last_rules_loaded_at = rules.get("updated_at")
        self.last_rules_snapshot = {**rules}
        cameras = self.storage.list_cameras(include_secret=True)
        cameras_by_id = {int(camera["id"]): camera for camera in cameras}
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
            self.inference_scheduler.mark_error(camera_id, now=self._monotonic_clock())
            raise

        completed_at = self._monotonic_clock()
        if result.get("ok"):
            self.inference_scheduler.observe(
                camera_id,
                result.get("analysis") if isinstance(result.get("analysis"), dict) else {},
                now=completed_at,
                frame_age_seconds=self._snapshot_frame_age_seconds(result.get("snapshot")),
            )
            self.last_error = ""
        else:
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
            "continual_pose": continual_status,
            "continual_pose_error": self.last_continual_pose_error,
            "continual_identity_bridge": {
                "count": self.continual_identity_bridge_count,
                "last": dict(self.last_continual_identity_bridge),
            },
            "motion_gate": self.motion_gate.status() if self.motion_gate is not None else {"schema_version": "disabled"},
            "camera_streams": stream_status,
            "runtime_reconciliation": self.runtime_reconciliation,
            "last_error": self.last_error,
        }

    def request_rules_reload(self) -> None:
        self.inference_scheduler.wake_all(now=self._monotonic_clock())
        self._wake.set()

    def _reset_camera_runtime_memory(self, camera_id: int) -> None:
        camera_id = int(camera_id)
        self.temporal_engine.reset_camera(camera_id)
        self.pose_factor_graph_engine.reset_camera(camera_id)
        self.inference_scheduler.reset_camera(camera_id)
        self.rule_engine.reset_camera(camera_id)
        if self.continual_pose_tracker is not None:
            self.continual_pose_tracker.reset_camera(camera_id)
        if self.motion_gate is not None:
            self.motion_gate.reset_camera(camera_id)
        self.previous_frames.pop(camera_id, None)
        self.latest_evaluations.pop(camera_id, None)
        self.last_live_upload_at.pop(camera_id, None)
        self.last_persisted_analysis_at.pop(camera_id, None)
        self.last_persisted_person_state.pop(camera_id, None)
        self._last_tracked_frame_ids.pop(camera_id, None)

    def _run_continual_tracking(self) -> None:
        while not self._stop.is_set():
            self._run_continual_tracking_iteration()
            self._stop.wait(self._continual_tracking_interval_seconds())

    def _continual_tracking_interval_seconds(self) -> float:
        interval = getattr(self.continual_pose_tracker, "minimum_interval_seconds", 0.1)
        try:
            return max(0.08, min(0.25, float(interval)))
        except (TypeError, ValueError):
            return 0.1

    def _run_continual_tracking_iteration(self) -> None:
        if self.camera_agent is None or self.continual_pose_tracker is None:
            return
        cameras = list(self._runtime_cameras.values())
        for camera in cameras:
            if not camera.get("enabled", True) or not camera.get("id"):
                continue
            camera_id = int(camera["id"])
            capture = self.camera_agent.latest_cached_frame(camera, max_age_seconds=0.5)
            if not capture:
                continue
            frame_id = str(capture.get("frame_id") or "")
            if self.motion_gate is not None:
                gate = self.motion_gate.update(camera_id, capture["frame"], frame_id=frame_id)
                if gate.get("detected"):
                    self.inference_scheduler.signal_activity(
                        camera_id,
                        now=self._monotonic_clock(),
                    )
                    self._wake.set()
            if not self.continual_pose_tracker.has_anchor(camera_id):
                continue
            if not frame_id or frame_id == self._last_tracked_frame_ids.get(camera_id):
                continue
            self._last_tracked_frame_ids[camera_id] = frame_id
            self.observe_stream_frame(camera, capture["frame"], capture)

    def _prune_history_if_due(self) -> None:
        if self.snapshot_dir is None:
            return
        now = time.monotonic()
        if now - self.last_history_cleanup_at < self.history_cleanup_interval_seconds:
            return
        self.last_history_cleanup_at = now
        try:
            self.last_history_cleanup_result = self.storage.prune_runtime_history(
                snapshot_dir=self.snapshot_dir,
                retention_hours=self.history_retention_hours,
                completed_upload_retention_days=self.completed_upload_retention_days,
                batch_size=self.history_cleanup_batch_size,
            )
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
        camera_id = int(camera["id"])
        try:
            capture = self.camera_agent.capture_frame(camera)
            frame = capture["frame"]
            pose_runtime_config = self._pose_runtime_config(camera_id, rules, adaptive=adaptive_pose)
            analysis_config = {
                **rules,
                "force_demo_vision": str(camera.get("stream_url", "")).strip().lower().startswith("demo:"),
                "camera_id": camera_id,
                **pose_runtime_config,
            }
            analysis = self.detect_agent.analyze_frame_with_config(
                frame,
                previous_frame=self.previous_frames.get(camera_id),
                config=analysis_config,
            )
            analysis["inference_runtime"] = self._inference_runtime_payload(pose_runtime_config)
            self._attach_continual_identity_hints(camera_id, analysis)
            temporal = self.temporal_engine.update(camera_id, analysis)
            self._publish_continual_pose_anchor(camera_id, frame=frame, capture=capture, analysis=analysis)
            self.pose_factor_graph_engine.update(camera_id, analysis, config=rules)
            self._attach_temporal_evidence(camera_id, analysis)
            persistence_now = self._monotonic_clock()
            should_persist = self._should_persist_analysis(
                camera_id,
                analysis,
                temporal,
                rules,
                now=persistence_now,
            )
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
                )
            self._attach_temporal_evidence(camera_id, analysis)
            self.storage.update_camera_status(camera_id, "online")

            evaluation = self.rule_engine.evaluate_snapshot(camera, snapshot, analysis, rules)
            if not should_persist and self._requires_durable_candidate(evaluation):
                snapshot, detection_result = self._persist_analysis_frame(
                    camera,
                    capture,
                    frame,
                    analysis,
                    temporal,
                    persisted_at=self._monotonic_clock(),
                )
                should_persist = True
                self._attach_temporal_evidence(camera_id, analysis)
                self._attach_snapshot_to_evaluation(evaluation, snapshot, analysis)

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
            self._close_recovered_observations(camera, evaluation, analysis)
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
                "snapshot": snapshot,
                "analysis": analysis,
                "detection_result": detection_result,
                "evaluation": persisted_evaluation or evaluation_dict,
            }

        except CameraError as exc:
            self.storage.update_camera_status(camera_id, "offline", str(exc))
            self.storage.close_camera_runtime_state(camera_id, reason="camera_offline")
            self._reset_camera_runtime_memory(camera_id)
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
        try:
            payload = self.continual_pose_tracker.update_frame(
                int(camera["id"]),
                frame,
                frame_id=str(metadata.get("frame_id") or ""),
                captured_at=str(metadata.get("captured_at") or ""),
            )
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
        if str(analysis.get("pose_model_status") or "") != "ready":
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
                poses=poses,
                context=analysis,
            )
            analysis["continual_pose_anchor"] = payload
            self.last_continual_pose_error = ""
        except Exception as exc:
            self.last_continual_pose_error = str(exc)

    def _attach_continual_identity_hints(self, camera_id: int, analysis: Dict[str, Any]) -> None:
        if self.continual_pose_tracker is None:
            return
        tracking = self.continual_pose_tracker.latest(int(camera_id))
        if str(tracking.get("state") or "") not in {"observed", "tracked"}:
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
            if targets is pose_targets:
                matching_person = max(
                    person_targets,
                    key=lambda item: self._bbox_iou(item["bbox"], targets[target_index]["bbox"]),
                    default=None,
                )
                if matching_person is not None and self._bbox_iou(matching_person["bbox"], targets[target_index]["bbox"]) >= 0.12:
                    matching_person["_continual_track_id_hint"] = str(tracked_poses[tracked_index]["track_id"])
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
        self._update_presence_session(camera, snapshot, temporal)
        self._persist_posture_episodes(camera, snapshot, temporal)
        self._enqueue_live_frame_upload(camera_id, snapshot)
        detection_result = self.storage.create_detection_result(
            camera_id=camera_id,
            snapshot_id=int(snapshot["id"]),
            captured_at=snapshot["captured_at"],
            width=capture["width"],
            height=capture["height"],
            analysis=analysis,
        )
        self.last_persisted_analysis_at[camera_id] = float(persisted_at)
        self.last_persisted_person_state[camera_id] = bool(
            temporal.get("credible_person_present")
            if "credible_person_present" in temporal
            else int(analysis.get("person_count") or 0) > 0
        )
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
        if not isinstance(evidence_track, dict) and not bool(analysis.get("fire_event_candidate")):
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

    def _update_presence_session(
        self,
        camera: Dict[str, Any],
        snapshot: Dict[str, Any],
        temporal: Dict[str, Any],
    ) -> None:
        camera_id = int(camera["id"])
        observed_at = str(snapshot.get("captured_at") or snapshot.get("created_at") or "")
        persistence_state = str(temporal.get("presence_persistence_state") or "")
        if not persistence_state:
            persistence_state = "visible" if temporal.get("person_present") else "absent"
        if persistence_state == "visible":
            self.storage.upsert_presence_session(
                camera_id=camera_id,
                observed_at=observed_at,
                person_count=int(temporal.get("credible_person_count") or temporal.get("person_count") or 1),
                snapshot_id=int(snapshot["id"]),
                payload={
                    "schema_version": "gohome-presence-session-v2",
                    "track_ids": temporal.get("credible_track_ids") or temporal.get("current_track_ids") or [],
                    "active_tracks": temporal.get("active_tracks") or [],
                    "quality": temporal.get("presence_quality") or {},
                },
            )
            return
        if persistence_state == "uncertain":
            return
        self.storage.close_presence_session(
            camera_id=camera_id,
            ended_at=observed_at,
            reason="person_not_visible",
        )

    def _persist_posture_episodes(
        self,
        camera: Dict[str, Any],
        snapshot: Dict[str, Any],
        temporal: Dict[str, Any],
    ) -> None:
        camera_id = int(camera["id"])
        for closure in temporal.get("posture_episode_closures") or []:
            self.storage.close_posture_episode(
                camera_id=camera_id,
                track_id=str(closure.get("track_id") or "") or None,
                posture=str(closure.get("posture") or "") or None,
                ended_at=str(closure.get("ended_at") or "") or None,
                reason=str(closure.get("reason") or "track_expired"),
            )
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
                snapshot_id=int(snapshot["id"]),
                payload={"schema_version": "gohome-posture-episode-v1"},
            )

    def _enqueue_live_frame_upload(self, camera_id: int, snapshot: Dict[str, Any]) -> None:
        if not self.live_frame_upload_enabled:
            return
        snapshot_id = snapshot.get("id")
        snapshot_path = str(snapshot.get("image_path") or "").strip()
        if not snapshot_id or not snapshot_path:
            return
        now = time.time()
        last_uploaded = float(self.last_live_upload_at.get(camera_id) or 0)
        if now - last_uploaded < self.live_frame_upload_interval_seconds:
            return
        self.last_live_upload_at[camera_id] = now
        try:
            remote_camera_id = self.remote_camera_id_resolver(camera_id) or camera_id
            bucket = int(now // self.live_frame_upload_interval_seconds)
            self.storage.enqueue_upload_job(
                job_type="media_upload",
                object_type="live_frame",
                idempotency_key=f"live-frame:{remote_camera_id}:{bucket}",
                priority=80,
                snapshot_id=int(snapshot_id),
                camera_id=int(camera_id),
                payload={
                    "target": "app_server",
                    "purpose": "live_preview",
                    "camera_id": remote_camera_id,
                    "local_camera_id": camera_id,
                    "snapshot_id": int(snapshot_id),
                    "snapshot_path": snapshot_path,
                    "captured_at": snapshot.get("captured_at") or snapshot.get("created_at") or "",
                    "content_type": "image/jpeg",
                },
            )
        except Exception:
            return

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
        enabled = bool(schedule.get("pose_required"))
        last_risk_at = schedule.get("last_risk_signal_at_monotonic")
        rapid_descent_age = (
            max(0.0, now - float(last_risk_at))
            if last_risk_at is not None
            and str(schedule.get("last_risk_signal_source") or "") == "rapid_downward_pose_motion"
            else None
        )
        return {
            "pose_detection_enabled": enabled,
            "pose_runtime_reason": f"eacp_{mode}_pose" if enabled else f"eacp_{mode}_person_probe",
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

    def _inference_runtime_payload(self, pose_runtime_config: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "schema_version": "eacp-analysis-runtime-v1",
            "scheduler_version": self.inference_scheduler.version,
            "mode": str(pose_runtime_config.get("eacp_mode") or "idle"),
            "pose_requested": bool(pose_runtime_config.get("pose_detection_enabled")),
            "pose_reason": str(pose_runtime_config.get("pose_runtime_reason") or ""),
            "recent_rapid_descent": bool(pose_runtime_config.get("recent_rapid_descent")),
            "rapid_descent_age_seconds": pose_runtime_config.get("rapid_descent_age_seconds"),
            "rapid_descent_source": str(pose_runtime_config.get("rapid_descent_source") or ""),
        }

    def _should_persist_analysis(
        self,
        camera_id: int,
        analysis: Dict[str, Any],
        temporal: Dict[str, Any],
        rules: Dict[str, Any],
        *,
        now: float,
    ) -> bool:
        last_persisted_at = self.last_persisted_analysis_at.get(int(camera_id))
        if last_persisted_at is None:
            return True
        elapsed = max(0.0, float(now) - float(last_persisted_at))
        if analysis.get("black_screen") or any(bool(analysis.get(key)) for key in (
            "fall_candidate",
            "pose_fall_candidate",
            "fire_event_candidate",
        )):
            return True
        factor_graph = analysis.get("pose_factor_graph")
        if isinstance(factor_graph, dict) and (
            factor_graph.get("fast_fall_candidate")
            or factor_graph.get("prolonged_floor_lying_candidate")
        ):
            return True
        interval = max(1.0, float(rules.get("capture_interval_seconds") or 5.0))
        if elapsed >= interval:
            return True
        person_present = bool(
            temporal.get("credible_person_present")
            if "credible_person_present" in temporal
            else int(analysis.get("person_count") or 0) > 0
        )
        if (
            elapsed >= 1.0
            and
            int(camera_id) in self.last_persisted_person_state
            and self.last_persisted_person_state[int(camera_id)] != person_present
        ):
            return True
        runtime = analysis.get("inference_runtime") if isinstance(analysis.get("inference_runtime"), dict) else {}
        if runtime.get("mode") == "risk" and elapsed >= 1.0:
            return True
        return False

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

    def _close_recovered_observations(
        self,
        camera: Dict[str, Any],
        evaluation: RuleEvaluation,
        analysis: Dict[str, Any] | None = None,
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
        recovery = self._credible_fall_recovery(state, analysis or {})
        if not recovery:
            return
        event = self.storage.latest_unresolved_event(
            camera_id=camera_id,
            event_types=["fall_candidate", "prolonged_floor_lying"],
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

    def _credible_fall_recovery(self, state: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any] | None:
        if str(state.get("fall_stage") or "") != "recovered" or state.get("person_state") != "visible":
            return None
        candidates = []
        for item in [*(analysis.get("poses") or []), *(analysis.get("people") or [])]:
            if not isinstance(item, dict):
                continue
            posture = str(item.get("posture") or "").strip().lower()
            confidence = float(item.get("posture_confidence") or item.get("confidence") or 0.0)
            if posture not in {"standing", "sitting", "squatting"} or confidence < 0.45:
                continue
            candidates.append({
                "posture": posture,
                "confidence": round(confidence, 4),
                "track_id": str(item.get("track_id") or ""),
                "bbox": item.get("bbox") if isinstance(item.get("bbox"), list) else [],
            })
        if not candidates:
            return None
        best = max(candidates, key=lambda item: item["confidence"])
        return {
            "schema_version": "gohome-fall-recovery-v1",
            "reason": "credible_upright_posture",
            **best,
        }
