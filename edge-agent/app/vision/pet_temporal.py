from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import math
from threading import RLock
import time
from typing import Any, Callable, Dict


PET_CLASS_IDS = {15, 16}
PET_CLASS_NAMES = {15: "cat", 16: "dog"}


@dataclass
class _PetTrack:
    bbox: list[float]
    last_detection: Dict[str, Any]
    last_seen: float
    hits: int = 0
    class_hits: Dict[int, int] = field(default_factory=dict)
    class_scores: Dict[int, float] = field(default_factory=dict)
    class_weights: Dict[int, float] = field(default_factory=dict)
    confirmed_class_id: int | None = None


class PetTemporalStabilizer:
    """Confirm and classify small pet detections across camera-local observations."""

    version = "pet-temporal-stabilizer-v2"

    def __init__(
        self,
        *,
        confirmation_hits: int = 2,
        hold_seconds: float = 2.2,
        score_decay: float = 0.82,
        class_margin: float = 0.08,
        final_class_confidence: float = 0.40,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        self.confirmation_hits = max(2, int(confirmation_hits))
        self.hold_seconds = max(0.5, float(hold_seconds))
        self.score_decay = max(0.5, min(0.98, float(score_decay)))
        self.class_margin = max(0.0, float(class_margin))
        self.final_class_confidence = max(0.0, min(1.0, float(final_class_confidence)))
        self._clock = monotonic_clock or time.monotonic
        self._tracks: dict[str, list[_PetTrack]] = {}
        self._lock = RLock()

    def update(
        self,
        camera_id: Any,
        detections: list[Dict[str, Any]],
        *,
        now: float | None = None,
    ) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
        observed_at = float(self._clock() if now is None else now)
        with self._lock:
            return self._update_locked(camera_id, detections, observed_at=observed_at)

    def _update_locked(
        self,
        camera_id: Any,
        detections: list[Dict[str, Any]],
        *,
        observed_at: float,
    ) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
        camera_key = str(camera_id)
        passthrough = [
            deepcopy(item)
            for item in detections
            if int(item.get("class_id") or -1) not in PET_CLASS_IDS
        ]
        candidates = [
            deepcopy(item)
            for item in detections
            if int(item.get("class_id") or -1) in PET_CLASS_IDS
            and self._valid_bbox(item.get("bbox"))
        ]
        tracks = [
            track
            for track in self._tracks.get(camera_key, [])
            if observed_at - track.last_seen <= self.hold_seconds
        ]
        for track in tracks:
            track.class_scores = {
                class_id: score * self.score_decay
                for class_id, score in track.class_scores.items()
            }
            track.class_weights = {
                class_id: weight * self.score_decay
                for class_id, weight in track.class_weights.items()
            }

        used_tracks: set[int] = set()
        groups = self._candidate_groups(candidates)
        for group in groups:
            candidate = max(group, key=lambda item: float(item.get("confidence") or 0.0))
            match_index = self._best_track(candidate, tracks, used_tracks)
            if match_index is None:
                track = _PetTrack(
                    bbox=[float(value) for value in candidate["bbox"]],
                    last_detection=deepcopy(candidate),
                    last_seen=observed_at,
                )
                tracks.append(track)
                match_index = len(tracks) - 1
            used_tracks.add(match_index)
            self._observe(tracks[match_index], group, observed_at)

        confirmed = []
        rejected_low_confidence = 0
        for track in tracks:
            self._update_confirmation(track)
            class_id = track.confirmed_class_id
            if class_id is None or observed_at - track.last_seen > self.hold_seconds:
                continue
            class_confidence = self._class_confidence(track, class_id)
            if class_confidence < self.final_class_confidence:
                rejected_low_confidence += 1
                continue
            output = deepcopy(track.last_detection)
            output["class_id"] = class_id
            output["bbox"] = list(track.bbox)
            output["confidence"] = round(class_confidence, 4)
            output["temporal_confirmed"] = True
            output["temporal_hits"] = int(track.class_hits.get(class_id, 0))
            output["temporal_cached"] = bool(observed_at > track.last_seen)
            confirmed.append(output)

        self._tracks[camera_key] = tracks[:8]
        uncertain_count = sum(1 for track in tracks if self._uncertain_track(track))
        return [*passthrough, *confirmed], {
            "schema_version": self.version,
            "candidate_count": len(candidates),
            "observation_count": len(groups),
            "track_count": len(tracks),
            "confirmed_count": len(confirmed),
            "uncertain_count": uncertain_count,
            "rejected_low_confidence_count": rejected_low_confidence,
        }

    def reset_camera(self, camera_id: Any) -> None:
        with self._lock:
            self._tracks.pop(str(camera_id), None)

    def reset(self) -> None:
        with self._lock:
            self._tracks.clear()

    def status(self, *, now: float | None = None) -> Dict[str, Any]:
        current = float(self._clock() if now is None else now)
        with self._lock:
            tracks = [track for camera_tracks in self._tracks.values() for track in camera_tracks]
            return {
                "schema_version": self.version,
                "camera_count": len(self._tracks),
                "track_count": len(tracks),
                "uncertain_track_count": sum(1 for track in tracks if self._uncertain_track(track)),
                "confirmation_hits": self.confirmation_hits,
                "hold_seconds": self.hold_seconds,
                "final_class_confidence": self.final_class_confidence,
                "cameras": [
                    self._camera_status_locked(camera_key, camera_tracks, current=current)
                    for camera_key, camera_tracks in sorted(self._tracks.items())
                ],
            }

    def _camera_status_locked(
        self,
        camera_key: str,
        tracks: list[_PetTrack],
        *,
        current: float,
    ) -> Dict[str, Any]:
        return {
            "camera_id": int(camera_key) if camera_key.isdigit() else camera_key,
            "track_count": len(tracks),
            "confirmed_count": sum(1 for track in tracks if track.confirmed_class_id is not None),
            "uncertain_count": sum(1 for track in tracks if self._uncertain_track(track)),
            "tracks": [
                {
                    "confirmed_class_id": track.confirmed_class_id,
                    "confirmed_category": PET_CLASS_NAMES.get(track.confirmed_class_id),
                    "confirmed_confidence": (
                        None
                        if track.confirmed_class_id is None
                        else round(self._class_confidence(track, track.confirmed_class_id), 4)
                    ),
                    "hits": int(track.hits),
                    "last_seen_age_seconds": round(max(0.0, current - track.last_seen), 3),
                    "class_evidence": [
                        {
                            "class_id": class_id,
                            "category": PET_CLASS_NAMES.get(class_id),
                            "hits": int(track.class_hits.get(class_id, 0)),
                            "confidence": round(self._class_confidence(track, class_id), 4),
                        }
                        for class_id in sorted(track.class_scores)
                    ],
                }
                for track in tracks
            ],
        }

    def _observe(self, track: _PetTrack, group: list[Dict[str, Any]], observed_at: float) -> None:
        detection = max(group, key=lambda item: float(item.get("confidence") or 0.0))
        track.bbox = [float(value) for value in detection["bbox"]]
        track.last_detection = deepcopy(detection)
        track.last_seen = observed_at
        track.hits += 1
        for candidate in group:
            class_id = int(candidate.get("class_id") or -1)
            confidence = max(0.0, min(1.0, float(candidate.get("confidence") or 0.0)))
            track.class_hits[class_id] = int(track.class_hits.get(class_id, 0)) + 1
            track.class_scores[class_id] = float(track.class_scores.get(class_id, 0.0)) + confidence
            track.class_weights[class_id] = float(track.class_weights.get(class_id, 0.0)) + 1.0

    def _candidate_groups(self, candidates: list[Dict[str, Any]]) -> list[list[Dict[str, Any]]]:
        groups: list[list[Dict[str, Any]]] = []
        for candidate in sorted(candidates, key=lambda item: float(item.get("confidence") or 0.0), reverse=True):
            bbox = [float(value) for value in candidate["bbox"]]
            group = next((
                current
                for current in groups
                if self._iou(bbox, [float(value) for value in current[0]["bbox"]]) >= 0.55
            ), None)
            if group is None:
                groups.append([candidate])
            else:
                group.append(candidate)
        return groups

    def _update_confirmation(self, track: _PetTrack) -> None:
        ranked = sorted(track.class_scores.items(), key=lambda item: item[1], reverse=True)
        if not ranked:
            return
        winner_id, winner_score = ranked[0]
        runner_score = ranked[1][1] if len(ranked) > 1 else 0.0
        winner_hits = int(track.class_hits.get(winner_id, 0))
        winner_confidence = self._class_confidence(track, winner_id)
        if track.confirmed_class_id is None:
            if (
                winner_hits >= self.confirmation_hits
                and winner_score - runner_score >= self.class_margin
                and winner_confidence >= self.final_class_confidence
            ):
                track.confirmed_class_id = int(winner_id)
            return
        if winner_id == track.confirmed_class_id:
            return
        current_score = float(track.class_scores.get(track.confirmed_class_id, 0.0))
        if (
            winner_hits >= self.confirmation_hits + 1
            and winner_score >= current_score * 1.35
            and winner_confidence >= self.final_class_confidence
        ):
            track.confirmed_class_id = int(winner_id)

    def _best_track(
        self,
        detection: Dict[str, Any],
        tracks: list[_PetTrack],
        used_tracks: set[int],
    ) -> int | None:
        bbox = [float(value) for value in detection["bbox"]]
        scored = []
        for index, track in enumerate(tracks):
            if index in used_tracks:
                continue
            overlap = self._iou(bbox, track.bbox)
            proximity = self._center_proximity(bbox, track.bbox)
            if overlap < 0.12 and proximity <= 0.0:
                continue
            scored.append((overlap * 2.0 + proximity, index))
        return max(scored, default=(0.0, None))[1]

    def _class_confidence(self, track: _PetTrack, class_id: int) -> float:
        weight = max(1e-6, float(track.class_weights.get(class_id, 0.0)))
        return max(0.0, min(1.0, float(track.class_scores.get(class_id, 0.0)) / weight))

    def _uncertain_track(self, track: _PetTrack) -> bool:
        if track.confirmed_class_id is not None or not track.class_scores:
            return False
        winner_id = max(track.class_scores, key=track.class_scores.get)
        return (
            int(track.class_hits.get(winner_id, 0)) >= self.confirmation_hits
            and self._class_confidence(track, winner_id) < self.final_class_confidence
        )

    def _iou(self, first: list[float], second: list[float]) -> float:
        width = max(0.0, min(first[2], second[2]) - max(first[0], second[0]))
        height = max(0.0, min(first[3], second[3]) - max(first[1], second[1]))
        intersection = width * height
        union = self._area(first) + self._area(second) - intersection
        return intersection / max(1.0, union)

    def _center_proximity(self, first: list[float], second: list[float]) -> float:
        first_center = ((first[0] + first[2]) * 0.5, (first[1] + first[3]) * 0.5)
        second_center = ((second[0] + second[2]) * 0.5, (second[1] + second[3]) * 0.5)
        distance = math.hypot(first_center[0] - second_center[0], first_center[1] - second_center[1])
        scale = max(
            first[2] - first[0],
            first[3] - first[1],
            second[2] - second[0],
            second[3] - second[1],
            1.0,
        )
        return max(0.0, 1.0 - distance / (scale * 1.25))

    def _area(self, bbox: list[float]) -> float:
        return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])

    def _valid_bbox(self, bbox: Any) -> bool:
        if not isinstance(bbox, list) or len(bbox) != 4:
            return False
        try:
            values = [float(value) for value in bbox]
        except (TypeError, ValueError):
            return False
        return all(math.isfinite(value) for value in values) and values[2] > values[0] and values[3] > values[1]
