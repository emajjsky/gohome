from __future__ import annotations

from datetime import datetime, timezone
import math
import time
from typing import Any, Dict


UPRIGHT_POSTURES = {
    "standing", "sitting", "squatting", "bending", "upper_body",
    "standing_or_sitting", "seated_or_half_body", "low_body",
}


class PoseFactorGraphEngine:
    """Build explainable per-track temporal factors without owning alert policy."""

    version = "pose-factor-graph-v1"

    def __init__(
        self,
        *,
        upright_window_seconds: float = 20.0,
        prolonged_lying_seconds: float = 180.0,
        recovery_samples: int = 2,
        min_posture_confidence: float = 0.40,
    ) -> None:
        self.upright_window_seconds = max(5.0, float(upright_window_seconds))
        self.prolonged_lying_seconds = max(10.0, float(prolonged_lying_seconds))
        self.recovery_samples = max(1, int(recovery_samples))
        self.min_posture_confidence = max(0.0, min(1.0, float(min_posture_confidence)))
        self._states: dict[int, dict[str, Dict[str, Any]]] = {}

    def update(
        self,
        camera_id: int,
        analysis: Dict[str, Any],
        *,
        observed_at: str | None = None,
        monotonic_at: float | None = None,
    ) -> Dict[str, Any]:
        camera_id = int(camera_id)
        now_mono = float(monotonic_at if monotonic_at is not None else time.monotonic())
        timestamp = str(observed_at or datetime.now(timezone.utc).isoformat())
        width = max(1.0, float(analysis.get("image_width") or 1.0))
        height = max(1.0, float(analysis.get("image_height") or 1.0))
        motion_score = float(analysis.get("motion_score") or 0.0)
        targets = self._track_targets(analysis)
        states = self._states.setdefault(camera_id, {})
        graphs: list[Dict[str, Any]] = []

        for target in targets:
            track_id = str(target["track_id"])
            state = states.setdefault(track_id, {})
            posture = str(target.get("posture") or "unknown")
            posture_confidence = float(target.get("posture_confidence") or target.get("confidence") or 0.0)
            center = self._center(target["bbox"], width, height)
            normal_lying_zone = bool(target.get("normal_lying_zone"))
            recent_upright = state.get("upright") if isinstance(state.get("upright"), dict) else None
            if posture in UPRIGHT_POSTURES and posture_confidence >= self.min_posture_confidence:
                recent_upright = {
                    "observed_at": timestamp,
                    "monotonic_at": now_mono,
                    "center": center,
                    "bbox": list(target["bbox"]),
                    "posture": posture,
                }
                state["upright"] = recent_upright

            lying = posture == "lying" and posture_confidence >= self.min_posture_confidence
            if lying and not normal_lying_zone:
                if state.get("lying_started_monotonic") is None:
                    state["lying_started_monotonic"] = now_mono
                    state["lying_started_at"] = timestamp
                state["recovery_count"] = 0
            else:
                state["recovery_count"] = int(state.get("recovery_count") or 0) + 1
                if state["recovery_count"] >= self.recovery_samples:
                    state.pop("lying_started_monotonic", None)
                    state.pop("lying_started_at", None)

            lying_started = state.get("lying_started_monotonic")
            lying_duration = max(0.0, now_mono - float(lying_started)) if lying_started is not None else 0.0
            graphs.append(self._graph(
                target=target,
                center=center,
                recent_upright=recent_upright,
                now_mono=now_mono,
                motion_score=motion_score,
                lying_duration=lying_duration,
                lying_started_at=state.get("lying_started_at"),
            ))
            state.update({"last_seen_monotonic": now_mono, "last_seen_at": timestamp, "last_posture": posture})

        visible_ids = {str(target["track_id"]) for target in targets}
        for track_id, state in list(states.items()):
            last_seen = float(state.get("last_seen_monotonic") or now_mono)
            if track_id not in visible_ids and now_mono - last_seen > self.upright_window_seconds:
                states.pop(track_id, None)

        best_fast = max(graphs, key=lambda item: float(item.get("fast_fall_score") or 0.0), default=None)
        prolonged = [item for item in graphs if item.get("prolonged_floor_lying_candidate")]
        result = {
            "schema_version": self.version,
            "camera_id": camera_id,
            "observed_at": timestamp,
            "tracks": graphs,
            "fast_fall_candidate": bool(best_fast and best_fast.get("fast_fall_candidate")),
            "fast_fall_score": float(best_fast.get("fast_fall_score") or 0.0) if best_fast else 0.0,
            "fast_fall_track": best_fast if best_fast and best_fast.get("fast_fall_candidate") else None,
            "prolonged_floor_lying_candidate": bool(prolonged),
            "prolonged_floor_lying_tracks": prolonged,
        }
        analysis["pose_factor_graph"] = result
        return result

    def reset_camera(self, camera_id: int) -> None:
        self._states.pop(int(camera_id), None)

    def _graph(
        self,
        *,
        target: Dict[str, Any],
        center: list[float],
        recent_upright: Dict[str, Any] | None,
        now_mono: float,
        motion_score: float,
        lying_duration: float,
        lying_started_at: Any,
    ) -> Dict[str, Any]:
        posture = str(target.get("posture") or "unknown")
        confidence = float(target.get("posture_confidence") or target.get("confidence") or 0.0)
        body_aspect = self._body_aspect(target)
        normal_lying_zone = bool(target.get("normal_lying_zone"))
        upright_age = None
        vertical_drop = 0.0
        horizontal_distance = 1.0
        recent_upright_ok = False
        if recent_upright:
            upright_age = max(0.0, now_mono - float(recent_upright.get("monotonic_at") or now_mono))
            upright_center = recent_upright.get("center") or center
            vertical_drop = float(center[1]) - float(upright_center[1])
            horizontal_distance = abs(float(center[0]) - float(upright_center[0]))
            recent_upright_ok = upright_age <= self.upright_window_seconds

        low_posture = posture == "lying" or (posture in {"squatting", "low_body"} and center[1] >= 0.62)
        factors = {
            "recent_upright": recent_upright_ok,
            "vertical_drop": vertical_drop >= 0.12,
            "spatial_consistency": horizontal_distance <= 0.28,
            "low_posture": low_posture,
            "horizontal_body": posture == "lying" or body_aspect >= 1.10,
            "motion": motion_score >= 0.02 or vertical_drop >= 0.18,
            "non_normal_lying_surface": not normal_lying_zone,
        }
        weights = {
            "recent_upright": 0.20, "vertical_drop": 0.20, "spatial_consistency": 0.10,
            "low_posture": 0.20, "horizontal_body": 0.10, "motion": 0.10,
            "non_normal_lying_surface": 0.10,
        }
        score = sum(weights[name] for name, matched in factors.items() if matched)
        score *= max(0.55, min(1.0, confidence if confidence > 0 else 0.55))
        fast_candidate = bool(
            score >= 0.72 and factors["recent_upright"] and factors["vertical_drop"]
            and factors["spatial_consistency"] and factors["low_posture"]
            and factors["non_normal_lying_surface"]
        )
        prolonged_candidate = bool(
            posture == "lying" and confidence >= self.min_posture_confidence
            and not normal_lying_zone and lying_duration >= self.prolonged_lying_seconds
        )
        return {
            "track_id": str(target.get("track_id") or ""),
            "bbox": [round(float(value), 1) for value in target["bbox"]],
            "center": center,
            "posture": posture,
            "posture_confidence": round(confidence, 4),
            "posture_factors": target.get("posture_factors") or {},
            "body_aspect": round(body_aspect, 4),
            "normal_lying_zone": normal_lying_zone,
            "scene_zone_id": target.get("scene_zone_id"),
            "scene_zone_label": target.get("scene_zone_label"),
            "recent_upright_age_seconds": None if upright_age is None else round(upright_age, 3),
            "vertical_drop": round(vertical_drop, 4),
            "horizontal_distance": round(horizontal_distance, 4),
            "motion_score": round(motion_score, 4),
            "lying_started_at": lying_started_at,
            "lying_duration_seconds": round(lying_duration, 3),
            "factors": factors,
            "factor_weights": weights,
            "fast_fall_score": round(score, 4),
            "fast_fall_candidate": fast_candidate,
            "prolonged_floor_lying_candidate": prolonged_candidate,
        }

    def _track_targets(self, analysis: Dict[str, Any]) -> list[Dict[str, Any]]:
        poses = analysis.get("poses") if isinstance(analysis.get("poses"), list) else []
        people = analysis.get("people") if isinstance(analysis.get("people"), list) else []
        targets: dict[str, Dict[str, Any]] = {}
        for pose in poses:
            if pose.get("track_id") and self._valid_bbox(pose.get("bbox")):
                targets[str(pose["track_id"])] = dict(pose)
        for person in people:
            track_id = str(person.get("track_id") or "")
            if not track_id or not self._valid_bbox(person.get("bbox")):
                continue
            if track_id in targets:
                pose = targets[track_id]
                targets[track_id] = {
                    **person, **pose,
                    "normal_lying_zone": bool(pose.get("normal_lying_zone") or person.get("normal_lying_zone")),
                    "scene_zone_id": pose.get("scene_zone_id") or person.get("scene_zone_id"),
                    "scene_zone_label": pose.get("scene_zone_label") or person.get("scene_zone_label"),
                }
            else:
                targets[track_id] = dict(person)
        return [{**item, "track_id": track_id} for track_id, item in targets.items()]

    def _body_aspect(self, target: Dict[str, Any]) -> float:
        factors = target.get("posture_factors") if isinstance(target.get("posture_factors"), dict) else {}
        if factors.get("body_aspect") is not None:
            return float(factors["body_aspect"])
        x1, y1, x2, y2 = [float(value) for value in target["bbox"]]
        return (x2 - x1) / max(1.0, y2 - y1)

    def _center(self, bbox: list[float], width: float, height: float) -> list[float]:
        x1, y1, x2, y2 = [float(value) for value in bbox]
        return [round((x1 + x2) / (2.0 * width), 4), round((y1 + y2) / (2.0 * height), 4)]

    def _valid_bbox(self, bbox: Any) -> bool:
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return False
        try:
            x1, y1, x2, y2 = [float(value) for value in bbox]
        except (TypeError, ValueError):
            return False
        return x2 > x1 and y2 > y1 and math.isfinite(x1 + y1 + x2 + y2)
