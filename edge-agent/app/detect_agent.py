from __future__ import annotations

from threading import Lock
from typing import Any, Dict, Optional

from .vision import VisionPipeline
from .vision.pose_inference import PoseInferenceService


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
        inference_backend: str = "auto",
        hailo_pose_model: str = "/usr/share/hailo-models/yolov8s_pose_h8.hef",
        hailo_pose_confidence: float = 0.25,
        hailo_pose_nms_iou: float = 0.70,
        hailo_object_mode: str = "auto",
        hailo_object_model: str = "/usr/share/hailo-models/yolov8s_h8.hef",
        hailo_object_confidence: float = 0.30,
        hailo_object_interval_seconds: float = 1.0,
        hailo_retry_seconds: float = 30.0,
        context_detection_interval_seconds: float = 3.0,
    ) -> None:
        self.pose_inference_service = PoseInferenceService(
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
            inference_backend=inference_backend,
            hailo_pose_model=hailo_pose_model,
            hailo_pose_confidence=hailo_pose_confidence,
            hailo_pose_nms_iou=hailo_pose_nms_iou,
            hailo_retry_seconds=hailo_retry_seconds,
        )
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
            inference_backend=inference_backend,
            hailo_pose_model=hailo_pose_model,
            hailo_pose_confidence=hailo_pose_confidence,
            hailo_pose_nms_iou=hailo_pose_nms_iou,
            hailo_object_mode=hailo_object_mode,
            hailo_object_model=hailo_object_model,
            hailo_object_confidence=hailo_object_confidence,
            hailo_object_interval_seconds=hailo_object_interval_seconds,
            hailo_retry_seconds=hailo_retry_seconds,
            context_detection_interval_seconds=context_detection_interval_seconds,
            pose_inference_service=self.pose_inference_service,
        )
        self._initialize_inference_lock()

    def _initialize_inference_lock(self) -> None:
        self._inference_lock = Lock()

    def analyze_frame(self, frame: Any, previous_frame: Optional[Any] = None) -> Dict[str, Any]:
        return self.analyze_frame_with_config(frame, previous_frame=previous_frame)

    def analyze_frame_with_config(
        self,
        frame: Any,
        previous_frame: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
        *,
        pose_accelerated: Dict[str, Any] | None = None,
        pose_accelerated_provided: bool = False,
    ) -> Dict[str, Any]:
        with self._inference_lock:
            if not pose_accelerated_provided:
                return self.pipeline.analyze(frame, previous_frame=previous_frame, config=config)
            return self.pipeline.analyze(
                frame,
                previous_frame=previous_frame,
                config=config,
                pose_accelerated=pose_accelerated,
                pose_accelerated_provided=True,
            )

    def runtime_status(self) -> Dict[str, Any]:
        return self.pipeline.runtime_status()

    def close(self) -> None:
        self.pipeline.close()
        self.pose_inference_service.close()
