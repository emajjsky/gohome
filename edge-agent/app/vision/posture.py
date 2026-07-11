from __future__ import annotations

import math
from typing import Any, Dict


POSTURE_LABELS = {
    "standing",
    "sitting",
    "squatting",
    "bending",
    "lying",
    "upper_body",
    "unknown",
}

LEGACY_POSTURE_MAP = {
    "standing": "standing_or_sitting",
    "sitting": "seated_or_half_body",
    "squatting": "low_body",
    "bending": "standing_or_sitting",
    "lying": "lying",
    "upper_body": "upper_body",
    "unknown": "unknown",
}


class PostureClassifier:
    """Interpretable posture baseline built from COCO body keypoint geometry."""

    version = "posture-geometry-v1"

    def classify(self, keypoints: list[Dict[str, Any]]) -> Dict[str, Any]:
        visible = {
            str(point.get("name") or ""): point
            for point in keypoints
            if point.get("visible") and point.get("name")
        }
        visible_points = list(visible.values())
        if len(visible_points) < 4:
            return self._result("unknown", 0.0, {"reason": "insufficient_keypoints", "visible_keypoints": len(visible_points)})

        shoulders = self._points(visible, "left_shoulder", "right_shoulder")
        hips = self._points(visible, "left_hip", "right_hip")
        knees = self._points(visible, "left_knee", "right_knee")
        ankles = self._points(visible, "left_ankle", "right_ankle")
        shoulder_mid = self._midpoint(shoulders)
        hip_mid = self._midpoint(hips)
        knee_mid = self._midpoint(knees)
        ankle_mid = self._midpoint(ankles)
        xs = [float(point["x"]) for point in visible_points]
        ys = [float(point["y"]) for point in visible_points]
        body_width = max(xs) - min(xs)
        body_height = max(1.0, max(ys) - min(ys))
        body_aspect = body_width / body_height
        torso_angle = self._angle_from_vertical(shoulder_mid, hip_mid)
        knee_angles = self._joint_angles(visible, "hip", "knee", "ankle")
        mean_knee_angle = sum(knee_angles) / len(knee_angles) if knee_angles else None
        leg_vertical_ratio = None
        if hip_mid and ankle_mid:
            leg_vertical_ratio = abs(float(ankle_mid[1]) - float(hip_mid[1])) / body_height
        hip_knee_vertical_ratio = None
        if hip_mid and knee_mid:
            hip_knee_vertical_ratio = abs(float(knee_mid[1]) - float(hip_mid[1])) / body_height
        hip_spread = self._horizontal_spread(hips)
        knee_spread = self._horizontal_spread(knees)
        knee_hip_spread_ratio = None
        if hip_spread is not None and knee_spread is not None:
            knee_hip_spread_ratio = knee_spread / max(1.0, hip_spread)

        factors = {
            "visible_keypoints": len(visible_points),
            "body_aspect": round(body_aspect, 4),
            "torso_angle_from_vertical": self._round(torso_angle),
            "mean_knee_angle": self._round(mean_knee_angle),
            "leg_vertical_ratio": self._round(leg_vertical_ratio),
            "hip_knee_vertical_ratio": self._round(hip_knee_vertical_ratio),
            "knee_hip_spread_ratio": self._round(knee_hip_spread_ratio),
            "shoulders_visible": len(shoulders),
            "hips_visible": len(hips),
            "knees_visible": len(knees),
            "ankles_visible": len(ankles),
        }

        pose_confidence = self._mean_confidence(visible_points)
        if self._is_lying(body_aspect, torso_angle, shoulders, hips):
            margin = max(body_aspect / 1.35, (torso_angle or 0.0) / 58.0)
            return self._result("lying", self._confidence(pose_confidence, 0.72, margin), factors)

        if not shoulders or not hips:
            return self._result("upper_body", self._confidence(pose_confidence, 0.52, 1.0), factors)

        if torso_angle is not None and 28.0 <= torso_angle < 68.0 and (mean_knee_angle is None or mean_knee_angle >= 120.0):
            margin = min(1.4, torso_angle / 36.0)
            return self._result("bending", self._confidence(pose_confidence, 0.62, margin), factors)

        if mean_knee_angle is not None:
            compact_legs = leg_vertical_ratio is not None and leg_vertical_ratio <= 0.50
            hips_near_knees = hip_knee_vertical_ratio is not None and hip_knee_vertical_ratio <= 0.24
            knees_wider_than_hips = knee_hip_spread_ratio is not None and knee_hip_spread_ratio >= 1.35
            if len(ankles) >= 1 and mean_knee_angle <= 112.0 and compact_legs and hips_near_knees and knees_wider_than_hips:
                margin = min(1.5, (112.0 - mean_knee_angle) / 35.0 + 0.8)
                return self._result("squatting", self._confidence(pose_confidence, 0.66, margin), factors)
            if mean_knee_angle <= 145.0:
                margin = min(1.4, (145.0 - mean_knee_angle) / 45.0 + 0.65)
                return self._result("sitting", self._confidence(pose_confidence, 0.64, margin), factors)

        if knees and not ankles and (torso_angle is None or torso_angle < 28.0):
            return self._result("sitting", self._confidence(pose_confidence, 0.54, 1.0), factors)

        if knees or ankles:
            upright_margin = 1.0 if torso_angle is None else max(0.6, 1.25 - torso_angle / 45.0)
            straight_margin = 1.0 if mean_knee_angle is None else min(1.3, mean_knee_angle / 155.0)
            return self._result("standing", self._confidence(pose_confidence, 0.64, min(upright_margin, straight_margin)), factors)

        return self._result("upper_body", self._confidence(pose_confidence, 0.48, 1.0), factors)

    def _is_lying(
        self,
        body_aspect: float,
        torso_angle: float | None,
        shoulders: list[Dict[str, Any]],
        hips: list[Dict[str, Any]],
    ) -> bool:
        if body_aspect >= 1.45:
            return True
        if shoulders and hips and torso_angle is not None and torso_angle >= 62.0:
            return True
        return body_aspect >= 1.10 and torso_angle is not None and torso_angle >= 52.0

    def _joint_angles(self, points: Dict[str, Dict[str, Any]], first: str, vertex: str, third: str) -> list[float]:
        values = []
        for side in ("left", "right"):
            a = points.get(f"{side}_{first}")
            b = points.get(f"{side}_{vertex}")
            c = points.get(f"{side}_{third}")
            angle = self._angle(a, b, c)
            if angle is not None:
                values.append(angle)
        return values

    def _angle(self, first: Any, vertex: Any, third: Any) -> float | None:
        if not first or not vertex or not third:
            return None
        ax = float(first["x"]) - float(vertex["x"])
        ay = float(first["y"]) - float(vertex["y"])
        bx = float(third["x"]) - float(vertex["x"])
        by = float(third["y"]) - float(vertex["y"])
        denominator = math.sqrt(ax * ax + ay * ay) * math.sqrt(bx * bx + by * by)
        if denominator <= 1e-6:
            return None
        cosine = max(-1.0, min(1.0, (ax * bx + ay * by) / denominator))
        return math.degrees(math.acos(cosine))

    def _angle_from_vertical(self, first: Any, second: Any) -> float | None:
        if not first or not second:
            return None
        dx = abs(float(second[0]) - float(first[0]))
        dy = abs(float(second[1]) - float(first[1]))
        if dx <= 1e-6 and dy <= 1e-6:
            return None
        return math.degrees(math.atan2(dx, max(1e-6, dy)))

    def _points(self, points: Dict[str, Dict[str, Any]], *names: str) -> list[Dict[str, Any]]:
        return [points[name] for name in names if name in points]

    def _midpoint(self, points: list[Dict[str, Any]]) -> tuple[float, float] | None:
        if not points:
            return None
        return (
            sum(float(point["x"]) for point in points) / len(points),
            sum(float(point["y"]) for point in points) / len(points),
        )

    def _horizontal_spread(self, points: list[Dict[str, Any]]) -> float | None:
        if len(points) < 2:
            return None
        xs = [float(point["x"]) for point in points]
        return max(xs) - min(xs)

    def _mean_confidence(self, points: list[Dict[str, Any]]) -> float:
        values = [float(point.get("confidence") or 0.0) for point in points]
        return sum(values) / max(1, len(values))

    def _confidence(self, pose_confidence: float, base: float, margin: float) -> float:
        geometry = max(0.35, min(1.0, base * max(0.65, min(1.25, margin))))
        return round(max(0.0, min(0.99, pose_confidence * 0.55 + geometry * 0.45)), 4)

    def _result(self, label: str, confidence: float, factors: Dict[str, Any]) -> Dict[str, Any]:
        normalized = label if label in POSTURE_LABELS else "unknown"
        return {
            "label": normalized,
            "confidence": round(float(confidence), 4),
            "legacy_label": LEGACY_POSTURE_MAP[normalized],
            "classifier_version": self.version,
            "factors": factors,
        }

    def _round(self, value: float | None) -> float | None:
        return None if value is None else round(float(value), 4)
