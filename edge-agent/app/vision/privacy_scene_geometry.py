from __future__ import annotations

from typing import Any

import numpy as np


class SceneGeometryVerifier:
    """Distinguish camera viewpoint changes from ordinary household changes."""

    version = "privacy-scene-geometry-v4"

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
        minimum_change_spatial_coverage_ratio: float = 0.12,
        minimum_change_grid_coverage_ratio: float = 0.25,
        maximum_median_corner_displacement_ratio: float = 0.015,
        maximum_corner_displacement_ratio: float = 0.025,
        minimum_phase_response: float = 0.08,
        maximum_phase_displacement_ratio: float = 0.012,
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
        self.minimum_change_spatial_coverage_ratio = max(
            0.05,
            min(0.8, float(minimum_change_spatial_coverage_ratio)),
        )
        self.minimum_change_grid_coverage_ratio = max(
            0.1,
            min(0.8, float(minimum_change_grid_coverage_ratio)),
        )
        self.maximum_median_corner_displacement_ratio = max(
            0.002,
            float(maximum_median_corner_displacement_ratio),
        )
        self.maximum_corner_displacement_ratio = max(
            self.maximum_median_corner_displacement_ratio,
            float(maximum_corner_displacement_ratio),
        )
        self.minimum_phase_response = max(0.02, min(0.8, float(minimum_phase_response)))
        self.maximum_phase_displacement_ratio = max(
            0.002,
            min(0.05, float(maximum_phase_displacement_ratio)),
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
        phase = self._phase_alignment(
            cv2,
            baseline_gray,
            current_gray,
            visible_mask=current_mask,
        )
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
            return self._feature_fallback(
                "insufficient_geometry_features",
                phase=phase,
            )

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
            return self._feature_fallback(
                "insufficient_geometry_matches",
                phase=phase,
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
            return self._feature_fallback(
                "geometry_transform_failed",
                phase=phase,
                good_matches=len(matches),
            )
        inliers = int(np.count_nonzero(inlier_mask))
        inlier_ratio = inliers / max(1, len(matches))
        if (
            inliers < self.minimum_transform_inliers
            or inlier_ratio < self.minimum_transform_inlier_ratio
        ):
            return self._feature_fallback(
                "insufficient_geometry_inliers",
                phase=phase,
                good_matches=len(matches),
                inliers=inliers,
                inlier_ratio=inlier_ratio,
            )

        height, width = frame.shape[:2]
        inlier_flags = np.asarray(inlier_mask).reshape(-1).astype(bool)
        current_inliers = current_coordinates.reshape(-1, 2)[inlier_flags]
        baseline_inliers = baseline_coordinates.reshape(-1, 2)[inlier_flags]
        current_coverage = self._spatial_coverage(current_inliers, width, height)
        baseline_coverage = self._spatial_coverage(baseline_inliers, width, height)
        spatial_coverage = min(current_coverage[0], baseline_coverage[0])
        grid_coverage = min(current_coverage[1], baseline_coverage[1])
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
        homography_same_view = bool(
            median_displacement <= self.maximum_median_corner_displacement_ratio
            and maximum_displacement <= self.maximum_corner_displacement_ratio
        )
        homography_strong = bool(
            len(matches) >= self.minimum_matches
            and inliers >= self.minimum_inliers
            and inlier_ratio >= self.minimum_inlier_ratio
        )

        affine, affine_inlier_mask = cv2.estimateAffinePartial2D(
            current_coordinates.reshape(-1, 2),
            baseline_coordinates.reshape(-1, 2),
            method=cv2.RANSAC,
            ransacReprojThreshold=3.0,
            maxIters=2000,
            confidence=0.995,
            refineIters=10,
        )
        affine_inliers = (
            int(np.count_nonzero(affine_inlier_mask))
            if affine_inlier_mask is not None
            else 0
        )
        affine_inlier_ratio = affine_inliers / max(1, len(matches))
        affine_reliable = bool(
            affine is not None
            and affine_inliers >= self.minimum_transform_inliers
            and affine_inlier_ratio >= self.minimum_transform_inlier_ratio
        )
        affine_strong = bool(
            affine_reliable
            and len(matches) >= self.minimum_matches
            and affine_inliers >= self.minimum_inliers
            and affine_inlier_ratio >= self.minimum_inlier_ratio
        )
        affine_median_displacement: float | None = None
        affine_maximum_displacement: float | None = None
        affine_same_view: bool | None = None
        affine_spatial_coverage = 0.0
        affine_grid_coverage = 0.0
        if affine_reliable:
            affine_inlier_flags = np.asarray(affine_inlier_mask).reshape(-1).astype(bool)
            affine_current_coverage = self._spatial_coverage(
                current_coordinates.reshape(-1, 2)[affine_inlier_flags],
                width,
                height,
            )
            affine_baseline_coverage = self._spatial_coverage(
                baseline_coordinates.reshape(-1, 2)[affine_inlier_flags],
                width,
                height,
            )
            affine_spatial_coverage = min(
                affine_current_coverage[0],
                affine_baseline_coverage[0],
            )
            affine_grid_coverage = min(
                affine_current_coverage[1],
                affine_baseline_coverage[1],
            )
            affine_corners = cv2.transform(corners, affine)
            affine_displacement = np.linalg.norm(
                (affine_corners - corners).reshape(-1, 2),
                axis=1,
            ) / max(1.0, float(np.hypot(width, height)))
            affine_median_displacement = float(np.median(affine_displacement))
            affine_maximum_displacement = float(np.max(affine_displacement))
            affine_same_view = bool(
                affine_median_displacement <= self.maximum_median_corner_displacement_ratio
                and affine_maximum_displacement <= self.maximum_corner_displacement_ratio
            )

        broad_evidence = bool(
            min(spatial_coverage, affine_spatial_coverage)
            >= self.minimum_change_spatial_coverage_ratio
            and min(grid_coverage, affine_grid_coverage)
            >= self.minimum_change_grid_coverage_ratio
        )
        model_agreement = (
            "same_view"
            if affine_same_view is True and homography_same_view
            else "camera_view_changed"
            if affine_same_view is False and not homography_same_view
            else "conflict"
            if affine_same_view is not None
            else "homography_only"
        )
        common = {
            "geometry_good_matches": len(matches),
            "geometry_inliers": inliers,
            "geometry_inlier_ratio": round(inlier_ratio, 4),
            "geometry_median_corner_displacement_ratio": round(median_displacement, 5),
            "geometry_max_corner_displacement_ratio": round(maximum_displacement, 5),
            "geometry_spatial_coverage_ratio": round(spatial_coverage, 4),
            "geometry_grid_coverage_ratio": round(grid_coverage, 4),
            "geometry_affine_inliers": affine_inliers,
            "geometry_affine_inlier_ratio": round(affine_inlier_ratio, 4),
            "geometry_affine_spatial_coverage_ratio": round(
                affine_spatial_coverage,
                4,
            ),
            "geometry_affine_grid_coverage_ratio": round(affine_grid_coverage, 4),
            "geometry_affine_median_corner_displacement_ratio": (
                None
                if affine_median_displacement is None
                else round(affine_median_displacement, 5)
            ),
            "geometry_affine_max_corner_displacement_ratio": (
                None
                if affine_maximum_displacement is None
                else round(affine_maximum_displacement, 5)
            ),
            "geometry_model_agreement": model_agreement,
            **phase,
            "geometry_cached": False,
        }

        same_view = bool(
            homography_same_view
            and (affine_same_view is not False or not affine_strong)
        ) or bool(
            affine_same_view is True
            and affine_strong
            and not broad_evidence
        )
        if same_view:
            return {
                "accepted": True,
                "geometry_status": "same_view",
                "geometry_reason": "",
                "geometry_confidence": (
                    "strong" if homography_strong or affine_strong else "moderate"
                ),
                **common,
            }

        confirmed_change = bool(
            not homography_same_view
            and affine_same_view is False
            and homography_strong
            and affine_strong
            and broad_evidence
        )
        if not confirmed_change:
            return self._unverifiable(
                "geometry_models_inconclusive",
                good_matches=len(matches),
                inliers=inliers,
                inlier_ratio=inlier_ratio,
                median_corner_displacement_ratio=median_displacement,
                max_corner_displacement_ratio=maximum_displacement,
                confidence="strong" if homography_strong or affine_strong else "moderate",
                extra=common,
            )
        return {
            "accepted": False,
            "geometry_status": "camera_view_changed",
            "geometry_reason": "camera_view_changed",
            "geometry_confidence": "strong",
            **common,
        }

    def _feature_fallback(
        self,
        reason: str,
        *,
        phase: dict[str, Any],
        good_matches: int = 0,
        inliers: int = 0,
        inlier_ratio: float | None = None,
    ) -> dict[str, Any]:
        if phase.get("geometry_phase_status") == "same_view":
            return {
                "accepted": True,
                "geometry_status": "same_view",
                "geometry_reason": "",
                "geometry_confidence": "moderate",
                "geometry_good_matches": int(good_matches),
                "geometry_inliers": int(inliers),
                "geometry_inlier_ratio": (
                    None if inlier_ratio is None else round(float(inlier_ratio), 4)
                ),
                "geometry_median_corner_displacement_ratio": None,
                "geometry_max_corner_displacement_ratio": None,
                **phase,
                "geometry_cached": False,
            }
        return self._unverifiable(
            reason,
            good_matches=good_matches,
            inliers=inliers,
            inlier_ratio=inlier_ratio,
            extra=phase,
        )

    def _phase_alignment(
        self,
        cv2: Any,
        baseline_gray: Any,
        current_gray: Any,
        *,
        visible_mask: Any | None,
    ) -> dict[str, Any]:
        baseline_x = cv2.Sobel(baseline_gray, cv2.CV_32F, 1, 0, ksize=3)
        baseline_y = cv2.Sobel(baseline_gray, cv2.CV_32F, 0, 1, ksize=3)
        current_x = cv2.Sobel(current_gray, cv2.CV_32F, 1, 0, ksize=3)
        current_y = cv2.Sobel(current_gray, cv2.CV_32F, 0, 1, ksize=3)
        baseline_edges = cv2.magnitude(baseline_x, baseline_y)
        current_edges = cv2.magnitude(current_x, current_y)
        if visible_mask is not None:
            visible = np.asarray(visible_mask) > 0
            baseline_edges = np.where(visible, baseline_edges, 0.0).astype(np.float32)
            current_edges = np.where(visible, current_edges, 0.0).astype(np.float32)
        edge_energy = min(float(np.std(baseline_edges)), float(np.std(current_edges)))
        if edge_energy < 4.0:
            return {
                "geometry_phase_status": "unverifiable",
                "geometry_phase_reason": "insufficient_global_edge_energy",
                "geometry_phase_response": None,
                "geometry_phase_displacement_ratio": None,
            }
        height, width = baseline_gray.shape[:2]
        window = cv2.createHanningWindow((int(width), int(height)), cv2.CV_32F)
        shift, response = cv2.phaseCorrelate(
            baseline_edges,
            current_edges,
            window,
        )
        displacement_ratio = float(np.hypot(float(shift[0]), float(shift[1]))) / max(
            1.0,
            float(np.hypot(width, height)),
        )
        same_view = bool(
            np.isfinite(response)
            and np.isfinite(displacement_ratio)
            and float(response) >= self.minimum_phase_response
            and displacement_ratio <= self.maximum_phase_displacement_ratio
        )
        return {
            "geometry_phase_status": "same_view" if same_view else "unverifiable",
            "geometry_phase_reason": "" if same_view else "global_phase_alignment_inconclusive",
            "geometry_phase_response": round(float(response), 5) if np.isfinite(response) else None,
            "geometry_phase_displacement_ratio": (
                round(displacement_ratio, 5) if np.isfinite(displacement_ratio) else None
            ),
        }

    @staticmethod
    def _spatial_coverage(points: Any, width: int, height: int) -> tuple[float, float]:
        coordinates = np.asarray(points, dtype=np.float32).reshape(-1, 2)
        if len(coordinates) < 2:
            return 0.0, 0.0
        span = np.ptp(coordinates, axis=0)
        area_ratio = float(
            (span[0] * span[1])
            / max(1.0, float((width - 1) * (height - 1)))
        )
        columns = np.clip((coordinates[:, 0] * 4 / max(1, width)).astype(int), 0, 3)
        rows = np.clip((coordinates[:, 1] * 3 / max(1, height)).astype(int), 0, 2)
        occupied_cells = len({
            (int(row), int(column))
            for row, column in zip(rows, columns)
        })
        return min(1.0, area_ratio), occupied_cells / 12.0

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
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = {
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
        if extra:
            result.update(extra)
        return result
