from __future__ import annotations

from threading import Event, Thread
from typing import Any, Callable, Dict
import time
from datetime import datetime, timezone
from pathlib import Path

from .camera_agent import CameraError
from .rule_engine import RuleEngine, RuleEvaluation
from .vision.temporal import TemporalObservationEngine


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
        self.last_history_cleanup_at = time.monotonic()
        self.last_history_cleanup_result: Dict[str, Any] = {}
        self.last_error = ""
        self.last_live_upload_at: Dict[int, float] = {}
        self._stop = Event()
        self._wake = Event()
        self._thread: Thread | None = None
        self.previous_frames: Dict[int, Any] = {}
        self.pose_frame_counts: Dict[int, int] = {}
        self.rule_engine = RuleEngine()
        self.latest_evaluations: Dict[int, Dict[str, Any]] = {}
        self.last_loop_started_at: str | None = None
        self.last_rules_loaded_at: str | None = None
        self.last_rules_snapshot: Dict[str, Any] = {}
        self._known_camera_ids: set[int] = set()
        self.runtime_reconciliation: Dict[str, Any] = {}
        self._runtime_reconciled = False

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._wake.clear()
        self._thread = Thread(target=self._run, name="gohome-edge-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            interval = 5
            try:
                if not self._runtime_reconciled:
                    self.runtime_reconciliation = self.storage.reconcile_camera_runtime_state()
                    self.runtime_reconciliation["completed_at"] = datetime.now(timezone.utc).isoformat()
                    self._runtime_reconciled = True
                rules = self.storage.get_rules()
                self.last_loop_started_at = datetime.now(timezone.utc).isoformat()
                self.last_rules_loaded_at = rules.get("updated_at")
                self.last_rules_snapshot = {**rules}
                cameras = self.storage.list_cameras(include_secret=True)
                current_camera_ids = {int(camera["id"]) for camera in cameras}
                for removed_camera_id in self._known_camera_ids - current_camera_ids:
                    self._reset_camera_runtime_memory(removed_camera_id)
                self._known_camera_ids = current_camera_ids
                for camera in cameras:
                    if self._stop.is_set():
                        break
                    if not camera.get("enabled"):
                        camera_id = int(camera["id"])
                        self.storage.close_camera_runtime_state(camera_id, reason="camera_disabled")
                        self._reset_camera_runtime_memory(camera_id)
                        continue
                    self.process_camera(camera, rules)
                self._prune_history_if_due()
                interval = max(1, int(rules["capture_interval_seconds"]))
                self.last_error = ""
            except Exception as exc:
                self.last_error = str(exc)
            self._wake.wait(interval)
            self._wake.clear()

    def runtime_status(self) -> Dict[str, Any]:
        return {
            "worker_running": self.is_running,
            "last_loop_started_at": self.last_loop_started_at,
            "last_rules_loaded_at": self.last_rules_loaded_at,
            "rules": self.last_rules_snapshot,
            "history_cleanup": self.last_history_cleanup_result,
            "temporal_engine": self.temporal_engine.version,
            "runtime_reconciliation": self.runtime_reconciliation,
            "last_error": self.last_error,
        }

    def request_rules_reload(self) -> None:
        self._wake.set()

    def _reset_camera_runtime_memory(self, camera_id: int) -> None:
        camera_id = int(camera_id)
        self.temporal_engine.reset_camera(camera_id)
        self.rule_engine.reset_camera(camera_id)
        self.previous_frames.pop(camera_id, None)
        self.pose_frame_counts.pop(camera_id, None)
        self.latest_evaluations.pop(camera_id, None)
        self.last_live_upload_at.pop(camera_id, None)

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

    def process_camera(self, camera: Dict[str, Any], rules: Dict[str, Any]) -> Dict[str, Any]:
        camera_id = int(camera["id"])
        try:
            capture = self.camera_agent.capture_frame(camera)
            frame = capture["frame"]
            analysis_config = {
                **rules,
                "force_demo_vision": str(camera.get("stream_url", "")).strip().lower().startswith("demo:"),
                "camera_id": camera_id,
                **self._pose_runtime_config(camera_id, rules),
            }
            analysis = self.detect_agent.analyze_frame_with_config(
                frame,
                previous_frame=self.previous_frames.get(camera_id),
                config=analysis_config,
            )
            temporal = self.temporal_engine.update(camera_id, analysis)

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
                person_count=analysis.get("person_count"),
                analysis=analysis,
            )
            self.temporal_engine.attach_snapshot(camera_id, snapshot)
            self._update_presence_session(camera, snapshot, temporal)
            self._persist_posture_episodes(camera, snapshot, temporal)
            self._enqueue_live_frame_upload(camera_id, snapshot)
            self.storage.update_camera_status(camera_id, "online")

            detection_result = self.storage.create_detection_result(
                camera_id=camera_id,
                snapshot_id=int(snapshot["id"]),
                captured_at=snapshot["captured_at"],
                width=capture["width"],
                height=capture["height"],
                analysis=analysis,
            )
            evaluation = self.rule_engine.evaluate_snapshot(camera, snapshot, analysis, rules)
            evaluation_dict = evaluation.to_dict()
            persisted_evaluation = self.storage.create_rule_evaluation(
                camera_id=camera_id,
                snapshot_id=int(snapshot["id"]),
                detection_result_id=int(detection_result["id"]),
                evaluation=evaluation_dict,
                rule_set_version=str(rules.get("updated_at") or ""),
            )
            self.latest_evaluations[camera_id] = persisted_evaluation
            self._close_recovered_observations(camera, evaluation)
            self._emit_candidates(
                camera,
                evaluation=evaluation,
                detection_result_id=int(detection_result["id"]),
                rule_evaluation_id=int(persisted_evaluation["id"]),
            )
            self.previous_frames[camera_id] = frame.copy()
            return {
                "ok": True,
                "snapshot": snapshot,
                "analysis": analysis,
                "detection_result": detection_result,
                "evaluation": persisted_evaluation,
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

    def _update_presence_session(
        self,
        camera: Dict[str, Any],
        snapshot: Dict[str, Any],
        temporal: Dict[str, Any],
    ) -> None:
        camera_id = int(camera["id"])
        observed_at = str(snapshot.get("captured_at") or snapshot.get("created_at") or "")
        if temporal.get("person_present"):
            self.storage.upsert_presence_session(
                camera_id=camera_id,
                observed_at=observed_at,
                person_count=int(temporal.get("person_count") or 1),
                snapshot_id=int(snapshot["id"]),
                payload={
                    "schema_version": "gohome-presence-session-v1",
                    "track_ids": temporal.get("current_track_ids") or [],
                    "active_tracks": temporal.get("active_tracks") or [],
                },
            )
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

    def _pose_runtime_config(self, camera_id: int, rules: Dict[str, Any]) -> Dict[str, Any]:
        needs_pose = bool(rules.get("fall_detection_enabled") or rules.get("activity_detection_enabled"))
        if not needs_pose:
            return {
                "pose_detection_enabled": False,
                "pose_runtime_reason": "worker_pose_not_required",
            }
        if rules.get("fall_detection_enabled"):
            return {
                "pose_detection_enabled": True,
                "pose_runtime_reason": "worker_pose_required_for_fall_sequence",
                "worker_pose_interval_frames": 1,
            }
        interval = max(2, int(rules.get("worker_pose_interval_frames") or 5))
        count = self.pose_frame_counts.get(camera_id, 0) + 1
        self.pose_frame_counts[camera_id] = count
        enabled = (count % interval) == 1
        return {
            "pose_detection_enabled": enabled,
            "pose_runtime_reason": "worker_pose_sampled" if enabled else "worker_pose_skipped_for_latency",
            "worker_pose_interval_frames": interval,
        }

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

    def _close_recovered_observations(self, camera: Dict[str, Any], evaluation: RuleEvaluation) -> None:
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
