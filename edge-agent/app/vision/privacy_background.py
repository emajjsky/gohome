from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from threading import RLock
import os
import re
import time
from typing import Any, Callable

import numpy as np

from .privacy_scene_geometry import SceneGeometryVerifier


class PrivacyCalibrationRequired(RuntimeError):
    def __init__(self, camera_id: int, reason: str = "calibration_required") -> None:
        self.camera_id = int(camera_id)
        self.reason = str(reason)
        super().__init__(self.reason)


@dataclass
class _BackgroundState:
    background: Any | None = None
    calibrated: bool = False
    baseline_revision: int = 0
    baseline_sha256: str = ""
    active_generation: str = ""
    generation_validated: bool = False
    revalidation_observations: int = 0
    last_revalidation_token: str = ""
    scene_status: str = "calibration_required"
    scene_match_observations: int = 0
    scene_mismatch_observations: int = 0
    last_scene_match_ratio: float | None = None
    last_scene_median_residual: float | None = None
    last_geometry_check_at: float = 0.0
    last_geometry_status: str = "not_checked"
    last_geometry_reason: str = ""
    last_geometry_good_matches: int = 0
    last_geometry_inliers: int = 0
    last_geometry_inlier_ratio: float | None = None
    last_geometry_median_corner_displacement_ratio: float | None = None
    last_geometry_max_corner_displacement_ratio: float | None = None
    last_geometry_signature: Any | None = None
    calibration_active: bool = False
    calibration_id: str = ""
    calibration_reference: Any | None = None
    calibration_average: Any | None = None
    calibration_observations: int = 0
    calibration_rejections: int = 0
    last_calibration_token: str = ""
    recent_person_mask: Any | None = None
    recent_person_at: float = 0.0
    person_frames: int = 0
    scene_review_events: int = 0
    composites: int = 0
    last_error: str = ""
    last_used: float = 0.0
    latencies_ms: deque[float] = field(default_factory=lambda: deque(maxlen=240))


class PrivacyBackgroundReconstructor:
    """Compose pure-skeleton scenes from an explicitly calibrated empty room."""

    version = "privacy-background-calibration-v2"

    def __init__(
        self,
        *,
        storage_dir: Path | str | None = None,
        max_states: int = 6,
        confirmation_frames: int = 8,
        revalidation_frames: int = 3,
        foreground_threshold: int = 24,
        recent_mask_seconds: float = 1.4,
        geometry_recheck_seconds: float = 1.0,
        geometry_verifier: SceneGeometryVerifier | None = None,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        self.storage_dir = Path(storage_dir) if storage_dir else None
        self.max_states = max(1, int(max_states))
        self.confirmation_frames = max(3, int(confirmation_frames))
        self.revalidation_frames = max(2, int(revalidation_frames))
        self.foreground_threshold = max(8, min(80, int(foreground_threshold)))
        self.recent_mask_seconds = max(0.2, min(float(recent_mask_seconds), 3.0))
        self.geometry_recheck_seconds = max(0.25, min(float(geometry_recheck_seconds), 5.0))
        self.geometry_verifier = geometry_verifier or SceneGeometryVerifier()
        self._clock = monotonic_clock or time.monotonic
        self._states: OrderedDict[tuple[int, str, int, int], _BackgroundState] = OrderedDict()
        self._lock = RLock()
        if self.storage_dir is not None:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            os.chmod(self.storage_dir, 0o700)

    def begin_calibration(
        self,
        camera_id: int,
        *,
        source_key: str,
        width: int,
        height: int,
        calibration_id: str,
    ) -> dict[str, Any]:
        key, generation = self._state_key(camera_id, source_key, width, height)
        now = self._clock()
        with self._lock:
            state = self._state(key, now)
            if state.calibration_active:
                raise PrivacyCalibrationRequired(camera_id, "calibration_in_progress")
            state.active_generation = generation
            state.generation_validated = False
            state.revalidation_observations = 0
            state.scene_status = "calibrating"
            state.calibration_active = True
            state.calibration_id = str(calibration_id)
            state.calibration_reference = None
            state.calibration_average = None
            state.calibration_observations = 0
            state.calibration_rejections = 0
            state.last_calibration_token = ""
            state.recent_person_mask = None
            state.recent_person_at = 0.0
            state.last_error = ""
            state.last_used = now
            return self._state_status(key, state)

    def cancel_calibration(
        self,
        camera_id: int,
        *,
        source_key: str,
        width: int,
        height: int,
        reason: str,
    ) -> dict[str, Any]:
        key, generation = self._state_key(camera_id, source_key, width, height)
        with self._lock:
            state = self._state(key, self._clock())
            state.active_generation = generation
            state.generation_validated = False
            state.revalidation_observations = 0
            state.calibration_active = False
            state.calibration_reference = None
            state.calibration_average = None
            state.calibration_observations = 0
            state.scene_status = "revalidation_required" if state.background is not None else "calibration_required"
            state.last_error = str(reason or "calibration_cancelled")
            return self._state_status(key, state)

    def observe_calibration(
        self,
        cv2: Any,
        camera_id: int,
        frame: Any,
        person_mask: Any,
        *,
        frame_token: str,
        source_key: str,
        person_evidence: bool = False,
    ) -> dict[str, Any]:
        height, width = frame.shape[:2]
        key, generation = self._state_key(camera_id, source_key, width, height)
        mask = self._binary_mask(cv2, person_mask, width, height)
        now = self._clock()
        with self._lock:
            state = self._state(key, now)
            if not state.calibration_active:
                raise PrivacyCalibrationRequired(camera_id, "calibration_not_started")
            token = str(frame_token or "")
            if token and token == state.last_calibration_token:
                return self._state_status(key, state)
            state.last_calibration_token = token
            state.active_generation = generation
            state.last_used = now

            if person_evidence or bool(cv2.countNonZero(mask)):
                state.calibration_rejections += 1
                state.calibration_reference = None
                state.calibration_average = None
                state.calibration_observations = 0
                state.last_error = "person_present"
                return self._state_status(key, state)

            if state.calibration_reference is None:
                state.calibration_reference = frame.copy()
                state.calibration_average = frame.astype(np.float32)
                state.calibration_observations = 1
                state.last_error = ""
                return self._state_status(key, state)

            if not self._calibration_frame_matches(state.calibration_reference, frame):
                state.calibration_rejections += 1
                state.calibration_reference = frame.copy()
                state.calibration_average = frame.astype(np.float32)
                state.calibration_observations = 1
                state.last_error = "scene_unstable"
                return self._state_status(key, state)

            count = state.calibration_observations
            state.calibration_average = (
                state.calibration_average * float(count) + frame.astype(np.float32)
            ) / float(count + 1)
            state.calibration_observations = count + 1
            state.last_error = ""
            if state.calibration_observations >= self.confirmation_frames:
                completed_background = np.clip(
                    np.rint(state.calibration_average),
                    0,
                    255,
                ).astype(np.uint8)
                self._persist(key, completed_background)
                state.background = completed_background
                state.calibrated = True
                state.baseline_revision += 1
                state.baseline_sha256 = self._background_sha256(completed_background)
                state.generation_validated = True
                state.revalidation_observations = self.revalidation_frames
                state.scene_status = "stable"
                state.scene_match_observations = 0
                state.scene_mismatch_observations = 0
                state.last_scene_match_ratio = 1.0
                state.last_scene_median_residual = 0.0
                state.last_geometry_check_at = 0.0
                state.last_geometry_status = "not_checked"
                state.last_geometry_reason = ""
                state.last_geometry_signature = None
                state.calibration_active = False
                state.calibration_reference = None
                state.calibration_average = None
                state.last_error = ""
            result = self._state_status(key, state)
        return result

    def reconstruct(
        self,
        cv2: Any,
        camera_id: int,
        frame: Any,
        person_mask: Any,
        *,
        clear_token: str = "",
        source_key: str = "",
    ) -> Any:
        height, width = frame.shape[:2]
        key, generation = self._state_key(camera_id, source_key, width, height)
        mask = self._binary_mask(cv2, person_mask, width, height)
        started = time.perf_counter()
        with self._lock:
            state = self._state(key, self._clock())
            self._activate_generation(state, generation)
            if state.calibration_active:
                raise PrivacyCalibrationRequired(camera_id, "calibration_in_progress")
            mask = self._protected_mask(cv2, state, mask)
            background = None if state.background is None else state.background.copy()
            baseline_revision = state.baseline_revision
            generation_validated = state.generation_validated
            scene_status = state.scene_status
            revalidation_token_seen = bool(
                clear_token
                and str(clear_token) == state.last_revalidation_token
            )

        if background is None:
            raise PrivacyCalibrationRequired(camera_id)

        if not generation_validated:
            if bool(cv2.countNonZero(mask)):
                raise PrivacyCalibrationRequired(
                    camera_id,
                    "scene_revalidation_required"
                    if scene_status == "scene_review_required"
                    else "stream_revalidation_required",
                )
            if revalidation_token_seen:
                raise PrivacyCalibrationRequired(
                    camera_id,
                    "scene_revalidation_required"
                    if scene_status == "scene_review_required"
                    else "stream_revalidation_required",
                )
            generation_ready, blocked_reason = self._revalidate_generation(
                key,
                baseline_revision,
                background,
                frame,
            )
            if not generation_ready:
                raise PrivacyCalibrationRequired(camera_id, blocked_reason)

        assessment = self._scene_assessment(
            key,
            baseline_revision,
            background,
            frame,
            excluded_mask=mask,
        )
        if not bool(cv2.countNonZero(mask)):
            if not assessment["accepted"]:
                self._mark_scene_review(key, baseline_revision, assessment)
                raise PrivacyCalibrationRequired(camera_id, "scene_revalidation_required")
            self._record_scene_match(key, baseline_revision, assessment)
            return frame.copy()

        if assessment["status"] != "insufficient_visible_area":
            if not assessment["accepted"]:
                self._mark_scene_review(key, baseline_revision, assessment)
                raise PrivacyCalibrationRequired(camera_id, "scene_revalidation_required")
            self._record_scene_match(key, baseline_revision, assessment)

        with self._lock:
            current = self._states.get(key)
            if (
                current is None
                or current.baseline_revision != baseline_revision
                or current.calibration_active
                or not current.generation_validated
            ):
                raise PrivacyCalibrationRequired(camera_id, "background_state_changed")

        expanded = self._expand_person_mask(cv2, frame, background, mask)
        output = frame.copy()
        output[expanded > 0] = background[expanded > 0]
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        with self._lock:
            current = self._states.get(key)
            if current is not None:
                current.person_frames += 1
                current.composites += 1
                current.latencies_ms.append(elapsed_ms)
                current.last_used = self._clock()
        return output

    def ready(
        self,
        camera_id: int,
        *,
        source_key: str,
        width: int,
        height: int,
    ) -> bool:
        key, generation = self._state_key(camera_id, source_key, width, height)
        with self._lock:
            state = self._state(key, self._clock())
            self._activate_generation(state, generation)
            return bool(state.calibrated and state.generation_validated and state.background is not None)

    def inspect(
        self,
        camera_id: int,
        *,
        source_key: str,
        width: int,
        height: int,
    ) -> dict[str, Any]:
        key, generation = self._state_key(camera_id, source_key, width, height)
        with self._lock:
            state = self._state(key, self._clock())
            self._activate_generation(state, generation)
            return self._state_status(key, state)

    def discover_persisted(
        self,
        camera_id: int,
        *,
        source_key: str,
    ) -> list[dict[str, Any]]:
        if self.storage_dir is None:
            return []
        discovery_key, generation = self._state_key(camera_id, source_key, 1, 1)
        configured_source = discovery_key[1]
        digest = sha256(configured_source.encode("utf-8")).hexdigest()[:16]
        filename_pattern = re.compile(
            rf"camera-{int(camera_id)}-{re.escape(digest)}-(\d+)x(\d+)\.npz"
        )
        dimensions: list[tuple[int, int]] = []
        for path in self.storage_dir.glob(f"camera-{int(camera_id)}-{digest}-*x*.npz"):
            match = filename_pattern.fullmatch(path.name)
            if match is None:
                continue
            width = int(match.group(1))
            height = int(match.group(2))
            if width > 0 and height > 0:
                dimensions.append((width, height))

        discovered: list[dict[str, Any]] = []
        now = self._clock()
        with self._lock:
            for width, height in sorted(set(dimensions)):
                key = (int(camera_id), configured_source, width, height)
                state = self._state(key, now)
                self._activate_generation(state, generation)
                if state.calibrated and state.background is not None:
                    discovered.append(self._state_status(key, state))
        return discovered

    def observe_revalidation(
        self,
        camera_id: int,
        frame: Any,
        *,
        frame_token: str,
        source_key: str,
        person_evidence: bool,
        evidence_synchronized: bool,
    ) -> dict[str, Any]:
        height, width = frame.shape[:2]
        key, generation = self._state_key(camera_id, source_key, width, height)
        token = str(frame_token or "")
        with self._lock:
            state = self._state(key, self._clock())
            self._activate_generation(state, generation)
            if token and token == state.last_revalidation_token:
                return self._state_status(key, state)
            state.last_revalidation_token = token
            if (
                not state.calibrated
                or state.background is None
                or state.calibration_active
                or state.generation_validated
            ):
                return self._state_status(key, state)
            if not evidence_synchronized:
                state.revalidation_observations = 0
                state.scene_status = "revalidation_required"
                state.last_error = "person_evidence_unavailable"
                return self._state_status(key, state)
            if person_evidence:
                state.revalidation_observations = 0
                state.scene_status = "revalidation_required"
                state.last_error = "person_present"
                return self._state_status(key, state)
            background = state.background.copy()
            baseline_revision = state.baseline_revision

        self._revalidate_generation(
            key,
            baseline_revision,
            background,
            frame,
        )
        with self._lock:
            state = self._states.get(key)
            if state is None:
                raise PrivacyCalibrationRequired(camera_id, "background_state_changed")
            return self._state_status(key, state)

    def require_baseline(
        self,
        camera_id: int,
        *,
        source_key: str,
        width: int,
        height: int,
    ) -> dict[str, Any]:
        """Reject missing baselines before segmentation while allowing stream revalidation."""
        key, generation = self._state_key(camera_id, source_key, width, height)
        with self._lock:
            state = self._state(key, self._clock())
            self._activate_generation(state, generation)
            if state.calibration_active:
                raise PrivacyCalibrationRequired(camera_id, "calibration_in_progress")
            if not state.calibrated or state.background is None:
                raise PrivacyCalibrationRequired(camera_id, "calibration_required")
            return self._state_status(key, state)

    def reset_camera(self, camera_id: int) -> None:
        camera_id = int(camera_id)
        with self._lock:
            for key in [item for item in self._states if item[0] == camera_id]:
                self._states.pop(key, None)

    def status(self) -> dict[str, Any]:
        with self._lock:
            state_items = list(self._states.items())
            states = [self._state_status(key, state) for key, state in state_items]
            memory_bytes = sum(
                int(state.background.nbytes) if state.background is not None else 0
                for _, state in state_items
            )
        return {
            "schema_version": self.version,
            "strategy": "explicit_empty_room_calibration",
            "retained_pixel_state": True,
            "automatic_background_learning": False,
            "neutral_fill": False,
            "confirmation_frames": self.confirmation_frames,
            "revalidation_frames": self.revalidation_frames,
            "foreground_threshold": self.foreground_threshold,
            "geometry_recheck_seconds": self.geometry_recheck_seconds,
            "state_count": len(states),
            "max_states": self.max_states,
            "memory_bytes": memory_bytes,
            "states": states,
            "cameras": states,
        }

    def _state_key(
        self,
        camera_id: int,
        source_key: str,
        width: int,
        height: int,
    ) -> tuple[tuple[int, str, int, int], str]:
        source = str(source_key or "unidentified-source")
        match = re.fullmatch(r"(.+):g(\d+)", source)
        configured_source = match.group(1) if match else source
        generation = match.group(2) if match else "0"
        return (
            (int(camera_id), configured_source, int(width), int(height)),
            generation,
        )

    def _state(self, key: tuple[int, str, int, int], now: float) -> _BackgroundState:
        state = self._states.get(key)
        if state is None:
            while len(self._states) >= self.max_states:
                self._states.popitem(last=False)
            state = _BackgroundState(last_used=now)
            persisted = self._load_persisted(key)
            if persisted is not None:
                state.background = persisted
                state.calibrated = True
                state.baseline_revision = 1
                state.baseline_sha256 = self._background_sha256(persisted)
                state.scene_status = "revalidation_required"
            self._states[key] = state
        state.last_used = now
        self._states.move_to_end(key)
        return state

    def _activate_generation(self, state: _BackgroundState, generation: str) -> None:
        if state.active_generation == generation:
            return
        state.active_generation = generation
        state.generation_validated = False
        state.revalidation_observations = 0
        state.last_revalidation_token = ""
        state.scene_status = "revalidation_required" if state.background is not None else "calibration_required"
        state.recent_person_mask = None
        state.recent_person_at = 0.0
        state.last_geometry_check_at = 0.0
        state.last_geometry_status = "not_checked"
        state.last_geometry_reason = ""
        state.last_geometry_signature = None

    def _protected_mask(self, cv2: Any, state: _BackgroundState, mask: Any) -> Any:
        now = self._clock()
        if bool(cv2.countNonZero(mask)):
            state.recent_person_mask = mask.copy()
            state.recent_person_at = now
            return mask
        if (
            state.recent_person_mask is not None
            and now - state.recent_person_at <= self.recent_mask_seconds
        ):
            return state.recent_person_mask.copy()
        state.recent_person_mask = None
        return mask

    def _revalidate_generation(
        self,
        key: tuple[int, str, int, int],
        baseline_revision: int,
        background: Any,
        frame: Any,
    ) -> tuple[bool, str]:
        assessment = self._scene_assessment(key, baseline_revision, background, frame)
        with self._lock:
            state = self._states.get(key)
            if state is None or state.baseline_revision != baseline_revision:
                return False, "background_state_changed"
            if assessment["accepted"]:
                state.revalidation_observations += 1
                state.scene_status = str(assessment["status"])
                state.last_error = ""
                self._store_scene_metrics(state, assessment)
                if state.revalidation_observations >= self.revalidation_frames:
                    state.generation_validated = True
            else:
                state.revalidation_observations = 0
                state.scene_status = "scene_review_required"
                state.last_error = "stream_revalidation_failed"
                self._store_scene_metrics(state, assessment)
            state.last_used = self._clock()
            self._states.move_to_end(key)
            if state.generation_validated:
                return True, ""
            return (
                False,
                "stream_revalidation_required"
                if assessment["accepted"]
                else "scene_revalidation_required",
            )

    def _mark_scene_review(
        self,
        key: tuple[int, str, int, int],
        baseline_revision: int,
        assessment: dict[str, Any],
    ) -> None:
        with self._lock:
            state = self._states.get(key)
            if state is None or state.baseline_revision != baseline_revision:
                return
            state.generation_validated = False
            state.revalidation_observations = 0
            state.scene_status = "scene_review_required"
            state.scene_mismatch_observations += 1
            state.scene_review_events += 1
            state.last_error = str(assessment.get("reason") or "scene_revalidation_required")
            self._store_scene_metrics(state, assessment)

    def _record_scene_match(
        self,
        key: tuple[int, str, int, int],
        baseline_revision: int,
        assessment: dict[str, Any],
    ) -> None:
        with self._lock:
            state = self._states.get(key)
            if state is None or state.baseline_revision != baseline_revision:
                return
            state.scene_status = str(assessment["status"])
            state.scene_match_observations += 1
            state.scene_mismatch_observations = 0
            state.last_error = ""
            self._store_scene_metrics(state, assessment)

    def _store_scene_metrics(self, state: _BackgroundState, assessment: dict[str, Any]) -> None:
        state.last_scene_match_ratio = assessment.get("match_ratio")
        state.last_scene_median_residual = assessment.get("median_residual")
        geometry_status = assessment.get("geometry_status")
        if geometry_status and geometry_status != "not_required":
            state.last_geometry_status = str(geometry_status)
            state.last_geometry_reason = str(assessment.get("geometry_reason") or "")
            state.last_geometry_good_matches = int(assessment.get("geometry_good_matches") or 0)
            state.last_geometry_inliers = int(assessment.get("geometry_inliers") or 0)
            state.last_geometry_inlier_ratio = assessment.get("geometry_inlier_ratio")
            state.last_geometry_median_corner_displacement_ratio = assessment.get(
                "geometry_median_corner_displacement_ratio"
            )
            state.last_geometry_max_corner_displacement_ratio = assessment.get(
                "geometry_max_corner_displacement_ratio"
            )

    def _calibration_frame_matches(self, reference: Any, frame: Any) -> bool:
        if reference.shape != frame.shape:
            return False
        delta = np.max(np.abs(frame.astype(np.int16) - reference.astype(np.int16)), axis=2)
        return bool(float(np.median(delta)) <= 6.0 and float(np.mean(delta <= 20.0)) >= 0.96)

    def _scene_assessment(
        self,
        key: tuple[int, str, int, int],
        baseline_revision: int,
        background: Any,
        frame: Any,
        excluded_mask: Any | None = None,
    ) -> dict[str, Any]:
        if background.shape != frame.shape:
            return {
                "accepted": False,
                "status": "scene_review_required",
                "reason": "resolution_changed",
                "match_ratio": 0.0,
                "median_residual": None,
            }
        height, width = frame.shape[:2]
        step = max(3, min(height, width) // 64)
        visible = np.ones(frame[::step, ::step].shape[:2], dtype=bool)
        if excluded_mask is not None:
            visible &= excluded_mask[::step, ::step] == 0
        if int(np.count_nonzero(visible)) < 256:
            return {
                "accepted": False,
                "status": "insufficient_visible_area",
                "reason": "insufficient_visible_area",
                "match_ratio": None,
                "median_residual": None,
            }
        current = frame[::step, ::step].astype(np.int16)[visible]
        retained = background[::step, ::step].astype(np.int16)[visible]
        color_shift = np.rint(np.median(current - retained, axis=0)).astype(np.int16)
        residual = np.max(np.abs((current - retained) - color_shift), axis=1)
        median_residual = float(np.median(residual))
        match_ratio = float(np.mean(residual <= 44.0))
        accepted = bool(median_residual <= 24.0 and match_ratio >= 0.68)
        status = "stable" if median_residual <= 12.0 and match_ratio >= 0.90 else "local_change"
        photometric = {
            "accepted": accepted,
            "status": status if accepted else "scene_review_required",
            "reason": "" if accepted else "scene_geometry_changed",
            "match_ratio": round(match_ratio, 4),
            "median_residual": round(median_residual, 3),
            "color_shift_bgr": [int(value) for value in color_shift],
            "geometry_status": "not_required" if accepted else "not_checked",
            "geometry_reason": "",
            "geometry_good_matches": 0,
            "geometry_inliers": 0,
            "geometry_inlier_ratio": None,
            "geometry_median_corner_displacement_ratio": None,
            "geometry_max_corner_displacement_ratio": None,
        }
        if accepted:
            return photometric
        geometry = self._geometry_assessment_cached(
            key,
            baseline_revision,
            background,
            frame,
            excluded_mask=excluded_mask,
        )
        geometry_accepted = bool(geometry.get("accepted"))
        return {
            **photometric,
            "accepted": geometry_accepted,
            "status": "local_change" if geometry_accepted else "scene_review_required",
            "reason": "" if geometry_accepted else str(geometry.get("geometry_reason") or "scene_geometry_changed"),
            **{name: value for name, value in geometry.items() if name != "accepted"},
        }

    def _geometry_assessment_cached(
        self,
        key: tuple[int, str, int, int],
        baseline_revision: int,
        background: Any,
        frame: Any,
        *,
        excluded_mask: Any | None,
    ) -> dict[str, Any]:
        now = self._clock()
        signature = self.geometry_verifier.signature(frame, excluded_mask=excluded_mask)
        with self._lock:
            state = self._states.get(key)
            if (
                state is not None
                and state.baseline_revision == baseline_revision
                and state.last_geometry_check_at > 0.0
                and now - state.last_geometry_check_at < self.geometry_recheck_seconds
                and self.geometry_verifier.signatures_match(state.last_geometry_signature, signature)
            ):
                return {
                    "accepted": state.last_geometry_status == "same_view",
                    "geometry_status": state.last_geometry_status,
                    "geometry_reason": state.last_geometry_reason,
                    "geometry_good_matches": state.last_geometry_good_matches,
                    "geometry_inliers": state.last_geometry_inliers,
                    "geometry_inlier_ratio": state.last_geometry_inlier_ratio,
                    "geometry_median_corner_displacement_ratio": state.last_geometry_median_corner_displacement_ratio,
                    "geometry_max_corner_displacement_ratio": state.last_geometry_max_corner_displacement_ratio,
                    "geometry_cached": True,
                }
        assessment = self.geometry_verifier.assess(background, frame, excluded_mask=excluded_mask)
        with self._lock:
            state = self._states.get(key)
            if state is not None and state.baseline_revision == baseline_revision:
                state.last_geometry_check_at = now
                state.last_geometry_status = str(assessment.get("geometry_status") or "unverifiable")
                state.last_geometry_reason = str(assessment.get("geometry_reason") or "")
                state.last_geometry_good_matches = int(assessment.get("geometry_good_matches") or 0)
                state.last_geometry_inliers = int(assessment.get("geometry_inliers") or 0)
                state.last_geometry_inlier_ratio = assessment.get("geometry_inlier_ratio")
                state.last_geometry_median_corner_displacement_ratio = assessment.get(
                    "geometry_median_corner_displacement_ratio"
                )
                state.last_geometry_max_corner_displacement_ratio = assessment.get(
                    "geometry_max_corner_displacement_ratio"
                )
                state.last_geometry_signature = signature
        return assessment

    def _expand_person_mask(self, cv2: Any, frame: Any, background: Any, mask: Any) -> Any:
        points = cv2.findNonZero(mask)
        if points is None:
            return mask
        x, y, box_width, box_height = cv2.boundingRect(points)
        radius = max(5, min(24, int(round(max(box_width, box_height) * 0.08))))
        x1 = max(0, x - radius)
        y1 = max(0, y - radius)
        x2 = min(frame.shape[1], x + box_width + radius)
        y2 = min(frame.shape[0], y + box_height + radius)
        local_mask = mask[y1:y2, x1:x2]
        halo = cv2.dilate(
            local_mask,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radius * 2 + 1, radius * 2 + 1)),
            iterations=1,
        )
        delta = cv2.absdiff(frame[y1:y2, x1:x2], background[y1:y2, x1:x2])
        foreground = np.where(
            np.max(delta, axis=2) >= self.foreground_threshold,
            255,
            0,
        ).astype(np.uint8)
        foreground = cv2.morphologyEx(
            foreground,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        )
        foreground = cv2.morphologyEx(
            foreground,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)),
        )
        expanded = mask.copy()
        expanded[y1:y2, x1:x2] = cv2.bitwise_or(
            local_mask,
            cv2.bitwise_and(foreground, halo),
        )
        return cv2.dilate(
            expanded,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
            iterations=1,
        )

    def _state_status(
        self,
        key: tuple[int, str, int, int],
        state: _BackgroundState,
    ) -> dict[str, Any]:
        return {
            "camera_id": key[0],
            "configured_source_key": key[1],
            "stream_generation": state.active_generation,
            "width": key[2],
            "height": key[3],
            "status": (
                "calibrating"
                if state.calibration_active
                else "ready"
                if state.calibrated and state.generation_validated
                else "scene_review_required"
                if state.calibrated and state.scene_status == "scene_review_required"
                else "revalidating"
                if state.calibrated
                else "calibration_required"
            ),
            "ready": bool(state.calibrated and state.generation_validated),
            "calibrated": bool(state.calibrated),
            "baseline_retained": state.background is not None,
            "baseline_revision": state.baseline_revision,
            "baseline_sha256": state.baseline_sha256,
            "scene_status": state.scene_status,
            "scene_match_observations": state.scene_match_observations,
            "scene_mismatch_observations": state.scene_mismatch_observations,
            "last_scene_match_ratio": state.last_scene_match_ratio,
            "last_scene_median_residual": state.last_scene_median_residual,
            "last_geometry_status": state.last_geometry_status,
            "last_geometry_reason": state.last_geometry_reason,
            "last_geometry_good_matches": state.last_geometry_good_matches,
            "last_geometry_inliers": state.last_geometry_inliers,
            "last_geometry_inlier_ratio": state.last_geometry_inlier_ratio,
            "last_geometry_median_corner_displacement_ratio": state.last_geometry_median_corner_displacement_ratio,
            "last_geometry_max_corner_displacement_ratio": state.last_geometry_max_corner_displacement_ratio,
            "last_geometry_check_age_ms": (
                round(max(0.0, self._clock() - state.last_geometry_check_at) * 1000.0, 1)
                if state.last_geometry_check_at > 0.0
                else None
            ),
            "calibration_active": bool(state.calibration_active),
            "calibration_id": state.calibration_id,
            "calibration_observations": state.calibration_observations,
            "calibration_required_frames": self.confirmation_frames,
            "calibration_rejections": state.calibration_rejections,
            "revalidation_observations": state.revalidation_observations,
            "revalidation_required_frames": self.revalidation_frames,
            "person_frames": state.person_frames,
            "scene_review_events": state.scene_review_events,
            "composites": state.composites,
            "last_error": state.last_error,
            "render_latency_ms_p50": round(self._percentile(list(state.latencies_ms), 0.50), 2),
            "render_latency_ms_p95": round(self._percentile(list(state.latencies_ms), 0.95), 2),
        }

    def _persisted_path(self, key: tuple[int, str, int, int]) -> Path | None:
        if self.storage_dir is None:
            return None
        digest = sha256(key[1].encode("utf-8")).hexdigest()[:16]
        return self.storage_dir / f"camera-{key[0]}-{digest}-{key[2]}x{key[3]}.npz"

    def _persist(self, key: tuple[int, str, int, int], background: Any) -> None:
        path = self._persisted_path(key)
        if path is None:
            return
        temporary = path.with_suffix(".tmp")
        try:
            with temporary.open("wb") as handle:
                np.savez_compressed(handle, background=np.asarray(background, dtype=np.uint8))
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def _load_persisted(self, key: tuple[int, str, int, int]) -> Any | None:
        path = self._persisted_path(key)
        if path is None or not path.exists():
            return None
        try:
            with np.load(path, allow_pickle=False) as values:
                background = np.asarray(values["background"], dtype=np.uint8)
            if background.shape != (key[3], key[2], 3):
                return None
            return background
        except (OSError, ValueError, KeyError):
            return None

    def _percentile(self, values: list[float], quantile: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * quantile))))
        return float(ordered[index])

    def _background_sha256(self, background: Any) -> str:
        return sha256(np.ascontiguousarray(background, dtype=np.uint8).tobytes()).hexdigest()

    def _binary_mask(self, cv2: Any, mask: Any, width: int, height: int) -> Any:
        array = np.asarray(mask, dtype=np.uint8)
        if array.shape != (height, width):
            array = cv2.resize(array, (width, height), interpolation=cv2.INTER_NEAREST)
        return np.where(array > 0, 255, 0).astype(np.uint8)
