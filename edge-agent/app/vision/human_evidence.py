from __future__ import annotations

from copy import deepcopy
from threading import RLock
import time
from typing import Any, Callable, Dict


class HumanEvidenceGate:
    """Activate person tracks from motion, then retain them while detections stay continuous."""

    version = "human-evidence-gate-v1"

    def __init__(
        self,
        *,
        activation_motion: float = 0.012,
        activation_displacement: float = 0.012,
        track_max_gap_seconds: float = 2.5,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        self.activation_motion = max(0.001, float(activation_motion))
        self.activation_displacement = max(0.002, float(activation_displacement))
        self.track_max_gap_seconds = max(0.5, float(track_max_gap_seconds))
        self._clock = monotonic_clock or time.monotonic
        self._tracks: dict[str, list[Dict[str, Any]]] = {}
        self._lock = RLock()

    def evaluate(
        self,
        camera_id: Any,
        bbox: Any,
        *,
        frame_width: float,
        frame_height: float,
        frame_motion: float,
        independent_person_matched: bool,
        candidate_quality_ok: bool,
    ) -> Dict[str, Any]:
        now = float(self._clock())
        camera_key = str(camera_id or "__default__")
        normalized_bbox = self._normalized_bbox(bbox)
        if normalized_bbox is None:
            return {"confirmed": False, "reason": "invalid_bbox"}

        with self._lock:
            tracks = self._tracks.setdefault(camera_key, [])
            tracks[:] = [
                track
                for track in tracks
                if now - float(track.get("last_seen_at") or 0.0) <= self.track_max_gap_seconds
            ]
            track = self._matching_track(tracks, normalized_bbox)
            created = track is None
            if track is None:
                track = {
                    "bbox": normalized_bbox,
                    "first_seen_at": now,
                    "last_seen_at": now,
                    "confirmed": False,
                    "activation_count": 0,
                }
                tracks.append(track)

            displacement = self._center_displacement(
                track.get("bbox"),
                normalized_bbox,
                frame_width=frame_width,
                frame_height=frame_height,
            )
            motion_present = float(frame_motion) >= self.activation_motion
            moved = displacement >= self.activation_displacement
            activation = (
                candidate_quality_ok
                and motion_present
                and (created or moved)
                and (independent_person_matched or moved)
            )
            if activation:
                track["confirmed"] = True
                track["activation_count"] = int(track.get("activation_count") or 0) + 1
                track["last_activated_at"] = now

            track["bbox"] = normalized_bbox
            track["last_seen_at"] = now
            track["independent_person_matched"] = bool(independent_person_matched)
            track["last_motion"] = round(float(frame_motion), 5)
            track["last_displacement"] = round(displacement, 5)
            confirmed = bool(track.get("confirmed"))
            return {
                "confirmed": confirmed,
                "reason": (
                    "motion_activated"
                    if activation
                    else "confirmed_track"
                    if confirmed
                    else "waiting_for_human_motion"
                ),
                "created": created,
                "frame_motion": round(float(frame_motion), 5),
                "normalized_displacement": round(displacement, 5),
                "track_age_seconds": round(max(0.0, now - float(track["first_seen_at"])), 3),
                "independent_person_matched": bool(independent_person_matched),
            }

    def reset(self, camera_id: Any | None = None) -> None:
        with self._lock:
            if camera_id is None:
                self._tracks.clear()
            else:
                self._tracks.pop(str(camera_id or "__default__"), None)

    def status(self) -> Dict[str, Any]:
        now = float(self._clock())
        with self._lock:
            cameras = []
            for camera_id, tracks in self._tracks.items():
                active = [
                    deepcopy(track)
                    for track in tracks
                    if now - float(track.get("last_seen_at") or 0.0) <= self.track_max_gap_seconds
                ]
                cameras.append({
                    "camera_id": camera_id,
                    "track_count": len(active),
                    "confirmed_count": sum(1 for track in active if track.get("confirmed")),
                })
            return {
                "schema_version": self.version,
                "activation_motion": self.activation_motion,
                "activation_displacement": self.activation_displacement,
                "track_max_gap_seconds": self.track_max_gap_seconds,
                "cameras": cameras,
            }

    @staticmethod
    def _normalized_bbox(bbox: Any) -> list[float] | None:
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return None
        try:
            values = [float(value) for value in bbox]
        except (TypeError, ValueError):
            return None
        if values[2] <= values[0] or values[3] <= values[1]:
            return None
        return values

    def _matching_track(
        self,
        tracks: list[Dict[str, Any]],
        bbox: list[float],
    ) -> Dict[str, Any] | None:
        ranked = [
            (self._overlap_ratio(track.get("bbox"), bbox), track)
            for track in tracks
        ]
        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked[0][1] if ranked and ranked[0][0] >= 0.35 else None

    @staticmethod
    def _overlap_ratio(first: Any, second: Any) -> float:
        if not first or not second:
            return 0.0
        ax1, ay1, ax2, ay2 = [float(value) for value in first]
        bx1, by1, bx2, by2 = [float(value) for value in second]
        intersection = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(0.0, min(ay2, by2) - max(ay1, by1))
        if intersection <= 0.0:
            return 0.0
        first_area = max(1.0, (ax2 - ax1) * (ay2 - ay1))
        second_area = max(1.0, (bx2 - bx1) * (by2 - by1))
        return intersection / min(first_area, second_area)

    @staticmethod
    def _center_displacement(
        previous: Any,
        current: list[float],
        *,
        frame_width: float,
        frame_height: float,
    ) -> float:
        if not previous or frame_width <= 0.0 or frame_height <= 0.0:
            return 0.0
        px1, py1, px2, py2 = [float(value) for value in previous]
        cx1, cy1, cx2, cy2 = current
        dx = ((cx1 + cx2) - (px1 + px2)) / 2.0
        dy = ((cy1 + cy2) - (py1 + py2)) / 2.0
        diagonal = max(1.0, (frame_width * frame_width + frame_height * frame_height) ** 0.5)
        return (dx * dx + dy * dy) ** 0.5 / diagonal
