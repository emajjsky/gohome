from __future__ import annotations

from typing import Any, Dict

from .base import AlgorithmResult, clamp


class ActivityAnalyzer:
    def analyze(
        self,
        people: list[Dict[str, Any]],
        poses: list[Dict[str, Any]],
        motion_score: float | None,
        config: Dict[str, Any],
        temporal: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        temporal = temporal or {}
        person_present = bool(people) or bool(poses)
        motion = float(motion_score or 0.0)
        enabled = bool(config.get("activity_detection_enabled", True))

        min_samples = max(2, int(config.get("activity_temporal_min_samples", 3)))
        sample_count = int(temporal.get("sample_count") or 0)
        enough_window = sample_count >= min_samples
        hand_ratio = float(temporal.get("hand_near_face_ratio") or 0.0)
        seated_ratio = float(temporal.get("seated_or_upper_body_ratio") or 0.0)
        low_motion_ratio = float(temporal.get("low_motion_ratio") or 0.0)
        active_motion_ratio = float(temporal.get("active_motion_ratio") or 0.0)
        pose_visible_ratio = float(temporal.get("pose_visible_ratio") or 0.0)
        mean_motion = float(temporal.get("mean_motion_score") or 0.0)
        current_hints = set(temporal.get("current_action_hints") or [])

        frame_still = person_present and motion_score is not None and motion <= float(config.get("stillness_motion_threshold", 0.004))
        stillness_score = clamp(low_motion_ratio * 0.62 + seated_ratio * 0.24 + pose_visible_ratio * 0.14)
        daze_score = clamp(low_motion_ratio * 0.54 + seated_ratio * 0.30 + (1.0 - min(1.0, hand_ratio * 3.0)) * 0.16)
        stillness_candidate = enabled and person_present and (
            (enough_window and stillness_score >= float(config.get("stillness_temporal_threshold", 0.68)))
            or (not enough_window and frame_still)
        )

        if enabled and person_present:
            confidence = max([float(person.get("confidence") or 0.0) for person in people], default=0.45)
            motion_component = clamp((motion - 0.003) / 0.045) if motion_score is not None else 0.25
            temporal_component = clamp(hand_ratio * 0.46 + seated_ratio * 0.24 + active_motion_ratio * 0.18 + pose_visible_ratio * 0.12)
            frame_hand_signal = 1.0 if "hand_near_face" in current_hints else 0.0
            meal_score = clamp(confidence * 0.22 + motion_component * 0.18 + temporal_component * 0.46 + frame_hand_signal * 0.14)
        else:
            meal_score = 0.0
        meal_candidate = enabled and person_present and enough_window and meal_score >= float(config.get("meal_temporal_threshold", 0.56))
        daze_candidate = enabled and person_present and enough_window and not meal_candidate and daze_score >= float(config.get("daze_temporal_threshold", 0.74)) and mean_motion <= float(config.get("daze_mean_motion_max", 0.010))

        tags: list[str] = []
        if stillness_candidate:
            tags.append("stillness_candidate")
        if daze_candidate:
            tags.append("daze_candidate")
        if meal_candidate:
            tags.append("meal_candidate")

        status = "disabled"
        summary = "动作识别未启用。"
        if enabled:
            if meal_candidate:
                status = "meal_candidate"
                summary = "时间窗口内出现用餐/手部活动候选。"
            elif daze_candidate:
                status = "daze_candidate"
                summary = "时间窗口内出现久坐/发呆观察候选。"
            elif stillness_candidate:
                status = "stillness_candidate"
                summary = "检测到静止观察候选。"
            else:
                status = "observing"
                summary = "动作状态观察中。"

        result = AlgorithmResult(
            algorithm_id="activity",
            label="用餐 / 动作识别",
            status=status,
            score=max(meal_score, stillness_score, daze_score) if enabled and person_present else None,
            level="info",
            summary=summary,
            tags=tags,
            data={
                "enabled": enabled,
                "person_present": person_present,
                "motion_score": motion_score,
                "temporal": temporal,
                "meal_score": meal_score,
                "meal_candidate": meal_candidate,
                "stillness_score": stillness_score,
                "stillness_candidate": stillness_candidate,
                "daze_score": daze_score,
                "daze_candidate": daze_candidate,
                "method": "pose_motion_temporal_window_v1",
            },
        )
        return {
            "activity": result.data,
            "meal_score": meal_score,
            "meal_candidate": meal_candidate,
            "stillness_score": stillness_score,
            "stillness_candidate": stillness_candidate,
            "daze_score": daze_score,
            "daze_candidate": daze_candidate,
            "tags": tags,
            "result": result,
        }
