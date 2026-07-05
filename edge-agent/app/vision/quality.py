from __future__ import annotations

from typing import Any, Dict

from .base import AlgorithmResult


class QualityAnalyzer:
    def analyze(
        self,
        frame: Any,
        previous_frame: Any | None,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            import numpy as np  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError("NumPy is not installed. Run: python -m pip install -r requirements.txt") from exc

        black_brightness_threshold = float(config.get("black_brightness_threshold", 18))
        black_contrast_threshold = float(config.get("black_contrast_threshold", 4))
        motion_threshold = float(config.get("motion_threshold", 0.015))

        sample = frame[::8, ::8].astype("float32")
        brightness = float(sample.mean())
        contrast = float(sample.std())
        black_screen = brightness < black_brightness_threshold and contrast < black_contrast_threshold

        previous_sample = None
        motion_score = None
        if previous_frame is not None:
            previous_sample = previous_frame[::8, ::8].astype("float32")
            if previous_sample.shape == sample.shape:
                motion_score = float(np.abs(sample - previous_sample).mean() / 255.0)

        motion_detected = motion_score is None or motion_score >= motion_threshold
        tags: list[str] = []
        if black_screen:
            tags.append("black_screen")
        if motion_score is not None and not motion_detected:
            tags.append("low_motion")

        result = AlgorithmResult(
            algorithm_id="quality",
            label="画面质量",
            status="abnormal" if black_screen else "ok",
            score=0.0 if black_screen else min(1.0, (brightness / 120.0 + contrast / 48.0) / 2.0),
            level="warning" if black_screen else "info",
            summary="画面疑似黑屏或遮挡。" if black_screen else "画面亮度和对比度正常。",
            tags=tags,
            data={
                "brightness": brightness,
                "contrast": contrast,
                "motion_score": motion_score,
                "motion_detected": motion_detected,
                "thresholds": {
                    "black_brightness_threshold": black_brightness_threshold,
                    "black_contrast_threshold": black_contrast_threshold,
                    "motion_threshold": motion_threshold,
                },
            },
        )
        return {
            "sample": sample,
            "previous_sample": previous_sample,
            "brightness": brightness,
            "contrast": contrast,
            "black_screen": black_screen,
            "motion_score": motion_score,
            "motion_detected": motion_detected,
            "tags": tags,
            "result": result,
        }
