from __future__ import annotations

from threading import RLock
import math
import time
from typing import Any, Callable, Dict


class PoseCandidateValidationGate:
    """Require a short, coherent Pose sequence before waking formal analysis."""

    version = "pose-candidate-validation-v1"

    def __init__(
        self,
        *,
        minimum_consistent_hits: int = 2,
        maximum_gap_seconds: float = 0.8,
        minimum_iou: float = 0.08,
        maximum_center_shift: float = 0.22,
        rejection_cooldown_seconds: float = 10.0,
        maximum_rejection_cooldown_seconds: float = 60.0,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        self.minimum_consistent_hits = max(2, int(minimum_consistent_hits))
        self.maximum_gap_seconds = max(0.2, float(maximum_gap_seconds))
        self.minimum_iou = max(0.0, min(1.0, float(minimum_iou)))
        self.maximum_center_shift = max(0.02, float(maximum_center_shift))
        self.rejection_cooldown_seconds = max(0.5, float(rejection_cooldown_seconds))
        self.maximum_rejection_cooldown_seconds = max(
            self.rejection_cooldown_seconds,
            float(maximum_rejection_cooldown_seconds),
        )
        self._clock = monotonic_clock or time.monotonic
        self._states: dict[int, Dict[str, Any]] = {}
        self._metrics: dict[int, Dict[str, Any]] = {}
        self._lock = RLock()

    def observe(
        self,
        camera_id: int,
        *,
        source_key: str,
        poses: list[Dict[str, Any]],
        frame_width: int,
        frame_height: int,
        now: float | None = None,
    ) -> Dict[str, Any]:
        camera_id = int(camera_id)
        current = float(self._clock() if now is None else now)
        bboxes = [
            bbox
            for bbox in (self._bbox(pose.get("bbox")) for pose in poses if isinstance(pose, dict))
            if bbox is not None
        ]
        with self._lock:
            metric = self._metric_locked(camera_id)
            metric["samples"] += 1
            state = self._states.get(camera_id)
            if state is None or str(state.get("source_key") or "") != str(source_key or ""):
                state = self._new_state(source_key)
                self._states[camera_id] = state
                metric["source_resets"] += 1

            if not bboxes:
                metric["empty_samples"] += 1
                self._clear_geometry(state)
                return self._decision(
                    camera_id,
                    state,
                    validation_requested=False,
                    reason="awaiting_formal" if state.get("awaiting_formal") else "empty",
                )

            metric["pose_samples"] += 1
            if current < float(state.get("cooldown_until") or 0.0):
                metric["cooldown_suppressions"] += 1
                self._clear_candidate(state)
                return self._decision(
                    camera_id,
                    state,
                    validation_requested=False,
                    reason="formal_rejection_cooldown",
                )

            if state.get("awaiting_formal"):
                metric["awaiting_formal_samples"] += 1
                return self._decision(
                    camera_id,
                    state,
                    validation_requested=False,
                    reason="awaiting_formal",
                )

            previous_bboxes = list(state.get("bboxes") or [])
            previous_at = state.get("last_seen_at")
            continuous = bool(
                previous_bboxes
                and previous_at is not None
                and current - float(previous_at) <= self.maximum_gap_seconds
                and self._geometry_continues(
                    previous_bboxes,
                    bboxes,
                    frame_width=max(1, int(frame_width)),
                    frame_height=max(1, int(frame_height)),
                )
            )
            state["consistent_hits"] = int(state.get("consistent_hits") or 0) + 1 if continuous else 1
            state["bboxes"] = bboxes
            state["last_seen_at"] = current
            if not continuous:
                state["awaiting_formal"] = False
                state["validation_requested_at"] = None
                metric["candidate_starts"] += 1
            else:
                metric["consistent_samples"] += 1

            validation_requested = bool(
                int(state["consistent_hits"]) >= self.minimum_consistent_hits
                and not state.get("awaiting_formal")
            )
            if validation_requested:
                state["awaiting_formal"] = True
                state["validation_requested_at"] = current
                metric["validation_requests"] += 1
                metric["last_validation_requested_at_monotonic"] = current
            return self._decision(
                camera_id,
                state,
                validation_requested=validation_requested,
                reason="consistent_pose_candidate" if validation_requested else "collecting_consistent_pose",
            )

    def observe_formal(
        self,
        camera_id: int,
        *,
        person_present: bool,
        analysis_started_at: float,
        now: float | None = None,
    ) -> None:
        camera_id = int(camera_id)
        current = float(self._clock() if now is None else now)
        with self._lock:
            state = self._states.get(camera_id)
            if state is None:
                return
            requested_at = state.get("validation_requested_at")
            if not state.get("awaiting_formal") or requested_at is None:
                return
            if float(analysis_started_at) + 1e-6 < float(requested_at):
                return
            metric = self._metric_locked(camera_id)
            if person_present:
                metric["formal_confirmations"] += 1
                metric["last_formal_confirmation_at_monotonic"] = current
                state["cooldown_until"] = 0.0
                state["rejection_streak"] = 0
            else:
                metric["formal_rejections"] += 1
                metric["last_formal_rejection_at_monotonic"] = current
                state["rejection_streak"] = int(state.get("rejection_streak") or 0) + 1
                cooldown_seconds = min(
                    self.maximum_rejection_cooldown_seconds,
                    self.rejection_cooldown_seconds * (2 ** min(16, int(state["rejection_streak"]) - 1)),
                )
                state["cooldown_until"] = current + cooldown_seconds
            self._clear_candidate(state)

    def observe_formal_error(
        self,
        camera_id: int,
        *,
        analysis_started_at: float,
        now: float | None = None,
    ) -> None:
        camera_id = int(camera_id)
        current = float(self._clock() if now is None else now)
        with self._lock:
            state = self._states.get(camera_id)
            if state is None:
                return
            requested_at = state.get("validation_requested_at")
            if not state.get("awaiting_formal") or requested_at is None:
                return
            if float(analysis_started_at) + 1e-6 < float(requested_at):
                return
            metric = self._metric_locked(camera_id)
            metric["formal_errors"] += 1
            metric["last_formal_error_at_monotonic"] = current
            self._clear_candidate(state)

    def reset_camera(self, camera_id: int) -> None:
        with self._lock:
            self._states.pop(int(camera_id), None)
            self._metrics.pop(int(camera_id), None)

    def status(self) -> Dict[str, Any]:
        current = float(self._clock())
        with self._lock:
            camera_ids = sorted(set(self._states) | set(self._metrics))
            return {
                "schema_version": self.version,
                "minimum_consistent_hits": self.minimum_consistent_hits,
                "maximum_gap_seconds": self.maximum_gap_seconds,
                "rejection_cooldown_seconds": self.rejection_cooldown_seconds,
                "maximum_rejection_cooldown_seconds": self.maximum_rejection_cooldown_seconds,
                "cameras": [
                    self._camera_status_locked(camera_id, current=current)
                    for camera_id in camera_ids
                ],
            }

    def _camera_status_locked(self, camera_id: int, *, current: float) -> Dict[str, Any]:
        metric = dict(self._metric_locked(camera_id))
        state = self._states.get(camera_id) or {}
        for field in (
            "last_validation_requested_at_monotonic",
            "last_formal_confirmation_at_monotonic",
            "last_formal_rejection_at_monotonic",
            "last_formal_error_at_monotonic",
        ):
            value = metric.get(field)
            metric[field.removesuffix("_at_monotonic") + "_age_seconds"] = (
                None if value is None else round(max(0.0, current - float(value)), 3)
            )
        return {
            "camera_id": int(camera_id),
            **metric,
            "consistent_hits": int(state.get("consistent_hits") or 0),
            "awaiting_formal": bool(state.get("awaiting_formal")),
            "rejection_streak": int(state.get("rejection_streak") or 0),
            "cooldown_remaining_seconds": round(max(
                0.0,
                float(state.get("cooldown_until") or 0.0) - current,
            ), 3),
        }

    def _geometry_continues(
        self,
        previous: list[list[float]],
        current: list[list[float]],
        *,
        frame_width: int,
        frame_height: int,
    ) -> bool:
        diagonal = max(1.0, math.hypot(float(frame_width), float(frame_height)))
        for first in previous:
            for second in current:
                if self._iou(first, second) >= self.minimum_iou:
                    return True
                first_center = ((first[0] + first[2]) / 2.0, (first[1] + first[3]) / 2.0)
                second_center = ((second[0] + second[2]) / 2.0, (second[1] + second[3]) / 2.0)
                shift = math.hypot(second_center[0] - first_center[0], second_center[1] - first_center[1]) / diagonal
                if shift <= self.maximum_center_shift:
                    return True
        return False

    @staticmethod
    def _bbox(value: Any) -> list[float] | None:
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            return None
        try:
            bbox = [float(item) for item in value]
        except (TypeError, ValueError):
            return None
        if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
            return None
        return bbox

    @staticmethod
    def _iou(first: list[float], second: list[float]) -> float:
        intersection = max(0.0, min(first[2], second[2]) - max(first[0], second[0])) * max(
            0.0,
            min(first[3], second[3]) - max(first[1], second[1]),
        )
        if intersection <= 0.0:
            return 0.0
        first_area = max(1.0, (first[2] - first[0]) * (first[3] - first[1]))
        second_area = max(1.0, (second[2] - second[0]) * (second[3] - second[1]))
        return intersection / max(1.0, first_area + second_area - intersection)

    def _metric_locked(self, camera_id: int) -> Dict[str, Any]:
        return self._metrics.setdefault(int(camera_id), {
            "samples": 0,
            "empty_samples": 0,
            "pose_samples": 0,
            "source_resets": 0,
            "candidate_starts": 0,
            "consistent_samples": 0,
            "validation_requests": 0,
            "formal_confirmations": 0,
            "formal_rejections": 0,
            "formal_errors": 0,
            "last_validation_requested_at_monotonic": None,
            "last_formal_confirmation_at_monotonic": None,
            "last_formal_rejection_at_monotonic": None,
            "last_formal_error_at_monotonic": None,
            "cooldown_suppressions": 0,
            "awaiting_formal_samples": 0,
        })

    @staticmethod
    def _new_state(source_key: str) -> Dict[str, Any]:
        return {
            "source_key": str(source_key or ""),
            "bboxes": [],
            "consistent_hits": 0,
            "last_seen_at": None,
            "awaiting_formal": False,
            "validation_requested_at": None,
            "cooldown_until": 0.0,
            "rejection_streak": 0,
        }

    @staticmethod
    def _clear_candidate(state: Dict[str, Any]) -> None:
        PoseCandidateValidationGate._clear_geometry(state)
        state["awaiting_formal"] = False
        state["validation_requested_at"] = None

    @staticmethod
    def _clear_geometry(state: Dict[str, Any]) -> None:
        state["bboxes"] = []
        state["consistent_hits"] = 0
        state["last_seen_at"] = None

    @staticmethod
    def _decision(
        camera_id: int,
        state: Dict[str, Any],
        *,
        validation_requested: bool,
        reason: str,
    ) -> Dict[str, Any]:
        return {
            "camera_id": int(camera_id),
            "validation_requested": bool(validation_requested),
            "reason": str(reason),
            "consistent_hits": int(state.get("consistent_hits") or 0),
            "awaiting_formal": bool(state.get("awaiting_formal")),
        }
