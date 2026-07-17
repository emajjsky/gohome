from __future__ import annotations

from threading import RLock
from typing import Any, Dict

from .base import AlgorithmResult
from .posture import PostureClassifier


KEYPOINT_NAMES = [
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
]

SKELETON_EDGES = [
    ("nose", "left_eye"),
    ("nose", "right_eye"),
    ("left_eye", "left_ear"),
    ("right_eye", "right_ear"),
    ("left_ear", "left_shoulder"),
    ("right_ear", "right_shoulder"),
    ("left_shoulder", "right_shoulder"),
    ("left_shoulder", "left_elbow"),
    ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"),
    ("right_elbow", "right_wrist"),
    ("left_shoulder", "left_hip"),
    ("right_shoulder", "right_hip"),
    ("left_hip", "right_hip"),
    ("left_hip", "left_knee"),
    ("left_knee", "left_ankle"),
    ("right_hip", "right_knee"),
    ("right_knee", "right_ankle"),
]

FALL_CORE_KEYPOINT_NAMES = {
    "left_shoulder",
    "right_shoulder",
    "left_hip",
    "right_hip",
}


class RtmposeAnalyzer:
    def __init__(
        self,
        *,
        enabled: bool = False,
        mode: str = "lightweight",
        runtime_backend: str = "onnxruntime",
        device: str = "cpu",
        det_frequency: int = 8,
        min_keypoint_confidence: float = 0.30,
        max_poses: int = 1,
        fall_threshold: float = 0.78,
        fall_min_pose_confidence: float = 0.36,
        fall_min_visible_keypoints: int = 8,
        fall_min_core_keypoints: int = 2,
        tracking: bool = False,
    ) -> None:
        self.enabled = enabled
        self.mode = self._normalize_mode(mode)
        self.runtime_backend = runtime_backend.strip().lower() or "onnxruntime"
        self.device = device.strip().lower() or "cpu"
        self.min_keypoint_confidence = float(min_keypoint_confidence)
        self.max_poses = max(1, int(max_poses))
        self.fall_threshold = float(fall_threshold)
        self.fall_min_pose_confidence = float(fall_min_pose_confidence)
        self.fall_min_visible_keypoints = max(1, int(fall_min_visible_keypoints))
        self.fall_min_core_keypoints = max(1, int(fall_min_core_keypoints))
        self.tracking = bool(tracking)
        # PoseTracker only supports detector skipping when tracking is active.
        # This analyzer is shared by multiple cameras, so cross-camera tracking
        # stays disabled and every sampled pose frame runs person detection.
        self.det_frequency = max(1, int(det_frequency)) if self.tracking else 1
        self._pose_tracker: Any = None
        self._pose_estimator: Any = None
        self._pose_detector: Any = None
        self._load_error = ""
        self._detector_load_error = ""
        self._model_lock = RLock()
        self.posture_classifier = PostureClassifier()

    @property
    def model_name(self) -> str:
        return f"RTMPose-{self.mode} ({self.runtime_backend}/{self.device})"

    def analyze(
        self,
        frame: Any,
        config: Dict[str, Any],
        *,
        people: list[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        runtime_enabled = bool(config.get("pose_detection_enabled", self.enabled))
        if not runtime_enabled:
            return self._disabled_result("姿态检测未启用。")

        external_bboxes = self._external_person_boxes(people or [], config)
        detection_source = "external_person_boxes" if external_bboxes else "rtmlib_detector_fallback"
        with self._model_lock:
            ready, message = (
                self._ensure_ready(require_detector=False)
                if external_bboxes
                else self._ensure_ready()
            )
            if not ready:
                return self._disabled_result(
                    message,
                    status="unavailable",
                    detection_source=detection_source,
                    external_box_count=len(external_bboxes),
                )

            try:
                keypoints, scores, inference_retried = (
                    self._infer_pose(frame, bboxes=external_bboxes)
                    if external_bboxes
                    else self._infer_pose(frame)
                )
                raw_poses = self._extract_poses(keypoints, scores, frame)
            except Exception as exc:
                return self._disabled_result(
                    f"RTMPose 推理失败：{exc}",
                    status="error",
                    detection_source=detection_source,
                    external_box_count=len(external_bboxes),
                )

        threshold = float(config.get("pose_fall_threshold", self.fall_threshold))
        raw_pose_fall_score = max([float(pose.get("fall_score") or 0.0) for pose in raw_poses], default=0.0)
        rejected_fall_candidates = 0
        poses: list[Dict[str, Any]] = []
        rejected_poses: list[Dict[str, Any]] = []
        for pose in raw_poses:
            quality = self._fall_evidence_quality(pose, config)
            pose["raw_fall_score"] = pose.get("fall_score")
            pose["fall_evidence_eligible"] = quality["eligible"]
            pose["person_evidence_eligible"] = quality["eligible"]
            pose["fall_quality"] = quality
            if not quality["eligible"]:
                if float(pose.get("fall_score") or 0.0) >= threshold:
                    rejected_fall_candidates += 1
                pose["action_hints"] = [
                    hint for hint in pose.get("action_hints", []) if hint != "fall_candidate"
                ]
                rejected_poses.append({
                    **pose,
                    "fall_score": 0.0,
                    "rejection_stage": "pose_quality",
                    "rejection_reasons": list(quality.get("reasons") or []),
                })
                continue
            poses.append(pose)

        pose_count = len(poses)
        tags: list[str] = []
        action_hints = self._merge_hints([hint for pose in poses for hint in pose.get("action_hints", [])])
        if pose_count:
            tags.append("pose_detected")
        if external_bboxes:
            tags.append("pose_external_person_boxes")
        if inference_retried:
            tags.append("pose_inference_retried")
        if any(pose.get("posture") == "lying" for pose in poses):
            tags.append("pose_low_body")
        if "hand_near_face" in action_hints:
            tags.append("pose_hand_near_face")

        pose_fall_score = max(
            [float(pose.get("fall_score") or 0.0) for pose in poses if pose.get("fall_evidence_eligible")],
            default=0.0,
        )
        pose_fall_candidate = pose_fall_score >= threshold
        if pose_fall_candidate:
            tags.append("pose_fall_candidate")
            action_hints = self._merge_hints([*action_hints, "fall_candidate"])
        elif rejected_fall_candidates:
            tags.append("pose_fall_low_quality")

        status = "not_visible"
        level = "info"
        score = None
        summary = "RTMPose 已运行，当前帧未检测到可用人体骨架。"
        if pose_count:
            status = "candidate" if pose_fall_candidate else "ready"
            level = "critical" if pose_fall_candidate else "info"
            score = pose_fall_score if pose_fall_candidate else poses[0].get("confidence")
            posture = poses[0].get("posture") or "unknown"
            if pose_fall_candidate:
                summary = f"RTMPose 骨架命中疑似跌倒候选，分数 {pose_fall_score:.2f}。"
            elif rejected_fall_candidates:
                summary = "RTMPose 检测到低质量跌倒形态，证据不足，未触发告警。"
            else:
                summary = f"RTMPose 检测到 {pose_count} 组骨架，主姿态为 {posture}。"

        result = AlgorithmResult(
            algorithm_id="pose",
            label="骨架 / 姿态",
            status=status,
            score=score,
            level=level,
            summary=summary,
            tags=tags,
            data={
                "pose_count": pose_count,
                "raw_pose_count": len(raw_poses),
                "poses": poses,
                "rejected_poses": rejected_poses,
                "pose_skeleton_edges": SKELETON_EDGES,
                "pose_action_hints": action_hints,
                "pose_fall_score": round(pose_fall_score, 4),
                "raw_pose_fall_score": round(raw_pose_fall_score, 4),
                "pose_fall_candidate": pose_fall_candidate,
                "pose_fall_rejected_low_quality": rejected_fall_candidates,
                "pose_model_status": "ready",
                "pose_model_name": self.model_name,
                "pose_model_message": self._ready_message(message, inference_retried),
                "pose_backend": "rtmpose",
                "pose_detection_source": detection_source,
                "pose_external_box_count": len(external_bboxes),
                "pose_fall_threshold": threshold,
            },
        )
        return {
            "pose_count": pose_count,
            "raw_pose_count": len(raw_poses),
            "poses": poses,
            "rejected_poses": rejected_poses,
            "pose_skeleton_edges": SKELETON_EDGES,
            "pose_action_hints": action_hints,
            "pose_fall_score": round(pose_fall_score, 4),
            "raw_pose_fall_score": round(raw_pose_fall_score, 4),
            "pose_fall_candidate": pose_fall_candidate,
            "pose_fall_rejected_low_quality": rejected_fall_candidates,
            "pose_model_status": "ready",
            "pose_model_name": self.model_name,
            "pose_model_message": self._ready_message(message, inference_retried),
            "pose_detection_source": detection_source,
            "pose_external_box_count": len(external_bboxes),
            "tags": tags,
            "result": result,
        }

    def _ensure_ready(self, *, require_detector: bool = True) -> tuple[bool, str]:
        if self._load_error:
            return False, self._load_error
        if not require_detector:
            return self._ensure_pose_estimator()
        if self._pose_tracker is not None:
            return True, "RTMPose 模型已就绪。"
        try:
            if self.tracking:
                from rtmlib import Body, PoseTracker  # type: ignore

                self._pose_tracker = PoseTracker(
                    Body,
                    det_frequency=self.det_frequency,
                    tracking=True,
                    mode=self.mode,
                    to_openpose=False,
                    backend=self.runtime_backend,
                    device=self.device,
                )
            else:
                ready, message = self._ensure_pose_estimator()
                if not ready:
                    return False, message
                if self._detector_load_error:
                    return False, self._detector_load_error
                from rtmlib import Body, YOLOX  # type: ignore

                pose_config = Body.MODE[self.mode]
                self._pose_detector = YOLOX(
                    pose_config["det"],
                    model_input_size=pose_config["det_input_size"],
                    backend=self.runtime_backend,
                    device=self.device,
                )
                self._pose_tracker = self._infer_with_internal_detector
        except ModuleNotFoundError as exc:
            self._detector_load_error = f"姿态回退检测依赖未安装：{exc.name}"
            return False, self._detector_load_error
        except Exception as exc:
            self._detector_load_error = f"RTMPose 回退检测器加载失败：{exc}"
            return False, self._detector_load_error
        return True, "RTMPose 模型已就绪。"

    def _ensure_pose_estimator(self) -> tuple[bool, str]:
        if self._pose_estimator is not None:
            return True, "RTMPose 姿态头已就绪，复用现有人形框。"
        try:
            from rtmlib import Body, RTMPose  # type: ignore

            pose_config = Body.MODE[self.mode]
            self._pose_estimator = RTMPose(
                pose_config["pose"],
                model_input_size=pose_config["pose_input_size"],
                to_openpose=False,
                backend=self.runtime_backend,
                device=self.device,
            )
        except ModuleNotFoundError as exc:
            self._load_error = f"姿态依赖未安装：{exc.name}"
            return False, self._load_error
        except Exception as exc:
            self._load_error = f"RTMPose 姿态头加载失败：{exc}"
            return False, self._load_error
        return True, "RTMPose 姿态头已就绪，复用现有人形框。"

    def _infer_with_internal_detector(self, frame: Any) -> tuple[Any, Any]:
        bboxes = self._pose_detector(frame)
        if bboxes is None or len(bboxes) == 0:
            return [], []
        return self._pose_estimator(frame, bboxes=bboxes)

    def _infer_pose(
        self,
        frame: Any,
        *,
        bboxes: list[list[float]] | None = None,
    ) -> tuple[Any, Any, bool]:
        runner = (
            (lambda image: self._pose_estimator(image, bboxes=bboxes))
            if bboxes
            else self._pose_tracker
        )
        try:
            keypoints, scores = runner(frame)
            return keypoints, scores, False
        except TypeError as exc:
            if "NoneType" not in str(exc):
                raise
            keypoints, scores = runner(frame)
            return keypoints, scores, True

    def _external_person_boxes(
        self,
        people: list[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> list[list[float]]:
        if not config.get("pose_reuse_person_boxes", True):
            return []
        candidates = []
        for person in people:
            bbox = person.get("bbox")
            if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                continue
            try:
                x1, y1, x2, y2 = [float(value) for value in bbox]
            except (TypeError, ValueError):
                continue
            if x2 <= x1 or y2 <= y1:
                continue
            candidates.append((float(person.get("confidence") or 0.0), [x1, y1, x2, y2]))
        candidates.sort(key=lambda item: item[0], reverse=True)
        return [bbox for _, bbox in candidates[:self.max_poses]]

    def _ready_message(self, message: str, inference_retried: bool) -> str:
        if inference_retried:
            return f"{message} 本帧人体框推理瞬态失败后重试成功。"
        return message

    def _extract_poses(self, keypoints: Any, scores: Any, frame: Any) -> list[Dict[str, Any]]:
        import math
        import numpy as np  # type: ignore

        points_array = np.asarray(keypoints)
        scores_array = np.asarray(scores)
        if points_array.size == 0:
            return []
        if points_array.ndim == 2:
            points_array = points_array[None, :, :]
        if scores_array.ndim == 1:
            scores_array = scores_array[None, :]
        if points_array.ndim != 3:
            return []

        frame_height, frame_width = frame.shape[:2]
        poses: list[Dict[str, Any]] = []
        pose_limit = min(points_array.shape[0], self.max_poses)
        for pose_index in range(pose_limit):
            keypoint_payload: list[Dict[str, Any]] = []
            keypoint_count = min(points_array.shape[1], len(KEYPOINT_NAMES))
            for keypoint_index in range(keypoint_count):
                x = float(points_array[pose_index, keypoint_index, 0])
                y = float(points_array[pose_index, keypoint_index, 1])
                confidence = self._score_at(scores_array, pose_index, keypoint_index)
                if not math.isfinite(x) or not math.isfinite(y) or not math.isfinite(confidence):
                    continue
                keypoint_payload.append(
                    {
                        "name": KEYPOINT_NAMES[keypoint_index],
                        "x": round(x, 1),
                        "y": round(y, 1),
                        "confidence": round(confidence, 4),
                        "visible": confidence >= self.min_keypoint_confidence,
                    }
                )

            visible = [point for point in keypoint_payload if point.get("visible")]
            if len(visible) < 4:
                continue
            confidence = self._pose_confidence(keypoint_payload)
            posture_result = self.posture_classifier.classify(keypoint_payload)
            posture = posture_result["label"]
            fall_score = self._estimate_fall_score(keypoint_payload, posture, frame_width, frame_height)
            action_hints = self._action_hints(keypoint_payload, posture, fall_score >= self.fall_threshold)
            poses.append(
                {
                    "keypoints": keypoint_payload,
                    "confidence": confidence,
                    "posture": posture,
                    "posture_confidence": posture_result["confidence"],
                    "posture_legacy": posture_result["legacy_label"],
                    "posture_factors": posture_result["factors"],
                    "posture_classifier_version": posture_result["classifier_version"],
                    "bbox": self._bbox_from_keypoints(visible, frame_width, frame_height),
                    "fall_score": fall_score,
                    "model_status": "ready",
                    "action_hints": action_hints,
                    "source": "rtmpose",
                }
            )
        poses.sort(key=lambda pose: float(pose.get("confidence") or 0.0), reverse=True)
        return poses

    def _fall_evidence_quality(self, pose: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        keypoints = pose.get("keypoints") if isinstance(pose.get("keypoints"), list) else []
        visible = [point for point in keypoints if point.get("visible")]
        core_visible = [point for point in visible if point.get("name") in FALL_CORE_KEYPOINT_NAMES]
        confidence = float(pose.get("confidence") or 0.0)
        min_confidence = float(config.get("pose_fall_min_confidence", self.fall_min_pose_confidence))
        min_visible = max(
            1,
            int(config.get("pose_fall_min_visible_keypoints", self.fall_min_visible_keypoints)),
        )
        min_core = max(
            1,
            int(config.get("pose_fall_min_core_keypoints", self.fall_min_core_keypoints)),
        )
        reasons: list[str] = []
        if confidence < min_confidence:
            reasons.append("low_pose_confidence")
        if len(visible) < min_visible:
            reasons.append("insufficient_visible_keypoints")
        if len(core_visible) < min_core:
            reasons.append("insufficient_core_keypoints")
        return {
            "eligible": not reasons,
            "reasons": reasons,
            "pose_confidence": round(confidence, 4),
            "visible_keypoints": len(visible),
            "core_keypoints": len(core_visible),
            "thresholds": {
                "pose_confidence": min_confidence,
                "visible_keypoints": min_visible,
                "core_keypoints": min_core,
            },
        }

    def _score_at(self, scores: Any, pose_index: int, keypoint_index: int) -> float:
        try:
            return float(scores[pose_index, keypoint_index])
        except Exception:
            return 0.0

    def _bbox_from_keypoints(self, keypoints: list[Dict[str, Any]], frame_width: int, frame_height: int) -> list[float]:
        xs = [float(point["x"]) for point in keypoints]
        ys = [float(point["y"]) for point in keypoints]
        if not xs or not ys:
            return [0.0, 0.0, 0.0, 0.0]
        padding_x = max(12.0, (max(xs) - min(xs)) * 0.16)
        padding_y = max(12.0, (max(ys) - min(ys)) * 0.12)
        return [
            round(max(0.0, min(xs) - padding_x), 1),
            round(max(0.0, min(ys) - padding_y), 1),
            round(min(float(frame_width), max(xs) + padding_x), 1),
            round(min(float(frame_height), max(ys) + padding_y), 1),
        ]

    def _estimate_posture(self, keypoints: list[Dict[str, Any]]) -> str:
        return str(self.posture_classifier.classify(keypoints)["label"])

    def _estimate_fall_score(
        self,
        keypoints: list[Dict[str, Any]],
        posture: str,
        frame_width: int,
        frame_height: int,
    ) -> float:
        visible = [point for point in keypoints if point.get("visible")]
        if not visible:
            return 0.0
        bbox = self._bbox_from_keypoints(visible, frame_width, frame_height)
        width = max(1.0, float(bbox[2]) - float(bbox[0]))
        height = max(1.0, float(bbox[3]) - float(bbox[1]))
        aspect = width / height
        center_y = (float(bbox[1]) + float(bbox[3])) / 2.0
        score_by_posture = {
            "lying": 0.82,
            "squatting": 0.36,
            "bending": 0.24,
            "sitting": 0.18,
            "standing": 0.08,
            "upper_body": 0.08,
            "unknown": 0.05,
            "low_body": 0.36,
            "seated_or_half_body": 0.18,
            "standing_or_sitting": 0.08,
        }
        score = score_by_posture.get(posture, 0.0)
        if aspect >= 1.35:
            score += 0.08
        if frame_height and center_y / frame_height >= 0.62:
            score += 0.06
        if posture == "lying" and aspect < 0.9:
            score -= 0.20
        return round(max(0.0, min(score, 0.98)), 4)

    def _action_hints(self, keypoints: list[Dict[str, Any]], posture: str, fall_candidate: bool) -> list[str]:
        hints: list[str] = []
        if fall_candidate:
            hints.append("fall_candidate")
        if posture == "lying":
            hints.append("lying")
        if posture in {"sitting", "seated_or_half_body", "upper_body"}:
            hints.append("seated_or_upper_body")

        by_name = {point["name"]: point for point in keypoints if point.get("visible")}
        nose = by_name.get("nose")
        wrists = [by_name.get("left_wrist"), by_name.get("right_wrist")]
        shoulders = [by_name.get("left_shoulder"), by_name.get("right_shoulder")]
        if nose:
            for wrist in wrists:
                if wrist and self._distance(wrist, nose) <= 92:
                    hints.append("hand_near_face")
                    break
        if shoulders:
            shoulder_y = sum(float(point["y"]) for point in shoulders) / len(shoulders)
            if any(wrist and float(wrist["y"]) < shoulder_y - 28 for wrist in wrists):
                hints.append("arm_raised")
        return self._merge_hints(hints)

    def _pose_confidence(self, keypoints: list[Dict[str, Any]]) -> float:
        visible = [float(point.get("confidence") or 0.0) for point in keypoints if point.get("visible")]
        if not visible:
            return 0.0
        return round(sum(visible) / len(visible), 4)

    def _midpoint(self, points: list[Dict[str, Any]]) -> tuple[float, float]:
        return (
            sum(float(point["x"]) for point in points) / len(points),
            sum(float(point["y"]) for point in points) / len(points),
        )

    def _distance(self, point_a: Dict[str, Any], point_b: Dict[str, Any]) -> float:
        return ((float(point_a["x"]) - float(point_b["x"])) ** 2 + (float(point_a["y"]) - float(point_b["y"])) ** 2) ** 0.5

    def _disabled_result(
        self,
        message: str,
        status: str = "disabled",
        *,
        detection_source: str = "disabled",
        external_box_count: int = 0,
    ) -> Dict[str, Any]:
        result = AlgorithmResult(
            algorithm_id="pose",
            label="骨架 / 姿态",
            status=status,
            score=None,
            level="info",
            summary=message,
            tags=[],
            data={
                "pose_count": 0,
                "poses": [],
                "pose_skeleton_edges": SKELETON_EDGES,
                "pose_action_hints": [],
                "pose_fall_score": 0.0,
                "raw_pose_fall_score": 0.0,
                "pose_fall_candidate": False,
                "pose_fall_rejected_low_quality": 0,
                "pose_model_status": status,
                "pose_model_name": self.model_name,
                "pose_model_message": message,
                "pose_backend": "rtmpose",
                "pose_detection_source": detection_source,
                "pose_external_box_count": int(external_box_count),
            },
        )
        return {
            "pose_count": 0,
            "poses": [],
            "pose_skeleton_edges": SKELETON_EDGES,
            "pose_action_hints": [],
            "pose_fall_score": 0.0,
            "raw_pose_fall_score": 0.0,
            "pose_fall_candidate": False,
            "pose_fall_rejected_low_quality": 0,
            "pose_model_status": status,
            "pose_model_name": self.model_name,
            "pose_model_message": message,
            "pose_detection_source": detection_source,
            "pose_external_box_count": int(external_box_count),
            "tags": [],
            "result": result,
        }

    def _merge_hints(self, hints: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for hint in hints:
            if hint and hint not in seen:
                result.append(hint)
                seen.add(hint)
        return result

    def _normalize_mode(self, mode: str) -> str:
        value = str(mode or "lightweight").strip().lower()
        return value if value in {"lightweight", "balanced", "performance"} else "lightweight"
