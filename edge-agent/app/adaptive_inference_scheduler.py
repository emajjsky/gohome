from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Dict, Iterable, Protocol


class ResourceMonitor(Protocol):
    def snapshot(self, *, now: float | None = None) -> Dict[str, Any]: ...


@dataclass
class _CameraSchedule:
    next_due_at: float
    in_flight: bool = False
    active_until: float = 0.0
    risk_until: float = 0.0
    person_until: float = 0.0
    last_started_at: float | None = None
    last_completed_at: float | None = None
    last_duration_seconds: float | None = None
    last_frame_age_seconds: float | None = None
    observed_count: int = 0
    deadline_miss_count: int = 0
    starts: deque[float] = field(default_factory=lambda: deque(maxlen=24))


class AdaptiveInferenceScheduler:
    """Schedule latest-frame inference without owning detection or alert policy."""

    version = "eacp-scheduler-v1"

    def __init__(
        self,
        *,
        idle_interval_seconds: float = 1.0,
        active_interval_seconds: float = 0.5,
        risk_interval_seconds: float = 0.25,
        active_hold_seconds: float = 8.0,
        risk_hold_seconds: float = 5.0,
        error_interval_seconds: float = 2.0,
        resource_monitor: ResourceMonitor | None = None,
        max_starvation_seconds: float = 3.0,
    ) -> None:
        self.idle_interval_seconds = max(0.25, float(idle_interval_seconds))
        self.active_interval_seconds = max(0.15, min(self.idle_interval_seconds, float(active_interval_seconds)))
        self.risk_interval_seconds = max(0.10, min(self.active_interval_seconds, float(risk_interval_seconds)))
        self.active_hold_seconds = max(self.active_interval_seconds, float(active_hold_seconds))
        self.risk_hold_seconds = max(self.risk_interval_seconds, float(risk_hold_seconds))
        self.error_interval_seconds = max(0.5, float(error_interval_seconds))
        self.resource_monitor = resource_monitor
        self.max_starvation_seconds = max(0.5, float(max_starvation_seconds))
        self._states: dict[int, _CameraSchedule] = {}
        self._lock = RLock()
        self._global_next_due_at = 0.0
        self._last_resource_status: Dict[str, Any] = {"thermal_state": "unknown", "available": False}
        self._resource_transition_count = 0
        self._last_resource_transition: Dict[str, Any] | None = None

    def reconcile(self, camera_ids: Iterable[int], *, now: float) -> None:
        normalized = {int(camera_id) for camera_id in camera_ids}
        with self._lock:
            for camera_id in list(self._states):
                if camera_id not in normalized:
                    self._states.pop(camera_id, None)
            for camera_id in sorted(normalized):
                self._states.setdefault(camera_id, _CameraSchedule(next_due_at=float(now)))

    def reset_camera(self, camera_id: int) -> None:
        with self._lock:
            self._states.pop(int(camera_id), None)

    def wake_all(self, *, now: float) -> None:
        with self._lock:
            for state in self._states.values():
                if not state.in_flight:
                    state.next_due_at = min(state.next_due_at, float(now))

    def signal_activity(self, camera_id: int, *, now: float, risk: bool = False) -> None:
        """Wake inference from a cheap gate without treating it as formal evidence."""
        with self._lock:
            current = float(now)
            state = self._states.setdefault(int(camera_id), _CameraSchedule(next_due_at=current))
            previous_mode = self._mode_at(state, current)
            state.active_until = max(state.active_until, current + self.active_hold_seconds)
            if risk:
                state.risk_until = max(state.risk_until, current + self.risk_hold_seconds)
            should_wake = previous_mode == "idle" or (risk and previous_mode != "risk")
            if should_wake and not state.in_flight:
                state.next_due_at = min(state.next_due_at, current)

    def next_due_camera(self, camera_ids: Iterable[int], *, now: float) -> int | None:
        allowed = {int(camera_id) for camera_id in camera_ids}
        with self._lock:
            if self._global_next_due_at > float(now):
                return None
            due = [
                (camera_id, state)
                for camera_id, state in self._states.items()
                if camera_id in allowed and not state.in_flight and state.next_due_at <= float(now)
            ]
            if not due:
                return None
            due.sort(key=lambda item: (
                not self._starved(item[1], now=float(now)),
                -self._mode_priority(self._mode_at(item[1], float(now))),
                item[1].next_due_at,
                item[1].last_started_at if item[1].last_started_at is not None else -1.0,
                item[0],
            ))
            return int(due[0][0])

    def mark_started(self, camera_id: int, *, now: float) -> None:
        with self._lock:
            state = self._states.setdefault(int(camera_id), _CameraSchedule(next_due_at=float(now)))
            state.in_flight = True
            state.last_started_at = float(now)
            state.starts.append(float(now))

    def observe(
        self,
        camera_id: int,
        analysis: Dict[str, Any],
        *,
        now: float,
        frame_age_seconds: float | None = None,
    ) -> None:
        with self._lock:
            state = self._states.setdefault(int(camera_id), _CameraSchedule(next_due_at=float(now)))
            current = float(now)
            if self._risk_signal(analysis):
                state.risk_until = max(state.risk_until, current + self.risk_hold_seconds)
                state.active_until = max(state.active_until, current + self.active_hold_seconds)
            elif self._active_signal(analysis):
                state.active_until = max(state.active_until, current + self.active_hold_seconds)
            if int(analysis.get("person_count") or 0) > 0:
                state.person_until = max(state.person_until, current + self.active_hold_seconds)

            mode = self._mode_at(state, current)
            interval = self._interval_for_mode(mode)
            started_at = state.last_started_at if state.last_started_at is not None else current
            expected_due_at = float(started_at) + interval
            if current > expected_due_at:
                state.deadline_miss_count += 1
                state.next_due_at = current
            else:
                state.next_due_at = expected_due_at
            state.in_flight = False
            state.last_completed_at = current
            state.last_duration_seconds = max(0.0, current - float(started_at))
            state.last_frame_age_seconds = (
                None if frame_age_seconds is None else max(0.0, float(frame_age_seconds))
            )
            state.observed_count += 1
            self._global_next_due_at = max(
                self._global_next_due_at,
                current + self._cooldown_seconds(mode=mode, now=current),
            )

    def mark_error(self, camera_id: int, *, now: float) -> None:
        with self._lock:
            state = self._states.setdefault(int(camera_id), _CameraSchedule(next_due_at=float(now)))
            state.in_flight = False
            state.last_completed_at = float(now)
            state.next_due_at = float(now) + self.error_interval_seconds
            self._global_next_due_at = max(
                self._global_next_due_at,
                float(now) + self._cooldown_seconds(mode="active", now=float(now)),
            )

    def wait_seconds(self, camera_ids: Iterable[int], *, now: float, maximum: float = 0.25) -> float:
        allowed = {int(camera_id) for camera_id in camera_ids}
        with self._lock:
            deadlines = [
                state.next_due_at
                for camera_id, state in self._states.items()
                if camera_id in allowed and not state.in_flight
            ]
            if not deadlines:
                next_due = float(maximum)
            else:
                next_due = min(deadlines) - float(now)
            next_due = max(next_due, self._global_next_due_at - float(now))
            return max(0.0, min(float(maximum), next_due))

    def mode(self, camera_id: int, *, now: float) -> str:
        with self._lock:
            state = self._states.get(int(camera_id))
            return self._mode_at(state, float(now)) if state is not None else "idle"

    def camera_state(self, camera_id: int, *, now: float) -> Dict[str, Any]:
        with self._lock:
            state = self._states.get(int(camera_id))
            if state is None:
                return {}
            mode = self._mode_at(state, float(now))
            return {
                "camera_id": int(camera_id),
                "mode": mode,
                "pose_required": float(now) < state.person_until,
                "person_confirmed_until": round(state.person_until, 6),
                "interval_seconds": self._interval_for_mode(mode),
                "next_due_at": round(state.next_due_at, 6),
                "next_due_in_seconds": round(max(0.0, state.next_due_at - float(now)), 4),
                "in_flight": state.in_flight,
                "last_started_at": state.last_started_at,
                "last_completed_at": state.last_completed_at,
                "last_duration_seconds": self._rounded(state.last_duration_seconds),
                "last_frame_age_seconds": self._rounded(state.last_frame_age_seconds),
                "observed_count": state.observed_count,
                "deadline_miss_count": state.deadline_miss_count,
                "effective_fps": self._effective_fps(state.starts),
            }

    def status(self, *, now: float) -> Dict[str, Any]:
        with self._lock:
            resource = self._resource_status(now=float(now))
            return {
                "schema_version": self.version,
                "intervals": {
                    "idle": self.idle_interval_seconds,
                    "active": self.active_interval_seconds,
                    "risk": self.risk_interval_seconds,
                },
                "holds": {
                    "active": self.active_hold_seconds,
                    "risk": self.risk_hold_seconds,
                },
                "global_next_due_at": round(self._global_next_due_at, 6),
                "global_next_due_in_seconds": round(max(0.0, self._global_next_due_at - float(now)), 4),
                "max_starvation_seconds": self.max_starvation_seconds,
                "resource": resource,
                "resource_transition_count": self._resource_transition_count,
                "last_resource_transition": self._last_resource_transition,
                "cameras": [
                    self.camera_state(camera_id, now=float(now))
                    for camera_id in sorted(self._states)
                ],
            }

    def _mode_at(self, state: _CameraSchedule, now: float) -> str:
        if now < state.risk_until:
            return "risk"
        if now < state.active_until:
            return "active"
        return "idle"

    def _starved(self, state: _CameraSchedule, *, now: float) -> bool:
        return now - float(state.next_due_at) >= self.max_starvation_seconds

    def _resource_status(self, *, now: float) -> Dict[str, Any]:
        if self.resource_monitor is None:
            self._last_resource_status = {"thermal_state": "unknown", "available": False}
            return dict(self._last_resource_status)
        try:
            value = self.resource_monitor.snapshot(now=now)
            next_status = dict(value or {})
            previous_state = str(self._last_resource_status.get("thermal_state") or "unknown")
            next_state = str(next_status.get("thermal_state") or "unknown")
            if next_state != previous_state:
                self._resource_transition_count += 1
                self._last_resource_transition = {
                    "from": previous_state,
                    "to": next_state,
                    "at_monotonic": round(float(now), 3),
                }
            self._last_resource_status = next_status
        except Exception as exc:
            self._last_resource_status = {
                "thermal_state": "unknown",
                "available": False,
                "error": str(exc),
            }
        return dict(self._last_resource_status)

    def _cooldown_seconds(self, *, mode: str, now: float) -> float:
        thermal_state = str(self._resource_status(now=now).get("thermal_state") or "unknown")
        if thermal_state in {"normal", "unknown"}:
            return 0.0
        if thermal_state == "warm":
            return 0.04 if mode == "risk" else 0.08
        if thermal_state == "hot":
            return 0.08 if mode == "risk" else 0.22
        return 0.18 if mode == "risk" else 0.55

    def _interval_for_mode(self, mode: str) -> float:
        if mode == "risk":
            return self.risk_interval_seconds
        if mode == "active":
            return self.active_interval_seconds
        return self.idle_interval_seconds

    def _active_signal(self, analysis: Dict[str, Any]) -> bool:
        return int(analysis.get("person_count") or 0) > 0 or bool(analysis.get("motion_detected"))

    def _risk_signal(self, analysis: Dict[str, Any]) -> bool:
        if bool(analysis.get("fire_event_candidate")):
            return True
        factor_graph = analysis.get("pose_factor_graph")
        if isinstance(factor_graph, dict):
            if factor_graph.get("fast_fall_candidate") or factor_graph.get("prolonged_floor_lying_candidate"):
                return True
            if float(factor_graph.get("fast_fall_score") or 0.0) >= 0.45:
                return True
            for track in factor_graph.get("tracks") or []:
                if not isinstance(track, dict):
                    continue
                factors = track.get("factors") if isinstance(track.get("factors"), dict) else {}
                if factors.get("vertical_drop") and factors.get("motion"):
                    return True
        if self._normal_lying_only(analysis):
            return False
        if bool(analysis.get("fall_candidate")) or bool(analysis.get("pose_fall_candidate")):
            return True
        if (
            max(float(analysis.get("fall_score") or 0.0), float(analysis.get("pose_fall_score") or 0.0)) >= 0.45
            and self._fall_like_target_present(analysis)
        ):
            return True
        return False

    def _fall_like_target_present(self, analysis: Dict[str, Any]) -> bool:
        for target in [*(analysis.get("people") or []), *(analysis.get("poses") or [])]:
            if not isinstance(target, dict):
                continue
            posture = str(target.get("posture") or "").lower()
            if (
                bool(target.get("fall_candidate"))
                or bool(target.get("pose_fall_candidate"))
                or posture in {"lying", "low_body", "fallen"}
            ):
                return True
        return False

    def _normal_lying_only(self, analysis: Dict[str, Any]) -> bool:
        fall_targets = []
        for target in [*(analysis.get("people") or []), *(analysis.get("poses") or [])]:
            if not isinstance(target, dict):
                continue
            posture = str(target.get("posture") or "").lower()
            is_fall_target = (
                bool(target.get("normal_lying_zone"))
                or bool(target.get("fall_candidate"))
                or bool(target.get("pose_fall_candidate"))
                or posture in {"lying", "low_body", "fallen"}
                or float(target.get("fall_score") or 0.0) >= 0.45
            )
            if is_fall_target:
                fall_targets.append(target)
        return bool(fall_targets) and all(bool(target.get("normal_lying_zone")) for target in fall_targets)

    def _mode_priority(self, mode: str) -> int:
        return {"idle": 0, "active": 1, "risk": 2}.get(mode, 0)

    def _effective_fps(self, starts: deque[float]) -> float | None:
        if len(starts) < 2:
            return None
        duration = float(starts[-1]) - float(starts[0])
        if duration <= 0.0:
            return None
        return round((len(starts) - 1) / duration, 3)

    def _rounded(self, value: float | None) -> float | None:
        return None if value is None else round(float(value), 4)
