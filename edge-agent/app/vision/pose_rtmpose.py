from __future__ import annotations

from typing import Any, Dict

from .base import AlgorithmResult


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
        tracking: bool = False,
    ) -> None:
        self.enabled = enabled
        self.mode = self._normalize_mode(mode)
        self.runtime_backend = runtime_backend.strip().lower() or "onnxruntime"
        self.device = device.strip().lower() or "cpu"
        self.det_frequency = max(1, int(det_frequency))
        self.min_keypoint_confidence = float(min_keypoint_confidence)
        self.max_poses = max(1, int(max_poses))
        self.fall_threshold = float(fall_threshold)
        self.tracking = bool(tracking)
        self._pose_tracker: Any = None
        self._load_error = ""

    @property
    def model_name(self) -> str:
        return f"RTMPose-{self.mode} ({self.runtime_backend}/{self.device})"

    def analyze(self, frame: Any, config: Dict[str, Any]) -> Dict[str, Any]:
        runtime_enabled = bool(config.get("pose_detection_enabled", self.enabled))
        if not runtime_enabled:
            return self._disabled_result("姿态检测未启用。")

        ready, message = self._ensure_ready()
        if not ready:
            return self._disabled_result(message, status="unavailable")

        try:
            keypoints, scores = self._pose_tracker(frame)
            poses = self._extract_poses(keypoints, scores, frame)
        except Exception as exc:
            return self._disabled_result(f"RTMPose 推理失败：{exc}", status="error")

        pose_count = len(poses)
        tags: list[str] = []
        action_hints = self._merge_hints([hint for pose in poses for hint in pose.get("action_hints", [])])
        if pose_count:
            tags.append("pose_detected")
        if any(pose.get("posture") == "lying" for pose in poses):
            tags.append("pose_low_body")
        if "hand_near_face" in action_hints:
            tags.append("pose_hand_near_face")

        threshold = float(config.get("pose_fall_threshold", self.fall_threshold))
        pose_fall_score = max([float(pose.get("fall_score") or 0.0) for pose in poses], default=0.0)
        pose_fall_candidate = pose_fall_score >= threshold
        if pose_fall_candidate:
            tags.append("pose_fall_candidate")
            action_hints = self._merge_hints([*action_hints, "fall_candidate"])

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
                "poses": poses,
                "pose_skeleton_edges": SKELETON_EDGES,
                "pose_action_hints": action_hints,
                "pose_fall_score": round(pose_fall_score, 4),
                "pose_fall_candidate": pose_fall_candidate,
                "pose_model_status": "ready",
                "pose_model_name": self.model_name,
                "pose_model_message": message,
                "pose_backend": "rtmpose",
                "pose_fall_threshold": threshold,
            },
        )
        return {
            "pose_count": pose_count,
            "poses": poses,
            "pose_skeleton_edges": SKELETON_EDGES,
            "pose_action_hints": action_hints,
            "pose_fall_score": round(pose_fall_score, 4),
            "pose_fall_candidate": pose_fall_candidate,
            "pose_model_status": "ready",
            "pose_model_name": self.model_name,
            "pose_model_message": message,
            "tags": tags,
            "result": result,
        }

    def _ensure_ready(self) -> tuple[bool, str]:
        if self._load_error:
            return False, self._load_error
        if self._pose_tracker is not None:
            return True, "RTMPose 模型已就绪。"
        try:
            from rtmlib import Body, PoseTracker  # type: ignore

            self._pose_tracker = PoseTracker(
                Body,
                det_frequency=self.det_frequency,
                tracking=self.tracking,
                mode=self.mode,
                to_openpose=False,
                backend=self.runtime_backend,
                device=self.device,
            )
        except ModuleNotFoundError as exc:
            self._load_error = f"姿态依赖未安装：{exc.name}"
            return False, self._load_error
        except Exception as exc:
            self._load_error = f"RTMPose 模型加载失败：{exc}"
            return False, self._load_error
        return True, "RTMPose 模型已就绪。"

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
            posture = self._estimate_posture(keypoint_payload)
            fall_score = self._estimate_fall_score(keypoint_payload, posture, frame_width, frame_height)
            action_hints = self._action_hints(keypoint_payload, posture, fall_score >= self.fall_threshold)
            poses.append(
                {
                    "keypoints": keypoint_payload,
                    "confidence": confidence,
                    "posture": posture,
                    "bbox": self._bbox_from_keypoints(visible, frame_width, frame_height),
                    "fall_score": fall_score,
                    "model_status": "ready",
                    "action_hints": action_hints,
                    "source": "rtmpose",
                }
            )
        poses.sort(key=lambda pose: float(pose.get("confidence") or 0.0), reverse=True)
        return poses

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
        by_name = {point["name"]: point for point in keypoints if point.get("visible")}
        left_shoulder = by_name.get("left_shoulder")
        right_shoulder = by_name.get("right_shoulder")
        left_hip = by_name.get("left_hip")
        right_hip = by_name.get("right_hip")
        shoulders = [point for point in [left_shoulder, right_shoulder] if point]
        hips = [point for point in [left_hip, right_hip] if point]
        knees = [point for point in [by_name.get("left_knee"), by_name.get("right_knee")] if point]
        ankles = [point for point in [by_name.get("left_ankle"), by_name.get("right_ankle")] if point]
        torso = [*shoulders, *hips]
        visible_points = list(by_name.values())
        if shoulders and (knees or ankles) and len(visible_points) >= 5:
            all_xs = [float(point["x"]) for point in visible_points]
            all_ys = [float(point["y"]) for point in visible_points]
            body_width = max(all_xs) - min(all_xs)
            body_height = max(all_ys) - min(all_ys)
            if body_width >= max(96.0, body_height * 2.15):
                return "lying"
        if len(torso) < 2:
            return "upper_body"

        xs = [float(point["x"]) for point in torso]
        ys = [float(point["y"]) for point in torso]
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        if shoulders and hips:
            mid_shoulder = self._midpoint(shoulders)
            mid_hip = self._midpoint(hips)
            torso_dx = abs(mid_hip[0] - mid_shoulder[0])
            torso_dy = abs(mid_hip[1] - mid_shoulder[1])
            if torso_dy <= max(26.0, torso_dx * 0.72) and width >= height * 0.95:
                return "lying"
        if width > height * 1.45:
            return "lying"
        if knees and not ankles:
            return "seated_or_half_body"
        if shoulders and not hips:
            return "upper_body"
        if height < 72:
            return "low_body"
        return "standing_or_sitting"

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
            "low_body": 0.48,
            "seated_or_half_body": 0.22,
            "upper_body": 0.08,
            "standing_or_sitting": 0.10,
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
        if posture in {"seated_or_half_body", "upper_body"}:
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

    def _disabled_result(self, message: str, status: str = "disabled") -> Dict[str, Any]:
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
                "pose_fall_candidate": False,
                "pose_model_status": status,
                "pose_model_name": self.model_name,
                "pose_model_message": message,
                "pose_backend": "rtmpose",
            },
        )
        return {
            "pose_count": 0,
            "poses": [],
            "pose_skeleton_edges": SKELETON_EDGES,
            "pose_action_hints": [],
            "pose_fall_score": 0.0,
            "pose_fall_candidate": False,
            "pose_model_status": status,
            "pose_model_name": self.model_name,
            "pose_model_message": message,
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
