from __future__ import annotations

from typing import Any, Dict

from .base import AlgorithmResult, clamp


class FallAnalyzer:
    def analyze(self, people: list[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
        candidates = [person for person in people if person.get("fall_candidate")]
        score = 0.0
        for person in people:
            aspect_ratio = float(person.get("aspect_ratio") or 0.0)
            center_y_ratio = float(person.get("center_y_ratio") or 0.0)
            area_ratio = float(person.get("area_ratio") or 0.0)
            score = max(score, clamp((aspect_ratio - 1.15) / 1.1) * 0.55 + clamp(center_y_ratio - 0.38) * 0.25 + clamp(area_ratio / 0.16) * 0.2)
        fall_candidate = bool(candidates)
        result = AlgorithmResult(
            algorithm_id="fall",
            label="跌倒候选",
            status="candidate" if fall_candidate else "clear",
            score=score if people else None,
            level="critical" if fall_candidate else "info",
            summary="检测到疑似倒地姿态。" if fall_candidate else "未命中跌倒候选。",
            tags=["fall_candidate"] if fall_candidate else [],
            data={
                "fall_candidate": fall_candidate,
                "candidate_count": len(candidates),
                "people": candidates,
                "method": "person_box_heuristic",
            },
        )
        return {
            "fall_candidate": fall_candidate,
            "fall_score": score if people else None,
            "tags": ["fall_candidate"] if fall_candidate else [],
            "result": result,
        }
