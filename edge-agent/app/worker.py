from __future__ import annotations

from threading import Event, Thread
from typing import Any, Dict
import time

from .camera_agent import CameraError
from .rule_engine import RuleEngine, RuleEvaluation


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
        self._thread: Thread | None = None
        self.previous_frames: Dict[int, Any] = {}
        self.rule_engine = RuleEngine()
        self.latest_evaluations: Dict[int, Dict[str, Any]] = {}

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._thread = Thread(target=self._run, name="gohome-edge-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            rules = self.storage.get_rules()
            cameras = self.storage.list_cameras(include_secret=True)
            for camera in cameras:
                if self._stop.is_set():
                    break
                if not camera.get("enabled"):
                    continue
                self.process_camera(camera, rules)
            interval = max(1, int(rules["capture_interval_seconds"]))
            self._stop.wait(interval)

    def process_camera(self, camera: Dict[str, Any], rules: Dict[str, Any]) -> Dict[str, Any]:
        camera_id = int(camera["id"])
        try:
            capture = self.camera_agent.capture_frame(camera)
            frame = capture["frame"]
            analysis = self.detect_agent.analyze_frame_with_config(
                frame,
                previous_frame=self.previous_frames.get(camera_id),
                config=rules,
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

            evaluation = self.rule_engine.evaluate_snapshot(camera, snapshot, analysis, rules)
            self.latest_evaluations[camera_id] = evaluation.to_dict()
            self._emit_candidates(camera, evaluation)
            self.previous_frames[camera_id] = frame.copy()
            return {"ok": True, "snapshot": snapshot, "analysis": analysis, "evaluation": evaluation.to_dict()}

        except CameraError as exc:
            self.storage.update_camera_status(camera_id, "offline", str(exc))
            evaluation = self.rule_engine.evaluate_camera_error(camera, rules, str(exc))
            self.latest_evaluations[camera_id] = evaluation.to_dict()
            self._emit_candidates(camera, evaluation)
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            self.storage.update_camera_status(camera_id, "error", str(exc))
            return {"ok": False, "error": str(exc)}

    def _emit_candidates(self, camera: Dict[str, Any], evaluation: RuleEvaluation) -> None:
        for candidate in evaluation.candidates:
            self.event_agent.emit(
                event_type=candidate.event_type,
                summary=candidate.summary,
                level=candidate.level,
                camera=camera,
                snapshot_id=candidate.snapshot_id,
                payload={
                    **(candidate.payload or {}),
                    "evaluation": {
                        "camera_id": evaluation.camera_id,
                        "snapshot_id": evaluation.snapshot_id,
                        "evaluated_at": evaluation.evaluated_at,
                        "state": evaluation.state,
                    },
                },
            )
