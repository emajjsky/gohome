from __future__ import annotations

from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
import math
import time
from typing import Any, Dict


class TemporalObservationEngine:
    """Maintains compact per-camera tracks and a bounded observation history."""

    version = "temporal-observation-v1"

    def __init__(
        self,
        *,
        history_size: int = 48,
        track_ttl_seconds: float = 20.0,
        min_iou: float = 0.12,
        max_center_distance: float = 0.24,
        posture_min_duration_seconds: float = 3.0,
        posture_min_samples: int = 2,
        posture_min_confidence: float = 0.40,
    ) -> None:
        self.history_size = max(8, int(history_size))
        self.track_ttl_seconds = max(2.0, float(track_ttl_seconds))
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

        unmatched_track_ids = set(tracks)
        assigned: list[Dict[str, Any]] = []
        for detection in sorted(detections, key=lambda item: float(item.get("confidence") or 0.0), reverse=True):
            track_id = self._match_track(
                detection,
                tracks,
                unmatched_track_ids,
                frame_width=frame_width,
                frame_height=frame_height,
            )
            if track_id is None:
                track_id = self._new_track_id(camera_id)
                tracks[track_id] = {
                    "track_id": track_id,
                    "first_seen_at": timestamp,
                    "sample_count": 0,
                }
            track = tracks[track_id]
            track.update({
                "last_seen_at": timestamp,
                "last_seen_monotonic": now_mono,
                "bbox": list(detection["bbox"]),
                "confidence": float(detection.get("confidence") or 0.0),
                "source": str(detection.get("source") or "person"),
                "posture": str(detection.get("posture") or "unknown"),
                "posture_confidence": float(detection.get("posture_confidence") or 0.0),
                "sample_count": int(track.get("sample_count") or 0) + 1,
            })
            unmatched_track_ids.discard(track_id)
            assigned.append({**detection, "track_id": track_id})

        self._annotate_analysis(people, poses, assigned, frame_width, frame_height)
        episode_updates, switched_closures = self._update_posture_states(camera_id, assigned, timestamp, now_mono)
        episode_closures.extend(switched_closures)
        active_tracks = [self._public_track(item) for item in tracks.values() if now_mono - float(item.get("last_seen_monotonic") or 0.0) <= self.track_ttl_seconds]
        current_track_ids = [str(item["track_id"]) for item in assigned]
        observation = {
            "observed_at": timestamp,
            "person_present": bool(assigned),
            "person_count": len(assigned),
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
            "camera_id": camera_id,
            "person_present": observation["person_present"],
            "person_count": observation["person_count"],
            "current_track_ids": current_track_ids,
            "active_tracks": sorted(active_tracks, key=lambda item: item["track_id"]),
            "history_sample_count": len(history),
            "history_capacity": self.history_size,
            "posture_episode_updates": episode_updates,
            "posture_episode_closures": episode_closures,
        }
        analysis["temporal_observation"] = result
        return result

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
    ) -> Dict[str, Any]:
        history = list(self._histories.get(int(camera_id), ()))
        if track_id:
            history = [item for item in history if str(track_id) in (item.get("track_ids") or [])]
        snapshots = [item for item in history if item.get("snapshot_id")]
        selected = self._representative_samples(snapshots, max(1, min(3, int(limit))))
        return {
            "schema_version": "temporal-evidence-bundle-v1",
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
        for person in people:
            if not self._valid_bbox(person.get("bbox")):
                continue
            matching_pose = self._best_overlapping_pose(person.get("bbox"), poses)
            item = self._detection(person, "person", posture_source=matching_pose)
            if item is not None:
                detections.append(item)
        for pose in poses:
            if not self._valid_bbox(pose.get("bbox")):
                continue
            if any(self._iou(pose.get("bbox"), item.get("bbox")) >= 0.35 for item in detections):
                continue
            item = self._detection(pose, "pose", posture_source=pose)
            if item is not None:
                detections.append(item)
        return detections

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
            "source_item": item,
            "pose_item": posture_source,
        }

    def _best_overlapping_pose(self, bbox: Any, poses: list[Dict[str, Any]]) -> Dict[str, Any] | None:
        candidates = [pose for pose in poses if self._valid_bbox(pose.get("bbox"))]
        if not candidates:
            return None
        best = max(candidates, key=lambda pose: self._iou(bbox, pose.get("bbox")))
        return best if self._iou(bbox, best.get("bbox")) >= 0.20 else None

    def _match_track(
        self,
        detection: Dict[str, Any],
        tracks: dict[str, Dict[str, Any]],
        candidates: set[str],
        *,
        frame_width: float,
        frame_height: float,
    ) -> str | None:
        best_id = None
        best_score = -1.0
        for track_id in candidates:
            track = tracks[track_id]
            overlap = self._iou(detection["bbox"], track.get("bbox"))
            distance = self._center_distance(detection["bbox"], track.get("bbox"), frame_width, frame_height)
            if overlap < self.min_iou and distance > self.max_center_distance:
                continue
            score = overlap * 2.0 + max(0.0, self.max_center_distance - distance)
            if score > best_score:
                best_id = track_id
                best_score = score
        return best_id

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
        }

    def _history_track(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "track_id": str(item.get("track_id") or ""),
            "bbox": [round(float(value), 1) for value in item.get("bbox") or []],
            "posture": str(item.get("posture") or "unknown"),
            "posture_confidence": round(float(item.get("posture_confidence") or 0.0), 4),
            "normal_lying_zone": bool(item.get("normal_lying_zone")),
            "scene_zone_id": item.get("scene_zone_id"),
            "scene_zone_label": item.get("scene_zone_label"),
        }

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
