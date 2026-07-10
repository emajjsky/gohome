from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


NORMAL_LYING_SURFACES = {"bed", "couch"}
SCENE_LABELS_ZH = {
    "bed": "床",
    "couch": "沙发",
    "chair": "椅子",
    "dining_table": "餐桌",
}


class SceneContextTracker:
    def __init__(self) -> None:
        self._tracks: dict[str, list[Dict[str, Any]]] = {}

    def update(self, objects: list[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
        if not config.get("scene_context_enabled", True):
            return self._result(objects, [], "disabled")

        objects = self._coalesce_objects(objects)
        camera_id = str(config.get("camera_id") or "").strip()
        if not camera_id:
            return self._result(objects, [], "single_frame")

        min_hits = max(2, int(config.get("scene_stable_min_hits") or 2))
        max_misses = max(1, int(config.get("scene_stable_max_misses") or 12))
        match_iou = float(config.get("scene_stable_match_iou") or 0.45)
        smoothing = min(0.8, max(0.05, float(config.get("scene_bbox_smoothing") or 0.30)))
        tracks = [deepcopy(item) for item in self._tracks.get(camera_id, [])]
        matched_tracks: set[int] = set()

        for detected in objects:
            best_index = None
            best_iou = 0.0
            for index, track in enumerate(tracks):
                if index in matched_tracks or track.get("label") != detected.get("label"):
                    continue
                overlap = self._box_iou(track.get("bbox"), detected.get("bbox"))
                if overlap >= match_iou and overlap > best_iou:
                    best_iou = overlap
                    best_index = index
            if best_index is None:
                tracks.append({**detected, "hits": 1, "misses": 0})
                matched_tracks.add(len(tracks) - 1)
                continue
            previous = tracks[best_index]
            tracks[best_index] = {
                **previous,
                **detected,
                "bbox": self._smooth_box(previous.get("bbox"), detected.get("bbox"), smoothing),
                "confidence": round(max(float(previous.get("confidence") or 0.0), float(detected.get("confidence") or 0.0)), 4),
                "hits": int(previous.get("hits") or 0) + 1,
                "misses": 0,
            }
            matched_tracks.add(best_index)

        retained = []
        for index, track in enumerate(tracks):
            if index not in matched_tracks:
                track["misses"] = int(track.get("misses") or 0) + 1
            if int(track.get("misses") or 0) <= max_misses:
                retained.append(track)
        self._tracks[camera_id] = retained

        stable_zones = []
        for index, track in enumerate(retained):
            if int(track.get("hits") or 0) < min_hits:
                continue
            label = str(track.get("label") or "")
            stable_zones.append({
                **track,
                "id": f"{label}-{index + 1}",
                "label_zh": SCENE_LABELS_ZH.get(label, label),
                "stable": True,
                "zone_kind": "normal_lying_surface" if label in NORMAL_LYING_SURFACES else "scene_furniture",
            })
        status = "stable" if stable_zones else "learning" if objects or retained else "empty"
        return self._result(objects, stable_zones, status)

    def annotate(
        self,
        people: list[Dict[str, Any]],
        poses: list[Dict[str, Any]],
        zones: list[Dict[str, Any]],
    ) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
        normal_zones = [zone for zone in zones if zone.get("zone_kind") == "normal_lying_surface"]
        annotated_poses = [self._annotate_target(pose, normal_zones, posture=str(pose.get("posture") or "")) for pose in poses]
        annotated_people = [self._annotate_target(person, normal_zones, posture="") for person in people]
        return annotated_people, annotated_poses

    def _annotate_target(
        self,
        target: Dict[str, Any],
        zones: list[Dict[str, Any]],
        *,
        posture: str,
    ) -> Dict[str, Any]:
        annotated = {**target}
        can_be_lying = posture in {"lying", "low_body"} or bool(target.get("fall_candidate"))
        if not can_be_lying:
            annotated["normal_lying_zone"] = False
            return annotated
        best_zone = None
        best_overlap = 0.0
        for zone in zones:
            overlap = self._target_overlap(target.get("bbox"), zone.get("bbox"))
            if overlap > best_overlap:
                best_overlap = overlap
                best_zone = zone
        if best_zone is None or best_overlap < 0.28:
            annotated["normal_lying_zone"] = False
            return annotated
        annotated.update({
            "normal_lying_zone": True,
            "scene_zone_id": best_zone.get("id"),
            "scene_zone_label": best_zone.get("label"),
            "scene_zone_label_zh": best_zone.get("label_zh"),
            "scene_zone_bbox": best_zone.get("bbox"),
            "scene_zone_overlap": round(best_overlap, 4),
        })
        return annotated

    def _result(self, objects: list[Dict[str, Any]], zones: list[Dict[str, Any]], status: str) -> Dict[str, Any]:
        normal_zones = [zone for zone in zones if zone.get("zone_kind") == "normal_lying_surface"]
        return {
            "scene_objects": objects,
            "scene_zones": zones,
            "normal_lying_zones": normal_zones,
            "scene_map_status": status,
        }

    def _smooth_box(self, previous: Any, current: Any, weight: float) -> list[float]:
        if not self._valid_box(previous):
            return [round(float(value), 1) for value in current]
        if not self._valid_box(current):
            return [round(float(value), 1) for value in previous]
        return [
            round(float(old) * (1.0 - weight) + float(new) * weight, 1)
            for old, new in zip(previous, current)
        ]

    def _coalesce_objects(self, objects: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        merged: list[Dict[str, Any]] = []
        for detected in sorted(objects, key=lambda item: self._box_area(item.get("bbox")), reverse=True):
            match_index = None
            for index, existing in enumerate(merged):
                if existing.get("label") != detected.get("label"):
                    continue
                if self._box_iou(existing.get("bbox"), detected.get("bbox")) >= 0.30 or self._containment(existing.get("bbox"), detected.get("bbox")) >= 0.65:
                    match_index = index
                    break
            if match_index is None:
                merged.append({**detected})
                continue
            existing = merged[match_index]
            keep = existing if self._box_area(existing.get("bbox")) >= self._box_area(detected.get("bbox")) else detected
            merged[match_index] = {
                **keep,
                "confidence": round(max(float(existing.get("confidence") or 0.0), float(detected.get("confidence") or 0.0)), 4),
            }
        return merged

    def _containment(self, first: Any, second: Any) -> float:
        if not self._valid_box(first) or not self._valid_box(second):
            return 0.0
        ax1, ay1, ax2, ay2 = [float(value) for value in first]
        bx1, by1, bx2, by2 = [float(value) for value in second]
        intersection = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(0.0, min(ay2, by2) - max(ay1, by1))
        return intersection / max(1.0, min(self._box_area(first), self._box_area(second)))

    def _box_area(self, bbox: Any) -> float:
        if not self._valid_box(bbox):
            return 0.0
        x1, y1, x2, y2 = [float(value) for value in bbox]
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)

    def _target_overlap(self, target: Any, zone: Any) -> float:
        if not self._valid_box(target) or not self._valid_box(zone):
            return 0.0
        tx1, ty1, tx2, ty2 = [float(value) for value in target]
        zx1, zy1, zx2, zy2 = [float(value) for value in zone]
        intersection = max(0.0, min(tx2, zx2) - max(tx1, zx1)) * max(0.0, min(ty2, zy2) - max(ty1, zy1))
        target_area = max(1.0, (tx2 - tx1) * (ty2 - ty1))
        return intersection / target_area

    def _box_iou(self, first: Any, second: Any) -> float:
        if not self._valid_box(first) or not self._valid_box(second):
            return 0.0
        ax1, ay1, ax2, ay2 = [float(value) for value in first]
        bx1, by1, bx2, by2 = [float(value) for value in second]
        intersection = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(0.0, min(ay2, by2) - max(ay1, by1))
        first_area = max(1.0, (ax2 - ax1) * (ay2 - ay1))
        second_area = max(1.0, (bx2 - bx1) * (by2 - by1))
        return intersection / max(1.0, first_area + second_area - intersection)

    def _valid_box(self, bbox: Any) -> bool:
        if not isinstance(bbox, list) or len(bbox) != 4:
            return False
        try:
            x1, y1, x2, y2 = [float(value) for value in bbox]
        except (TypeError, ValueError):
            return False
        return x2 > x1 and y2 > y1
