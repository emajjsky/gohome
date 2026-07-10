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
        pose_enabled: bool = False,
        pose_mode: str = "lightweight",
        pose_runtime_backend: str = "onnxruntime",
        pose_device: str = "cpu",
        pose_fall_threshold: float = 0.90,
        pose_fall_min_confidence: float = 0.36,
        pose_fall_min_visible_keypoints: int = 8,
        pose_fall_min_core_keypoints: int = 2,
        pose_det_frequency: int = 8,
        pose_min_keypoint_confidence: float = 0.30,
        pose_max_poses: int = 3,
        pose_tracking: bool = False,
        pose_cache_seconds: float = 1.8,
        pose_cache_max_motion: float = 0.06,
        activity_window_seconds: float = 30.0,
        activity_max_samples: int = 90,
    ) -> None:
        self.pipeline = VisionPipeline(
            black_brightness_threshold=black_brightness_threshold,
            black_contrast_threshold=black_contrast_threshold,
            motion_threshold=motion_threshold,
            detector_backend=detector_backend,
            yolo_model=yolo_model,
            yolo_confidence=yolo_confidence,
            yolo_imgsz=yolo_imgsz,
            pose_enabled=pose_enabled,
            pose_mode=pose_mode,
            pose_runtime_backend=pose_runtime_backend,
            pose_device=pose_device,
            pose_fall_threshold=pose_fall_threshold,
            pose_fall_min_confidence=pose_fall_min_confidence,
            pose_fall_min_visible_keypoints=pose_fall_min_visible_keypoints,
            pose_fall_min_core_keypoints=pose_fall_min_core_keypoints,
            pose_det_frequency=pose_det_frequency,
            pose_min_keypoint_confidence=pose_min_keypoint_confidence,
            pose_max_poses=pose_max_poses,
            pose_tracking=pose_tracking,
            pose_cache_seconds=pose_cache_seconds,
            pose_cache_max_motion=pose_cache_max_motion,
            activity_window_seconds=activity_window_seconds,
            activity_max_samples=activity_max_samples,
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
