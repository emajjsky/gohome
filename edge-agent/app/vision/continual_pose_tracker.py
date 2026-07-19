from __future__ import annotations

from copy import deepcopy
import math
from threading import RLock
import time
from typing import Any, Callable, Dict


class ContinualPoseTracker:
    """Propagate fresh pose anchors briefly without creating safety evidence."""

    version = "eacp-continual-pose-v1"
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
        "fire_candidate",
        "fire_event_candidate",
        "fire_score",
        "fire_temporal_candidate",
        "fire_temporal_score",
        "meal_candidate",
        "meal_score",
        "stillness_candidate",
        "stillness_score",
        "daze_candidate",
        "daze_score",
        "tags",
        "inference_runtime",
        "pose_factor_graph",
    }

    def __init__(
        self,
        *,
        max_age_seconds: float = 0.6,
        max_display_age_seconds: float = 1.2,
        minimum_interval_seconds: float = 0.1,
        min_tracked_points: int = 6,
        min_tracked_ratio: float = 0.55,
        max_forward_backward_error: float = 1.8,
        min_geometry_scale: float = 0.65,
        max_geometry_scale: float = 1.45,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        self.max_age_seconds = max(0.1, float(max_age_seconds))
        self.max_display_age_seconds = max(self.max_age_seconds, float(max_display_age_seconds))
        self.minimum_interval_seconds = max(0.02, float(minimum_interval_seconds))
        self.min_tracked_points = max(3, int(min_tracked_points))
        self.min_tracked_ratio = max(0.2, min(1.0, float(min_tracked_ratio)))
        self.max_forward_backward_error = max(0.2, float(max_forward_backward_error))
        self.min_geometry_scale = max(0.1, float(min_geometry_scale))
        self.max_geometry_scale = max(self.min_geometry_scale, float(max_geometry_scale))
        self._clock = monotonic_clock or time.monotonic
        self._states: dict[int, Dict[str, Any]] = {}
        self._latest: dict[int, Dict[str, Any]] = {}
        self._latest_frames: dict[int, Any] = {}
        self._metrics: dict[int, Dict[str, Any]] = {}
        self._lock = RLock()

    def observe(
        self,
        camera_id: int,
        frame: Any,
        *,
        frame_id: str,
        captured_at: str,
        poses: list[Dict[str, Any]],
        context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        cv2, np = self._vision_modules()
        camera_id = int(camera_id)
        now = float(self._clock())
        gray = self._gray(cv2, frame)
        tracked_poses = []
        for pose in poses:
            prepared = self._prepare_pose(np, pose)
            if prepared is not None:
                tracked_poses.append(prepared)
        with self._lock:
            if not tracked_poses:
                self._states.pop(camera_id, None)
                self._latest_frames.pop(camera_id, None)
                payload = self._empty_payload(camera_id, "empty", "no_observed_pose", frame_id, captured_at)
                self._latest[camera_id] = payload
                return deepcopy(payload)
            self._states[camera_id] = {
                "observed_monotonic": now,
                "last_updated_monotonic": now,
                "previous_gray": gray,
                "frame_id": str(frame_id or ""),
                "display_frame_id": str(frame_id or ""),
                "captured_at": str(captured_at or ""),
                "image_width": int(frame.shape[1]),
                "image_height": int(frame.shape[0]),
                "poses": tracked_poses,
                "context": self._display_context(context or {}),
            }
            payload = self._payload(
                camera_id,
                state="observed",
                frame_id=frame_id,
                captured_at=captured_at,
                age_seconds=0.0,
                poses=[self._public_observed_pose(item["pose"]) for item in tracked_poses],
                quality={
                    "tracked_point_count": sum(len(item["point_indices"]) for item in tracked_poses),
                    "forward_backward_error": 0.0,
                    "geometry_scale": 1.0,
                },
            )
            self._latest[camera_id] = payload
            self._latest_frames[camera_id] = frame.copy()
            metric = self._metric(camera_id)
            metric["observed_count"] += 1
            metric["last_state"] = "observed"
            metric["last_frame_id"] = str(frame_id or "")
            return deepcopy(payload)

    def update_frame(
        self,
        camera_id: int,
        frame: Any,
        *,
        frame_id: str,
        captured_at: str,
    ) -> Dict[str, Any]:
        cv2, np = self._vision_modules()
        camera_id = int(camera_id)
        now = float(self._clock())
        gray = self._gray(cv2, frame)
        with self._lock:
            state = self._states.get(camera_id)
            if state is None:
                payload = self._empty_payload(camera_id, "empty", "no_anchor", frame_id, captured_at)
                self._latest[camera_id] = payload
                return deepcopy(payload)
            if str(frame_id or "") and str(frame_id) == str(state.get("frame_id") or ""):
                return deepcopy(self._latest.get(camera_id) or self._empty_payload(
                    camera_id, "empty", "same_frame", frame_id, captured_at
                ))
            anchor_age = max(0.0, now - float(state["observed_monotonic"]))
            if anchor_age > self.max_display_age_seconds:
                return self._expire_locked(camera_id, "anchor_expired", frame_id, captured_at, anchor_age)
            if now - float(state.get("last_updated_monotonic") or 0.0) < self.minimum_interval_seconds:
                return deepcopy(self._latest.get(camera_id) or self._empty_payload(
                    camera_id, "empty", "tracking_throttled", frame_id, captured_at
                ))

            next_poses = []
            public_poses = []
            tracked_points = 0
            errors = []
            scales = []
            rejection_reasons = []
            track_age = max(0.0, now - float(state.get("last_updated_monotonic") or 0.0))
            for item in state["poses"]:
                result = self._track_pose(cv2, np, state["previous_gray"], gray, item, frame, track_age)
                if not result.get("ok"):
                    rejection_reasons.append(str(result.get("reason") or "optical_flow_failed"))
                    continue
                next_poses.append(result["state"])
                public_poses.append(result["pose"])
                tracked_points += int(result["tracked_point_count"])
                errors.append(float(result["forward_backward_error"]))
                scales.append(float(result["geometry_scale"]))

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
                )

            state["previous_gray"] = gray
            state["last_updated_monotonic"] = now
            state["frame_id"] = str(frame_id or "")
            state["display_frame_id"] = str(frame_id or "")
            state["captured_at"] = str(captured_at or "")
            state["image_width"] = int(frame.shape[1])
            state["image_height"] = int(frame.shape[0])
            state["poses"] = next_poses
            payload = self._payload(
                camera_id,
                state="tracked",
                frame_id=frame_id,
                captured_at=captured_at,
                age_seconds=anchor_age,
                poses=public_poses,
                quality={
                    "tracked_point_count": tracked_points,
                    "forward_backward_error": round(max(errors, default=0.0), 4),
                    "geometry_scale": round(sum(scales) / max(1, len(scales)), 4),
                },
                display_only_stale=anchor_age > self.max_age_seconds,
            )
            self._latest[camera_id] = payload
            self._latest_frames[camera_id] = frame.copy()
            metric = self._metric(camera_id)
            metric["tracked_count"] += 1
            metric["last_state"] = "tracked"
            metric["last_frame_id"] = str(frame_id or "")
            metric["last_quality"] = dict(payload["quality"])
            return deepcopy(payload)

    def latest(self, camera_id: int) -> Dict[str, Any]:
        camera_id = int(camera_id)
        with self._lock:
            payload = self._latest.get(camera_id)
            return deepcopy(payload) if payload is not None else self._empty_payload(
                camera_id, "empty", "no_anchor", "", ""
            )

    def latest_frame(self, camera_id: int) -> Dict[str, Any] | None:
        """Return pixels and pose data from the exact same tracked frame."""
        camera_id = int(camera_id)
        if not self.has_anchor(camera_id):
            return None
        with self._lock:
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
            }

    def latest_metadata(self, camera_id: int) -> Dict[str, Any]:
        """Return display metadata without copying or encoding frame pixels."""
        camera_id = int(camera_id)
        self.has_anchor(camera_id)
        with self._lock:
            state = self._states.get(camera_id) or {}
            payload = self._latest.get(camera_id)
            tracking = deepcopy(payload) if payload is not None else self._empty_payload(
                camera_id, "empty", "no_anchor", "", ""
            )
            return {
                "tracking": tracking,
                "analysis_context": deepcopy(state.get("context") or {}),
                "image_width": int(state.get("image_width") or 0),
                "image_height": int(state.get("image_height") or 0),
            }

    def has_anchor(self, camera_id: int) -> bool:
        camera_id = int(camera_id)
        with self._lock:
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
            return {
                "schema_version": self.version,
                "max_age_seconds": self.max_age_seconds,
                "max_display_age_seconds": self.max_display_age_seconds,
                "minimum_interval_seconds": self.minimum_interval_seconds,
                "cameras": [
                    {
                        "camera_id": camera_id,
                        **deepcopy(self._metric(camera_id)),
                        "state": str((self._latest.get(camera_id) or {}).get("state") or "empty"),
                        "age_seconds": (self._latest.get(camera_id) or {}).get("age_seconds"),
                        "pose_count": int((self._latest.get(camera_id) or {}).get("pose_count") or 0),
                    }
                    for camera_id in ids
                ],
            }

    def reset_camera(self, camera_id: int) -> None:
        camera_id = int(camera_id)
        with self._lock:
            self._states.pop(camera_id, None)
            self._latest.pop(camera_id, None)
            self._latest_frames.pop(camera_id, None)
            self._metrics.pop(camera_id, None)

    def _prepare_pose(self, np: Any, pose: Dict[str, Any]) -> Dict[str, Any] | None:
        keypoints = list(pose.get("keypoints") or [])
        indices = [
            index
            for index, point in enumerate(keypoints)
            if point.get("visible")
            and float(point.get("confidence") or 0.0) >= 0.2
            and self._finite(point.get("x"))
            and self._finite(point.get("y"))
        ]
        if len(indices) < self.min_tracked_points:
            return None
        points = np.asarray(
            [[float(keypoints[index]["x"]), float(keypoints[index]["y"])] for index in indices],
            dtype=np.float32,
        ).reshape(-1, 1, 2)
        return {
            "pose": deepcopy(pose),
            "points": points,
            "point_indices": indices,
        }

    def _track_pose(
        self,
        cv2: Any,
        np: Any,
        previous_gray: Any,
        gray: Any,
        item: Dict[str, Any],
        frame: Any,
        age_seconds: float,
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
        scale = self._geometry_scale(np, old_valid, new_valid)
        if scale < self.min_geometry_scale or scale > self.max_geometry_scale:
            return {"ok": False, "reason": "geometry_drift"}

        pose = deepcopy(item["pose"])
        keypoints = list(pose.get("keypoints") or [])
        point_indices = list(item["point_indices"])
        valid_indices = []
        valid_points = []
        decay = max(0.0, math.exp(-age_seconds / self.max_age_seconds))
        for point_offset, keypoint_index in enumerate(point_indices):
            point = dict(keypoints[keypoint_index])
            if bool(valid[point_offset]):
                x, y = next_points.reshape(-1, 2)[point_offset]
                point.update({
                    "x": round(float(x), 2),
                    "y": round(float(y), 2),
                    "confidence": round(float(point.get("confidence") or 0.0) * decay, 4),
                    "visible": True,
                })
                valid_indices.append(keypoint_index)
                valid_points.append([float(x), float(y)])
            else:
                point.update({"visible": False, "confidence": 0.0})
            keypoints[keypoint_index] = point

        displacement = np.median(new_valid - old_valid, axis=0)
        pose["bbox"] = self._shift_bbox(pose.get("bbox"), displacement, frame)
        pose["keypoints"] = keypoints
        pose["confidence"] = round(float(pose.get("confidence") or 0.0) * decay, 4)
        pose["tracking_state"] = "tracked"
        pose["tracking_source"] = "klt"
        pose["track_age_seconds"] = round(age_seconds, 4)
        pose["fall_score"] = 0.0
        pose["pose_fall_candidate"] = False
        pose["fall_evidence_eligible"] = False
        pose["person_evidence_eligible"] = False
        pose["action_hints"] = [hint for hint in pose.get("action_hints") or [] if hint != "fall_candidate"]
        return {
            "ok": True,
            "pose": pose,
            "state": {
                "pose": pose,
                "points": np.asarray(valid_points, dtype=np.float32).reshape(-1, 1, 2),
                "point_indices": valid_indices,
            },
            "tracked_point_count": valid_count,
            "forward_backward_error": float(fb_error[valid].max()),
            "geometry_scale": float(scale),
        }

    def _geometry_scale(self, np: Any, old_points: Any, new_points: Any) -> float:
        old_center = np.median(old_points, axis=0)
        new_center = np.median(new_points, axis=0)
        old_radius = np.linalg.norm(old_points - old_center, axis=1)
        new_radius = np.linalg.norm(new_points - new_center, axis=1)
        valid = old_radius > 1.0
        if not bool(valid.any()):
            return 1.0
        return float(np.median(new_radius[valid] / old_radius[valid]))

    def _shift_bbox(self, bbox: Any, displacement: Any, frame: Any) -> list[float]:
        height, width = frame.shape[:2]
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return []
        dx, dy = [float(value) for value in displacement]
        x1, y1, x2, y2 = [float(value) for value in bbox]
        return [
            round(max(0.0, min(float(width - 1), x1 + dx)), 1),
            round(max(0.0, min(float(height - 1), y1 + dy)), 1),
            round(max(1.0, min(float(width), x2 + dx)), 1),
            round(max(1.0, min(float(height), y2 + dy)), 1),
        ]

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
    ) -> Dict[str, Any]:
        state = self._states.get(camera_id)
        if state is None or anchor_age_seconds > self.max_display_age_seconds:
            return self._expire_locked(
                camera_id,
                "anchor_expired" if anchor_age_seconds > self.max_display_age_seconds else reason,
                frame_id,
                captured_at,
                anchor_age_seconds,
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
            age_seconds=anchor_age_seconds,
            poses=poses,
            quality=previous_quality,
            display_only_stale=True,
        )
        state["display_frame_id"] = str(frame_id or "")
        self._latest[camera_id] = payload
        self._latest_frames[camera_id] = frame.copy()
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
    ) -> Dict[str, Any]:
        self._states.pop(camera_id, None)
        self._latest_frames.pop(camera_id, None)
        payload = self._empty_payload(camera_id, "expired", reason, frame_id, captured_at)
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
            "last_state": "empty",
            "last_frame_id": "",
            "last_reason": "",
            "last_quality": {},
        })

    def _payload(
        self,
        camera_id: int,
        *,
        state: str,
        frame_id: str,
        captured_at: str,
        age_seconds: float,
        poses: list[Dict[str, Any]],
        quality: Dict[str, Any],
        display_only_stale: bool = False,
        reason: str = "",
    ) -> Dict[str, Any]:
        return {
            "schema_version": self.version,
            "camera_id": int(camera_id),
            "state": state,
            "reason": str(reason or ""),
            "frame_id": str(frame_id or ""),
            "captured_at": str(captured_at or ""),
            "age_seconds": round(float(age_seconds), 4),
            "pose_count": len(poses),
            "poses": poses,
            "quality": quality,
            "formal_evidence_eligible": state == "observed",
            "display_only_stale": bool(display_only_stale),
        }

    def _empty_payload(
        self,
        camera_id: int,
        state: str,
        reason: str,
        frame_id: str,
        captured_at: str,
    ) -> Dict[str, Any]:
        return {
            "schema_version": self.version,
            "camera_id": int(camera_id),
            "state": state,
            "reason": str(reason or ""),
            "frame_id": str(frame_id or ""),
            "captured_at": str(captured_at or ""),
            "age_seconds": None,
            "pose_count": 0,
            "poses": [],
            "quality": {},
            "formal_evidence_eligible": False,
        }

    def _gray(self, cv2: Any, frame: Any) -> Any:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

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
