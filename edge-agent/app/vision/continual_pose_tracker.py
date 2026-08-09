from __future__ import annotations

from collections import OrderedDict, deque
from copy import deepcopy
import math
from threading import RLock
import time
from typing import Any, Callable, Dict


class ContinualPoseTracker:
    """Propagate fresh pose anchors briefly without creating safety evidence."""

    version = "eacp-continual-pose-v3"
    display_context_keys = {
        "detector_backend",
        "model_status",
        "model_message",
        "model_name",
        "model_version",
        "pipeline_version",
        "pose_model_status",
        "pose_model_message",
        "pose_model_name",
        "pose_detection_source",
        "pose_external_box_count",
        "pose_skeleton_edges",
        "brightness",
        "contrast",
        "black_screen",
        "motion_score",
        "motion_detected",
        "thresholds",
        "pets",
        "pet_count",
        "pet_types",
        "scene_objects",
        "scene_zones",
        "normal_lying_zones",
        "scene_map_status",
        "screen_content_suppressed",
        "fall_candidate",
        "fall_score",
        "pose_fall_candidate",
        "pose_fall_score",
        "meal_candidate",
        "meal_score",
        "stillness_candidate",
        "stillness_score",
        "daze_candidate",
        "daze_score",
        "tags",
        "inference_runtime",
        "pose_factor_graph",
        "people",
    }

    def __init__(
        self,
        *,
        max_age_seconds: float = 0.6,
        max_display_age_seconds: float = 1.2,
        max_model_rebase_seconds: float = 0.2,
        minimum_interval_seconds: float = 0.02,
        tracking_scale: float = 0.5,
        min_tracked_points: int = 6,
        min_tracked_ratio: float = 0.45,
        max_forward_backward_error: float = 3.0,
        min_geometry_scale: float = 0.65,
        max_geometry_scale: float = 1.45,
        min_pose_points: int = 3,
        feature_count: int = 48,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        self.max_age_seconds = max(0.1, float(max_age_seconds))
        self.max_display_age_seconds = max(self.max_age_seconds, float(max_display_age_seconds))
        self.max_model_rebase_seconds = max(
            0.05,
            min(self.max_age_seconds, float(max_model_rebase_seconds)),
        )
        self.minimum_interval_seconds = max(0.02, float(minimum_interval_seconds))
        self.tracking_scale = max(0.35, min(1.0, float(tracking_scale)))
        self.min_tracked_points = max(3, int(min_tracked_points))
        self.min_tracked_ratio = max(0.2, min(1.0, float(min_tracked_ratio)))
        self.max_forward_backward_error = max(0.2, float(max_forward_backward_error))
        self.min_geometry_scale = max(0.1, float(min_geometry_scale))
        self.max_geometry_scale = max(self.min_geometry_scale, float(max_geometry_scale))
        self.min_pose_points = max(2, int(min_pose_points))
        self.feature_count = max(16, int(feature_count))
        self._clock = monotonic_clock or time.monotonic
        self._states: dict[int, Dict[str, Any]] = {}
        self._latest: dict[int, Dict[str, Any]] = {}
        self._latest_frames: dict[int, Any] = {}
        self._latest_contexts: dict[int, Dict[str, Any]] = {}
        self._metadata_history: dict[int, OrderedDict[str, Dict[str, Any]]] = {}
        self._metrics: dict[int, Dict[str, Any]] = {}
        self._model_updates: dict[int, deque[float]] = {}
        self._display_updates: dict[int, deque[float]] = {}
        self._last_display_samples: dict[int, tuple[float, str]] = {}
        self._camera_locks: dict[int, RLock] = {}
        self._lock = RLock()

    def observe(
        self,
        camera_id: int,
        frame: Any,
        *,
        frame_id: str,
        captured_at: str,
        captured_monotonic: float | None = None,
        poses: list[Dict[str, Any]],
        context: Dict[str, Any] | None = None,
        source_key: str = "",
        person_present: bool = False,
    ) -> Dict[str, Any]:
        cv2, np = self._vision_modules()
        camera_id = int(camera_id)
        now = float(self._clock())
        sample_at = self._source_sample_time(captured_monotonic, now)
        gray = self._gray(cv2, frame)
        tracked_poses = []
        for pose in poses:
            prepared = self._prepare_pose(cv2, np, gray, pose)
            if prepared is not None:
                tracked_poses.append(prepared)
        with self._camera_lock(camera_id):
            self._record_rate_sample(self._model_updates, camera_id, now)
            publish_display = self._display_frame_is_newer_locked(camera_id, sample_at, frame_id)
            if not publish_display and self._model_frame_is_current_display_locked(
                camera_id,
                frame_id=frame_id,
                source_key=source_key,
            ):
                publish_display = True
            if not publish_display:
                rebased = self._rebase_model_result_locked(
                    cv2,
                    np,
                    camera_id,
                    model_gray=gray,
                    model_frame_id=frame_id,
                    model_captured_at=captured_at,
                    model_sample_at=sample_at,
                    tracked_poses=tracked_poses,
                    context=context or {},
                    source_key=source_key,
                    person_present=person_present,
                    now=now,
                )
                if rebased is not None:
                    return deepcopy(rebased)
                metric = self._metric(camera_id)
                if tracked_poses:
                    metric["late_anchor_count"] += 1
                    reason = str(metric.get("last_reason") or "late_model_anchor")
                    return deepcopy(self._payload(
                        camera_id,
                        state="observed",
                        reason=reason,
                        frame_id=frame_id,
                        captured_at=captured_at,
                        captured_monotonic=sample_at,
                        age_seconds=max(0.0, now - sample_at),
                        poses=[self._public_observed_pose(item["pose"]) for item in tracked_poses],
                        quality={
                            "tracked_point_count": sum(len(item["points"]) for item in tracked_poses),
                            "forward_backward_error": 0.0,
                            "geometry_scale": 1.0,
                        },
                        source_key=source_key,
                        display_published=False,
                    ))
                metric["late_model_result_drop_count"] += 1
                metric["last_reason"] = str(metric.get("last_reason") or "late_model_result")
                return deepcopy(self._empty_payload(
                    camera_id,
                    "untracked" if bool(person_present or poses) else "empty",
                    metric["last_reason"],
                    frame_id,
                    captured_at,
                    captured_monotonic=sample_at,
                    source_key=source_key,
                    display_published=False,
                ))
            if not tracked_poses:
                self._states.pop(camera_id, None)
                confirmed_person = bool(person_present or poses)
                payload = self._empty_payload(
                    camera_id,
                    "untracked" if confirmed_person else "empty",
                    "person_without_trackable_pose" if confirmed_person else "no_observed_pose",
                    frame_id,
                    captured_at,
                    captured_monotonic=sample_at,
                    source_key=source_key,
                )
                self._latest[camera_id] = payload
                self._latest_frames[camera_id] = frame.copy()
                self._latest_contexts[camera_id] = self._display_context(context or {})
                self._record_display_sample(camera_id, sample_at, frame_id)
                metric = self._metric(camera_id)
                metric["untracked_count" if confirmed_person else "empty_count"] += 1
                metric["last_state"] = payload["state"]
                metric["last_frame_id"] = str(frame_id or "")
                metric["last_reason"] = payload["reason"]
                return deepcopy(payload)
            self._states[camera_id] = {
                "observed_monotonic": now,
                "last_updated_monotonic": now,
                "previous_gray": gray,
                "frame_id": str(frame_id or ""),
                "display_frame_id": str(
                    frame_id
                    if publish_display
                    else (self._latest.get(camera_id) or {}).get("frame_id") or ""
                ),
                "captured_at": str(captured_at or ""),
                "captured_monotonic": sample_at,
                "image_width": int(frame.shape[1]),
                "image_height": int(frame.shape[0]),
                "poses": tracked_poses,
                "context": self._display_context(context or {}),
                "source_key": str(source_key or ""),
            }
            payload = self._payload(
                camera_id,
                state="observed",
                frame_id=frame_id,
                captured_at=captured_at,
                captured_monotonic=sample_at,
                age_seconds=0.0,
                poses=[self._public_observed_pose(item["pose"]) for item in tracked_poses],
                quality={
                    "tracked_point_count": sum(len(item["points"]) for item in tracked_poses),
                    "forward_backward_error": 0.0,
                    "geometry_scale": 1.0,
                },
                source_key=source_key,
                display_published=publish_display,
            )
            self._latest[camera_id] = payload
            self._latest_frames[camera_id] = frame.copy()
            self._latest_contexts[camera_id] = self._display_context(context or {})
            self._record_display_sample(camera_id, sample_at, frame_id)
            metric = self._metric(camera_id)
            metric["observed_count"] += 1
            metric["last_state"] = "observed"
            metric["last_frame_id"] = str(frame_id or "")
            metric["last_reason"] = ""
            return deepcopy(payload)

    def _rebase_model_result_locked(
        self,
        cv2: Any,
        np: Any,
        camera_id: int,
        *,
        model_gray: Any,
        model_frame_id: str,
        model_captured_at: str,
        model_sample_at: float,
        tracked_poses: list[Dict[str, Any]],
        context: Dict[str, Any],
        source_key: str,
        person_present: bool,
        now: float,
    ) -> Dict[str, Any] | None:
        latest = self._latest.get(camera_id)
        current_frame = self._latest_frames.get(camera_id)
        if latest is None or current_frame is None:
            return None
        current_frame_id = str(latest.get("frame_id") or "")
        current_captured_at = str(latest.get("captured_at") or "")
        current_source_key = str(latest.get("source_key") or "")
        if not current_frame_id:
            return None
        if source_key and current_source_key and str(source_key) != current_source_key:
            metric = self._metric(camera_id)
            metric["late_model_source_rejection_count"] += 1
            metric["last_reason"] = "late_model_source_changed"
            return None
        try:
            current_sample_at = float(latest.get("captured_monotonic"))
        except (TypeError, ValueError):
            return None
        lag_seconds = current_sample_at - float(model_sample_at)
        if lag_seconds <= 1e-6:
            return None
        if lag_seconds > self.max_model_rebase_seconds:
            metric = self._metric(camera_id)
            metric["late_model_expired_count"] += 1
            metric["last_reason"] = "late_model_expired"
            return None

        resolved_source_key = current_source_key or str(source_key or "")
        display_context = self._display_context(context)
        if not tracked_poses:
            self._states.pop(camera_id, None)
            confirmed_person = bool(person_present)
            payload = self._empty_payload(
                camera_id,
                "untracked" if confirmed_person else "empty",
                "person_without_trackable_pose" if confirmed_person else "no_observed_pose",
                current_frame_id,
                current_captured_at,
                captured_monotonic=current_sample_at,
                source_key=resolved_source_key,
            )
            payload["model_frame_id"] = str(model_frame_id or "")
            payload["model_result_lag_seconds"] = round(lag_seconds, 4)
            self._latest[camera_id] = payload
            self._latest_contexts[camera_id] = display_context
            self._store_metadata_history_locked(camera_id, current_frame_id)
            metric = self._metric(camera_id)
            metric["late_untracked_applied_count" if confirmed_person else "late_empty_applied_count"] += 1
            metric["last_state"] = payload["state"]
            metric["last_frame_id"] = current_frame_id
            metric["last_reason"] = payload["reason"]
            return payload

        current_gray = self._gray(cv2, current_frame)
        next_poses = []
        public_poses = []
        tracked_points = 0
        errors = []
        scales = []
        inlier_ratios = []
        rejection_reasons = []
        for item in tracked_poses:
            result = self._track_pose(
                cv2,
                np,
                model_gray,
                current_gray,
                item,
                current_frame,
                max(self.minimum_interval_seconds, lag_seconds),
                lag_seconds,
            )
            if not result.get("ok"):
                rejection_reasons.append(str(result.get("reason") or "optical_flow_failed"))
                continue
            pose = result["pose"]
            pose["tracking_state"] = "tracked"
            pose["tracking_source"] = "model_anchor_rebased"
            pose["track_age_seconds"] = round(lag_seconds, 4)
            result["state"]["pose"] = pose
            next_poses.append(result["state"])
            public_poses.append(pose)
            tracked_points += int(result["tracked_point_count"])
            errors.append(float(result["forward_backward_error"]))
            scales.append(float(result["geometry_scale"]))
            inlier_ratios.append(float(result.get("affine_inlier_ratio") or 0.0))
        if not next_poses:
            metric = self._metric(camera_id)
            metric["late_anchor_rebase_rejection_count"] += 1
            metric["last_reason"] = rejection_reasons[0] if rejection_reasons else "late_anchor_rebase_failed"
            return None

        self._states[camera_id] = {
            "observed_monotonic": float(model_sample_at),
            "last_updated_monotonic": float(now),
            "previous_gray": current_gray,
            "frame_id": current_frame_id,
            "display_frame_id": current_frame_id,
            "captured_at": current_captured_at,
            "captured_monotonic": current_sample_at,
            "image_width": int(current_frame.shape[1]),
            "image_height": int(current_frame.shape[0]),
            "poses": next_poses,
            "context": display_context,
            "source_key": resolved_source_key,
        }
        payload = self._payload(
            camera_id,
            state="tracked",
            reason="late_anchor_rebased",
            frame_id=current_frame_id,
            captured_at=current_captured_at,
            captured_monotonic=current_sample_at,
            age_seconds=lag_seconds,
            poses=public_poses,
            quality={
                "tracked_point_count": tracked_points,
                "forward_backward_error": round(max(errors, default=0.0), 4),
                "geometry_scale": round(sum(scales) / max(1, len(scales)), 4),
                "affine_inlier_ratio": round(sum(inlier_ratios) / max(1, len(inlier_ratios)), 4),
            },
            source_key=resolved_source_key,
        )
        payload["model_frame_id"] = str(model_frame_id or "")
        payload["model_captured_at"] = str(model_captured_at or "")
        payload["model_result_lag_seconds"] = round(lag_seconds, 4)
        self._latest[camera_id] = payload
        self._latest_contexts[camera_id] = display_context
        self._store_metadata_history_locked(camera_id, current_frame_id)
        metric = self._metric(camera_id)
        metric["late_anchor_rebased_count"] += 1
        metric["last_state"] = "tracked"
        metric["last_frame_id"] = current_frame_id
        metric["last_reason"] = "late_anchor_rebased"
        metric["last_quality"] = dict(payload["quality"])
        return payload

    def update_frame(
        self,
        camera_id: int,
        frame: Any,
        *,
        frame_id: str,
        captured_at: str,
        captured_monotonic: float | None = None,
        source_key: str = "",
    ) -> Dict[str, Any]:
        cv2, np = self._vision_modules()
        camera_id = int(camera_id)
        now = float(self._clock())
        sample_at = self._source_sample_time(captured_monotonic, now)
        gray = self._gray(cv2, frame)
        with self._camera_lock(camera_id):
            if not self._display_frame_is_newer_locked(camera_id, sample_at, frame_id):
                metric = self._metric(camera_id)
                metric["late_frame_drop_count"] += 1
                metric["last_reason"] = "late_stream_frame"
                return deepcopy(self._latest.get(camera_id) or self._empty_payload(
                    camera_id,
                    "empty",
                    "late_stream_frame",
                    frame_id,
                    captured_at,
                    captured_monotonic=sample_at,
                    source_key=source_key,
                    display_published=False,
                ))
            state = self._states.get(camera_id)
            if state is None:
                payload = self._empty_payload(
                    camera_id,
                    "empty",
                    "no_anchor",
                    frame_id,
                    captured_at,
                    captured_monotonic=sample_at,
                    source_key=source_key,
                )
                self._latest[camera_id] = payload
                self._latest_frames[camera_id] = frame.copy()
                self._record_display_sample(camera_id, sample_at, frame_id)
                metric = self._metric(camera_id)
                metric["last_state"] = "empty"
                metric["last_frame_id"] = str(frame_id or "")
                metric["last_reason"] = "no_anchor"
                return deepcopy(payload)
            active_source_key = str(state.get("source_key") or "")
            if source_key and active_source_key and str(source_key) != active_source_key:
                self._states.pop(camera_id, None)
                self._latest_frames.pop(camera_id, None)
                self._latest_contexts.pop(camera_id, None)
                payload = self._empty_payload(
                    camera_id,
                    "expired",
                    "source_changed",
                    frame_id,
                    captured_at,
                    captured_monotonic=sample_at,
                    source_key=source_key,
                )
                self._latest[camera_id] = payload
                return deepcopy(payload)
            if str(frame_id or "") and str(frame_id) == str(state.get("frame_id") or ""):
                return deepcopy(self._latest.get(camera_id) or self._empty_payload(
                    camera_id, "empty", "same_frame", frame_id, captured_at
                ))
            anchor_age = max(0.0, now - float(state["observed_monotonic"]))
            if anchor_age > self.max_display_age_seconds:
                return self._expire_locked(
                    camera_id,
                    "anchor_expired",
                    frame_id,
                    captured_at,
                    anchor_age,
                    captured_monotonic=sample_at,
                )
            if now - float(state.get("last_updated_monotonic") or 0.0) < self.minimum_interval_seconds:
                return deepcopy(self._latest.get(camera_id) or self._empty_payload(
                    camera_id, "empty", "tracking_throttled", frame_id, captured_at
                ))

            next_poses = []
            public_poses = []
            tracked_points = 0
            errors = []
            scales = []
            inlier_ratios = []
            rejection_reasons = []
            risk_tracks = []
            track_age = max(0.0, now - float(state.get("last_updated_monotonic") or 0.0))
            for item in state["poses"]:
                result = self._track_pose(
                    cv2,
                    np,
                    state["previous_gray"],
                    gray,
                    item,
                    frame,
                    track_age,
                    anchor_age,
                )
                if not result.get("ok"):
                    rejection_reasons.append(str(result.get("reason") or "optical_flow_failed"))
                    continue
                next_poses.append(result["state"])
                public_poses.append(result["pose"])
                tracked_points += int(result["tracked_point_count"])
                errors.append(float(result["forward_backward_error"]))
                scales.append(float(result["geometry_scale"]))
                inlier_ratios.append(float(result.get("affine_inlier_ratio") or 0.0))
                if result.get("rapid_downward_motion"):
                    risk_tracks.append({
                        "track_id": str(result["pose"].get("track_id") or ""),
                        "downward_displacement_ratio": round(float(result.get("downward_displacement_ratio") or 0.0), 4),
                        "downward_velocity_ratio_per_second": round(float(result.get("downward_velocity_ratio_per_second") or 0.0), 4),
                        "cumulative_downward_ratio": round(float(result.get("cumulative_downward_ratio") or 0.0), 4),
                    })

            if not next_poses:
                reason = rejection_reasons[0] if rejection_reasons else "optical_flow_failed"
                return self._coast_locked(
                    camera_id,
                    reason,
                    frame,
                    frame_id,
                    captured_at,
                    anchor_age,
                    track_age,
                    sample_at,
                )

            state["previous_gray"] = gray
            state["last_updated_monotonic"] = now
            state["frame_id"] = str(frame_id or "")
            state["display_frame_id"] = str(frame_id or "")
            state["captured_at"] = str(captured_at or "")
            state["captured_monotonic"] = sample_at
            state["image_width"] = int(frame.shape[1])
            state["image_height"] = int(frame.shape[0])
            state["poses"] = next_poses
            state["source_key"] = str(source_key or active_source_key)
            payload = self._payload(
                camera_id,
                state="tracked",
                frame_id=frame_id,
                captured_at=captured_at,
                captured_monotonic=sample_at,
                age_seconds=anchor_age,
                poses=public_poses,
                quality={
                    "tracked_point_count": tracked_points,
                    "forward_backward_error": round(max(errors, default=0.0), 4),
                    "geometry_scale": round(sum(scales) / max(1, len(scales)), 4),
                    "affine_inlier_ratio": round(sum(inlier_ratios) / max(1, len(inlier_ratios)), 4),
                },
                risk_hint={
                    "detected": bool(risk_tracks),
                    "reason": "rapid_downward_pose_motion" if risk_tracks else "",
                    "tracks": risk_tracks,
                    "formal_evidence_eligible": False,
                },
                display_only_stale=anchor_age > self.max_age_seconds,
                source_key=str(source_key or active_source_key),
            )
            self._latest[camera_id] = payload
            self._latest_frames[camera_id] = frame.copy()
            self._record_display_sample(camera_id, sample_at, frame_id)
            metric = self._metric(camera_id)
            metric["tracked_count"] += 1
            metric["last_state"] = "tracked"
            metric["last_frame_id"] = str(frame_id or "")
            metric["last_reason"] = ""
            metric["last_quality"] = dict(payload["quality"])
            if risk_tracks:
                metric["risk_hint_count"] += 1
                metric["last_risk_hint_at_monotonic"] = round(now, 6)
                metric["last_risk_hint"] = deepcopy(payload["risk_hint"])
            return deepcopy(payload)

    def latest(self, camera_id: int) -> Dict[str, Any]:
        camera_id = int(camera_id)
        with self._camera_lock(camera_id):
            payload = self._latest.get(camera_id)
            return deepcopy(payload) if payload is not None else self._empty_payload(
                camera_id, "empty", "no_anchor", "", ""
            )

    def latest_frame(self, camera_id: int) -> Dict[str, Any] | None:
        """Return pixels and pose data from the exact same tracked frame."""
        camera_id = int(camera_id)
        if not self.has_anchor(camera_id):
            return None
        with self._camera_lock(camera_id):
            payload = self._latest.get(camera_id)
            frame = self._latest_frames.get(camera_id)
            state = self._states.get(camera_id)
            if (
                payload is None
                or frame is None
                or state is None
                or payload.get("state") not in {"observed", "tracked", "coasting"}
                or str(payload.get("frame_id") or "") != str(state.get("display_frame_id") or "")
            ):
                return None
            return {
                "frame": frame.copy(),
                "tracking": deepcopy(payload),
                "analysis_context": deepcopy(state.get("context") or {}),
                "source_key": str(state.get("source_key") or payload.get("source_key") or ""),
            }

    def latest_synchronized_frame(self, camera_id: int) -> Dict[str, Any] | None:
        """Return one privacy-safe frame whose pixels and model/tracking data match."""
        camera_id = int(camera_id)
        self.has_anchor(camera_id)
        with self._camera_lock(camera_id):
            payload = self._latest.get(camera_id)
            frame = self._latest_frames.get(camera_id)
            if payload is None or frame is None:
                return None
            state = str(payload.get("state") or "")
            if state in {"observed", "tracked", "coasting"}:
                active = self._states.get(camera_id)
                if active is None or str(payload.get("frame_id") or "") != str(active.get("display_frame_id") or ""):
                    return None
                context = active.get("context") or {}
            elif state in {"empty", "untracked"} and str(payload.get("reason") or "") in {
                "no_observed_pose",
                "person_without_trackable_pose",
                "no_anchor",
            }:
                context = self._latest_contexts.get(camera_id) or {}
            else:
                return None
            return {
                "frame": frame.copy(),
                "tracking": deepcopy(payload),
                "analysis_context": deepcopy(context),
                "source_key": str(payload.get("source_key") or ""),
            }

    def latest_metadata(self, camera_id: int) -> Dict[str, Any]:
        """Return display metadata without copying or encoding frame pixels."""
        camera_id = int(camera_id)
        self.has_anchor(camera_id)
        with self._camera_lock(camera_id):
            state = self._states.get(camera_id) or {}
            payload = self._latest.get(camera_id)
            frame = self._latest_frames.get(camera_id)
            tracking = deepcopy(payload) if payload is not None else self._empty_payload(
                camera_id, "empty", "no_anchor", "", ""
            )
            context = state.get("context") or self._latest_contexts.get(camera_id) or {}
            frame_height, frame_width = frame.shape[:2] if frame is not None else (0, 0)
            return {
                "tracking": tracking,
                "analysis_context": deepcopy(context),
                "image_width": int(state.get("image_width") or frame_width),
                "image_height": int(state.get("image_height") or frame_height),
                "source_key": str(tracking.get("source_key") or state.get("source_key") or ""),
            }

    def metadata_for_frame(
        self,
        camera_id: int,
        *,
        frame_id: str,
        source_key: str = "",
    ) -> Dict[str, Any] | None:
        camera_id = int(camera_id)
        frame_id = str(frame_id or "")
        if not frame_id:
            return None
        with self._camera_lock(camera_id):
            item = (self._metadata_history.get(camera_id) or {}).get(frame_id)
            if item is None:
                return None
            recorded_source = str(item.get("source_key") or "")
            if source_key and recorded_source != str(source_key):
                return None
            return deepcopy(item)

    def has_anchor(self, camera_id: int) -> bool:
        camera_id = int(camera_id)
        with self._camera_lock(camera_id):
            state = self._states.get(camera_id)
            if state is None:
                return False
            age = max(0.0, float(self._clock()) - float(state["observed_monotonic"]))
            if age > self.max_display_age_seconds:
                self._expire_locked(
                    camera_id,
                    "anchor_expired",
                    str(state.get("frame_id") or ""),
                    str(state.get("captured_at") or ""),
                    age,
                )
                return False
            return True

    def status(self, camera_ids: list[int] | None = None) -> Dict[str, Any]:
        with self._lock:
            ids = sorted(
                {int(camera_id) for camera_id in camera_ids}
                if camera_ids is not None
                else set(self._metrics) | set(self._latest)
            )
        now = float(self._clock())
        cameras = []
        for camera_id in ids:
            with self._camera_lock(camera_id):
                latest = self._latest.get(camera_id) or {}
                cameras.append({
                    "camera_id": camera_id,
                    **deepcopy(self._metric(camera_id)),
                    "state": str(latest.get("state") or "empty"),
                    "age_seconds": latest.get("age_seconds"),
                    "pose_count": int(latest.get("pose_count") or 0),
                    "model_anchor_fps": self._rate(self._model_updates.get(camera_id), now),
                    "display_output_fps": self._rate(self._display_updates.get(camera_id), now),
                    "display_frame_age_ms": self._frame_age_ms(self._display_updates.get(camera_id), now),
                })
        return {
            "schema_version": self.version,
            "max_age_seconds": self.max_age_seconds,
            "max_display_age_seconds": self.max_display_age_seconds,
            "max_model_rebase_seconds": self.max_model_rebase_seconds,
            "minimum_interval_seconds": self.minimum_interval_seconds,
            "tracking_scale": self.tracking_scale,
            "cameras": cameras,
        }

    def reset_camera(self, camera_id: int) -> None:
        camera_id = int(camera_id)
        with self._camera_lock(camera_id):
            self._states.pop(camera_id, None)
            self._latest.pop(camera_id, None)
            self._latest_frames.pop(camera_id, None)
            self._latest_contexts.pop(camera_id, None)
            self._metadata_history.pop(camera_id, None)
            self._metrics.pop(camera_id, None)
            self._model_updates.pop(camera_id, None)
            self._display_updates.pop(camera_id, None)
            self._last_display_samples.pop(camera_id, None)

    def _camera_lock(self, camera_id: int) -> RLock:
        camera_id = int(camera_id)
        with self._lock:
            return self._camera_locks.setdefault(camera_id, RLock())

    def _prepare_pose(self, cv2: Any, np: Any, gray: Any, pose: Dict[str, Any]) -> Dict[str, Any] | None:
        keypoints = list(pose.get("keypoints") or [])
        indices = [
            index
            for index, point in enumerate(keypoints)
            if point.get("visible")
            and float(point.get("confidence") or 0.0) >= 0.2
            and self._finite(point.get("x"))
            and self._finite(point.get("y"))
        ]
        if len(indices) < self.min_pose_points:
            return None
        points = self._person_features(cv2, np, gray, pose)
        if points is None or len(points) < self.min_tracked_points:
            return None
        return {
            "pose": deepcopy(pose),
            "points": points,
            "anchor_center_y": self._bbox_center_y(pose.get("bbox")),
        }

    def _person_features(self, cv2: Any, np: Any, gray: Any, pose: Dict[str, Any]) -> Any | None:
        bbox = pose.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return None
        try:
            x1, y1, x2, y2 = [float(value) * self.tracking_scale for value in bbox]
        except (TypeError, ValueError):
            return None
        height, width = gray.shape[:2]
        x1 = max(0, min(width - 1, int(math.floor(x1))))
        y1 = max(0, min(height - 1, int(math.floor(y1))))
        x2 = max(x1 + 1, min(width, int(math.ceil(x2))))
        y2 = max(y1 + 1, min(height, int(math.ceil(y2))))
        if x2 - x1 < 8 or y2 - y1 < 12:
            return None
        mask = np.zeros(gray.shape, dtype=np.uint8)
        mask[y1:y2, x1:x2] = 255
        pose_points = [
            [
                float(point["x"]) * self.tracking_scale,
                float(point["y"]) * self.tracking_scale,
            ]
            for point in pose.get("keypoints") or []
            if isinstance(point, dict)
            and point.get("visible")
            and self._finite(point.get("x"))
            and self._finite(point.get("y"))
        ]
        if len(pose_points) >= 3:
            silhouette = np.zeros_like(mask)
            hull = cv2.convexHull(np.asarray(pose_points, dtype=np.float32).reshape(-1, 1, 2))
            cv2.fillConvexPoly(silhouette, np.rint(hull).astype(np.int32), 255)
            margin = max(3, int(round(min(x2 - x1, y2 - y1) * 0.12)))
            kernel = np.ones((margin * 2 + 1, margin * 2 + 1), dtype=np.uint8)
            silhouette = cv2.dilate(silhouette, kernel, iterations=1)
            mask = cv2.bitwise_and(mask, silhouette)
        return cv2.goodFeaturesToTrack(
            gray,
            maxCorners=self.feature_count,
            qualityLevel=0.008,
            minDistance=4,
            mask=mask,
            blockSize=7,
            useHarrisDetector=False,
        )

    def _track_pose(
        self,
        cv2: Any,
        np: Any,
        previous_gray: Any,
        gray: Any,
        item: Dict[str, Any],
        frame: Any,
        age_seconds: float,
        anchor_age_seconds: float,
    ) -> Dict[str, Any]:
        previous_points = item["points"]
        next_points, forward_status, _ = cv2.calcOpticalFlowPyrLK(
            previous_gray,
            gray,
            previous_points,
            None,
            winSize=(21, 21),
            maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.01),
        )
        if next_points is None or forward_status is None:
            return {"ok": False, "reason": "optical_flow_failed"}
        back_points, backward_status, _ = cv2.calcOpticalFlowPyrLK(
            gray,
            previous_gray,
            next_points,
            None,
            winSize=(21, 21),
            maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.01),
        )
        if back_points is None or backward_status is None:
            return {"ok": False, "reason": "optical_flow_failed"}

        forward_ok = forward_status.reshape(-1).astype(bool)
        backward_ok = backward_status.reshape(-1).astype(bool)
        fb_error = np.linalg.norm(previous_points.reshape(-1, 2) - back_points.reshape(-1, 2), axis=1)
        finite = np.isfinite(next_points.reshape(-1, 2)).all(axis=1) & np.isfinite(fb_error)
        valid = forward_ok & backward_ok & finite & (fb_error <= self.max_forward_backward_error)
        valid_count = int(valid.sum())
        required = max(self.min_tracked_points, int(math.ceil(len(previous_points) * self.min_tracked_ratio)))
        if valid_count < required:
            reason = "forward_backward_error" if int((forward_ok & backward_ok).sum()) >= required else "insufficient_points"
            return {"ok": False, "reason": reason}

        old_valid = previous_points.reshape(-1, 2)[valid]
        new_valid = next_points.reshape(-1, 2)[valid]
        transform, inliers = cv2.estimateAffinePartial2D(
            old_valid,
            new_valid,
            method=cv2.RANSAC,
            ransacReprojThreshold=2.5,
            maxIters=200,
            confidence=0.99,
            refineIters=10,
        )
        if transform is None:
            return {"ok": False, "reason": "affine_estimation_failed"}
        inlier_mask = (
            inliers.reshape(-1).astype(bool)
            if inliers is not None and len(inliers) == len(old_valid)
            else np.ones(len(old_valid), dtype=bool)
        )
        inlier_count = int(inlier_mask.sum())
        if inlier_count < self.min_tracked_points:
            return {"ok": False, "reason": "insufficient_affine_inliers"}
        scale = float(math.hypot(float(transform[0, 0]), float(transform[0, 1])))
        if scale < self.min_geometry_scale or scale > self.max_geometry_scale:
            return {"ok": False, "reason": "geometry_drift"}

        pose = deepcopy(item["pose"])
        keypoints = list(pose.get("keypoints") or [])
        decay = max(0.0, math.exp(-age_seconds / self.max_age_seconds))
        for index, value in enumerate(keypoints):
            point = dict(value)
            if not self._finite(point.get("x")) or not self._finite(point.get("y")):
                point.update({"visible": False, "confidence": 0.0})
                keypoints[index] = point
                continue
            transformed = self._transform_point(
                np,
                transform,
                float(point["x"]),
                float(point["y"]),
            )
            point.update({
                "x": round(transformed[0], 2),
                "y": round(transformed[1], 2),
                "confidence": round(float(point.get("confidence") or 0.0) * decay, 4),
                "visible": bool(point.get("visible")),
            })
            keypoints[index] = point

        previous_center_y = self._bbox_center_y(pose.get("bbox"))
        pose["bbox"] = self._transform_bbox(np, transform, pose.get("bbox"), frame)
        current_center_y = self._bbox_center_y(pose.get("bbox"))
        displacement_y = current_center_y - previous_center_y
        frame_height = max(1.0, float(frame.shape[0]))
        downward_displacement_ratio = max(0.0, displacement_y / frame_height)
        downward_velocity_ratio = downward_displacement_ratio / max(0.02, float(age_seconds))
        anchor_center_y = float(item.get("anchor_center_y") or current_center_y)
        cumulative_downward_ratio = max(0.0, (current_center_y - anchor_center_y) / frame_height)
        rapid_downward_motion = bool(
            (
                downward_displacement_ratio >= 0.03
                and downward_velocity_ratio >= 0.25
            )
            or (
                cumulative_downward_ratio >= 0.08
                and anchor_age_seconds <= self.max_age_seconds
            )
        )
        pose["keypoints"] = keypoints
        pose["confidence"] = round(float(pose.get("confidence") or 0.0) * decay, 4)
        pose["tracking_state"] = "tracked"
        pose["tracking_source"] = "klt"
        pose["track_age_seconds"] = round(age_seconds, 4)
        pose["fall_score"] = 0.0
        pose["pose_fall_candidate"] = False
        pose["fall_evidence_eligible"] = False
        pose["person_evidence_eligible"] = False
        pose["tracking_motion"] = {
            "downward_displacement_ratio": round(downward_displacement_ratio, 4),
            "downward_velocity_ratio_per_second": round(downward_velocity_ratio, 4),
            "cumulative_downward_ratio": round(cumulative_downward_ratio, 4),
            "risk_hint": rapid_downward_motion,
            "formal_evidence_eligible": False,
        }
        pose["action_hints"] = [hint for hint in pose.get("action_hints") or [] if hint != "fall_candidate"]
        refreshed_points = self._person_features(cv2, np, gray, pose)
        next_tracking_points = (
            refreshed_points
            if refreshed_points is not None and len(refreshed_points) >= self.min_tracked_points
            else new_valid[inlier_mask].astype(np.float32).reshape(-1, 1, 2)
        )
        return {
            "ok": True,
            "pose": pose,
            "state": {
                "pose": pose,
                "points": next_tracking_points,
                "anchor_center_y": anchor_center_y,
            },
            "tracked_point_count": inlier_count,
            "forward_backward_error": float(fb_error[valid].max()),
            "geometry_scale": float(scale),
            "affine_inlier_ratio": inlier_count / max(1, valid_count),
            "downward_displacement_ratio": downward_displacement_ratio,
            "downward_velocity_ratio_per_second": downward_velocity_ratio,
            "cumulative_downward_ratio": cumulative_downward_ratio,
            "rapid_downward_motion": rapid_downward_motion,
        }

    def _bbox_center_y(self, bbox: Any) -> float:
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return 0.0
        try:
            return (float(bbox[1]) + float(bbox[3])) / 2.0
        except (TypeError, ValueError):
            return 0.0

    def _transform_bbox(self, np: Any, transform: Any, bbox: Any, frame: Any) -> list[float]:
        height, width = frame.shape[:2]
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return []
        x1, y1, x2, y2 = [float(value) for value in bbox]
        corners = [
            self._transform_point(np, transform, x1, y1),
            self._transform_point(np, transform, x2, y1),
            self._transform_point(np, transform, x1, y2),
            self._transform_point(np, transform, x2, y2),
        ]
        xs = [point[0] for point in corners]
        ys = [point[1] for point in corners]
        return [
            round(max(0.0, min(float(width - 1), min(xs))), 1),
            round(max(0.0, min(float(height - 1), min(ys))), 1),
            round(max(1.0, min(float(width), max(xs))), 1),
            round(max(1.0, min(float(height), max(ys))), 1),
        ]

    def _transform_point(
        self,
        np: Any,
        transform: Any,
        x: float,
        y: float,
    ) -> tuple[float, float]:
        scaled = np.asarray([x * self.tracking_scale, y * self.tracking_scale, 1.0], dtype=np.float64)
        output = transform @ scaled
        return (float(output[0] / self.tracking_scale), float(output[1] / self.tracking_scale))

    def _public_observed_pose(self, pose: Dict[str, Any]) -> Dict[str, Any]:
        item = deepcopy(pose)
        item["tracking_state"] = "observed"
        item["tracking_source"] = "model_anchor"
        item["track_age_seconds"] = 0.0
        return item

    def _public_coasting_pose(self, pose: Dict[str, Any], coast_age_seconds: float) -> Dict[str, Any]:
        item = deepcopy(pose)
        item["tracking_state"] = "coasting"
        item["tracking_source"] = "last_good_overlay"
        item["coast_age_seconds"] = round(float(coast_age_seconds), 4)
        item["fall_score"] = 0.0
        item["pose_fall_candidate"] = False
        item["fall_evidence_eligible"] = False
        item["person_evidence_eligible"] = False
        item["action_hints"] = [hint for hint in item.get("action_hints") or [] if hint != "fall_candidate"]
        return item

    def _coast_locked(
        self,
        camera_id: int,
        reason: str,
        frame: Any,
        frame_id: str,
        captured_at: str,
        anchor_age_seconds: float,
        coast_age_seconds: float,
        captured_monotonic: float,
    ) -> Dict[str, Any]:
        state = self._states.get(camera_id)
        if state is None or anchor_age_seconds > self.max_display_age_seconds:
            return self._expire_locked(
                camera_id,
                "anchor_expired" if anchor_age_seconds > self.max_display_age_seconds else reason,
                frame_id,
                captured_at,
                anchor_age_seconds,
                captured_monotonic=captured_monotonic,
            )
        poses = [self._public_coasting_pose(item["pose"], coast_age_seconds) for item in state["poses"]]
        previous_quality = dict((self._latest.get(camera_id) or {}).get("quality") or {})
        previous_quality["failure_reason"] = str(reason or "optical_flow_failed")
        previous_quality["coast_age_seconds"] = round(float(coast_age_seconds), 4)
        payload = self._payload(
            camera_id,
            state="coasting",
            reason=reason,
            frame_id=frame_id,
            captured_at=captured_at,
            captured_monotonic=captured_monotonic,
            age_seconds=anchor_age_seconds,
            poses=poses,
            quality=previous_quality,
            display_only_stale=True,
            source_key=str(state.get("source_key") or ""),
        )
        state["display_frame_id"] = str(frame_id or "")
        state["captured_monotonic"] = captured_monotonic
        self._latest[camera_id] = payload
        self._latest_frames[camera_id] = frame.copy()
        self._record_display_sample(camera_id, captured_monotonic, frame_id)
        metric = self._metric(camera_id)
        metric["coasting_count"] += 1
        metric["last_state"] = "coasting"
        metric["last_frame_id"] = str(frame_id or "")
        metric["last_reason"] = str(reason or "")
        metric["last_quality"] = dict(payload["quality"])
        return deepcopy(payload)

    def _expire_locked(
        self,
        camera_id: int,
        reason: str,
        frame_id: str,
        captured_at: str,
        age_seconds: float,
        *,
        captured_monotonic: float | None = None,
    ) -> Dict[str, Any]:
        state = self._states.pop(camera_id, None) or {}
        self._latest_frames.pop(camera_id, None)
        self._latest_contexts.pop(camera_id, None)
        payload = self._empty_payload(
            camera_id,
            "expired",
            reason,
            frame_id,
            captured_at,
            captured_monotonic=captured_monotonic,
            source_key=str(state.get("source_key") or ""),
        )
        payload["age_seconds"] = round(float(age_seconds), 4)
        self._latest[camera_id] = payload
        metric = self._metric(camera_id)
        metric["expired_count"] += 1
        metric["last_state"] = "expired"
        metric["last_frame_id"] = str(frame_id or "")
        metric["last_reason"] = str(reason or "")
        return deepcopy(payload)

    def _metric(self, camera_id: int) -> Dict[str, Any]:
        return self._metrics.setdefault(int(camera_id), {
            "observed_count": 0,
            "tracked_count": 0,
            "coasting_count": 0,
            "expired_count": 0,
            "empty_count": 0,
            "untracked_count": 0,
            "late_anchor_count": 0,
            "late_model_result_drop_count": 0,
            "late_anchor_rebased_count": 0,
            "late_empty_applied_count": 0,
            "late_untracked_applied_count": 0,
            "late_anchor_rebase_rejection_count": 0,
            "late_model_source_rejection_count": 0,
            "late_model_expired_count": 0,
            "late_frame_drop_count": 0,
            "risk_hint_count": 0,
            "last_risk_hint_at_monotonic": None,
            "last_risk_hint": self._empty_risk_hint(),
            "last_state": "empty",
            "last_frame_id": "",
            "last_reason": "",
            "last_quality": {},
        })

    def _record_rate_sample(
        self,
        store: dict[int, deque[float]],
        camera_id: int,
        now: float,
    ) -> None:
        samples = store.setdefault(int(camera_id), deque(maxlen=300))
        samples.append(float(now))
        cutoff = float(now) - 10.0
        while samples and samples[0] < cutoff:
            samples.popleft()

    def _display_frame_is_newer_locked(self, camera_id: int, sample_at: float, frame_id: str) -> bool:
        camera_id = int(camera_id)
        frame_id = str(frame_id or "")
        if not frame_id:
            return False
        previous = self._last_display_samples.get(camera_id)
        if previous is None:
            return True
        previous_at, previous_frame_id = previous
        if frame_id == previous_frame_id:
            return False
        return float(sample_at) > float(previous_at) + 1e-6

    def _model_frame_is_current_display_locked(
        self,
        camera_id: int,
        *,
        frame_id: str,
        source_key: str,
    ) -> bool:
        latest = self._latest.get(int(camera_id)) or {}
        if not frame_id or str(latest.get("frame_id") or "") != str(frame_id):
            return False
        current_source_key = str(latest.get("source_key") or "")
        return not source_key or not current_source_key or str(source_key) == current_source_key

    def _record_display_sample(self, camera_id: int, now: float, frame_id: str) -> None:
        camera_id = int(camera_id)
        frame_id = str(frame_id or "")
        if not self._display_frame_is_newer_locked(camera_id, now, frame_id):
            return
        self._last_display_samples[camera_id] = (float(now), frame_id)
        self._record_rate_sample(self._display_updates, camera_id, now)
        self._store_metadata_history_locked(camera_id, frame_id)

    def _store_metadata_history_locked(self, camera_id: int, frame_id: str) -> None:
        payload = self._latest.get(int(camera_id))
        frame = self._latest_frames.get(int(camera_id))
        if payload is None or frame is None:
            return
        state = self._states.get(int(camera_id)) or {}
        context = state.get("context") or self._latest_contexts.get(int(camera_id)) or {}
        frame_height, frame_width = frame.shape[:2]
        item = {
            "tracking": deepcopy(payload),
            "analysis_context": deepcopy(context),
            "image_width": int(state.get("image_width") or frame_width),
            "image_height": int(state.get("image_height") or frame_height),
            "source_key": str(payload.get("source_key") or state.get("source_key") or ""),
        }
        history = self._metadata_history.setdefault(int(camera_id), OrderedDict())
        history[str(frame_id)] = item
        history.move_to_end(str(frame_id))
        while len(history) > 64:
            history.popitem(last=False)

    def _source_sample_time(self, captured_monotonic: Any, now: float) -> float:
        try:
            sample_at = float(captured_monotonic)
        except (TypeError, ValueError):
            return float(now)
        if not math.isfinite(sample_at) or sample_at <= 0.0 or abs(float(now) - sample_at) > 3600.0:
            return float(now)
        return sample_at

    def _rate(self, samples: deque[float] | None, now: float) -> float:
        if not samples:
            return 0.0
        recent = [value for value in samples if value >= now - 10.0]
        if len(recent) < 2:
            return 0.0
        return round((len(recent) - 1) / max(0.001, recent[-1] - recent[0]), 2)

    def _frame_age_ms(self, samples: deque[float] | None, now: float) -> float | None:
        if not samples:
            return None
        return round(max(0.0, now - samples[-1]) * 1000.0, 1)

    def _payload(
        self,
        camera_id: int,
        *,
        state: str,
        frame_id: str,
        captured_at: str,
        captured_monotonic: float | None,
        age_seconds: float,
        poses: list[Dict[str, Any]],
        quality: Dict[str, Any],
        risk_hint: Dict[str, Any] | None = None,
        display_only_stale: bool = False,
        reason: str = "",
        source_key: str = "",
        display_published: bool = True,
    ) -> Dict[str, Any]:
        return {
            "schema_version": self.version,
            "camera_id": int(camera_id),
            "state": state,
            "reason": str(reason or ""),
            "frame_id": str(frame_id or ""),
            "captured_at": str(captured_at or ""),
            "captured_monotonic": captured_monotonic,
            "source_key": str(source_key or ""),
            "age_seconds": round(float(age_seconds), 4),
            "pose_count": len(poses),
            "poses": poses,
            "quality": quality,
            "risk_hint": deepcopy(risk_hint) if isinstance(risk_hint, dict) else self._empty_risk_hint(),
            "formal_evidence_eligible": state == "observed",
            "display_only_stale": bool(display_only_stale),
            "display_published": bool(display_published),
        }

    def _empty_payload(
        self,
        camera_id: int,
        state: str,
        reason: str,
        frame_id: str,
        captured_at: str,
        *,
        captured_monotonic: float | None = None,
        source_key: str = "",
        display_published: bool = True,
    ) -> Dict[str, Any]:
        return {
            "schema_version": self.version,
            "camera_id": int(camera_id),
            "state": state,
            "reason": str(reason or ""),
            "frame_id": str(frame_id or ""),
            "captured_at": str(captured_at or ""),
            "captured_monotonic": captured_monotonic,
            "source_key": str(source_key or ""),
            "age_seconds": None,
            "pose_count": 0,
            "poses": [],
            "quality": {},
            "risk_hint": self._empty_risk_hint(),
            "formal_evidence_eligible": False,
            "display_published": bool(display_published),
        }

    def _empty_risk_hint(self) -> Dict[str, Any]:
        return {
            "detected": False,
            "reason": "",
            "tracks": [],
            "formal_evidence_eligible": False,
        }

    def _gray(self, cv2: Any, frame: Any) -> Any:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self.tracking_scale >= 0.999:
            return gray
        return cv2.resize(
            gray,
            (
                max(1, int(round(gray.shape[1] * self.tracking_scale))),
                max(1, int(round(gray.shape[0] * self.tracking_scale))),
            ),
            interpolation=cv2.INTER_AREA,
        )

    def _display_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            key: deepcopy(context[key])
            for key in self.display_context_keys
            if key in context
        }

    def _vision_modules(self) -> tuple[Any, Any]:
        import cv2  # type: ignore
        import numpy as np  # type: ignore

        return cv2, np

    def _finite(self, value: Any) -> bool:
        try:
            return math.isfinite(float(value))
        except (TypeError, ValueError):
            return False
