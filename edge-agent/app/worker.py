from __future__ import annotations

from threading import Event, Thread
from typing import Any, Dict
import time
from datetime import datetime, timezone

from .camera_agent import CameraError
from .rule_engine import RuleEngine, RuleEvaluation


LIFE_OBSERVATION_TYPES = {"no_motion", "no_person"}


class EdgeWorker:
    def __init__(
        self,
        storage: Any,
        camera_agent: Any,
        detect_agent: Any,
        event_agent: Any,
    ) -> None:
        self.storage = storage
        self.camera_agent = camera_agent
        self.detect_agent = detect_agent
        self.event_agent = event_agent
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
            rules = self.storage.get_rules()
            self.last_loop_started_at = datetime.now(timezone.utc).isoformat()
            self.last_rules_loaded_at = rules.get("updated_at")
            self.last_rules_snapshot = {**rules}
            cameras = self.storage.list_cameras(include_secret=True)
            for camera in cameras:
                if self._stop.is_set():
                    break
                if not camera.get("enabled"):
                    continue
                self.process_camera(camera, rules)
            interval = max(1, int(rules["capture_interval_seconds"]))
            self._wake.wait(interval)
            self._wake.clear()

    def runtime_status(self) -> Dict[str, Any]:
        return {
            "worker_running": self.is_running,
            "last_loop_started_at": self.last_loop_started_at,
            "last_rules_loaded_at": self.last_rules_loaded_at,
            "rules": self.last_rules_snapshot,
        }

    def request_rules_reload(self) -> None:
        self._wake.set()

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
            return {"ok": False, "error": str(exc)}

    def _pose_runtime_config(self, camera_id: int, rules: Dict[str, Any]) -> Dict[str, Any]:
        needs_pose = bool(rules.get("fall_detection_enabled") or rules.get("activity_detection_enabled"))
        if not needs_pose:
            return {
                "pose_detection_enabled": False,
                "pose_runtime_reason": "worker_pose_not_required",
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
            if candidate.event_type in LIFE_OBSERVATION_TYPES:
                self.storage.upsert_observation_log(
                    camera_id=int(camera["id"]),
                    observation_type=candidate.event_type,
                    summary=candidate.summary,
                    evaluated_at=evaluation.evaluated_at,
                    snapshot_id=candidate.snapshot_id,
                    detection_result_id=detection_result_id,
                    rule_evaluation_id=rule_evaluation_id,
                    event_candidate_id=int(persisted_candidate["id"]),
                    payload=payload,
                )
                self.storage.update_event_candidate_status(int(persisted_candidate["id"]), "aggregated")
                continue
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
