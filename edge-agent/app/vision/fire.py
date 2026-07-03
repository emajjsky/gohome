from __future__ import annotations

from typing import Any, Dict

from .base import AlgorithmResult


class FireAnalyzer:
    def analyze(self, sample: Any, config: Dict[str, Any]) -> Dict[str, Any]:
        try:
            import numpy as np  # type: ignore
        except ModuleNotFoundError:
            fire_score = 0.0
        else:
            fire_score = self.fire_color_score(sample, np)
        fire_threshold = float(config.get("fire_score_threshold", 0.035))
        fire_candidate = fire_score >= fire_threshold
        result = AlgorithmResult(
            algorithm_id="fire",
            label="火灾应急报警",
            status="candidate" if fire_candidate else "clear",
            score=fire_score,
            level="critical" if fire_candidate else "info",
            summary="检测到疑似明火视觉线索。" if fire_candidate else "未命中火灾视觉线索。",
            tags=["fire_candidate"] if fire_candidate else [],
            data={
                "fire_score": fire_score,
                "fire_candidate": fire_candidate,
                "threshold": fire_threshold,
                "method": "warm_bright_color_ratio",
            },
        )
        return {
            "fire_score": fire_score,
            "fire_candidate": fire_candidate,
            "tags": ["fire_candidate"] if fire_candidate else [],
            "result": result,
        }

    def fire_color_score(self, sample: Any, np: Any) -> float:
        if sample.ndim < 3 or sample.shape[2] < 3:
            return 0.0
        b = sample[:, :, 0].astype("float32")
        g = sample[:, :, 1].astype("float32")
        r = sample[:, :, 2].astype("float32")
        warm = (r > 145) & (g > 45) & (g < 210) & (b < 120) & ((r - b) > 60)
        bright = (r + g + b) / 3.0 > 80
        return float(np.count_nonzero(warm & bright) / max(1, warm.size))
