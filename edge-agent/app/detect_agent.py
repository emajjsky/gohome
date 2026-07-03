from __future__ import annotations

from typing import Any, Dict, Optional

from .vision import VisionPipeline


class DetectAgent:
    def __init__(
        self,
        black_brightness_threshold: float,
        black_contrast_threshold: float,
        motion_threshold: float,
        detector_backend: str = "basic",
        yolo_model: str = "yolo11n.pt",
        yolo_confidence: float = 0.20,
        yolo_imgsz: int = 960,
    ) -> None:
        self.pipeline = VisionPipeline(
            black_brightness_threshold=black_brightness_threshold,
            black_contrast_threshold=black_contrast_threshold,
            motion_threshold=motion_threshold,
            detector_backend=detector_backend,
            yolo_model=yolo_model,
            yolo_confidence=yolo_confidence,
            yolo_imgsz=yolo_imgsz,
        )

    def analyze_frame(self, frame: Any, previous_frame: Optional[Any] = None) -> Dict[str, Any]:
        return self.analyze_frame_with_config(frame, previous_frame=previous_frame)

    def analyze_frame_with_config(
        self,
        frame: Any,
        previous_frame: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.pipeline.analyze(frame, previous_frame=previous_frame, config=config)
