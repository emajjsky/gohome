from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class EventCandidate:
    event_type: str
    summary: str
    level: str = "warning"
    snapshot_id: Optional[int] = None
    payload: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RuleEvaluation:
    camera_id: int
    snapshot_id: Optional[int]
    evaluated_at: str
    candidates: list[EventCandidate]
    state: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "snapshot_id": self.snapshot_id,
            "evaluated_at": self.evaluated_at,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "state": self.state,
        }


class RuleEngine:
    def __init__(self) -> None:
        self.last_motion_at: Dict[int, datetime] = {}
        self.last_person_seen_at: Dict[int, datetime] = {}

    def evaluate_snapshot(
        self,
        camera: Dict[str, Any],
        snapshot: Dict[str, Any],
        analysis: Dict[str, Any],
        rules: Dict[str, Any],
    ) -> RuleEvaluation:
        now = utc_now()
        camera_id = int(camera["id"])
        snapshot_id = int(snapshot["id"])
        candidates: list[EventCandidate] = []
        state: Dict[str, Any] = {
            "motion_state": "unknown",
            "person_state": "unknown",
            "activity_state": "unknown",
            "no_motion_seconds": None,
            "no_person_seconds": None,
            "meal_candidate": bool(analysis.get("meal_candidate")),
            "meal_score": analysis.get("meal_score"),
            "stillness_candidate": bool(analysis.get("stillness_candidate")),
            "fall_score": analysis.get("fall_score"),
            "fire_score": analysis.get("fire_score"),
        }

        if analysis.get("black_screen") and rules.get("black_screen_enabled"):
            candidates.append(
                self._candidate(
                    event_type="black_screen",
                    summary=f"{camera.get('name', '摄像头')} 画面疑似黑屏或遮挡。",
                    level="warning",
                    snapshot_id=snapshot_id,
                    analysis=analysis,
                    rule={
                        "id": "black_screen",
                        "label": "黑屏/遮挡提醒",
                        "reason": "画面亮度和对比度同时低于阈值。",
                        "observed": {
                            "brightness": analysis.get("brightness"),
                            "contrast": analysis.get("contrast"),
                        },
                    },
                )
            )

        person_count = analysis.get("person_count")
        if person_count is not None and rules.get("person_detection_enabled"):
            if person_count > 0:
                self.last_person_seen_at[camera_id] = now
                state["person_state"] = "visible"
                state["no_person_seconds"] = 0
            else:
                last_seen_at = self.last_person_seen_at.setdefault(camera_id, now)
                no_person_seconds = int((now - last_seen_at).total_seconds())
                state["person_state"] = "not_visible"
                state["no_person_seconds"] = no_person_seconds
                if no_person_seconds >= int(rules["no_person_seconds"]):
                    candidates.append(
                        self._candidate(
                            event_type="no_person",
                            summary=f"{camera.get('name', '摄像头')} 已长时间没有检测到人。",
                            level="warning",
                            snapshot_id=snapshot_id,
                            analysis=analysis,
                            extra={"no_person_seconds": no_person_seconds},
                            rule={
                                "id": "no_person",
                                "label": "长时间无人提醒",
                                "reason": "连续未检测到人形的时长超过配置阈值。",
                                "observed": {"no_person_seconds": no_person_seconds},
                                "threshold": {"no_person_seconds": int(rules["no_person_seconds"])},
                            },
                        )
                    )

        if analysis.get("fall_candidate") and rules.get("fall_detection_enabled"):
            state["activity_state"] = "fall_candidate"
            candidates.append(
                self._candidate(
                    event_type="fall_candidate",
                    summary=f"{camera.get('name', '摄像头')} 检测到疑似跌倒姿态。",
                    level="critical",
                    snapshot_id=snapshot_id,
                    analysis=analysis,
                    rule={
                        "id": "fall_candidate",
                        "label": "疑似跌倒候选",
                        "reason": "YOLO 人体框比例、面积和画面位置命中跌倒候选启发式。",
                        "observed": {"people": analysis.get("people", [])},
                    },
                )
            )

        fire_score = float(analysis.get("fire_score") or 0.0)
        if rules.get("fire_detection_enabled") and (analysis.get("fire_candidate") or fire_score >= 0.035):
            state["activity_state"] = "fire_candidate"
            candidates.append(
                self._candidate(
                    event_type="fire_candidate",
                    summary=f"{camera.get('name', '摄像头')} 检测到疑似明火视觉线索。",
                    level="critical",
                    snapshot_id=snapshot_id,
                    analysis=analysis,
                    rule={
                        "id": "fire_candidate",
                        "label": "火灾应急报警",
                        "reason": "画面中高亮暖色区域达到火灾视觉线索阈值。",
                        "observed": {"fire_score": fire_score},
                        "threshold": {"fire_score": 0.035},
                    },
                )
            )

        motion_detected = bool(analysis.get("motion_detected"))
        if motion_detected:
            self.last_motion_at[camera_id] = now
            state["motion_state"] = "moving"
            state["no_motion_seconds"] = 0
        else:
            last_motion_at = self.last_motion_at.setdefault(camera_id, now)
            no_motion_seconds = int((now - last_motion_at).total_seconds())
            state["motion_state"] = "still"
            state["no_motion_seconds"] = no_motion_seconds
            if rules.get("no_motion_enabled") and no_motion_seconds >= int(rules["no_motion_seconds"]):
                candidates.append(
                    self._candidate(
                        event_type="no_motion",
                        summary=f"{camera.get('name', '摄像头')} 已长时间没有明显画面变化。",
                        level="warning",
                        snapshot_id=snapshot_id,
                        analysis=analysis,
                        extra={"no_motion_seconds": no_motion_seconds},
                        rule={
                            "id": "no_motion",
                            "label": "长时间无画面变化",
                            "reason": "连续低运动分数的时长超过配置阈值。",
                            "observed": {
                                "motion_score": analysis.get("motion_score"),
                                "no_motion_seconds": no_motion_seconds,
                            },
                            "threshold": {"no_motion_seconds": int(rules["no_motion_seconds"])},
                        },
                        )
                    )

        if rules.get("activity_detection_enabled"):
            critical_state = state.get("activity_state") in {"fall_candidate", "fire_candidate"}
            if analysis.get("meal_candidate") and not critical_state:
                state["activity_state"] = "meal_candidate"
            elif analysis.get("stillness_candidate") and not critical_state and state.get("activity_state") == "unknown":
                state["activity_state"] = "stillness_candidate"
            elif not critical_state and state.get("activity_state") == "unknown":
                state["activity_state"] = "observing"

        return RuleEvaluation(
            camera_id=camera_id,
            snapshot_id=snapshot_id,
            evaluated_at=now.isoformat(),
            candidates=candidates,
            state=state,
        )

    def evaluate_camera_error(
        self,
        camera: Dict[str, Any],
        rules: Dict[str, Any],
        error: str,
    ) -> RuleEvaluation:
        now = utc_now()
        candidate = None
        if rules.get("offline_enabled"):
            candidate = EventCandidate(
                event_type="camera_offline",
                summary=f"{camera.get('name', '摄像头')} 无法连接：{error}",
                level="critical",
                payload={
                    "error": error,
                    "rule": {
                        "id": "camera_offline",
                        "label": "摄像头离线提醒",
                        "reason": "edge-agent 无法打开或读取摄像头视频流。",
                    },
                },
            )
        return RuleEvaluation(
            camera_id=int(camera["id"]),
            snapshot_id=None,
            evaluated_at=now.isoformat(),
            candidates=[candidate] if candidate else [],
            state={"camera_state": "offline", "error": error},
        )

    def _candidate(
        self,
        event_type: str,
        summary: str,
        level: str,
        snapshot_id: int,
        analysis: Dict[str, Any],
        rule: Dict[str, Any],
        extra: Optional[Dict[str, Any]] = None,
    ) -> EventCandidate:
        payload = {**analysis, **(extra or {})}
        payload["rule"] = rule
        return EventCandidate(
            event_type=event_type,
            summary=summary,
            level=level,
            snapshot_id=snapshot_id,
            payload=payload,
        )
