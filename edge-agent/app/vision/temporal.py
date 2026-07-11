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
    ) -> None:
        self.history_size = max(8, int(history_size))
        self.track_ttl_seconds = max(2.0, float(track_ttl_seconds))
        self.min_iou = max(0.0, min(1.0, float(min_iou)))
        self.max_center_distance = max(0.01, float(max_center_distance))
        self._histories: dict[int, deque[Dict[str, Any]]] = {}
        self._tracks: dict[int, dict[str, Dict[str, Any]]] = {}
        self._next_track_ids: dict[int, int] = {}

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
        self._expire_tracks(tracks, now_mono)

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
                "sample_count": int(track.get("sample_count") or 0) + 1,
            })
            unmatched_track_ids.discard(track_id)
            assigned.append({**detection, "track_id": track_id})

        self._annotate_analysis(people, poses, assigned, frame_width, frame_height)
        active_tracks = [self._public_track(item) for item in tracks.values() if now_mono - float(item.get("last_seen_monotonic") or 0.0) <= self.track_ttl_seconds]
        current_track_ids = [str(item["track_id"]) for item in assigned]
        observation = {
            "observed_at": timestamp,
            "person_present": bool(assigned),
            "person_count": len(assigned),
            "track_ids": current_track_ids,
            "postures": sorted({str(item.get("posture") or "unknown") for item in assigned}),
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
        }
        analysis["temporal_observation"] = result
        return result

    def attach_snapshot(self, camera_id: int, snapshot: Dict[str, Any]) -> None:
        history = self._histories.get(int(camera_id))
        if not history:
            return
        history[-1]["snapshot_id"] = snapshot.get("id")
        history[-1]["snapshot_path"] = str(snapshot.get("image_path") or "")

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

    def _detections(self, people: list[Dict[str, Any]], poses: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        detections = [self._detection(item, "person") for item in people if self._valid_bbox(item.get("bbox"))]
        detections = [item for item in detections if item is not None]
        for pose in poses:
            if not self._valid_bbox(pose.get("bbox")):
                continue
            if any(self._iou(pose.get("bbox"), item.get("bbox")) >= 0.35 for item in detections):
                continue
            item = self._detection(pose, "pose")
            if item is not None:
                detections.append(item)
        return detections

    def _detection(self, item: Dict[str, Any], source: str) -> Dict[str, Any] | None:
        if not self._valid_bbox(item.get("bbox")):
            return None
        return {
            "bbox": [float(value) for value in item["bbox"]],
            "confidence": float(item.get("confidence") or item.get("score") or item.get("pose_confidence") or 0.0),
            "posture": str(item.get("posture") or "unknown"),
            "source": source,
            "source_item": item,
        }

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

    def _expire_tracks(self, tracks: dict[str, Dict[str, Any]], now_mono: float) -> None:
        expired = [track_id for track_id, item in tracks.items() if now_mono - float(item.get("last_seen_monotonic") or 0.0) > self.track_ttl_seconds]
        for track_id in expired:
            tracks.pop(track_id, None)

    def _public_track(self, track: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "track_id": str(track.get("track_id") or ""),
            "first_seen_at": track.get("first_seen_at"),
            "last_seen_at": track.get("last_seen_at"),
            "bbox": track.get("bbox"),
            "confidence": round(float(track.get("confidence") or 0.0), 4),
            "posture": str(track.get("posture") or "unknown"),
            "sample_count": int(track.get("sample_count") or 0),
        }

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
