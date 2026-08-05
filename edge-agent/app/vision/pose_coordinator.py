from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass, field
from threading import Condition, Event, Thread
import time
from typing import Any, Callable, Dict

from .pose_inference import PoseInferenceService


class PoseCoordinatorError(RuntimeError):
    pass


@dataclass
class _PoseRequest:
    camera_id: int
    frame: Any
    frame_id: str
    source_key: str
    captured_at: str
    captured_monotonic: float | None
    config: Dict[str, Any]
    submitted_at: float
    not_before_at: float
    sequence: int
    reset_revision: int
    roles: set[str] = field(default_factory=set)
    done: Event = field(default_factory=Event)
    result: Dict[str, Any] | None = None
    error: str = ""

    @property
    def identity(self) -> tuple[str, str]:
        return self.source_key, self.frame_id


class PoseInferenceCoordinator:
    """Run one bounded latest-frame queue against the shared Pose runtime."""

    version = "latest-frame-pose-coordinator-v1"

    def __init__(
        self,
        service: PoseInferenceService,
        *,
        on_display_result: Callable[[Dict[str, Any]], None] | None = None,
        result_history_size: int = 8,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        self.service = service
        self.on_display_result = on_display_result
        self.result_history_size = max(2, int(result_history_size))
        self._clock = monotonic_clock or time.monotonic
        self._condition = Condition()
        self._stop = False
        self._thread: Thread | None = None
        self._sequence = 0
        self._pending_display: dict[int, _PoseRequest] = {}
        self._pending_formal: dict[int, _PoseRequest] = {}
        self._in_flight: _PoseRequest | None = None
        self._results: dict[int, OrderedDict[tuple[str, str], Dict[str, Any]]] = {}
        self._reset_revisions: dict[int, int] = {}
        self._last_display_started_at: dict[int, float] = {}
        self._last_served_at: dict[int, float] = {}
        self._completion_samples: dict[int, deque[float]] = {}
        self._metrics: dict[int, Dict[str, Any]] = {}
        self._max_queue_depth = 0

    @property
    def is_running(self) -> bool:
        with self._condition:
            return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        with self._condition:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop = False
            self._thread = Thread(
                target=self._run,
                name="gohome-edge-pose-inference",
                daemon=True,
            )
            self._thread.start()

    def stop(self, *, timeout: float = 4.0) -> None:
        with self._condition:
            self._stop = True
            pending = self._unique_pending_locked()
            self._pending_display.clear()
            self._pending_formal.clear()
            for request in pending:
                request.error = "pose_coordinator_stopped"
                request.done.set()
            self._condition.notify_all()
            thread = self._thread
        if thread is not None:
            thread.join(timeout=max(0.0, float(timeout)))

    def submit_display(
        self,
        *,
        camera_id: int,
        frame: Any,
        frame_id: str,
        source_key: str,
        captured_at: str,
        captured_monotonic: float | None,
        config: Dict[str, Any],
        minimum_interval_seconds: float,
    ) -> bool:
        camera_id, frame_id, source_key = self._validated_identity(camera_id, frame_id, source_key)
        now = float(self._clock())
        with self._condition:
            if self._stop:
                return False
            metric = self._metric_locked(camera_id)
            metric["display_submitted"] += 1
            cached = self._cached_result_locked(camera_id, source_key, frame_id)
            if cached is not None:
                metric["display_cache_hits"] += 1
                if not cached.get("display_delivered"):
                    cached["display_delivered"] = True
                    delivery = self._display_delivery(frame, cached)
                    if self.on_display_result is not None:
                        try:
                            self.on_display_result(delivery)
                        except Exception as exc:
                            metric["display_delivery_failures"] += 1
                            metric["last_display_delivery_error"] = str(exc)
                return True

            in_flight = self._in_flight
            if in_flight is not None and in_flight.camera_id == camera_id and in_flight.identity == (source_key, frame_id):
                in_flight.roles.add("display")
                metric["display_coalesced"] += 1
                return True
            formal = self._pending_formal.get(camera_id)
            if formal is not None and formal.identity == (source_key, frame_id):
                formal.roles.add("display")
                self._pending_display[camera_id] = formal
                metric["display_coalesced"] += 1
                self._condition.notify()
                return True

            last_started = self._last_display_started_at.get(camera_id)
            not_before_at = (
                now
                if last_started is None
                else max(
                    now,
                    last_started + max(0.0, float(minimum_interval_seconds)),
                )
            )
            existing = self._pending_display.get(camera_id)
            if existing is not None:
                if not self._is_newer(captured_monotonic, frame_id, existing):
                    metric["display_stale_rejected"] += 1
                    return False
                if "formal" in existing.roles:
                    metric["display_deferred"] += 1
                    return False
                metric["display_replaced"] += 1
                not_before_at = existing.not_before_at
            if not_before_at > now:
                metric["display_deferred"] += 1
            request = self._new_request(
                camera_id=camera_id,
                frame=frame,
                frame_id=frame_id,
                source_key=source_key,
                captured_at=captured_at,
                captured_monotonic=captured_monotonic,
                config=config,
                roles={"display"},
                now=now,
                not_before_at=not_before_at,
            )
            self._pending_display[camera_id] = request
            self._update_queue_depth_locked()
            self._condition.notify()
            return True

    def infer_for_analysis(
        self,
        *,
        camera_id: int,
        frame: Any,
        frame_id: str,
        source_key: str,
        captured_at: str,
        captured_monotonic: float | None,
        config: Dict[str, Any],
        timeout: float = 0.75,
    ) -> Dict[str, Any]:
        camera_id, frame_id, source_key = self._validated_identity(camera_id, frame_id, source_key)
        now = float(self._clock())
        with self._condition:
            if self._stop:
                raise PoseCoordinatorError("pose_coordinator_stopped")
            metric = self._metric_locked(camera_id)
            metric["formal_requests"] += 1
            cached = self._cached_result_locked(camera_id, source_key, frame_id)
            if cached is not None:
                metric["formal_cache_hits"] += 1
                return {**cached, "cache_hit": True}
            request = self._in_flight
            if request is not None and request.camera_id == camera_id and request.identity == (source_key, frame_id):
                request.roles.add("formal")
                metric["formal_coalesced"] += 1
            else:
                display = self._pending_display.get(camera_id)
                if display is not None and display.identity == (source_key, frame_id):
                    request = display
                    request.roles.add("formal")
                    request.not_before_at = now
                    self._pending_formal[camera_id] = request
                    metric["formal_coalesced"] += 1
                else:
                    existing = self._pending_formal.get(camera_id)
                    if existing is not None and not existing.done.is_set():
                        raise PoseCoordinatorError(f"camera {camera_id} already has a formal Pose request")
                    request = self._new_request(
                        camera_id=camera_id,
                        frame=frame,
                        frame_id=frame_id,
                        source_key=source_key,
                        captured_at=captured_at,
                        captured_monotonic=captured_monotonic,
                        config=config,
                        roles={"formal"},
                        now=now,
                        not_before_at=now,
                    )
                    self._pending_formal[camera_id] = request
                    self._update_queue_depth_locked()
                self._condition.notify()
        if not request.done.wait(max(0.05, float(timeout))):
            with self._condition:
                self._metric_locked(camera_id)["formal_timeouts"] += 1
            raise PoseCoordinatorError(f"camera {camera_id} Pose inference timed out")
        if request.error:
            raise PoseCoordinatorError(request.error)
        if request.result is None:
            raise PoseCoordinatorError(f"camera {camera_id} Pose inference returned no result")
        return {**request.result, "cache_hit": False}

    def reset_camera(self, camera_id: int) -> None:
        camera_id = int(camera_id)
        with self._condition:
            self._reset_revisions[camera_id] = self._reset_revisions.get(camera_id, 0) + 1
            pending = {
                id(request): request
                for request in (
                    self._pending_display.pop(camera_id, None),
                    self._pending_formal.pop(camera_id, None),
                )
                if request is not None
            }
            for request in pending.values():
                request.error = "pose_camera_reset"
                request.done.set()
            self._results.pop(camera_id, None)
            self._last_display_started_at.pop(camera_id, None)
            self._last_served_at.pop(camera_id, None)
            self._completion_samples.pop(camera_id, None)
            self._metrics.pop(camera_id, None)
            self._condition.notify_all()

    def status(self) -> Dict[str, Any]:
        with self._condition:
            now = float(self._clock())
            camera_ids = sorted(
                set(self._metrics)
                | set(self._pending_display)
                | set(self._pending_formal)
                | ({self._in_flight.camera_id} if self._in_flight is not None else set())
            )
            return {
                "schema_version": self.version,
                "running": self._thread is not None and self._thread.is_alive(),
                "queue_depth": len(self._unique_pending_locked()),
                "max_queue_depth": self._max_queue_depth,
                "in_flight": self._request_status(self._in_flight),
                "cameras": [
                    {
                        "camera_id": camera_id,
                        **dict(self._metric_locked(camera_id)),
                        "pending_display_frame_id": str(
                            self._pending_display[camera_id].frame_id
                            if camera_id in self._pending_display
                            else ""
                        ),
                        "pending_formal_frame_id": str(
                            self._pending_formal[camera_id].frame_id
                            if camera_id in self._pending_formal
                            else ""
                        ),
                        "output_fps": self._rate(self._completion_samples.get(camera_id), now),
                    }
                    for camera_id in camera_ids
                ],
            }

    def _run(self) -> None:
        while True:
            with self._condition:
                while not self._stop:
                    pending = self._unique_pending_locked()
                    if not pending:
                        self._condition.wait(0.25)
                        continue
                    now = float(self._clock())
                    request = self._select_request_locked(now=now)
                    if request is not None:
                        break
                    next_due_at = min(item.not_before_at for item in pending)
                    self._condition.wait(max(0.001, min(0.25, next_due_at - now)))
                if self._stop:
                    return
                self._remove_pending_locked(request)
                self._in_flight = request
                started_at = float(self._clock())
                self._last_served_at[request.camera_id] = started_at
                if "display" in request.roles:
                    self._last_display_started_at[request.camera_id] = started_at
                metric = self._metric_locked(request.camera_id)
                metric["inferences_started"] += 1
                metric["last_started_frame_id"] = request.frame_id
            result: Dict[str, Any] | None = None
            error = ""
            try:
                payload = self.service.analyze_accelerated_frame(request.frame, request.config)
                completed_at = float(self._clock())
                result = {
                    "camera_id": request.camera_id,
                    "frame_id": request.frame_id,
                    "source_key": request.source_key,
                    "captured_at": request.captured_at,
                    "captured_monotonic": request.captured_monotonic,
                    "submitted_at_monotonic": request.submitted_at,
                    "completed_at_monotonic": completed_at,
                    "queue_wait_ms": round(max(0.0, started_at - request.submitted_at) * 1000.0, 2),
                    "coordinator_latency_ms": round(max(0.0, completed_at - started_at) * 1000.0, 2),
                    "accelerated": payload.get("accelerated"),
                    "display_analysis": payload.get("analysis"),
                    "roles": [],
                    "display_delivered": False,
                }
            except Exception as exc:
                error = str(exc) or exc.__class__.__name__
            delivery: Dict[str, Any] | None = None
            with self._condition:
                current_revision = self._reset_revisions.get(request.camera_id, 0)
                if request.reset_revision != current_revision:
                    error = "pose_camera_reset"
                    result = None
                metric = self._metric_locked(request.camera_id)
                if error:
                    metric["inference_failures"] += 1
                    metric["last_error"] = error
                elif result is not None:
                    result["roles"] = sorted(request.roles)
                    if "display" in request.roles and self.on_display_result is not None:
                        result["display_delivered"] = True
                        delivery = self._display_delivery(request.frame, result)
                    metric["inferences_completed"] += 1
                    metric["last_error"] = ""
                    metric["last_completed_frame_id"] = request.frame_id
                    metric["last_queue_wait_ms"] = result["queue_wait_ms"]
                    metric["last_latency_ms"] = result["coordinator_latency_ms"]
                    self._completion_samples.setdefault(request.camera_id, deque(maxlen=120)).append(
                        float(result["completed_at_monotonic"])
                    )
                    history = self._results.setdefault(request.camera_id, OrderedDict())
                    history[request.identity] = result
                    history.move_to_end(request.identity)
                    while len(history) > self.result_history_size:
                        history.popitem(last=False)
                request.result = result
                request.error = error
                self._in_flight = None
                self._condition.notify_all()
            if delivery is not None and self.on_display_result is not None:
                try:
                    self.on_display_result(delivery)
                except Exception as exc:
                    with self._condition:
                        metric = self._metric_locked(request.camera_id)
                        metric["display_delivery_failures"] += 1
                        metric["last_display_delivery_error"] = str(exc)
                        if request.result is not None:
                            request.result["display_delivery_error"] = str(exc)
            request.done.set()

    def _new_request(
        self,
        *,
        camera_id: int,
        frame: Any,
        frame_id: str,
        source_key: str,
        captured_at: str,
        captured_monotonic: float | None,
        config: Dict[str, Any],
        roles: set[str],
        now: float,
        not_before_at: float,
    ) -> _PoseRequest:
        self._sequence += 1
        return _PoseRequest(
            camera_id=camera_id,
            frame=frame.copy(),
            frame_id=frame_id,
            source_key=source_key,
            captured_at=str(captured_at or ""),
            captured_monotonic=(
                None if captured_monotonic is None else float(captured_monotonic)
            ),
            config=dict(config),
            submitted_at=now,
            not_before_at=float(not_before_at),
            sequence=self._sequence,
            reset_revision=self._reset_revisions.get(camera_id, 0),
            roles=set(roles),
        )

    def _select_request_locked(self, *, now: float) -> _PoseRequest | None:
        requests = [
            request
            for request in self._unique_pending_locked()
            if request.not_before_at <= float(now)
        ]
        if not requests:
            return None
        return min(
            requests,
            key=lambda request: (
                request.submitted_at,
                0 if "formal" in request.roles else 1,
                self._last_served_at.get(request.camera_id, 0.0),
                request.sequence,
            ),
        )

    def _unique_pending_locked(self) -> list[_PoseRequest]:
        unique: dict[int, _PoseRequest] = {}
        for request in [*self._pending_formal.values(), *self._pending_display.values()]:
            unique[id(request)] = request
        return list(unique.values())

    def _remove_pending_locked(self, request: _PoseRequest) -> None:
        if self._pending_formal.get(request.camera_id) is request:
            self._pending_formal.pop(request.camera_id, None)
        if self._pending_display.get(request.camera_id) is request:
            self._pending_display.pop(request.camera_id, None)

    def _cached_result_locked(
        self,
        camera_id: int,
        source_key: str,
        frame_id: str,
    ) -> Dict[str, Any] | None:
        return (self._results.get(camera_id) or {}).get((source_key, frame_id))

    def _metric_locked(self, camera_id: int) -> Dict[str, Any]:
        return self._metrics.setdefault(int(camera_id), {
            "display_submitted": 0,
            "display_replaced": 0,
            "display_deferred": 0,
            "display_stale_rejected": 0,
            "display_coalesced": 0,
            "display_cache_hits": 0,
            "display_delivery_failures": 0,
            "last_display_delivery_error": "",
            "formal_requests": 0,
            "formal_coalesced": 0,
            "formal_cache_hits": 0,
            "formal_timeouts": 0,
            "inferences_started": 0,
            "inferences_completed": 0,
            "inference_failures": 0,
            "last_started_frame_id": "",
            "last_completed_frame_id": "",
            "last_queue_wait_ms": None,
            "last_latency_ms": None,
            "last_error": "",
        })

    def _update_queue_depth_locked(self) -> None:
        self._max_queue_depth = max(self._max_queue_depth, len(self._unique_pending_locked()))

    @staticmethod
    def _display_delivery(frame: Any, result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "frame": frame.copy(),
            "camera_id": result["camera_id"],
            "frame_id": result["frame_id"],
            "source_key": result["source_key"],
            "captured_at": result["captured_at"],
            "captured_monotonic": result["captured_monotonic"],
            "analysis": result.get("display_analysis"),
            "roles": list(result.get("roles") or []),
        }

    @staticmethod
    def _validated_identity(camera_id: int, frame_id: str, source_key: str) -> tuple[int, str, str]:
        camera_id = int(camera_id)
        frame_id = str(frame_id or "")
        source_key = str(source_key or "")
        if camera_id <= 0 or not frame_id.startswith(f"{camera_id}-") or not source_key:
            raise ValueError("Pose request requires camera, source and frame identity")
        return camera_id, frame_id, source_key

    @staticmethod
    def _is_newer(captured_monotonic: float | None, frame_id: str, existing: _PoseRequest) -> bool:
        if captured_monotonic is not None and existing.captured_monotonic is not None:
            return float(captured_monotonic) > float(existing.captured_monotonic)
        return str(frame_id) > existing.frame_id

    @staticmethod
    def _request_status(request: _PoseRequest | None) -> Dict[str, Any] | None:
        if request is None:
            return None
        return {
            "camera_id": request.camera_id,
            "frame_id": request.frame_id,
            "roles": sorted(request.roles),
        }

    @staticmethod
    def _rate(samples: deque[float] | None, now: float) -> float:
        if not samples:
            return 0.0
        while samples and now - samples[0] > 10.0:
            samples.popleft()
        if len(samples) < 2:
            return 0.0
        elapsed = max(1e-6, samples[-1] - samples[0])
        return round((len(samples) - 1) / elapsed, 2)
