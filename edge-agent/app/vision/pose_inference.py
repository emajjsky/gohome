from __future__ import annotations

from threading import RLock
from typing import Any, Dict

from .hailo_pose import HailoPoseBackend
from .pose_rtmpose import RtmposeAnalyzer


class PoseInferenceService:
    """Own the single Pose runtime and the matching result interpreter."""

    version = "shared-pose-inference-v1"

    def __init__(
        self,
        *,
        pose_enabled: bool,
        pose_mode: str,
        pose_runtime_backend: str,
        pose_device: str,
        pose_fall_threshold: float,
        pose_fall_min_confidence: float,
        pose_fall_min_visible_keypoints: int,
        pose_fall_min_core_keypoints: int,
        pose_det_frequency: int,
        pose_min_keypoint_confidence: float,
        pose_max_poses: int,
        pose_tracking: bool,
        inference_backend: str,
        hailo_pose_model: str,
        hailo_pose_confidence: float,
        hailo_pose_nms_iou: float,
        hailo_retry_seconds: float,
    ) -> None:
        self.interpreter = RtmposeAnalyzer(
            enabled=pose_enabled,
            mode=pose_mode,
            runtime_backend=pose_runtime_backend,
            device=pose_device,
            fall_threshold=pose_fall_threshold,
            fall_min_pose_confidence=pose_fall_min_confidence,
            fall_min_visible_keypoints=pose_fall_min_visible_keypoints,
            fall_min_core_keypoints=pose_fall_min_core_keypoints,
            det_frequency=pose_det_frequency,
            min_keypoint_confidence=pose_min_keypoint_confidence,
            max_poses=pose_max_poses,
            tracking=pose_tracking,
        )
        self.hailo_backend = HailoPoseBackend(
            mode=inference_backend,
            model_path=hailo_pose_model,
            confidence=hailo_pose_confidence,
            nms_iou=hailo_pose_nms_iou,
            max_poses=pose_max_poses,
            retry_seconds=hailo_retry_seconds,
        )
        self._interpreter_lock = RLock()

    def infer_accelerated(
        self,
        frame: Any,
        config: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        return self.hailo_backend.analyze(frame, config)

    def analyze_accelerated_frame(
        self,
        frame: Any,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run one Hailo Pose frame and prepare display-only Pose output."""
        accelerated = self.hailo_backend.analyze(frame, config)
        if accelerated is None:
            return {"accelerated": None, "analysis": None}
        display_config = {
            **config,
            "pose_detection_enabled": True,
            "pose_allow_internal_detector_fallback": False,
        }
        return {
            "accelerated": accelerated,
            "analysis": self.interpret(
                frame,
                display_config,
                accelerated=accelerated,
                people=[],
            ),
        }

    def interpret(
        self,
        frame: Any,
        config: Dict[str, Any],
        *,
        accelerated: Dict[str, Any] | None,
        people: list[Dict[str, Any]],
    ) -> Dict[str, Any]:
        with self._interpreter_lock:
            return self._interpret_unlocked(
                frame,
                config,
                accelerated=accelerated,
                people=people,
            )

    def _interpret_unlocked(
        self,
        frame: Any,
        config: Dict[str, Any],
        *,
        accelerated: Dict[str, Any] | None,
        people: list[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if accelerated is None:
            return self.interpreter.analyze(frame, config, people=people)
        return self.interpreter.analyze_precomputed(
            frame,
            config,
            keypoints=accelerated["keypoints"],
            scores=accelerated["keypoint_scores"],
            source_person_boxes=[list(map(float, box)) for box in accelerated["boxes"]],
            source_person_scores=[float(score) for score in accelerated["scores"]],
            model_name=str(accelerated.get("model_name") or "yolov8s_pose_h8.hef"),
            model_message=f"Hailo 姿态推理 {float(accelerated['latency_ms']):.1f} ms。",
            backend="hailo",
            detection_source="hailo_unified_person_pose",
        )

    def status(self) -> Dict[str, Any]:
        return {
            "schema_version": self.version,
            "runtime_ownership": "single_shared_service",
            "runtime_count": 1,
            "inference_backend": self.hailo_backend.status(),
        }

    def close(self) -> None:
        self.hailo_backend.close()
