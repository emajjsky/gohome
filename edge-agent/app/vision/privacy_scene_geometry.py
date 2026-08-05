from __future__ import annotations

from typing import Any

import numpy as np


class SceneGeometryVerifier:
    """Distinguish camera viewpoint changes from ordinary household changes."""

    version = "privacy-scene-geometry-v2"

    def __init__(
        self,
        *,
        minimum_features: int = 12,
        minimum_matches: int = 12,
        minimum_inliers: int = 10,
        minimum_inlier_ratio: float = 0.55,
        minimum_transform_matches: int = 8,
        minimum_transform_inliers: int = 6,
        minimum_transform_inlier_ratio: float = 0.40,
        maximum_median_corner_displacement_ratio: float = 0.015,
        maximum_corner_displacement_ratio: float = 0.025,
    ) -> None:
        self.minimum_features = max(8, int(minimum_features))
        self.minimum_matches = max(8, int(minimum_matches))
        self.minimum_inliers = max(6, int(minimum_inliers))
        self.minimum_inlier_ratio = max(0.3, min(0.95, float(minimum_inlier_ratio)))
        self.minimum_transform_matches = max(6, min(
            self.minimum_matches,
            int(minimum_transform_matches),
        ))
        self.minimum_transform_inliers = max(4, min(
            self.minimum_inliers,
            int(minimum_transform_inliers),
        ))
        self.minimum_transform_inlier_ratio = max(
            0.25,
            min(self.minimum_inlier_ratio, float(minimum_transform_inlier_ratio)),
        )
        self.maximum_median_corner_displacement_ratio = max(
            0.002,
            float(maximum_median_corner_displacement_ratio),
        )
        self.maximum_corner_displacement_ratio = max(
            self.maximum_median_corner_displacement_ratio,
            float(maximum_corner_displacement_ratio),
        )

    def assess(
        self,
        background: Any,
        frame: Any,
        *,
        excluded_mask: Any | None,
    ) -> dict[str, Any]:
        import cv2  # type: ignore

        baseline_gray = cv2.equalizeHist(cv2.cvtColor(background, cv2.COLOR_BGR2GRAY))
        current_gray = cv2.equalizeHist(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        current_mask = None
        if excluded_mask is not None:
            current_mask = np.where(np.asarray(excluded_mask) == 0, 255, 0).astype(np.uint8)
        detector = cv2.ORB_create(
            nfeatures=800,
            scaleFactor=1.2,
            nlevels=8,
            fastThreshold=10,
        )
        baseline_points, baseline_descriptors = detector.detectAndCompute(baseline_gray, None)
        current_points, current_descriptors = detector.detectAndCompute(current_gray, current_mask)
        if (
            baseline_descriptors is None
            or current_descriptors is None
            or len(baseline_points) < self.minimum_features
            or len(current_points) < self.minimum_features
        ):
            return self._unverifiable("insufficient_geometry_features")

        pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(
            current_descriptors,
            baseline_descriptors,
            k=2,
        )
        matches = []
        for pair in pairs:
            if len(pair) != 2:
                continue
            first, second = pair
            if first.distance < 0.75 * second.distance:
                matches.append(first)
        if len(matches) < self.minimum_transform_matches:
            return self._unverifiable(
                "insufficient_geometry_matches",
                good_matches=len(matches),
            )

        current_coordinates = np.float32([
            current_points[match.queryIdx].pt for match in matches
        ]).reshape(-1, 1, 2)
        baseline_coordinates = np.float32([
            baseline_points[match.trainIdx].pt for match in matches
        ]).reshape(-1, 1, 2)
        transform, inlier_mask = cv2.findHomography(
            current_coordinates,
            baseline_coordinates,
            cv2.RANSAC,
            3.0,
        )
        if transform is None or inlier_mask is None:
            return self._unverifiable(
                "geometry_transform_failed",
                good_matches=len(matches),
            )
        inliers = int(np.count_nonzero(inlier_mask))
        inlier_ratio = inliers / max(1, len(matches))
        if (
            inliers < self.minimum_transform_inliers
            or inlier_ratio < self.minimum_transform_inlier_ratio
        ):
            return self._unverifiable(
                "insufficient_geometry_inliers",
                good_matches=len(matches),
                inliers=inliers,
                inlier_ratio=inlier_ratio,
            )

        height, width = frame.shape[:2]
        corners = np.float32([
            [[0.0, 0.0]],
            [[float(width - 1), 0.0]],
            [[float(width - 1), float(height - 1)]],
            [[0.0, float(height - 1)]],
        ])
        transformed_corners = cv2.perspectiveTransform(corners, transform)
        displacement = np.linalg.norm(
            (transformed_corners - corners).reshape(-1, 2),
            axis=1,
        ) / max(1.0, float(np.hypot(width, height)))
        median_displacement = float(np.median(displacement))
        maximum_displacement = float(np.max(displacement))
        same_view = bool(
            median_displacement <= self.maximum_median_corner_displacement_ratio
            and maximum_displacement <= self.maximum_corner_displacement_ratio
        )
        strong_evidence = bool(
            len(matches) >= self.minimum_matches
            and inliers >= self.minimum_inliers
            and inlier_ratio >= self.minimum_inlier_ratio
        )
        if not same_view and not strong_evidence:
            return self._unverifiable(
                "camera_change_evidence_weak",
                good_matches=len(matches),
                inliers=inliers,
                inlier_ratio=inlier_ratio,
                median_corner_displacement_ratio=median_displacement,
                max_corner_displacement_ratio=maximum_displacement,
                confidence="moderate",
            )
        return {
            "accepted": same_view,
            "geometry_status": "same_view" if same_view else "camera_view_changed",
            "geometry_reason": "" if same_view else "camera_view_changed",
            "geometry_confidence": "strong" if strong_evidence else "moderate",
            "geometry_good_matches": len(matches),
            "geometry_inliers": inliers,
            "geometry_inlier_ratio": round(inlier_ratio, 4),
            "geometry_median_corner_displacement_ratio": round(median_displacement, 5),
            "geometry_max_corner_displacement_ratio": round(maximum_displacement, 5),
            "geometry_cached": False,
        }

    def signature(
        self,
        frame: Any,
        *,
        excluded_mask: Any | None,
    ) -> tuple[Any, Any]:
        height, width = frame.shape[:2]
        rows = np.linspace(0, max(0, height - 1), num=min(18, height), dtype=np.int32)
        columns = np.linspace(0, max(0, width - 1), num=min(32, width), dtype=np.int32)
        sampled = frame[np.ix_(rows, columns)].astype(np.float32)
        luminance = np.rint(
            sampled[:, :, 0] * 0.114
            + sampled[:, :, 1] * 0.587
            + sampled[:, :, 2] * 0.299
        ).astype(np.int16)
        visible = np.ones(luminance.shape, dtype=bool)
        if excluded_mask is not None:
            visible &= np.asarray(excluded_mask)[np.ix_(rows, columns)] == 0
        return luminance, visible

    def signatures_match(self, previous: Any, current: Any) -> bool:
        if previous is None or current is None:
            return False
        previous_luminance, previous_visible = previous
        current_luminance, current_visible = current
        if previous_luminance.shape != current_luminance.shape:
            return False
        visible = np.asarray(previous_visible, dtype=bool) & np.asarray(current_visible, dtype=bool)
        if int(np.count_nonzero(visible)) < 128:
            return False
        residual = np.abs(
            np.asarray(previous_luminance, dtype=np.int16)[visible]
            - np.asarray(current_luminance, dtype=np.int16)[visible]
        )
        return bool(float(np.median(residual)) <= 6.0 and float(np.mean(residual <= 15)) >= 0.85)

    def _unverifiable(
        self,
        reason: str,
        *,
        good_matches: int = 0,
        inliers: int = 0,
        inlier_ratio: float | None = None,
        median_corner_displacement_ratio: float | None = None,
        max_corner_displacement_ratio: float | None = None,
        confidence: str = "none",
    ) -> dict[str, Any]:
        return {
            "accepted": False,
            "geometry_status": "unverifiable",
            "geometry_reason": str(reason),
            "geometry_confidence": str(confidence),
            "geometry_good_matches": int(good_matches),
            "geometry_inliers": int(inliers),
            "geometry_inlier_ratio": (
                None if inlier_ratio is None else round(float(inlier_ratio), 4)
            ),
            "geometry_median_corner_displacement_ratio": (
                None
                if median_corner_displacement_ratio is None
                else round(float(median_corner_displacement_ratio), 5)
            ),
            "geometry_max_corner_displacement_ratio": (
                None
                if max_corner_displacement_ratio is None
                else round(float(max_corner_displacement_ratio), 5)
            ),
            "geometry_cached": False,
        }
