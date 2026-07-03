from __future__ import annotations

from typing import Any, Dict

from .base import AlgorithmResult, clamp


class ActivityAnalyzer:
    def analyze(
        self,
        people: list[Dict[str, Any]],
        motion_score: float | None,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        person_present = bool(people)
        motion = float(motion_score or 0.0)
        enabled = bool(config.get("activity_detection_enabled", True))

        stillness_candidate = enabled and person_present and motion_score is not None and motion <= 0.004
        meal_score = 0.0
        if enabled and person_present:
            confidence = max([float(person.get("confidence") or 0.0) for person in people], default=0.45)
            motion_component = clamp((motion - 0.003) / 0.045) if motion_score is not None else 0.25
            meal_score = clamp(confidence * 0.58 + motion_component * 0.42)
        meal_candidate = enabled and meal_score >= 0.52

        tags: list[str] = []
        if stillness_candidate:
            tags.append("stillness_candidate")
        if meal_candidate:
            tags.append("meal_candidate")

        status = "disabled"
        summary = "动作识别未启用。"
        if enabled:
            status = "meal_candidate" if meal_candidate else "stillness_candidate" if stillness_candidate else "observing"
            summary = "检测到用餐/手部活动候选。" if meal_candidate else "检测到长时间静止候选。" if stillness_candidate else "动作状态观察中。"

        result = AlgorithmResult(
            algorithm_id="activity",
            label="用餐 / 动作识别",
            status=status,
            score=max(meal_score, 0.72 if stillness_candidate else 0.0) if enabled and person_present else None,
            level="info",
            summary=summary,
            tags=tags,
            data={
                "enabled": enabled,
                "person_present": person_present,
                "motion_score": motion_score,
                "meal_score": meal_score,
                "meal_candidate": meal_candidate,
                "stillness_candidate": stillness_candidate,
                "method": "person_motion_window_candidate_v1",
            },
        )
        return {
            "activity": result.data,
            "meal_score": meal_score,
            "meal_candidate": meal_candidate,
            "stillness_candidate": stillness_candidate,
            "tags": tags,
            "result": result,
        }
