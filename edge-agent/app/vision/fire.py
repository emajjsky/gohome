from __future__ import annotations

from typing import Any, Dict

from .base import AlgorithmResult


class FireAnalyzer:
    def analyze(
        self,
        sample: Any,
        config: Dict[str, Any],
        *,
        previous_sample: Any | None = None,
        motion_score: float | None = None,
    ) -> Dict[str, Any]:
        try:
            import numpy as np  # type: ignore
        except ModuleNotFoundError:
            fire_score = 0.0
            features: Dict[str, Any] = {}
        else:
            features = self.fire_color_features(sample, np, previous_sample=previous_sample)
            fire_score = float(features["fire_score"])
        visual_threshold = float(config.get("fire_score_threshold", 0.035))
        event_threshold = float(config.get("fire_event_score_threshold", 0.12))
        temporal_threshold = float(config.get("fire_temporal_threshold", 0.018))
        motion_threshold = float(config.get("fire_motion_threshold", 0.035))
        temporal_score = features.get("temporal_score")
        visual_candidate = fire_score >= visual_threshold
        temporal_candidate = temporal_score is not None and float(temporal_score) >= temporal_threshold
        motion_candidate = motion_score is not None and float(motion_score) >= motion_threshold
        component_candidate = bool(features.get("component_candidate", False))
        event_candidate = (
            visual_candidate
            and fire_score >= event_threshold
            and temporal_candidate
            and motion_candidate
            and component_candidate
        )
        result = AlgorithmResult(
            algorithm_id="fire",
            label="火灾应急报警",
            status="candidate" if visual_candidate else "clear",
            score=fire_score,
            level="warning" if visual_candidate else "info",
            summary="检测到疑似明火视觉线索。" if visual_candidate else "未命中火灾视觉线索。",
            tags=["fire_candidate"] if visual_candidate else [],
            data={
                "fire_score": fire_score,
                "fire_candidate": visual_candidate,
                "fire_event_candidate": event_candidate,
                "threshold": visual_threshold,
                "event_threshold": event_threshold,
                "temporal_threshold": temporal_threshold,
                "motion_threshold": motion_threshold,
                "method": "warm_yellow_texture_temporal_score",
                "features": features,
            },
        )
        return {
            "fire_score": fire_score,
            "fire_candidate": visual_candidate,
            "fire_event_candidate": event_candidate,
            "fire_temporal_candidate": temporal_candidate,
            "fire_temporal_score": temporal_score,
            "fire_features": features,
            "tags": ["fire_candidate"] if visual_candidate else [],
            "result": result,
        }

    def fire_color_features(self, sample: Any, np: Any, *, previous_sample: Any | None = None) -> Dict[str, Any]:
        if sample.ndim < 3 or sample.shape[2] < 3:
            return {
                "fire_score": 0.0,
                "warm_ratio": 0.0,
                "yellow_core_ratio": 0.0,
                "texture_score": 0.0,
                "red_only_ratio": 0.0,
                "temporal_score": None,
                "largest_component_ratio": 0.0,
                "largest_component_share": 0.0,
                "component_count": 0,
                "component_candidate": False,
            }
        b = sample[:, :, 0].astype("float32")
        g = sample[:, :, 1].astype("float32")
        r = sample[:, :, 2].astype("float32")
        intensity = (r + g + b) / 3.0
        warm = (
            (r > 155)
            & (g > 70)
            & (b < 130)
            & ((r - b) > 55)
            & (r >= g * 0.92)
            & (g > b * 1.12)
            & (intensity > 95)
        )
        yellow_core = (
            (r > 175)
            & (g > 105)
            & (b < 120)
            & ((r - g) < 125)
            & (g > b * 1.18)
            & (intensity > 115)
        )
        red_only = (r > 150) & (g < 78) & (b < 115)
        warm_count = int(np.count_nonzero(warm))
        total = max(1, warm.size)
        warm_ratio = float(warm_count / total)
        yellow_core_ratio = float(np.count_nonzero(yellow_core & warm) / total)
        red_only_ratio = float(np.count_nonzero(red_only) / total)
        if warm_count:
            texture_score = float(np.std(intensity[warm]) / 255.0)
        else:
            texture_score = 0.0
        component = self._component_features(warm, warm_count, total)
        temporal_score = self._temporal_score(sample, previous_sample, warm, np)
        core_balance = yellow_core_ratio / max(warm_ratio, 1e-6)
        red_penalty = max(0.35, 1.0 - (red_only_ratio / max(warm_ratio, 1e-6)) * 0.55)
        texture_factor = min(1.0, texture_score / 0.12)
        component_factor = 0.78 + min(0.22, float(component["largest_component_share"]) * 0.22)
        temporal_factor = 1.0
        if temporal_score is not None:
            temporal_factor = 0.72 + min(0.28, float(temporal_score) / 0.08 * 0.28)
        fire_score = warm_ratio * (0.45 + 0.55 * min(core_balance, 1.0)) * texture_factor * red_penalty
        fire_score *= component_factor * temporal_factor
        if warm_ratio < 0.018 or yellow_core_ratio < 0.004 or texture_score < 0.025:
            fire_score = 0.0
        return {
            "fire_score": float(fire_score),
            "warm_ratio": warm_ratio,
            "yellow_core_ratio": yellow_core_ratio,
            "texture_score": texture_score,
            "red_only_ratio": red_only_ratio,
            "temporal_score": temporal_score,
            **component,
        }

    def _component_features(self, warm: Any, warm_count: int, total: int) -> Dict[str, Any]:
        if warm_count <= 0:
            return {
                "largest_component_ratio": 0.0,
                "largest_component_share": 0.0,
                "component_count": 0,
                "component_candidate": False,
            }
        try:
            import cv2  # type: ignore

            component_count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(warm.astype("uint8"), 8)
            areas = [int(stats[index, cv2.CC_STAT_AREA]) for index in range(1, component_count)]
            largest = max(areas, default=0)
            count = len([area for area in areas if area >= 3])
        except Exception:
            largest = warm_count
            count = 1
        largest_ratio = float(largest / max(1, total))
        largest_share = float(largest / max(1, warm_count))
        component_candidate = largest_ratio >= 0.006 and largest_share >= 0.18 and count <= 12
        return {
            "largest_component_ratio": largest_ratio,
            "largest_component_share": largest_share,
            "component_count": count,
            "component_candidate": component_candidate,
        }

    def _temporal_score(self, sample: Any, previous_sample: Any | None, warm: Any, np: Any) -> float | None:
        if previous_sample is None or getattr(previous_sample, "shape", None) != sample.shape:
            return None
        previous = previous_sample.astype("float32")
        b = previous[:, :, 0]
        g = previous[:, :, 1]
        r = previous[:, :, 2]
        previous_intensity = (r + g + b) / 3.0
        previous_warm = (
            (r > 155)
            & (g > 70)
            & (b < 130)
            & ((r - b) > 55)
            & (r >= g * 0.92)
            & (g > b * 1.12)
            & (previous_intensity > 95)
        )
        union = warm | previous_warm
        if not bool(np.count_nonzero(union)):
            return 0.0
        mask_change = float(np.count_nonzero(warm ^ previous_warm) / max(1, np.count_nonzero(union)))
        intensity = sample.astype("float32").mean(axis=2)
        intensity_delta = float(np.abs(intensity - previous_intensity)[union].mean() / 255.0)
        return max(mask_change * 0.08, intensity_delta)
