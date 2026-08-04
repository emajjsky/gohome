from __future__ import annotations

from collections import OrderedDict, deque
from threading import RLock
from typing import Any, Callable, Dict, Generator
import time

import numpy as np

from ..camera_agent import _load_cv2
from ..video_privacy import normalize_privacy_mode, stricter_privacy_mode
from .privacy_background import PrivacyBackgroundReconstructor, PrivacyCalibrationRequired
from .synchronized_pose_stream import DEFAULT_SKELETON_EDGES


SKELETON_LINE_BGR = (219, 209, 33)
SKELETON_JOINT_BGR = (255, 255, 255)


class PrivacyFrameRenderer:
    """Render privacy-safe relay frames without changing safety inference inputs."""

    version = "privacy-frame-renderer-v22"
    maximum_pose_wait_seconds = 0.055

    def __init__(
        self,
        tracker: Any,
        background_reconstructor: PrivacyBackgroundReconstructor | None = None,
        segmentation_backend: Any | None = None,
        *,
        revalidation_interval_seconds: float = 1.0,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        self.tracker = tracker
        self.background_reconstructor = background_reconstructor or PrivacyBackgroundReconstructor()
        self.segmentation_backend = segmentation_backend
        self.revalidation_interval_seconds = max(
            0.25,
            min(float(revalidation_interval_seconds), 5.0),
        )
        self._clock = monotonic_clock or time.monotonic
        self._render_cache: OrderedDict[tuple[Any, ...], Any] = OrderedDict()
        self._sync_rejections: Dict[int, Dict[str, Any]] = {}
        self._segmentation_assists: Dict[int, Dict[str, Any]] = {}
        self._output_samples: Dict[int, deque[float]] = {}
        self._output_state: Dict[int, Dict[str, Any]] = {}
        self._stage_latency_samples: Dict[int, Dict[str, deque[float]]] = {}
        self._revalidation_schedule: Dict[tuple[int, str, int, int], Dict[str, Any]] = {}
        self._cache_lock = RLock()

    def render_jpeg(
        self,
        camera_id: int,
        jpeg: bytes,
        mode: str,
        *,
        quality: int = 55,
        source_key: str = "",
    ) -> bytes:
        resolved_mode = normalize_privacy_mode(mode)
        if resolved_mode == "original":
            self._record_output(int(camera_id), resolved_mode, "")
            return jpeg

        cv2 = _load_cv2()
        encoded = np.frombuffer(jpeg, dtype=np.uint8)
        frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if frame is None or frame.size == 0:
            raise RuntimeError("privacy frame decode failed")
        return self.render_frame(
            int(camera_id),
            frame,
            resolved_mode,
            quality=quality,
            source_key=source_key,
        )

    def render_frame(
        self,
        camera_id: int,
        frame: Any,
        mode: str,
        *,
        quality: int = 55,
        source_key: str = "",
        frame_id: str = "",
        captured_at: str = "",
        captured_monotonic: float | None = None,
    ) -> bytes:
        started_at = time.perf_counter()
        try:
            output = self.render_image(
                camera_id,
                frame,
                mode,
                source_key=source_key,
                frame_id=frame_id,
                captured_at=captured_at,
                captured_monotonic=captured_monotonic,
            )
            return self._encode_jpeg(
                _load_cv2(),
                output,
                quality,
                camera_id=int(camera_id),
            )
        finally:
            self._record_stage_latency(
                int(camera_id),
                "total",
                (time.perf_counter() - started_at) * 1000.0,
            )

    def render_image(
        self,
        camera_id: int,
        frame: Any,
        mode: str,
        *,
        source_key: str = "",
        frame_id: str = "",
        captured_at: str = "",
        captured_monotonic: float | None = None,
    ) -> Any:
        """Return the edge-composed BGR frame without transport encoding."""
        started_at = time.perf_counter()
        try:
            return self._render_image(
                camera_id,
                frame,
                mode,
                source_key=source_key,
                frame_id=frame_id,
                captured_at=captured_at,
                captured_monotonic=captured_monotonic,
            )
        finally:
            self._record_stage_latency(
                int(camera_id),
                "composition_total",
                (time.perf_counter() - started_at) * 1000.0,
            )

    def _render_image(
        self,
        camera_id: int,
        frame: Any,
        mode: str,
        *,
        source_key: str = "",
        frame_id: str = "",
        captured_at: str = "",
        captured_monotonic: float | None = None,
    ) -> Any:
        resolved_mode = normalize_privacy_mode(mode)
        cv2 = _load_cv2()
        if frame is None or not getattr(frame, "size", 0):
            raise RuntimeError("privacy source frame is unavailable")
        self._observe_pending_revalidation(
            cv2,
            int(camera_id),
            frame,
            source_key=str(source_key or ""),
            frame_id=str(frame_id or ""),
            captured_at=str(captured_at or ""),
            captured_monotonic=captured_monotonic,
        )
        if resolved_mode == "original":
            self._record_output(
                int(camera_id),
                resolved_mode,
                str(frame_id or ""),
                captured_monotonic=captured_monotonic,
            )
            return frame

        if resolved_mode == "skeleton":
            height, width = frame.shape[:2]
            self.background_reconstructor.require_baseline(
                int(camera_id),
                source_key=str(source_key or ""),
                width=int(width),
                height=int(height),
            )

        if frame_id:
            metadata_started_at = time.perf_counter()
            metadata = self._metadata_for_current_frame(
                int(camera_id),
                frame_id=str(frame_id),
                source_key=str(source_key or ""),
                captured_at=str(captured_at or ""),
                captured_monotonic=captured_monotonic,
                frame=frame,
            )
            self._record_stage_latency(
                int(camera_id),
                "pose_sync_wait",
                (time.perf_counter() - metadata_started_at) * 1000.0,
            )
            cache_key = (
                int(camera_id),
                str(source_key or ""),
                resolved_mode,
                str(frame_id),
                int(frame.shape[1]),
                int(frame.shape[0]),
            )
            cached = self._cached_render(cache_key)
            if cached is not None:
                self._record_output(
                    int(camera_id),
                    resolved_mode,
                    str(frame_id),
                    captured_monotonic=captured_monotonic,
                )
                return cached
            if resolved_mode == "person_blur":
                output = self._render_person_blur_for_camera(
                    cv2,
                    int(camera_id),
                    frame,
                    metadata,
                    source_key=source_key,
                )
            else:
                output = self._render_skeleton(
                    cv2,
                    int(camera_id),
                    frame,
                    metadata,
                    source_key=source_key,
                )
            self._store_cached_render(cache_key, output)
            self._record_output(
                int(camera_id),
                resolved_mode,
                str(frame_id),
                captured_monotonic=captured_monotonic,
            )
            return output

        synchronized = self._synchronized_bundle(int(camera_id), source_key=source_key)
        if synchronized is not None:
            source = synchronized.get("frame")
            tracking = dict(synchronized.get("tracking") or {})
            if source is None or not str(tracking.get("frame_id") or ""):
                if resolved_mode == "skeleton":
                    raise PrivacyCalibrationRequired(int(camera_id), "synchronized_frame_required")
                output = self._strong_blur(cv2, frame)
                self._record_output(int(camera_id), resolved_mode, "")
                return output
            cache_key = (
                int(camera_id),
                str(source_key or ""),
                resolved_mode,
                str(tracking.get("frame_id")),
                int(frame.shape[1]),
                int(frame.shape[0]),
            )
            cached = self._cached_render(cache_key)
            if cached is not None:
                self._record_output(
                    int(camera_id),
                    resolved_mode,
                    str(tracking.get("frame_id") or ""),
                    captured_monotonic=tracking.get("captured_monotonic"),
                )
                return cached
            source_height, source_width = source.shape[:2]
            output_frame = cv2.resize(
                source,
                (int(frame.shape[1]), int(frame.shape[0])),
                interpolation=cv2.INTER_AREA if source_width > frame.shape[1] else cv2.INTER_LINEAR,
            )
            metadata = {
                "tracking": tracking,
                "analysis_context": dict(synchronized.get("analysis_context") or {}),
                "image_width": int(source_width),
                "image_height": int(source_height),
            }
            if resolved_mode == "person_blur":
                output = self._render_person_blur_for_camera(
                    cv2,
                    int(camera_id),
                    output_frame,
                    metadata,
                    source_key=source_key,
                )
            else:
                output = self._render_skeleton(
                    cv2,
                    int(camera_id),
                    output_frame,
                    metadata,
                    source_key=source_key,
                )
            self._store_cached_render(cache_key, output)
            self._record_output(
                int(camera_id),
                resolved_mode,
                str(tracking.get("frame_id") or ""),
                captured_monotonic=tracking.get("captured_monotonic"),
            )
            return output

        if self._supports_synchronized_frames():
            if resolved_mode == "skeleton":
                raise PrivacyCalibrationRequired(int(camera_id), "synchronized_frame_required")
            output = self._strong_blur(cv2, frame)
            self._record_output(int(camera_id), resolved_mode, "")
            return output

        metadata = self._tracking_metadata(int(camera_id))
        if resolved_mode == "person_blur":
            output = self._render_person_blur_for_camera(
                cv2,
                int(camera_id),
                frame,
                metadata,
                source_key=source_key,
            )
        else:
            output = self._render_skeleton(
                cv2,
                int(camera_id),
                frame,
                metadata,
                source_key=source_key,
            )
        self._record_output(int(camera_id), resolved_mode, "")
        return output

    def _supports_synchronized_frames(self) -> bool:
        return self.tracker is not None and callable(getattr(self.tracker, "latest_synchronized_frame", None))

    def _synchronized_bundle(self, camera_id: int, *, source_key: str = "") -> Dict[str, Any] | None:
        if not self._supports_synchronized_frames():
            return None
        try:
            bundle = self.tracker.latest_synchronized_frame(camera_id)
            if not isinstance(bundle, dict):
                self._record_sync_rejection(camera_id, "bundle_unavailable")
                return None
            tracking = bundle.get("tracking") if isinstance(bundle.get("tracking"), dict) else {}
            if int(tracking.get("camera_id") or 0) != int(camera_id):
                self._record_sync_rejection(camera_id, "camera_mismatch")
                return None
            frame_id = str(tracking.get("frame_id") or "")
            if not frame_id.startswith(f"{int(camera_id)}-"):
                self._record_sync_rejection(camera_id, "frame_identity_mismatch")
                return None
            tracked_source_key = str(tracking.get("source_key") or bundle.get("source_key") or "")
            if source_key and tracked_source_key != str(source_key):
                self._record_sync_rejection(camera_id, "source_generation_mismatch")
                return None
            return dict(bundle)
        except Exception as exc:
            self._record_sync_rejection(camera_id, "tracker_error", detail=str(exc))
            return None

    def _record_sync_rejection(self, camera_id: int, reason: str, *, detail: str = "") -> None:
        with self._cache_lock:
            metrics = self._sync_rejections.setdefault(int(camera_id), {
                "total": 0,
                "reasons": {},
                "last_reason": "",
                "last_detail": "",
                "last_at_monotonic": 0.0,
            })
            metrics["total"] = int(metrics["total"]) + 1
            reasons = metrics["reasons"]
            reasons[str(reason)] = int(reasons.get(str(reason), 0)) + 1
            metrics["last_reason"] = str(reason)
            metrics["last_detail"] = str(detail or "")[:240]
            metrics["last_at_monotonic"] = time.monotonic()

    def _record_segmentation_assist(self, camera_id: int, reason: str) -> None:
        with self._cache_lock:
            metrics = self._segmentation_assists.setdefault(int(camera_id), {
                "total": 0,
                "last_reason": "",
                "last_at_monotonic": 0.0,
            })
            metrics["total"] = int(metrics["total"]) + 1
            metrics["last_reason"] = str(reason)
            metrics["last_at_monotonic"] = time.monotonic()

    def reset_camera(self, camera_id: int) -> None:
        camera_id = int(camera_id)
        self.background_reconstructor.reset_camera(camera_id)
        reset_segmentation = getattr(self.segmentation_backend, "reset_camera", None)
        if callable(reset_segmentation):
            reset_segmentation(camera_id)
        with self._cache_lock:
            for key in [item for item in self._render_cache if int(item[0]) == camera_id]:
                self._render_cache.pop(key, None)
            self._sync_rejections.pop(camera_id, None)
            self._segmentation_assists.pop(camera_id, None)
            self._output_samples.pop(camera_id, None)
            self._output_state.pop(camera_id, None)
            self._stage_latency_samples.pop(camera_id, None)
            for key in [item for item in self._revalidation_schedule if int(item[0]) == camera_id]:
                self._revalidation_schedule.pop(key, None)

    def begin_calibration(
        self,
        camera_id: int,
        *,
        source_key: str,
        width: int,
        height: int,
        calibration_id: str,
    ) -> Dict[str, Any]:
        return self.background_reconstructor.begin_calibration(
            int(camera_id),
            source_key=str(source_key or ""),
            width=int(width),
            height=int(height),
            calibration_id=str(calibration_id),
        )

    def discover_calibrations(
        self,
        camera_id: int,
        *,
        source_key: str,
    ) -> list[Dict[str, Any]]:
        return self.background_reconstructor.discover_persisted(
            int(camera_id),
            source_key=str(source_key or ""),
        )

    def cancel_calibration(
        self,
        camera_id: int,
        *,
        source_key: str,
        width: int,
        height: int,
        reason: str,
    ) -> Dict[str, Any]:
        return self.background_reconstructor.cancel_calibration(
            int(camera_id),
            source_key=str(source_key or ""),
            width=int(width),
            height=int(height),
            reason=str(reason or "calibration_cancelled"),
        )

    def observe_calibration_frame(
        self,
        camera_id: int,
        frame: Any,
        *,
        source_key: str,
        frame_id: str,
        captured_at: str = "",
        captured_monotonic: float | None = None,
    ) -> Dict[str, Any]:
        cv2 = _load_cv2()
        metadata = self._metadata_for_current_frame(
            int(camera_id),
            frame_id=str(frame_id),
            source_key=str(source_key or ""),
            captured_at=str(captured_at or ""),
            captured_monotonic=captured_monotonic,
            frame=frame,
        )
        mask = self._segmentation_mask(
            cv2,
            int(camera_id),
            frame,
            metadata,
            source_key=source_key,
        )
        if mask is None:
            raise PrivacyCalibrationRequired(int(camera_id), "segmentation_unavailable")
        return self.background_reconstructor.observe_calibration(
            cv2,
            int(camera_id),
            frame,
            mask,
            frame_token=str(frame_id),
            source_key=str(source_key or ""),
            person_evidence=self._has_person_evidence(metadata),
        )

    def _observe_pending_revalidation(
        self,
        cv2: Any,
        camera_id: int,
        frame: Any,
        *,
        source_key: str,
        frame_id: str,
        captured_at: str,
        captured_monotonic: float | None,
    ) -> None:
        if not frame_id:
            return
        height, width = frame.shape[:2]
        calibration = self.background_reconstructor.inspect(
            int(camera_id),
            source_key=str(source_key or ""),
            width=int(width),
            height=int(height),
        )
        if (
            not calibration.get("calibrated")
            or calibration.get("ready")
            or calibration.get("calibration_active")
        ):
            self._clear_revalidation_schedule(
                int(camera_id),
                str(source_key or ""),
                int(width),
                int(height),
            )
            return
        if not self._claim_revalidation_attempt(
            int(camera_id),
            str(source_key or ""),
            int(width),
            int(height),
            str(frame_id),
        ):
            return
        metadata = self._metadata_for_current_frame(
            int(camera_id),
            frame_id=str(frame_id),
            source_key=str(source_key or ""),
            captured_at=str(captured_at or ""),
            captured_monotonic=captured_monotonic,
            frame=frame,
        )
        mask = self._segmentation_mask(
            cv2,
            int(camera_id),
            frame,
            metadata,
            source_key=source_key,
            force_anchor=True,
        )
        render_identity = dict(metadata.get("render_identity") or {})
        result = self.background_reconstructor.observe_revalidation(
            int(camera_id),
            frame,
            frame_token=str(frame_id),
            source_key=str(source_key or ""),
            person_evidence=(
                self._has_person_evidence(metadata)
                or bool(mask is not None and cv2.countNonZero(mask))
            ),
            evidence_synchronized=bool(
                mask is not None
                and render_identity.get("pose_synchronized")
            ),
        )
        if result.get("ready"):
            self._clear_revalidation_schedule(
                int(camera_id),
                str(source_key or ""),
                int(width),
                int(height),
            )

    def _claim_revalidation_attempt(
        self,
        camera_id: int,
        source_key: str,
        width: int,
        height: int,
        frame_id: str,
    ) -> bool:
        key = (int(camera_id), str(source_key or ""), int(width), int(height))
        now = self._clock()
        with self._cache_lock:
            state = self._revalidation_schedule.get(key)
            if state is not None:
                if str(state.get("last_frame_id") or "") == str(frame_id):
                    return False
                if now < float(state.get("next_attempt_at") or 0.0):
                    return False
            for stale_key in [
                item
                for item in self._revalidation_schedule
                if int(item[0]) == int(camera_id) and item != key
            ]:
                self._revalidation_schedule.pop(stale_key, None)
            self._revalidation_schedule[key] = {
                "last_frame_id": str(frame_id),
                "last_attempt_at": now,
                "next_attempt_at": now + self.revalidation_interval_seconds,
            }
            return True

    def _clear_revalidation_schedule(
        self,
        camera_id: int,
        source_key: str,
        width: int,
        height: int,
    ) -> None:
        key = (int(camera_id), str(source_key or ""), int(width), int(height))
        with self._cache_lock:
            self._revalidation_schedule.pop(key, None)

    def status(self) -> Dict[str, Any]:
        now = time.monotonic()
        scheduler_now = self._clock()
        with self._cache_lock:
            render_cache_count = len(self._render_cache)
            sync_rejections = {
                str(camera_id): {
                    **metrics,
                    "reasons": dict(metrics.get("reasons") or {}),
                    "last_age_ms": round(
                        max(0.0, now - float(metrics.get("last_at_monotonic") or 0.0)) * 1000.0,
                        1,
                    ) if metrics.get("last_at_monotonic") else None,
                }
                for camera_id, metrics in sorted(self._sync_rejections.items())
            }
            segmentation_assists = {
                str(camera_id): {
                    **metrics,
                    "last_age_ms": round(
                        max(0.0, now - float(metrics.get("last_at_monotonic") or 0.0)) * 1000.0,
                        1,
                    ) if metrics.get("last_at_monotonic") else None,
                }
                for camera_id, metrics in sorted(self._segmentation_assists.items())
            }
            cameras = {
                str(camera_id): {
                    **dict(self._output_state.get(camera_id) or {}),
                    "output_fps": self._sample_rate(samples, now),
                    "output_frame_age_ms": round(max(0.0, now - samples[-1]) * 1000.0, 1) if samples else None,
                    "stage_latency_ms": {
                        stage: self._latency_summary(values)
                        for stage, values in sorted(
                            (self._stage_latency_samples.get(camera_id) or {}).items()
                        )
                    },
                }
                for camera_id, samples in sorted(self._output_samples.items())
            }
            revalidation_streams = {
                f"{camera_id}:{source_key}:{width}x{height}": {
                    "camera_id": int(camera_id),
                    "source_key": str(source_key),
                    "width": int(width),
                    "height": int(height),
                    "last_frame_id": str(state.get("last_frame_id") or ""),
                    "next_attempt_in_ms": round(
                        max(
                            0.0,
                            float(state.get("next_attempt_at") or 0.0) - scheduler_now,
                        ) * 1000.0,
                        1,
                    ),
                }
                for (camera_id, source_key, width, height), state
                in sorted(self._revalidation_schedule.items())
            }
        return {
            "schema_version": self.version,
            "render_cache_count": render_cache_count,
            "synchronization_rejections": sync_rejections,
            "segmentation_assists": segmentation_assists,
            "revalidation_scheduler": {
                "interval_seconds": self.revalidation_interval_seconds,
                "active_streams": len(revalidation_streams),
                "streams": revalidation_streams,
            },
            "cameras": cameras,
            "background": self.background_reconstructor.status(),
            "person_segmentation": (
                self.segmentation_backend.status()
                if callable(getattr(self.segmentation_backend, "status", None))
                else {"schema_version": "disabled", "status": "unavailable"}
            ),
        }

    def close(self) -> None:
        close_segmentation = getattr(self.segmentation_backend, "close", None)
        if callable(close_segmentation):
            close_segmentation()

    def _record_output(
        self,
        camera_id: int,
        mode: str,
        frame_id: str,
        *,
        captured_monotonic: Any = None,
    ) -> None:
        now = time.monotonic()
        try:
            sample_at = float(captured_monotonic)
        except (TypeError, ValueError):
            sample_at = now
        if not np.isfinite(sample_at) or sample_at <= 0.0 or abs(now - sample_at) > 3600.0:
            sample_at = now
        camera_id = int(camera_id)
        frame_id = str(frame_id or "")
        with self._cache_lock:
            previous = self._output_state.get(camera_id) or {}
            self._output_state[camera_id] = {
                "mode": str(mode or ""),
                "last_frame_id": frame_id or str(previous.get("last_frame_id") or ""),
            }
            if not frame_id or frame_id == str(previous.get("last_frame_id") or ""):
                return
            samples = self._output_samples.setdefault(camera_id, deque(maxlen=300))
            samples.append(sample_at)
            while samples and samples[0] < now - 10.0:
                samples.popleft()

    def _sample_rate(self, samples: deque[float], now: float) -> float:
        recent = [value for value in samples if value >= now - 10.0]
        if len(recent) < 2:
            return 0.0
        return round((len(recent) - 1) / max(0.001, recent[-1] - recent[0]), 2)

    def _record_stage_latency(self, camera_id: int, stage: str, elapsed_ms: float) -> None:
        with self._cache_lock:
            stages = self._stage_latency_samples.setdefault(int(camera_id), {})
            samples = stages.setdefault(str(stage), deque(maxlen=300))
            samples.append(max(0.0, float(elapsed_ms)))

    @staticmethod
    def _latency_summary(samples: deque[float]) -> Dict[str, float | int | None]:
        if not samples:
            return {"samples": 0, "median": None, "p95": None, "max": None, "last": None}
        values = np.asarray(samples, dtype=np.float64)
        return {
            "samples": len(samples),
            "median": round(float(np.percentile(values, 50)), 2),
            "p95": round(float(np.percentile(values, 95)), 2),
            "max": round(float(np.max(values)), 2),
            "last": round(float(values[-1]), 2),
        }

    def _encode_jpeg(self, cv2: Any, output: Any, quality: int, *, camera_id: int) -> bytes:
        started_at = time.perf_counter()
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), max(40, min(int(quality), 85))]
        ok, rendered = cv2.imencode(".jpg", output, encode_params)
        self._record_stage_latency(
            int(camera_id),
            "jpeg_encode",
            (time.perf_counter() - started_at) * 1000.0,
        )
        if not ok:
            raise RuntimeError("privacy frame encode failed")
        return rendered.tobytes()

    def _person_free_scene(
        self,
        cv2: Any,
        camera_id: int,
        frame: Any,
        metadata: Dict[str, Any],
        *,
        source_key: str = "",
    ) -> Any:
        tracking = dict(metadata.get("tracking") or {})
        render_identity = dict(metadata.get("render_identity") or {})
        segmentation_started_at = time.perf_counter()
        mask = self._segmentation_mask(
            cv2,
            camera_id,
            frame,
            metadata,
            source_key=source_key,
        )
        self._record_stage_latency(
            int(camera_id),
            "segmentation",
            (time.perf_counter() - segmentation_started_at) * 1000.0,
        )
        if mask is None:
            raise PrivacyCalibrationRequired(camera_id, "segmentation_unavailable")
        reconstruction_started_at = time.perf_counter()
        scene = self.background_reconstructor.reconstruct(
            cv2,
            camera_id,
            frame,
            mask,
            clear_token=str(render_identity.get("frame_id") or tracking.get("frame_id") or ""),
            source_key=source_key,
        )
        self._record_stage_latency(
            int(camera_id),
            "background_reconstruction",
            (time.perf_counter() - reconstruction_started_at) * 1000.0,
        )
        return scene

    def _cached_render(self, key: tuple[Any, ...]) -> Any | None:
        with self._cache_lock:
            value = self._render_cache.get(key)
            if value is not None:
                self._render_cache.move_to_end(key)
            return value

    def _store_cached_render(self, key: tuple[Any, ...], value: Any) -> None:
        with self._cache_lock:
            self._render_cache[key] = value
            self._render_cache.move_to_end(key)
            while len(self._render_cache) > 32:
                self._render_cache.popitem(last=False)

    def _tracking_metadata(self, camera_id: int) -> Dict[str, Any]:
        if self.tracker is None:
            return {"tracking": {"state": "empty", "poses": []}}
        try:
            metadata = dict(self.tracker.latest_metadata(camera_id) or {})
            tracking = metadata.get("tracking") if isinstance(metadata.get("tracking"), dict) else {}
            if int(tracking.get("camera_id") or camera_id) != int(camera_id):
                return {"tracking": {"state": "empty", "poses": []}}
            return metadata
        except Exception:
            return {"tracking": {"state": "empty", "poses": []}}

    def _metadata_for_current_frame(
        self,
        camera_id: int,
        *,
        frame_id: str,
        source_key: str,
        captured_at: str,
        captured_monotonic: float | None,
        frame: Any,
    ) -> Dict[str, Any]:
        deadline = time.monotonic() + self.maximum_pose_wait_seconds
        metadata: Dict[str, Any] = {}
        tracking: Dict[str, Any] = {}
        stale_reason = "pose_frame_unavailable"
        metadata_for_frame = getattr(self.tracker, "metadata_for_frame", None)
        while True:
            if callable(metadata_for_frame):
                exact = metadata_for_frame(
                    int(camera_id),
                    frame_id=str(frame_id),
                    source_key=str(source_key or ""),
                )
                if isinstance(exact, dict):
                    metadata = dict(exact)
                    tracking = dict(metadata.get("tracking") or {})
                    stale_reason = ""
                    break
            metadata = self._tracking_metadata(int(camera_id))
            tracking = dict(metadata.get("tracking") or {})
            tracked_source = str(tracking.get("source_key") or metadata.get("source_key") or "")
            tracked_frame_id = str(tracking.get("frame_id") or "")
            if tracked_source and source_key and tracked_source != source_key:
                stale_reason = "pose_source_mismatch"
                break
            if tracked_frame_id == str(frame_id):
                stale_reason = ""
                break
            try:
                current_time = float(captured_monotonic)
                tracked_time = float(tracking.get("captured_monotonic"))
            except (TypeError, ValueError):
                current_time = 0.0
                tracked_time = 0.0
            if current_time > 0.0 and tracked_time > current_time + 0.0005:
                stale_reason = "pose_frame_superseded"
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                break
            time.sleep(min(0.003, remaining))
        if stale_reason:
            self._record_sync_rejection(int(camera_id), stale_reason)
            metadata = {
                "tracking": {
                    "camera_id": int(camera_id),
                    "state": "empty",
                    "reason": stale_reason,
                    "poses": [],
                    "source_key": str(source_key or ""),
                },
                "analysis_context": {},
                "image_width": int(frame.shape[1]),
                "image_height": int(frame.shape[0]),
            }
        metadata["render_identity"] = {
            "camera_id": int(camera_id),
            "frame_id": str(frame_id),
            "source_key": str(source_key or ""),
            "stream_generation": self._stream_generation(source_key),
            "captured_at": str(captured_at or ""),
            "captured_monotonic": captured_monotonic,
            "pose_synchronized": not bool(stale_reason),
        }
        return metadata

    @staticmethod
    def _stream_generation(source_key: str) -> int:
        marker = str(source_key or "").rsplit(":g", 1)
        if len(marker) != 2:
            return 0
        try:
            return max(0, int(marker[1]))
        except ValueError:
            return 0

    def _render_skeleton(
        self,
        cv2: Any,
        camera_id: int,
        frame: Any,
        metadata: Dict[str, Any],
        *,
        source_key: str = "",
    ) -> Any:
        tracking = dict(metadata.get("tracking") or {})
        state = str(tracking.get("state") or "empty")
        height, width = frame.shape[:2]
        canvas = self._person_free_scene(
            cv2,
            camera_id,
            frame,
            metadata,
            source_key=source_key,
        )
        drawing_started_at = time.perf_counter()
        if state not in {"observed", "tracked"} or bool(tracking.get("display_only_stale")):
            self._record_stage_latency(int(camera_id), "skeleton_draw", 0.0)
            return canvas

        source_width = max(1, int(metadata.get("image_width") or width))
        source_height = max(1, int(metadata.get("image_height") or height))
        scale_x = width / source_width
        scale_y = height / source_height
        context = dict(metadata.get("analysis_context") or {})
        edges = context.get("pose_skeleton_edges")
        if not isinstance(edges, list) or not edges:
            edges = DEFAULT_SKELETON_EDGES
        line_color = SKELETON_LINE_BGR
        joint_color = SKELETON_JOINT_BGR

        for pose in tracking.get("poses") or []:
            if not isinstance(pose, dict):
                continue
            points = {
                str(point.get("name")): point
                for point in (pose.get("keypoints") or [])
                if isinstance(point, dict)
                and point.get("name")
                and point.get("visible")
                and float(point.get("confidence") or 0.0) >= 0.22
            }
            for edge in edges:
                if not isinstance(edge, (list, tuple)) or len(edge) < 2:
                    continue
                start = points.get(str(edge[0]))
                end = points.get(str(edge[1]))
                if start is None or end is None:
                    continue
                p1 = self._point(start, scale_x, scale_y, width, height)
                p2 = self._point(end, scale_x, scale_y, width, height)
                cv2.line(canvas, p1, p2, (8, 8, 8), 6, cv2.LINE_AA)
                cv2.line(canvas, p1, p2, line_color, 3, cv2.LINE_AA)
            for point in points.values():
                center = self._point(point, scale_x, scale_y, width, height)
                cv2.circle(canvas, center, 5, (8, 8, 8), -1, cv2.LINE_AA)
                cv2.circle(canvas, center, 3, joint_color, -1, cv2.LINE_AA)
            self._draw_head(cv2, canvas, points, scale_x, scale_y, width, height, line_color)
        self._record_stage_latency(
            int(camera_id),
            "skeleton_draw",
            (time.perf_counter() - drawing_started_at) * 1000.0,
        )
        return canvas

    def _render_person_blur_for_camera(
        self,
        cv2: Any,
        camera_id: int,
        frame: Any,
        metadata: Dict[str, Any],
        *,
        source_key: str = "",
    ) -> Any:
        segmentation_started_at = time.perf_counter()
        mask = self._segmentation_mask(
            cv2,
            camera_id,
            frame,
            metadata,
            source_key=source_key,
        )
        self._record_stage_latency(
            int(camera_id),
            "segmentation",
            (time.perf_counter() - segmentation_started_at) * 1000.0,
        )
        started_at = time.perf_counter()
        if mask is None:
            output = self._strong_blur(cv2, frame)
            self._record_stage_latency(
                int(camera_id),
                "person_blur_composition",
                (time.perf_counter() - started_at) * 1000.0,
            )
            return output
        if not bool(cv2.countNonZero(mask)):
            output = frame.copy()
            self._record_stage_latency(
                int(camera_id),
                "person_blur_composition",
                (time.perf_counter() - started_at) * 1000.0,
            )
            return output
        output = self._masked_privacy_blur(cv2, frame, mask)
        self._record_stage_latency(
            int(camera_id),
            "person_blur_composition",
            (time.perf_counter() - started_at) * 1000.0,
        )
        return output

    def _segmentation_mask(
        self,
        cv2: Any,
        camera_id: int,
        frame: Any,
        metadata: Dict[str, Any],
        *,
        source_key: str = "",
        force_anchor: bool = False,
    ) -> Any | None:
        backend = self.segmentation_backend
        segment = (
            getattr(backend, "segment_anchor", None)
            if force_anchor
            else None
        ) or getattr(backend, "segment", None)
        if not callable(segment):
            return None
        tracking = dict(metadata.get("tracking") or {})
        render_identity = dict(metadata.get("render_identity") or {})
        frame_id = str(render_identity.get("frame_id") or tracking.get("frame_id") or "")
        if not frame_id:
            return None
        resolved_source_key = str(
            render_identity.get("source_key")
            or source_key
            or tracking.get("source_key")
            or ""
        )
        try:
            result = dict(segment(
                int(camera_id),
                frame,
                frame_id=frame_id,
                source_key=resolved_source_key,
                captured_monotonic=render_identity.get("captured_monotonic"),
                person_evidence=self._has_person_evidence(metadata),
            ) or {})
        except Exception as exc:
            self._record_sync_rejection(camera_id, "segmentation_error", detail=str(exc))
            return None
        if (
            int(result.get("camera_id") or camera_id) != int(camera_id)
            or str(result.get("frame_id") or frame_id) != frame_id
            or str(result.get("source_key") or "")
            != resolved_source_key
        ):
            self._record_sync_rejection(camera_id, "segmentation_identity_mismatch")
            return None
        mask = np.asarray(result.get("mask"), dtype=np.uint8)
        if mask.shape != frame.shape[:2]:
            self._record_sync_rejection(
                camera_id,
                "segmentation_shape_mismatch",
                detail=f"mask={mask.shape} frame={frame.shape[:2]}",
            )
            return None
        mask_pixels = int(cv2.countNonZero(mask))
        if self._has_person_evidence(metadata):
            assisted = self._pose_privacy_mask(cv2, frame, metadata)
            if bool(cv2.countNonZero(assisted)):
                combined = cv2.bitwise_or(mask, assisted)
                added_pixels = int(cv2.countNonZero(combined)) - mask_pixels
                if added_pixels > 0:
                    self._record_segmentation_assist(
                        camera_id,
                        "pose_geometry" if mask_pixels == 0 else "pose_geometry_union",
                    )
                return combined
            if mask_pixels == 0:
                self._record_sync_rejection(camera_id, "segmentation_person_missed")
                return None
        return mask

    def _pose_privacy_mask(
        self,
        cv2: Any,
        frame: Any,
        metadata: Dict[str, Any],
    ) -> Any:
        height, width = frame.shape[:2]
        mask = np.zeros((height, width), dtype=np.uint8)
        tracking = dict(metadata.get("tracking") or {})
        if (
            str(tracking.get("state") or "") not in {"observed", "tracked"}
            or bool(tracking.get("display_only_stale"))
        ):
            return mask
        source_width = max(1, int(metadata.get("image_width") or width))
        source_height = max(1, int(metadata.get("image_height") or height))
        scale_x = width / source_width
        scale_y = height / source_height
        context = dict(metadata.get("analysis_context") or {})
        edges = context.get("pose_skeleton_edges")
        if not isinstance(edges, list) or not edges:
            edges = DEFAULT_SKELETON_EDGES

        for pose in tracking.get("poses") or []:
            if not isinstance(pose, dict):
                continue
            points = {
                str(point.get("name")): point
                for point in (pose.get("keypoints") or [])
                if isinstance(point, dict)
                and point.get("name")
                and point.get("visible")
                and float(point.get("confidence") or 0.0) >= 0.22
            }
            if len(points) < 5:
                continue
            bbox = pose.get("bbox")
            if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                body_scale = max(
                    (float(bbox[2]) - float(bbox[0])) * scale_x,
                    (float(bbox[3]) - float(bbox[1])) * scale_y,
                )
            else:
                coordinates = [self._point(point, scale_x, scale_y, width, height) for point in points.values()]
                body_scale = max(
                    max(point[0] for point in coordinates) - min(point[0] for point in coordinates),
                    max(point[1] for point in coordinates) - min(point[1] for point in coordinates),
                )
            thickness = max(10, min(42, int(round(max(1.0, body_scale) * 0.12))))
            for edge in edges:
                if not isinstance(edge, (list, tuple)) or len(edge) < 2:
                    continue
                start = points.get(str(edge[0]))
                end = points.get(str(edge[1]))
                if start is None or end is None:
                    continue
                cv2.line(
                    mask,
                    self._point(start, scale_x, scale_y, width, height),
                    self._point(end, scale_x, scale_y, width, height),
                    255,
                    thickness,
                    cv2.LINE_AA,
                )
            torso_names = ("left_shoulder", "right_shoulder", "right_hip", "left_hip")
            if all(name in points for name in torso_names):
                torso = np.asarray([
                    self._point(points[name], scale_x, scale_y, width, height)
                    for name in torso_names
                ], dtype=np.int32)
                cv2.fillConvexPoly(mask, torso, 255, cv2.LINE_AA)
            joint_radius = max(5, thickness // 2)
            for point in points.values():
                cv2.circle(
                    mask,
                    self._point(point, scale_x, scale_y, width, height),
                    joint_radius,
                    255,
                    -1,
                    cv2.LINE_AA,
                )
            nose = points.get("nose")
            if nose is not None:
                cv2.circle(
                    mask,
                    self._point(nose, scale_x, scale_y, width, height),
                    max(joint_radius * 2, int(round(max(1.0, body_scale) * 0.08))),
                    255,
                    -1,
                    cv2.LINE_AA,
                )
        if not bool(cv2.countNonZero(mask)):
            return mask
        return cv2.dilate(
            mask,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)),
            iterations=1,
        )

    @staticmethod
    def _has_person_evidence(metadata: Dict[str, Any]) -> bool:
        tracking = dict(metadata.get("tracking") or {})
        if (
            str(tracking.get("state") or "") in {"observed", "tracked"}
            and not bool(tracking.get("display_only_stale"))
        ):
            if tracking.get("poses"):
                return True
        context = dict(metadata.get("analysis_context") or {})
        return bool(context.get("people"))

    def _strong_blur(self, cv2: Any, frame: Any) -> Any:
        height, width = frame.shape[:2]
        reduced_width = max(8, int(round(width / 10.0)))
        reduced_height = max(8, int(round(height / 10.0)))
        reduced = cv2.resize(
            frame,
            (reduced_width, reduced_height),
            interpolation=cv2.INTER_AREA,
        )
        kernel = max(3, min(9, ((min(reduced_width, reduced_height) // 4) | 1)))
        softened = cv2.GaussianBlur(reduced, (kernel, kernel), 0)
        return cv2.resize(
            softened,
            (int(width), int(height)),
            interpolation=cv2.INTER_LINEAR,
        )

    def _masked_privacy_blur(self, cv2: Any, frame: Any, mask: Any) -> Any:
        points = cv2.findNonZero(mask)
        if points is None:
            return frame.copy()
        x, y, width, height = cv2.boundingRect(points)
        padding = max(6, int(round(max(width, height) * 0.04)))
        x1 = max(0, x - padding)
        y1 = max(0, y - padding)
        x2 = min(int(frame.shape[1]), x + width + padding)
        y2 = min(int(frame.shape[0]), y + height + padding)
        source = frame[y1:y2, x1:x2]
        local_mask = mask[y1:y2, x1:x2]
        blurred = self._strong_blur(cv2, source)
        feather = cv2.GaussianBlur(local_mask, (9, 9), 0).astype(np.uint16)
        alpha = feather[..., None]
        source_u16 = source.astype(np.uint16)
        output = frame.copy()
        output[y1:y2, x1:x2] = (
            (
                blurred.astype(np.uint16) * alpha
                + source_u16 * (255 - alpha)
                + 127
            ) // 255
        ).astype(np.uint8)
        return output

    def _draw_head(
        self,
        cv2: Any,
        frame: Any,
        points: Dict[str, Dict[str, Any]],
        scale_x: float,
        scale_y: float,
        width: int,
        height: int,
        color: tuple[int, int, int],
    ) -> None:
        nose = points.get("nose")
        left_ear = points.get("left_ear")
        right_ear = points.get("right_ear")
        left_shoulder = points.get("left_shoulder")
        right_shoulder = points.get("right_shoulder")
        if nose is None or left_shoulder is None or right_shoulder is None:
            return
        center = self._point(nose, scale_x, scale_y, width, height)
        if left_ear is not None and right_ear is not None:
            left = self._point(left_ear, scale_x, scale_y, width, height)
            right = self._point(right_ear, scale_x, scale_y, width, height)
            radius = int(round(max(7.0, np.hypot(right[0] - left[0], right[1] - left[1]) * 0.62)))
        else:
            left = self._point(left_shoulder, scale_x, scale_y, width, height)
            right = self._point(right_shoulder, scale_x, scale_y, width, height)
            radius = int(round(max(7.0, np.hypot(right[0] - left[0], right[1] - left[1]) * 0.28)))
        radius = min(radius, max(8, int(min(width, height) * 0.09)))
        cv2.circle(frame, center, radius, (8, 8, 8), 5, cv2.LINE_AA)
        cv2.circle(frame, center, radius, color, 2, cv2.LINE_AA)

    def _point(
        self,
        point: Dict[str, Any],
        scale_x: float,
        scale_y: float,
        width: int,
        height: int,
    ) -> tuple[int, int]:
        return (
            max(0, min(width - 1, int(round(float(point.get("x") or 0.0) * scale_x)))),
            max(0, min(height - 1, int(round(float(point.get("y") or 0.0) * scale_y)))),
        )


class PrivacyMjpegStream:
    def __init__(self, camera_agent: Any, renderer: PrivacyFrameRenderer) -> None:
        self.camera_agent = camera_agent
        self.renderer = renderer

    def mjpeg_frames(
        self,
        camera: Dict[str, Any],
        *,
        privacy_mode: str,
        privacy_mode_resolver: Callable[[], str] | None = None,
        fps: int,
        jpeg_quality: int,
        max_width: int,
        max_height: int,
    ) -> Generator[bytes, None, None]:
        requested_mode = normalize_privacy_mode(privacy_mode)
        for capture in self._source_frames(
            camera,
            fps=fps,
            jpeg_quality=jpeg_quality,
            max_width=max_width,
            max_height=max_height,
        ):
            frame = capture["frame"]
            source_key = str(capture.get("source_key") or "")
            mode = stricter_privacy_mode(
                privacy_mode_resolver() if privacy_mode_resolver is not None else requested_mode,
                requested_mode,
            )
            try:
                rendered = self.renderer.render_frame(
                    int(camera["id"]),
                    frame,
                    mode,
                    quality=jpeg_quality,
                    source_key=source_key,
                    frame_id=str(capture.get("frame_id") or ""),
                    captured_at=str(capture.get("captured_at") or ""),
                    captured_monotonic=capture.get("captured_monotonic"),
                )
            except Exception:
                continue
            yield self._multipart_frame(rendered, privacy_mode=mode, composition="server")

    def _source_frames(
        self,
        camera: Dict[str, Any],
        *,
        fps: int,
        jpeg_quality: int,
        max_width: int,
        max_height: int,
    ) -> Generator[Dict[str, Any], None, None]:
        for capture in self.camera_agent.raw_frames(
            camera,
            fps=fps,
            max_width=max_width,
            max_height=max_height,
        ):
            frame = capture.get("frame") if isinstance(capture, dict) else None
            if frame is None:
                continue
            yield {
                **capture,
                "frame": frame,
                "source_key": str(capture.get("source_key") or ""),
            }

    def _multipart_frame(self, jpeg: bytes, *, privacy_mode: str, composition: str) -> bytes:
        headers = (
            "Content-Type: image/jpeg\r\n"
            "Cache-Control: no-store\r\n"
            f"X-GoHome-Privacy-Mode: {privacy_mode}\r\n"
            f"X-GoHome-Composition: {composition}\r\n\r\n"
        ).encode("ascii")
        return b"--frame\r\n" + headers + jpeg + b"\r\n"
