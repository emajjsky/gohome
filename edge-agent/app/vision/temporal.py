from __future__ import annotations

from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
import math
import time
from typing import Any, Dict


LOW_POSTURES = {"lying", "low_body"}
TRACK_TRANSITION_POSTURES = LOW_POSTURES | {"squatting", "bending"}
UPRIGHT_POSTURES = {
    "standing", "sitting", "squatting", "bending", "upper_body", "standing_or_sitting",
}
EVIDENCE_BASELINE_POSTURES = {
    "standing", "sitting", "standing_or_sitting", "seated_or_half_body",
}
POSTURE_TRANSITION_MIN_SHAPE_SIMILARITY = 0.16
LOW_POSTURE_CONTINUITY_MIN_SHAPE_SIMILARITY = 0.22
DEFAULT_MIN_SHAPE_SIMILARITY = 0.28
LOW_POSTURE_CONTINUITY_SCORE_BONUS = 0.12
DIRECTION_REVERSAL_MIN_OBSERVED_IOU = 0.30
TRACK_MATCH_SCHEDULER_JITTER_SECONDS = 0.15
PRESENCE_DIRECT_MIN_CONFIDENCE = 0.35
PRESENCE_TRACKED_MIN_CONFIDENCE = 0.30
PRESENCE_TRACKED_MIN_SAMPLES = 2
PRESENCE_POSE_MIN_CONFIDENCE = 0.45


class TemporalObservationEngine:
    """Maintains compact per-camera tracks and a bounded observation history."""

    version = "temporal-observation-v2"
    tracker_version = "eacp-observation-centric-v1"

    def __init__(
        self,
        *,
        history_size: int = 48,
        track_ttl_seconds: float = 20.0,
        max_match_age_seconds: float = 2.0,
        min_iou: float = 0.12,
        max_center_distance: float = 0.24,
        posture_min_duration_seconds: float = 3.0,
        posture_min_samples: int = 2,
        posture_min_confidence: float = 0.40,
    ) -> None:
        self.history_size = max(8, int(history_size))
        self.track_ttl_seconds = max(2.0, float(track_ttl_seconds))
        self.max_match_age_seconds = max(0.5, min(self.track_ttl_seconds, float(max_match_age_seconds)))
        self.min_iou = max(0.0, min(1.0, float(min_iou)))
        self.max_center_distance = max(0.01, float(max_center_distance))
        self.posture_min_duration_seconds = max(0.0, float(posture_min_duration_seconds))
        self.posture_min_samples = max(1, int(posture_min_samples))
        self.posture_min_confidence = max(0.0, min(1.0, float(posture_min_confidence)))
        self._histories: dict[int, deque[Dict[str, Any]]] = {}
        self._tracks: dict[int, dict[str, Dict[str, Any]]] = {}
        self._next_track_ids: dict[int, int] = {}
        self._posture_states: dict[int, dict[str, Dict[str, Any]]] = {}

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
        frame_width = max(1.0, float(analysis.get("image_width") or 1.0))
        frame_height = max(1.0, float(analysis.get("image_height") or 1.0))
        people = analysis.get("people") if isinstance(analysis.get("people"), list) else []
        poses = analysis.get("poses") if isinstance(analysis.get("poses"), list) else []
        detections = self._detections(people, poses)
        tracks = self._tracks.setdefault(camera_id, {})
        expired_track_ids = self._expire_tracks(tracks, now_mono)
        episode_closures = self._close_expired_postures(camera_id, expired_track_ids, timestamp)

        assignments = self._assign_tracks(
            detections,
            tracks,
            now_mono=now_mono,
            frame_width=frame_width,
            frame_height=frame_height,
        )
        assigned: list[Dict[str, Any]] = []
        for detection_index, detection in enumerate(detections):
            track_id = assignments.get(detection_index)
            if track_id is None:
                track_id = self._new_track_id(camera_id)
                tracks[track_id] = {
                    "track_id": track_id,
                    "first_seen_at": timestamp,
                    "sample_count": 0,
                    "bbox_velocity": [0.0, 0.0, 0.0, 0.0],
                }
            track = tracks[track_id]
            previous_bbox = track.get("bbox")
            previous_seen = track.get("last_seen_monotonic")
            velocity = self._updated_velocity(
                previous_bbox,
                detection["bbox"],
                previous_velocity=track.get("bbox_velocity"),
                elapsed=None if previous_seen is None else now_mono - float(previous_seen),
                frame_width=frame_width,
                frame_height=frame_height,
            )
            track.update({
                "last_seen_at": timestamp,
                "last_seen_monotonic": now_mono,
                "bbox": list(detection["bbox"]),
                "confidence": float(detection.get("confidence") or 0.0),
                "source": str(detection.get("source") or "person"),
                "posture": str(detection.get("posture") or "unknown"),
                "posture_confidence": float(detection.get("posture_confidence") or 0.0),
                "sample_count": int(track.get("sample_count") or 0) + 1,
                "bbox_velocity": velocity,
            })
            assigned.append({
                **detection,
                "track_id": track_id,
                "track_sample_count": int(track["sample_count"]),
            })

        self._annotate_analysis(people, poses, assigned, frame_width, frame_height)
        credible_assigned, presence_quality = self._credible_presence(assigned)
        episode_updates, switched_closures = self._update_posture_states(camera_id, assigned, timestamp, now_mono)
        episode_closures.extend(switched_closures)
        active_tracks = [self._public_track(item) for item in tracks.values() if now_mono - float(item.get("last_seen_monotonic") or 0.0) <= self.track_ttl_seconds]
        current_track_ids = [str(item["track_id"]) for item in assigned]
        observation = {
            "observed_at": timestamp,
            "person_present": bool(assigned),
            "person_count": len(assigned),
            "credible_person_present": bool(credible_assigned),
            "credible_person_count": len(credible_assigned),
            "credible_track_ids": [str(item["track_id"]) for item in credible_assigned],
            "presence_persistence_state": (
                "visible" if credible_assigned else "uncertain" if assigned else "absent"
            ),
            "presence_quality": presence_quality,
            "track_ids": current_track_ids,
            "postures": sorted({str(item.get("posture") or "unknown") for item in assigned}),
            "tracks": [self._history_track(item) for item in assigned],
            "motion_score": analysis.get("motion_score"),
            "fall_candidate": bool(analysis.get("fall_candidate")),
            "fire_candidate": bool(analysis.get("fire_event_candidate") or analysis.get("fire_candidate")),
            "snapshot_id": None,
            "snapshot_path": "",
        }
        history = self._histories.setdefault(camera_id, deque(maxlen=self.history_size))
        history.append(observation)
        result = {
            "schema_version": self.version,
            "tracker_version": self.tracker_version,
            "camera_id": camera_id,
            "person_present": observation["person_present"],
            "person_count": observation["person_count"],
            "credible_person_present": observation["credible_person_present"],
            "credible_person_count": observation["credible_person_count"],
            "credible_track_ids": observation["credible_track_ids"],
            "presence_persistence_state": observation["presence_persistence_state"],
            "presence_quality": observation["presence_quality"],
            "current_track_ids": current_track_ids,
            "active_tracks": sorted(active_tracks, key=lambda item: item["track_id"]),
            "history_sample_count": len(history),
            "history_capacity": self.history_size,
            "posture_episode_updates": episode_updates,
            "posture_episode_closures": episode_closures,
        }
        analysis["temporal_observation"] = result
        return result

    def _credible_presence(
        self,
        assigned: list[Dict[str, Any]],
    ) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
        credible: list[Dict[str, Any]] = []
        decisions: list[Dict[str, Any]] = []
        for item in assigned:
            confidence = float(item.get("confidence") or 0.0)
            posture = str(item.get("posture") or "unknown")
            posture_confidence = float(item.get("posture_confidence") or 0.0)
            sample_count = int(item.get("track_sample_count") or 0)
            direct_model = confidence >= PRESENCE_DIRECT_MIN_CONFIDENCE
            pose_supported = posture != "unknown" and posture_confidence >= PRESENCE_POSE_MIN_CONFIDENCE
            repeated_model = bool(
                sample_count >= PRESENCE_TRACKED_MIN_SAMPLES
                and confidence >= PRESENCE_TRACKED_MIN_CONFIDENCE
            )
            accepted = bool(direct_model or pose_supported or repeated_model)
            if accepted:
                credible.append(item)
            decisions.append({
                "track_id": str(item.get("track_id") or ""),
                "accepted": accepted,
                "confidence": round(confidence, 4),
                "posture_confidence": round(posture_confidence, 4),
                "sample_count": sample_count,
                "evidence": {
                    "direct_model": direct_model,
                    "pose_supported": pose_supported,
                    "repeated_model": repeated_model,
                },
            })
        return credible, {
            "schema_version": "presence-evidence-quality-v1",
            "thresholds": {
                "direct_confidence": PRESENCE_DIRECT_MIN_CONFIDENCE,
                "tracked_confidence": PRESENCE_TRACKED_MIN_CONFIDENCE,
                "tracked_samples": PRESENCE_TRACKED_MIN_SAMPLES,
                "pose_confidence": PRESENCE_POSE_MIN_CONFIDENCE,
            },
            "tracks": decisions,
        }

    def attach_snapshot(self, camera_id: int, snapshot: Dict[str, Any]) -> None:
        history = self._histories.get(int(camera_id))
        if not history:
            return
        history[-1]["snapshot_id"] = snapshot.get("id")
        history[-1]["snapshot_path"] = str(snapshot.get("image_path") or "")

    def evidence_bundle(
        self,
        camera_id: int,
        *,
        event_type: str,
        track_id: str | None = None,
        limit: int = 3,
        max_age_seconds: float | None = None,
    ) -> Dict[str, Any]:
        history = list(self._histories.get(int(camera_id), ()))
        if track_id:
            history = [item for item in history if str(track_id) in (item.get("track_ids") or [])]
        if history and max_age_seconds is not None:
            try:
                ended_at = datetime.fromisoformat(str(history[-1].get("observed_at") or "").replace("Z", "+00:00"))
                window_seconds = max(0.0, float(max_age_seconds))
                history = [
                    item for item in history
                    if 0.0 <= (
                        ended_at
                        - datetime.fromisoformat(str(item.get("observed_at") or "").replace("Z", "+00:00"))
                    ).total_seconds() <= window_seconds
                ]
            except (TypeError, ValueError):
                pass
        evidence_limit = max(1, min(3, int(limit)))
        selected = self._role_aware_evidence_samples(
            history,
            track_id=track_id,
            limit=evidence_limit,
        )
        return {
            "schema_version": "temporal-evidence-bundle-v1",
            "selection_policy": "role-aware-pose-transition-v2",
            "event_type": str(event_type),
            "track_id": str(track_id or ""),
            "window_started_at": history[0].get("observed_at") if history else None,
            "window_ended_at": history[-1].get("observed_at") if history else None,
            "sample_count": len(history),
            "posture_sequence": self._posture_sequence(history, track_id),
            "snapshots": [
                {
                    "snapshot_id": item.get("snapshot_id"),
                    "snapshot_path": item.get("snapshot_path") or "",
                    "observed_at": item.get("observed_at"),
                    "postures": item.get("postures") or [],
                    "motion_score": item.get("motion_score"),
                    "role": item.get("_evidence_role") or "evidence",
                }
                for item in selected
            ],
        }

    def recent_history(self, camera_id: int, limit: int | None = None) -> list[Dict[str, Any]]:
        items = list(self._histories.get(int(camera_id), ()))
        if limit is not None:
            items = items[-max(0, int(limit)):]
        return deepcopy(items)

    def reset_camera(self, camera_id: int) -> None:
        camera_id = int(camera_id)
        self._histories.pop(camera_id, None)
        self._tracks.pop(camera_id, None)
        self._next_track_ids.pop(camera_id, None)
        self._posture_states.pop(camera_id, None)

    def _detections(self, people: list[Dict[str, Any]], poses: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        detections = []
        valid_people = [person for person in people if self._valid_bbox(person.get("bbox"))]
        valid_poses = [pose for pose in poses if self._valid_bbox(pose.get("bbox"))]
        pose_assignments = self._match_people_to_poses(valid_people, valid_poses)
        matched_pose_indices = set(pose_assignments.values())
        for person_index, person in enumerate(valid_people):
            pose_index = pose_assignments.get(person_index)
            matching_pose = valid_poses[pose_index] if pose_index is not None else None
            item = self._detection(person, "person", posture_source=matching_pose)
            if item is not None:
                detections.append(item)
        for pose_index, pose in enumerate(valid_poses):
            if pose_index in matched_pose_indices:
                continue
            item = self._detection(pose, "pose", posture_source=pose)
            if item is not None:
                detections.append(item)
        return detections

    def _match_people_to_poses(
        self,
        people: list[Dict[str, Any]],
        poses: list[Dict[str, Any]],
    ) -> dict[int, int]:
        candidates = sorted(
            (
                (self._iou(person["bbox"], pose["bbox"]), person_index, pose_index)
                for person_index, person in enumerate(people)
                for pose_index, pose in enumerate(poses)
            ),
            reverse=True,
        )
        assignments: dict[int, int] = {}
        used_pose_indices: set[int] = set()
        for overlap, person_index, pose_index in candidates:
            if overlap < 0.20:
                break
            if person_index in assignments or pose_index in used_pose_indices:
                continue
            assignments[person_index] = pose_index
            used_pose_indices.add(pose_index)
        return assignments

    def _detection(
        self,
        item: Dict[str, Any],
        source: str,
        *,
        posture_source: Dict[str, Any] | None = None,
    ) -> Dict[str, Any] | None:
        if not self._valid_bbox(item.get("bbox")):
            return None
        posture_item = posture_source if isinstance(posture_source, dict) else item
        return {
            "bbox": [float(value) for value in item["bbox"]],
            "confidence": float(item.get("confidence") or item.get("score") or item.get("pose_confidence") or 0.0),
            "posture": str(posture_item.get("posture") or "unknown"),
            "posture_confidence": float(posture_item.get("posture_confidence") or posture_item.get("confidence") or 0.0),
            "normal_lying_zone": bool(posture_item.get("normal_lying_zone") or item.get("normal_lying_zone")),
            "scene_zone_id": posture_item.get("scene_zone_id") or item.get("scene_zone_id"),
            "scene_zone_label": posture_item.get("scene_zone_label") or item.get("scene_zone_label"),
            "source": source,
            "track_id_hint": str(
                item.get("_continual_track_id_hint")
                or posture_item.get("_continual_track_id_hint")
                or ""
            ),
            "source_item": item,
            "pose_item": posture_source,
        }

    def _assign_tracks(
        self,
        detections: list[Dict[str, Any]],
        tracks: dict[str, Dict[str, Any]],
        *,
        now_mono: float,
        frame_width: float,
        frame_height: float,
    ) -> dict[int, str]:
        if not detections or not tracks:
            return {}
        candidate_ids = [
            track_id
            for track_id, track in tracks.items()
            if track.get("last_seen_monotonic") is not None
            and now_mono - float(track["last_seen_monotonic"]) <= (
                self.max_match_age_seconds + TRACK_MATCH_SCHEDULER_JITTER_SECONDS
            )
        ]
        if not candidate_ids:
            return {}
        assignments: dict[int, str] = {}
        used_track_ids: set[str] = set()
        for detection_index, detection in enumerate(detections):
            hint = str(detection.get("track_id_hint") or "")
            if hint and hint in candidate_ids and hint not in used_track_ids:
                assignments[detection_index] = hint
                used_track_ids.add(hint)

        remaining_detection_indices = [
            index for index in range(len(detections)) if index not in assignments
        ]
        remaining_candidate_ids = [
            track_id for track_id in candidate_ids if track_id not in used_track_ids
        ]
        if not remaining_detection_indices or not remaining_candidate_ids:
            return assignments
        scores = [
            [
                self._assignment_score(
                    detections[detection_index],
                    tracks[track_id],
                    now_mono=now_mono,
                    frame_width=frame_width,
                    frame_height=frame_height,
                )
                for track_id in remaining_candidate_ids
            ]
            for detection_index in remaining_detection_indices
        ]
        pairs = self._maximum_score_assignment(scores)
        assignments.update({
            remaining_detection_indices[detection_index]: remaining_candidate_ids[track_index]
            for detection_index, track_index in pairs
            if scores[detection_index][track_index] > 0.0
        })
        return assignments

    def _assignment_score(
        self,
        detection: Dict[str, Any],
        track: Dict[str, Any],
        *,
        now_mono: float,
        frame_width: float,
        frame_height: float,
    ) -> float:
        elapsed = max(0.0, now_mono - float(track.get("last_seen_monotonic") or now_mono))
        predicted_bbox = self._predicted_bbox(track, elapsed, frame_width, frame_height)
        predicted_iou = self._iou(detection["bbox"], predicted_bbox)
        observed_iou = self._iou(detection["bbox"], track.get("bbox"))
        predicted_distance = self._center_distance(
            detection["bbox"], predicted_bbox, frame_width, frame_height
        )
        shape_similarity = self._shape_similarity(detection["bbox"], track.get("bbox"))
        transition = self._credible_posture_transition(track.get("posture"), detection.get("posture"))
        low_posture_continuity = self._credible_low_posture_continuity(
            track.get("posture"),
            detection.get("posture"),
        )
        speed = self._velocity_speed(track.get("bbox_velocity"))
        distance_gate = self.max_center_distance + min(0.16, speed * min(1.5, elapsed) * 0.75)
        if transition:
            distance_gate = max(distance_gate, 0.38)
        if predicted_iou < self.min_iou and predicted_distance > distance_gate:
            return -math.inf
        minimum_shape_similarity = (
            POSTURE_TRANSITION_MIN_SHAPE_SIMILARITY
            if transition
            else LOW_POSTURE_CONTINUITY_MIN_SHAPE_SIMILARITY
            if low_posture_continuity
            else DEFAULT_MIN_SHAPE_SIMILARITY
        )
        if shape_similarity < minimum_shape_similarity:
            return -math.inf

        direction = self._direction_consistency(
            track,
            detection["bbox"],
            frame_width=frame_width,
            frame_height=frame_height,
        )
        if (
            direction < -0.65
            and predicted_iou < 0.30
            and observed_iou < DIRECTION_REVERSAL_MIN_OBSERVED_IOU
            and not transition
        ):
            return -math.inf
        distance_score = max(0.0, 1.0 - predicted_distance / max(distance_gate, 0.01))
        return (
            predicted_iou * 2.4
            + observed_iou * 0.35
            + distance_score * 0.9
            + shape_similarity * 0.35
            + max(0.0, direction) * 0.45
            + (0.20 if transition else 0.0)
            + (LOW_POSTURE_CONTINUITY_SCORE_BONUS if low_posture_continuity else 0.0)
            - min(0.25, elapsed * 0.08)
        )

    def _maximum_score_assignment(self, scores: list[list[float]]) -> list[tuple[int, int]]:
        detection_count = len(scores)
        track_count = len(scores[0]) if scores else 0
        if not detection_count or not track_count:
            return []
        if track_count > 10 or detection_count > 10:
            candidates = sorted(
                (
                    (score, detection_index, track_index)
                    for detection_index, row in enumerate(scores)
                    for track_index, score in enumerate(row)
                    if math.isfinite(score) and score > 0.0
                ),
                reverse=True,
            )
            used_detections: set[int] = set()
            used_tracks: set[int] = set()
            result = []
            for _, detection_index, track_index in candidates:
                if detection_index in used_detections or track_index in used_tracks:
                    continue
                used_detections.add(detection_index)
                used_tracks.add(track_index)
                result.append((detection_index, track_index))
            return result

        @lru_cache(maxsize=None)
        def solve(detection_index: int, used_tracks: int) -> tuple[float, tuple[tuple[int, int], ...]]:
            if detection_index >= detection_count:
                return 0.0, ()
            best_score, best_pairs = solve(detection_index + 1, used_tracks)
            for track_index, score in enumerate(scores[detection_index]):
                if used_tracks & (1 << track_index) or not math.isfinite(score) or score <= 0.0:
                    continue
                remainder_score, remainder_pairs = solve(
                    detection_index + 1,
                    used_tracks | (1 << track_index),
                )
                total = score + remainder_score
                if total > best_score:
                    best_score = total
                    best_pairs = ((detection_index, track_index), *remainder_pairs)
            return best_score, best_pairs

        return list(solve(0, 0)[1])

    def _updated_velocity(
        self,
        previous_bbox: Any,
        bbox: Any,
        *,
        previous_velocity: Any,
        elapsed: float | None,
        frame_width: float,
        frame_height: float,
    ) -> list[float]:
        if not self._valid_bbox(previous_bbox) or not self._valid_bbox(bbox) or not elapsed or elapsed <= 0.0:
            return [0.0, 0.0, 0.0, 0.0]
        previous = self._normalized_bbox_state(previous_bbox, frame_width, frame_height)
        current = self._normalized_bbox_state(bbox, frame_width, frame_height)
        measured = [(current[index] - previous[index]) / elapsed for index in range(4)]
        if not isinstance(previous_velocity, (list, tuple)) or len(previous_velocity) != 4:
            return measured
        old = [float(value) for value in previous_velocity]
        if max(abs(value) for value in old) <= 1e-6:
            return measured
        return [old[index] * 0.30 + measured[index] * 0.70 for index in range(4)]

    def _predicted_bbox(
        self,
        track: Dict[str, Any],
        elapsed: float,
        frame_width: float,
        frame_height: float,
    ) -> list[float]:
        bbox = track.get("bbox")
        if not self._valid_bbox(bbox):
            return []
        state = self._normalized_bbox_state(bbox, frame_width, frame_height)
        velocity = track.get("bbox_velocity")
        if not isinstance(velocity, (list, tuple)) or len(velocity) != 4:
            velocity = [0.0, 0.0, 0.0, 0.0]
        horizon = min(1.5, max(0.0, elapsed))
        cx = state[0] + float(velocity[0]) * horizon
        cy = state[1] + float(velocity[1]) * horizon
        width = max(0.01, state[2] + float(velocity[2]) * horizon)
        height = max(0.01, state[3] + float(velocity[3]) * horizon)
        return [
            (cx - width / 2.0) * frame_width,
            (cy - height / 2.0) * frame_height,
            (cx + width / 2.0) * frame_width,
            (cy + height / 2.0) * frame_height,
        ]

    def _normalized_bbox_state(self, bbox: Any, width: float, height: float) -> list[float]:
        x1, y1, x2, y2 = [float(value) for value in bbox]
        return [
            (x1 + x2) / (2.0 * max(1.0, width)),
            (y1 + y2) / (2.0 * max(1.0, height)),
            (x2 - x1) / max(1.0, width),
            (y2 - y1) / max(1.0, height),
        ]

    def _velocity_speed(self, velocity: Any) -> float:
        if not isinstance(velocity, (list, tuple)) or len(velocity) < 2:
            return 0.0
        return math.hypot(float(velocity[0]), float(velocity[1]))

    def _direction_consistency(
        self,
        track: Dict[str, Any],
        bbox: Any,
        *,
        frame_width: float,
        frame_height: float,
    ) -> float:
        velocity = track.get("bbox_velocity")
        if not isinstance(velocity, (list, tuple)) or len(velocity) < 2:
            return 0.0
        vx, vy = float(velocity[0]), float(velocity[1])
        speed = math.hypot(vx, vy)
        if speed <= 1e-5 or not self._valid_bbox(track.get("bbox")):
            return 0.0
        previous = self._normalized_bbox_state(track["bbox"], frame_width, frame_height)
        current = self._normalized_bbox_state(bbox, frame_width, frame_height)
        dx, dy = current[0] - previous[0], current[1] - previous[1]
        distance = math.hypot(dx, dy)
        if distance <= 1e-5:
            return 0.0
        return max(-1.0, min(1.0, (vx * dx + vy * dy) / (speed * distance)))

    def _shape_similarity(self, first: Any, second: Any) -> float:
        if not self._valid_bbox(first) or not self._valid_bbox(second):
            return 0.0
        ax1, ay1, ax2, ay2 = [float(value) for value in first]
        bx1, by1, bx2, by2 = [float(value) for value in second]
        width_ratio = max(1e-4, (ax2 - ax1) / max(1.0, bx2 - bx1))
        height_ratio = max(1e-4, (ay2 - ay1) / max(1.0, by2 - by1))
        return math.exp(-abs(math.log(width_ratio)) - abs(math.log(height_ratio)))

    def _credible_posture_transition(self, previous: Any, current: Any) -> bool:
        return bool(
            str(previous or "").lower() in UPRIGHT_POSTURES
            and str(current or "").lower() in TRACK_TRANSITION_POSTURES
        )

    def _credible_low_posture_continuity(self, previous: Any, current: Any) -> bool:
        return bool(
            str(previous or "").lower() in LOW_POSTURES
            and str(current or "").lower() in LOW_POSTURES
        )

    def _annotate_analysis(
        self,
        people: list[Dict[str, Any]],
        poses: list[Dict[str, Any]],
        assigned: list[Dict[str, Any]],
        frame_width: float,
        frame_height: float,
    ) -> None:
        for detection in assigned:
            source_item = detection.get("source_item")
            if isinstance(source_item, dict):
                source_item["track_id"] = detection["track_id"]
            pose_item = detection.get("pose_item")
            if isinstance(pose_item, dict):
                pose_item["track_id"] = detection["track_id"]
        for pose in poses:
            if pose.get("track_id") or not self._valid_bbox(pose.get("bbox")):
                continue
            best = self._nearest_assignment(pose["bbox"], assigned, frame_width, frame_height)
            if best is not None:
                pose["track_id"] = best["track_id"]
        for person in people:
            if person.get("track_id") or not self._valid_bbox(person.get("bbox")):
                continue
            best = self._nearest_assignment(person["bbox"], assigned, frame_width, frame_height)
            if best is not None:
                person["track_id"] = best["track_id"]
        for item in [*people, *poses]:
            if isinstance(item, dict):
                item.pop("_continual_track_id_hint", None)

    def _nearest_assignment(self, bbox: Any, assigned: list[Dict[str, Any]], width: float, height: float) -> Dict[str, Any] | None:
        if not assigned:
            return None
        best = min(assigned, key=lambda item: self._center_distance(bbox, item["bbox"], width, height))
        overlap = self._iou(bbox, best["bbox"])
        distance = self._center_distance(bbox, best["bbox"], width, height)
        return best if overlap >= self.min_iou or distance <= self.max_center_distance else None

    def _new_track_id(self, camera_id: int) -> str:
        value = int(self._next_track_ids.get(camera_id) or 0) + 1
        self._next_track_ids[camera_id] = value
        return f"c{camera_id}-p{value}"

    def _expire_tracks(self, tracks: dict[str, Dict[str, Any]], now_mono: float) -> list[str]:
        expired = [
            track_id
            for track_id, item in tracks.items()
            if item.get("last_seen_monotonic") is not None
            and now_mono - float(item["last_seen_monotonic"]) > self.track_ttl_seconds
        ]
        for track_id in expired:
            tracks.pop(track_id, None)
        return expired

    def _public_track(self, track: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "track_id": str(track.get("track_id") or ""),
            "first_seen_at": track.get("first_seen_at"),
            "last_seen_at": track.get("last_seen_at"),
            "bbox": track.get("bbox"),
            "confidence": round(float(track.get("confidence") or 0.0), 4),
            "posture": str(track.get("posture") or "unknown"),
            "posture_confidence": round(float(track.get("posture_confidence") or 0.0), 4),
            "sample_count": int(track.get("sample_count") or 0),
            "bbox_velocity": [round(float(value), 4) for value in track.get("bbox_velocity") or []],
        }

    def _history_track(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "track_id": str(item.get("track_id") or ""),
            "bbox": [round(float(value), 1) for value in item.get("bbox") or []],
            "posture": str(item.get("posture") or "unknown"),
            "posture_confidence": round(float(item.get("posture_confidence") or 0.0), 4),
            "normal_lying_zone": bool(item.get("normal_lying_zone")),
            "frame_edge_clipped": bool(item.get("frame_edge_clipped")),
            "scene_zone_id": item.get("scene_zone_id"),
            "scene_zone_label": item.get("scene_zone_label"),
        }

    def _role_aware_evidence_samples(
        self,
        history: list[Dict[str, Any]],
        *,
        track_id: str | None,
        limit: int,
    ) -> list[Dict[str, Any]]:
        snapshots = [(index, item) for index, item in enumerate(history) if item.get("snapshot_id")]
        if not snapshots:
            return []

        postures = [self._observation_posture(item, track_id) for item in history]
        transition_index = None
        for index in range(1, len(postures)):
            if postures[index] in LOW_POSTURES and postures[index - 1] not in LOW_POSTURES:
                transition_index = index
        if transition_index is None:
            representatives = self._representative_samples(
                [item for _index, item in snapshots],
                limit,
            )
            roles = (
                ["current"]
                if len(representatives) == 1
                else ["before", "current"]
                if len(representatives) == 2
                else ["before", "transition", "current"]
            )
            return [
                {**item, "_evidence_role": roles[index]}
                for index, item in enumerate(representatives)
            ]

        current_index, current = next(
            ((index, item) for index, item in reversed(snapshots) if index >= transition_index),
            snapshots[-1],
        )
        baseline_candidates = [
            (index, item)
            for index, item in snapshots
            if index < transition_index
            and postures[index] in EVIDENCE_BASELINE_POSTURES
            and not self._observation_edge_clipped(item, track_id)
        ]
        if not baseline_candidates:
            baseline_candidates = [
                (index, item)
                for index, item in snapshots
                if index < transition_index
                and postures[index] in UPRIGHT_POSTURES
                and not self._observation_edge_clipped(item, track_id)
            ]
        before_pair = baseline_candidates[-1] if baseline_candidates else None
        before_index = before_pair[0] if before_pair else -1

        transition_candidates = [
            (index, item)
            for index, item in snapshots
            if before_index < index < current_index
            and (before_pair is None or item.get("snapshot_id") != before_pair[1].get("snapshot_id"))
        ]
        transition_pair = max(
            transition_candidates,
            key=lambda pair: (
                -abs(pair[0] - transition_index),
                float(pair[1].get("motion_score") or 0.0),
            ),
            default=None,
        )

        selected: dict[str, Dict[str, Any]] = {"current": current}
        if before_pair is not None:
            selected["before"] = before_pair[1]
        if transition_pair is not None:
            selected["transition"] = transition_pair[1]

        used_ids = {item.get("snapshot_id") for item in selected.values()}
        remaining = [item for _index, item in snapshots if item.get("snapshot_id") not in used_ids]
        for role in ("before", "transition"):
            if role in selected or not remaining:
                continue
            candidate = remaining.pop(0 if role == "before" else -1)
            selected[role] = candidate

        role_order = (
            ("current",)
            if limit == 1
            else ("before", "current")
            if limit == 2 and "before" in selected
            else ("transition", "current")
            if limit == 2
            else ("before", "transition", "current")
        )
        return [
            {**selected[role], "_evidence_role": role}
            for role in role_order
            if role in selected
        ]

    def _observation_posture(self, observation: Dict[str, Any], track_id: str | None) -> str:
        tracks = observation.get("tracks") if isinstance(observation.get("tracks"), list) else []
        track = next(
            (item for item in tracks if not track_id or str(item.get("track_id") or "") == str(track_id)),
            None,
        )
        return str((track or {}).get("posture") or "unknown")

    def _observation_edge_clipped(self, observation: Dict[str, Any], track_id: str | None) -> bool:
        tracks = observation.get("tracks") if isinstance(observation.get("tracks"), list) else []
        track = next(
            (item for item in tracks if not track_id or str(item.get("track_id") or "") == str(track_id)),
            None,
        )
        return bool((track or {}).get("frame_edge_clipped"))

    def _representative_samples(self, items: list[Dict[str, Any]], limit: int) -> list[Dict[str, Any]]:
        if len(items) <= limit:
            return items
        if limit == 1:
            return [items[-1]]
        indices = {0, len(items) - 1}
        if limit >= 3:
            indices.add(len(items) // 2)
        return [items[index] for index in sorted(indices)][:limit]

    def _posture_sequence(self, history: list[Dict[str, Any]], track_id: str | None) -> list[Dict[str, Any]]:
        sequence: list[Dict[str, Any]] = []
        previous = None
        for observation in history:
            tracks = observation.get("tracks") if isinstance(observation.get("tracks"), list) else []
            track = next((item for item in tracks if not track_id or item.get("track_id") == track_id), None)
            posture = str((track or {}).get("posture") or "unknown")
            if posture == previous:
                continue
            sequence.append({"observed_at": observation.get("observed_at"), "posture": posture})
            previous = posture
        return sequence

    def _update_posture_states(
        self,
        camera_id: int,
        assigned: list[Dict[str, Any]],
        observed_at: str,
        monotonic_at: float,
    ) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
        states = self._posture_states.setdefault(int(camera_id), {})
        updates: list[Dict[str, Any]] = []
        closures: list[Dict[str, Any]] = []
        for item in assigned:
            track_id = str(item.get("track_id") or "")
            posture = str(item.get("posture") or "unknown")
            confidence = float(item.get("posture_confidence") or 0.0)
            if not track_id or posture == "unknown" or confidence < self.posture_min_confidence:
                continue
            state = states.setdefault(track_id, {})
            if state.get("active_posture") == posture:
                state["active_last_seen_at"] = observed_at
                state["active_sample_count"] = int(state.get("active_sample_count") or 0) + 1
                state["active_confidence_sum"] = float(state.get("active_confidence_sum") or 0.0) + confidence
                state["active_max_confidence"] = max(float(state.get("active_max_confidence") or 0.0), confidence)
                updates.append(self._episode_payload(camera_id, track_id, state, item, observed_at))
                continue

            if state.get("candidate_posture") != posture:
                state["candidate_posture"] = posture
                state["candidate_started_at"] = observed_at
                state["candidate_started_monotonic"] = monotonic_at
                state["candidate_sample_count"] = 1
                state["candidate_confidence_sum"] = confidence
                state["candidate_max_confidence"] = confidence
            else:
                state["candidate_sample_count"] = int(state.get("candidate_sample_count") or 0) + 1
                state["candidate_confidence_sum"] = float(state.get("candidate_confidence_sum") or 0.0) + confidence
                state["candidate_max_confidence"] = max(float(state.get("candidate_max_confidence") or 0.0), confidence)

            candidate_started_monotonic = state.get("candidate_started_monotonic")
            duration = max(
                0.0,
                monotonic_at - float(monotonic_at if candidate_started_monotonic is None else candidate_started_monotonic),
            )
            stable = int(state.get("candidate_sample_count") or 0) >= self.posture_min_samples and duration >= self.posture_min_duration_seconds
            if not stable:
                continue
            if state.get("active_posture"):
                closures.append({
                    "camera_id": int(camera_id),
                    "track_id": track_id,
                    "posture": state["active_posture"],
                    "ended_at": observed_at,
                    "reason": "posture_changed",
                })
            state.update({
                "active_posture": posture,
                "active_started_at": state["candidate_started_at"],
                "active_confirmed_at": observed_at,
                "active_last_seen_at": observed_at,
                "active_sample_count": int(state["candidate_sample_count"]),
                "active_confidence_sum": float(state["candidate_confidence_sum"]),
                "active_max_confidence": float(state["candidate_max_confidence"]),
                "candidate_posture": "",
            })
            updates.append(self._episode_payload(camera_id, track_id, state, item, observed_at))
        return updates, closures

    def _episode_payload(
        self,
        camera_id: int,
        track_id: str,
        state: Dict[str, Any],
        item: Dict[str, Any],
        observed_at: str,
    ) -> Dict[str, Any]:
        sample_count = max(1, int(state.get("active_sample_count") or 1))
        return {
            "camera_id": int(camera_id),
            "track_id": track_id,
            "posture": str(state.get("active_posture") or "unknown"),
            "started_at": state.get("active_started_at") or observed_at,
            "confirmed_at": state.get("active_confirmed_at") or observed_at,
            "last_seen_at": observed_at,
            "sample_count": sample_count,
            "mean_confidence": round(float(state.get("active_confidence_sum") or 0.0) / sample_count, 4),
            "max_confidence": round(float(state.get("active_max_confidence") or 0.0), 4),
            "normal_lying_zone": bool(item.get("normal_lying_zone")),
            "scene_zone_id": item.get("scene_zone_id"),
            "scene_zone_label": item.get("scene_zone_label"),
        }

    def _close_expired_postures(self, camera_id: int, track_ids: list[str], ended_at: str) -> list[Dict[str, Any]]:
        states = self._posture_states.setdefault(int(camera_id), {})
        closures = []
        for track_id in track_ids:
            state = states.pop(track_id, None) or {}
            if state.get("active_posture"):
                closures.append({
                    "camera_id": int(camera_id),
                    "track_id": track_id,
                    "posture": state["active_posture"],
                    "ended_at": ended_at,
                    "reason": "track_expired",
                })
        return closures

    def _valid_bbox(self, bbox: Any) -> bool:
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return False
        try:
            x1, y1, x2, y2 = [float(value) for value in bbox]
        except (TypeError, ValueError):
            return False
        return x2 > x1 and y2 > y1

    def _iou(self, first: Any, second: Any) -> float:
        if not self._valid_bbox(first) or not self._valid_bbox(second):
            return 0.0
        ax1, ay1, ax2, ay2 = [float(value) for value in first]
        bx1, by1, bx2, by2 = [float(value) for value in second]
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        intersection = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
        union = max(1.0, (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - intersection)
        return intersection / union

    def _center_distance(self, first: Any, second: Any, width: float, height: float) -> float:
        if not self._valid_bbox(first) or not self._valid_bbox(second):
            return math.inf
        ax1, ay1, ax2, ay2 = [float(value) for value in first]
        bx1, by1, bx2, by2 = [float(value) for value in second]
        dx = ((ax1 + ax2) - (bx1 + bx2)) / (2.0 * max(1.0, width))
        dy = ((ay1 + ay2) - (by1 + by2)) / (2.0 * max(1.0, height))
        return math.sqrt(dx * dx + dy * dy)
