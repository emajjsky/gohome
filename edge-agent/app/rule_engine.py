from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import math
from typing import Any, Dict, Optional


DYNAMIC_FLOOR_BOTTOM_Y = 0.88


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def event_category(event_type: str) -> str:
    if event_type in {"fall_candidate", "prolonged_floor_lying", "fire_candidate"}:
        return "safety_alert"
    if event_type in {"black_screen", "camera_offline"}:
        return "device_alert"
    if event_type in {"no_motion", "no_person"}:
        return "life_observation"
    return "system_event"


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
        self.fall_tracks: Dict[int, Dict[str, Any]] = {}
        self.fall_upright_states: Dict[int, Dict[str, Any]] = {}
        self.fire_confirm_counts: Dict[int, int] = {}
        self.prolonged_floor_tracks: Dict[int, set[str]] = {}

    def reset_camera(self, camera_id: int) -> None:
        camera_id = int(camera_id)
        self.last_motion_at.pop(camera_id, None)
        self.last_person_seen_at.pop(camera_id, None)
        self.fall_tracks.pop(camera_id, None)
        self.fall_upright_states.pop(camera_id, None)
        self.fire_confirm_counts.pop(camera_id, None)
        self.prolonged_floor_tracks.pop(camera_id, None)

    def evaluate_snapshot(
        self,
        camera: Dict[str, Any],
        snapshot: Dict[str, Any],
        analysis: Dict[str, Any],
        rules: Dict[str, Any],
    ) -> RuleEvaluation:
        now = utc_now()
        camera_id = int(camera["id"])
        raw_snapshot_id = snapshot.get("id")
        snapshot_id = int(raw_snapshot_id) if raw_snapshot_id is not None else None
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
            "daze_candidate": bool(analysis.get("daze_candidate")),
            "daze_score": analysis.get("daze_score"),
            "fall_score": analysis.get("fall_score"),
            "fall_state": "clear",
            "fall_confirm_count": 0,
            "fire_score": analysis.get("fire_score"),
            "fire_state": "clear",
            "fire_confirm_count": 0,
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
                            level="info",
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

        fall_runtime = self._evaluate_fall_state(camera_id, now, analysis, rules)
        state.update(fall_runtime["state"])
        if rules.get("fall_detection_enabled") and fall_runtime["emit_event"]:
            state["activity_state"] = "fall_candidate"
            candidates.append(
                self._candidate(
                    event_type="fall_candidate",
                    summary=f"{camera.get('name', '摄像头')} 连续复核确认疑似跌倒。",
                    level="critical",
                    snapshot_id=snapshot_id,
                    analysis=analysis,
                    rule={
                        "id": "fall_candidate",
                        "label": "跌倒应急报警",
                        "reason": "同一人体先出现站坐状态，随后快速下降，并达到连续姿态证据、帧数、持续时间和置信度阈值。",
                        "observed": {
                            **fall_runtime["observed"],
                            "people": analysis.get("people", []),
                            "poses": analysis.get("poses", []),
                        },
                        "threshold": fall_runtime["threshold"],
                    },
                )
            )

        factor_graph = analysis.get("pose_factor_graph") if isinstance(analysis.get("pose_factor_graph"), dict) else {}
        prolonged_tracks = factor_graph.get("prolonged_floor_lying_tracks") if isinstance(factor_graph.get("prolonged_floor_lying_tracks"), list) else []
        current_prolonged_ids = {str(item.get("track_id") or "") for item in prolonged_tracks if item.get("track_id")}
        previous_prolonged_ids = self.prolonged_floor_tracks.get(camera_id, set())
        new_prolonged_tracks = [item for item in prolonged_tracks if str(item.get("track_id") or "") not in previous_prolonged_ids]
        self.prolonged_floor_tracks[camera_id] = current_prolonged_ids
        state["prolonged_floor_lying_tracks"] = sorted(current_prolonged_ids)
        if rules.get("fall_detection_enabled") and new_prolonged_tracks:
            target = max(new_prolonged_tracks, key=lambda item: float(item.get("lying_duration_seconds") or 0.0))
            duration_seconds = float(target.get("lying_duration_seconds") or 0.0)
            state["activity_state"] = "prolonged_floor_lying"
            candidates.append(
                self._candidate(
                    event_type="prolonged_floor_lying",
                    summary=f"{camera.get('name', '摄像头')} 检测到非床或沙发区域持续躺卧。",
                    level="critical",
                    snapshot_id=snapshot_id,
                    analysis=analysis,
                    rule={
                        "id": "prolonged_floor_lying",
                        "label": "长时间倒地提醒",
                        "reason": "同一人体在非床或沙发区域连续保持躺卧姿态超过 3 分钟，且尚未检测到恢复。",
                        "observed": {
                            "track_id": target.get("track_id"),
                            "posture": target.get("posture"),
                            "posture_confidence": target.get("posture_confidence"),
                            "lying_duration_seconds": duration_seconds,
                            "scene_zone": target.get("scene_zone_label"),
                            "factor_graph": target,
                        },
                        "threshold": {
                            "lying_duration_seconds": 180,
                            "normal_lying_zone": False,
                        },
                    },
                )
            )

        fire_score = float(analysis.get("fire_score") or 0.0)
        motion_score = analysis.get("motion_score")
        fire_threshold = float((analysis.get("thresholds") or {}).get("fire_score_threshold") or 0.035)
        fire_event_threshold = max(fire_threshold, float(rules.get("fire_event_score_threshold") or 0.12))
        fire_motion_threshold = float(rules.get("fire_motion_threshold") or 0.035)
        fire_temporal_threshold = float(rules.get("fire_temporal_threshold") or 0.018)
        fire_confirm_frames = max(5, int(rules.get("fire_confirm_frames") or 5))
        fire_temporal_score = analysis.get("fire_temporal_score")
        fire_event_candidate = bool(analysis.get("fire_event_candidate"))
        fire_visual_hit = fire_event_candidate and fire_score >= fire_event_threshold
        fire_motion_ok = motion_score is not None and float(motion_score) >= fire_motion_threshold
        fire_temporal_ok = fire_temporal_score is not None and float(fire_temporal_score) >= fire_temporal_threshold
        if fire_visual_hit and fire_motion_ok and fire_temporal_ok:
            self.fire_confirm_counts[camera_id] = self.fire_confirm_counts.get(camera_id, 0) + 1
            state["fire_state"] = "confirming"
        else:
            self.fire_confirm_counts[camera_id] = 0
            if bool(analysis.get("fire_candidate")):
                state["fire_state"] = "visual_only"
        state["fire_confirm_count"] = self.fire_confirm_counts.get(camera_id, 0)
        fire_confirmed = state["fire_confirm_count"] >= fire_confirm_frames
        if rules.get("fire_detection_enabled") and fire_confirmed:
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
                        "reason": "连续帧中出现橙黄高亮纹理且画面存在变化，达到火灾视觉线索阈值。",
                        "observed": {
                            "fire_score": fire_score,
                            "motion_score": motion_score,
                            "temporal_score": fire_temporal_score,
                            "confirm_frames": state["fire_confirm_count"],
                            "fire_features": analysis.get("fire_features") or {},
                        },
                        "threshold": {
                            "fire_score": fire_event_threshold,
                            "motion_score": fire_motion_threshold,
                            "temporal_score": fire_temporal_threshold,
                            "confirm_frames": fire_confirm_frames,
                        },
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
            person_present = int(analysis.get("person_count") or 0) > 0
            if rules.get("no_motion_enabled") and person_present and no_motion_seconds >= int(rules["no_motion_seconds"]):
                candidates.append(
                    self._candidate(
                        event_type="no_motion",
                        summary=f"{camera.get('name', '摄像头')} 已长时间没有明显画面变化。",
                        level="info",
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
            elif analysis.get("daze_candidate") and not critical_state:
                state["activity_state"] = "daze_candidate"
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
            rule = {
                "id": "camera_offline",
                "label": "摄像头离线提醒",
                "reason": "edge-agent 无法打开或读取摄像头视频流。",
            }
            summary = f"{camera.get('name', '摄像头')} 无法连接：{error}"
            candidate = EventCandidate(
                event_type="camera_offline",
                summary=summary,
                level="critical",
                payload={
                    "error": error,
                    "rule": rule,
                    "evidence": build_event_evidence(
                        event_type="camera_offline",
                        summary=summary,
                        level="critical",
                        analysis={"tags": ["camera_offline"]},
                        rule=rule,
                        extra={"error": error},
                    ),
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
        snapshot_id: Optional[int],
        analysis: Dict[str, Any],
        rule: Dict[str, Any],
        extra: Optional[Dict[str, Any]] = None,
    ) -> EventCandidate:
        payload = {**analysis, **(extra or {})}
        payload["rule"] = rule
        payload["evidence"] = build_event_evidence(
            event_type=event_type,
            summary=summary,
            level=level,
            analysis=analysis,
            rule=rule,
            extra=extra,
        )
        return EventCandidate(
            event_type=event_type,
            summary=summary,
            level=level,
            snapshot_id=snapshot_id,
            payload=payload,
        )

    def _fall_evidence(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        algorithm_results = analysis.get("algorithm_results") if isinstance(analysis.get("algorithm_results"), dict) else {}
        fall_result = algorithm_results.get("fall") if isinstance(algorithm_results.get("fall"), dict) else {}
        fall_data = fall_result.get("data") if isinstance(fall_result.get("data"), dict) else {}
        people = fall_data.get("people") if isinstance(fall_data.get("people"), list) else []
        evidence_types = []
        if bool(analysis.get("pose_fall_candidate")):
            evidence_types.append("pose")
        for item in people:
            method = str(item.get("method") or item.get("source") or "").strip()
            if method and method not in evidence_types:
                evidence_types.append(method)
        if fall_data.get("single_low_body") and "single_low_body" not in evidence_types:
            evidence_types.append("single_low_body")
        if fall_data.get("floor_cluster") and "floor_cluster" not in evidence_types:
            evidence_types.append("floor_cluster")
        return {
            "types": evidence_types,
            "candidate_count": fall_data.get("candidate_count"),
            "single_low_body": fall_data.get("single_low_body"),
            "floor_cluster": fall_data.get("floor_cluster"),
        }

    def _evaluate_fall_state(
        self,
        camera_id: int,
        now: datetime,
        analysis: Dict[str, Any],
        rules: Dict[str, Any],
    ) -> Dict[str, Any]:
        fall_candidate = bool(analysis.get("fall_candidate"))
        pose_fall = bool(analysis.get("pose_fall_candidate"))
        fall_score = float(analysis.get("fall_score") or 0.0)
        pose_fall_score = float(analysis.get("pose_fall_score") or 0.0)
        thresholds = analysis.get("thresholds") if isinstance(analysis.get("thresholds"), dict) else {}
        fall_score_threshold = float(rules.get("fall_score_threshold") or 0.50)
        pose_fall_threshold = float(thresholds.get("pose_fall_threshold") or 0.78)
        confirm_frames = max(2, int(rules.get("fall_confirm_frames") or 2))
        confirm_seconds = max(0, int(rules.get("fall_confirm_seconds", 4)))
        dynamic_confirm_frames = max(3, confirm_frames)
        dynamic_confirm_seconds = min(float(confirm_seconds), 2.0)
        recover_frames = max(2, int(rules.get("fall_recover_frames") or 2))
        fall_evidence = self._fall_evidence(analysis)
        target = self._fall_target(analysis, fall_evidence)
        factor_graph = analysis.get("pose_factor_graph") if isinstance(analysis.get("pose_factor_graph"), dict) else {}
        graph_candidate = bool(factor_graph.get("fast_fall_candidate"))
        graph_score = float(factor_graph.get("fast_fall_score") or 0.0)
        upright_before = self.fall_upright_states.get(camera_id) or {}
        upright_targets = self._upright_targets(analysis)
        transition = self._fall_transition(target, upright_before, now, analysis, rules)
        normal_lying_zone = bool(target and target.get("normal_lying_zone"))

        fall_score_ok = fall_score >= fall_score_threshold
        pose_score_ok = pose_fall and pose_fall_score >= pose_fall_threshold
        strong_visual_candidate = bool(target) and (
            (fall_candidate and (fall_score_ok or pose_score_ok)) or graph_candidate
        )
        visual_candidate = bool(target) and (fall_candidate or graph_candidate)
        previous = self.fall_tracks.get(camera_id) or {}
        same_observed_target = bool(previous and target and self._same_fall_target(previous.get("target"), target))
        transition_confirmed = (
            bool(transition.get("confirmed"))
            or graph_candidate
            or bool(previous.get("transition_confirmed") and same_observed_target)
        )
        fast_transition_confirmed = bool(
            graph_candidate
            or (previous.get("fast_transition_confirmed") and same_observed_target)
        )
        dynamic_scene_override = bool(normal_lying_zone and pose_score_ok and transition_confirmed)
        scene_suppressed = bool(normal_lying_zone and not dynamic_scene_override)
        strong_candidate = strong_visual_candidate and transition_confirmed and not scene_suppressed
        dynamic_low_position = self._dynamic_low_position_signal(
            target,
            transition_confirmed=transition_confirmed,
        )
        dynamic_transition_signal = bool(
            transition_confirmed
            and not scene_suppressed
            and (strong_visual_candidate or dynamic_low_position)
        )
        confirmation_signal = bool(strong_candidate or dynamic_transition_signal)
        same_target = bool(confirmation_signal and same_observed_target)

        if confirmation_signal:
            if not same_target or previous.get("stage") in {"clear", "recovered"}:
                track = {
                    "stage": "suspect",
                    "started_at": now,
                    "last_seen_at": now,
                    "confirm_count": 1 if strong_candidate else 0,
                    "dynamic_low_count": 1 if dynamic_transition_signal else 0,
                    "clear_count": 0,
                    "target": target,
                    "alert_emitted": False,
                    "first_score": fall_score,
                    "max_score": max(fall_score, pose_fall_score, graph_score),
                    "transition_confirmed": transition_confirmed,
                    "fast_transition_confirmed": fast_transition_confirmed,
                    "confirmation_path": "dynamic_low_position" if dynamic_transition_signal else "standard",
                }
            else:
                track = {
                    **previous,
                    "last_seen_at": now,
                    "confirm_count": int(previous.get("confirm_count") or 0) + int(strong_candidate),
                    "dynamic_low_count": int(previous.get("dynamic_low_count") or 0) + int(dynamic_transition_signal),
                    "clear_count": 0,
                    "target": target,
                    "max_score": max(float(previous.get("max_score") or 0.0), fall_score, pose_fall_score, graph_score),
                    "transition_confirmed": transition_confirmed,
                    "fast_transition_confirmed": fast_transition_confirmed,
                    "confirmation_path": (
                        "dynamic_low_position"
                        if dynamic_transition_signal or previous.get("confirmation_path") == "dynamic_low_position"
                        else str(previous.get("confirmation_path") or "standard")
                    ),
                }
            duration = max(0.0, (now - track["started_at"]).total_seconds())
            track["duration_seconds"] = duration
            fast_path_confirmed = bool(
                track.get("fast_transition_confirmed")
                and int(track.get("confirm_count") or 0) >= confirm_frames
            )
            dynamic_path_confirmed = bool(
                track.get("confirmation_path") == "dynamic_low_position"
                and int(track.get("dynamic_low_count") or 0) >= dynamic_confirm_frames
                and duration >= dynamic_confirm_seconds
            )
            standard_path_confirmed = bool(
                int(track.get("confirm_count") or 0) >= confirm_frames
                and duration >= confirm_seconds
            )
            if fast_path_confirmed or dynamic_path_confirmed or standard_path_confirmed:
                track["stage"] = "confirmed"
                track["confirmation_path"] = (
                    "fast_factor_graph"
                    if fast_path_confirmed
                    else "dynamic_low_position"
                    if dynamic_path_confirmed
                    else "standard"
                )
            elif int(track.get("confirm_count") or 0) > 1 or int(track.get("dynamic_low_count") or 0) > 1:
                track["stage"] = "confirming"
            else:
                track["stage"] = "suspect"
            emit_event = track["stage"] == "confirmed" and not bool(track.get("alert_emitted"))
            if emit_event:
                track["alert_emitted"] = True
            self.fall_tracks[camera_id] = track
        else:
            track = {**previous} if previous else {}
            if scene_suppressed and visual_candidate:
                track = {
                    "stage": "normal_lying_zone",
                    "started_at": now,
                    "last_seen_at": now,
                    "confirm_count": 0,
                    "clear_count": 0,
                    "target": target,
                    "alert_emitted": False,
                    "duration_seconds": 0.0,
                }
            elif strong_visual_candidate and not transition.get("confirmed"):
                track = {
                    "stage": "awaiting_transition",
                    "started_at": now,
                    "last_seen_at": now,
                    "confirm_count": 0,
                    "clear_count": 0,
                    "target": target,
                    "alert_emitted": False,
                    "duration_seconds": 0.0,
                }
            elif track.get("stage") in {"suspect", "confirming", "confirmed"}:
                track["clear_count"] = int(track.get("clear_count") or 0) + 1
                if track["clear_count"] >= recover_frames:
                    track = {
                        "stage": "recovered",
                        "started_at": previous.get("started_at"),
                        "last_seen_at": now,
                        "confirm_count": 0,
                        "dynamic_low_count": 0,
                        "clear_count": int(track["clear_count"]),
                        "target": previous.get("target"),
                        "alert_emitted": bool(previous.get("alert_emitted")),
                        "duration_seconds": max(0.0, (now - previous.get("started_at", now)).total_seconds()) if previous.get("started_at") else 0.0,
                    }
            elif visual_candidate:
                track = {
                    "stage": "visual_only",
                    "started_at": now,
                    "last_seen_at": now,
                    "confirm_count": 0,
                    "clear_count": 0,
                    "target": target,
                    "alert_emitted": False,
                    "duration_seconds": 0.0,
                }
            else:
                track = {
                    "stage": "clear",
                    "started_at": None,
                    "last_seen_at": now,
                    "confirm_count": 0,
                    "clear_count": int(track.get("clear_count") or 0),
                    "target": None,
                    "alert_emitted": False,
                    "duration_seconds": 0.0,
                }
            emit_event = False
            self.fall_tracks[camera_id] = track

        if upright_targets and not (visual_candidate or dynamic_transition_signal):
            self._record_upright_targets(camera_id, now, upright_targets, rules)

        duration_seconds = float(track.get("duration_seconds") or 0.0)
        stage = str(track.get("stage") or "clear")
        threshold = {
            "fall_score": fall_score_threshold,
            "pose_fall_score": pose_fall_threshold,
            "confirm_frames": confirm_frames,
            "confirm_seconds": confirm_seconds,
            "dynamic_confirm_frames": dynamic_confirm_frames,
            "dynamic_confirm_seconds": dynamic_confirm_seconds,
            "dynamic_floor_bottom_y": DYNAMIC_FLOOR_BOTTOM_Y,
            "recover_frames": recover_frames,
            "transition_window_seconds": int(transition.get("window_seconds") or 20),
            "min_vertical_drop": float(transition.get("min_vertical_drop") or 0.12),
            "transition_motion_score": float(transition.get("motion_threshold") or 0.02),
        }
        observed = {
            "fall_score": fall_score,
            "pose_fall_score": pose_fall_score,
            "pose_factor_graph_score": graph_score,
            "confirm_frames": int(track.get("confirm_count") or 0),
            "dynamic_low_count": int(track.get("dynamic_low_count") or 0),
            "duration_seconds": round(duration_seconds, 3),
            "confirmation_path": str(track.get("confirmation_path") or "standard"),
            "fast_transition_confirmed": bool(track.get("fast_transition_confirmed")),
            "same_target": bool(same_target),
            "target": target,
            "evidence": fall_evidence,
            "scene_suppressed": scene_suppressed,
            "scene_zone": target.get("scene_zone_label") if target else None,
            "transition": {**transition, "confirmed": transition_confirmed, "inherited": transition_confirmed and not bool(transition.get("confirmed"))},
        }
        return {
            "emit_event": bool(emit_event),
            "observed": observed,
            "threshold": threshold,
            "state": {
                "fall_state": stage,
                "fall_stage": stage,
                "fall_confirm_count": int(track.get("confirm_count") or 0),
                "fall_dynamic_low_count": int(track.get("dynamic_low_count") or 0),
                "fall_confirm_seconds": round(duration_seconds, 3),
                "fall_confirmation_path": str(track.get("confirmation_path") or "standard"),
                "fall_clear_count": int(track.get("clear_count") or 0),
                "fall_alert_emitted": bool(track.get("alert_emitted")),
                "fall_target": target,
                "fall_scene_suppressed": scene_suppressed,
                "fall_transition_confirmed": transition_confirmed,
                "fall_fast_transition_confirmed": bool(track.get("fast_transition_confirmed")),
                "fall_transition": {**transition, "confirmed": transition_confirmed, "inherited": transition_confirmed and not bool(transition.get("confirmed"))},
                "fall_score": fall_score,
                "pose_fall_score": pose_fall_score,
                "pose_factor_graph_score": graph_score,
                "fall_threshold": threshold,
            },
        }

    def _dynamic_low_position_signal(
        self,
        target: Dict[str, Any] | None,
        *,
        transition_confirmed: bool,
    ) -> bool:
        if not target or not transition_confirmed or bool(target.get("normal_lying_zone")):
            return False
        posture = str(target.get("posture") or "")
        if posture not in {"lying", "sitting", "upper_body"}:
            return False
        if str(target.get("scene_zone_label") or "").lower() in {"bed", "couch", "chair", "sofa"}:
            return False
        center = target.get("center")
        if not isinstance(center, list) or len(center) != 2 or float(center[1]) < 0.62:
            return False
        if posture in {"sitting", "upper_body"} and float(target.get("bottom_y") or 0.0) < DYNAMIC_FLOOR_BOTTOM_Y:
            return False
        return float(target.get("score") or 0.0) >= 0.18

    def _fall_target(self, analysis: Dict[str, Any], fall_evidence: Dict[str, Any]) -> Dict[str, Any] | None:
        candidates = []
        factor_graph = analysis.get("pose_factor_graph") if isinstance(analysis.get("pose_factor_graph"), dict) else {}
        graph_target = factor_graph.get("fast_fall_track")
        if isinstance(graph_target, dict) and self._valid_bbox(graph_target.get("bbox")):
            candidates.append({**graph_target, "source": "pose_factor_graph", "score": graph_target.get("fast_fall_score")})
        for key in ("single_low_body", "floor_cluster"):
            item = fall_evidence.get(key)
            if isinstance(item, dict) and self._valid_bbox(item.get("bbox")):
                candidates.append(item)
        people = analysis.get("people") if isinstance(analysis.get("people"), list) else []
        candidates.extend([person for person in people if person.get("fall_candidate") and self._valid_bbox(person.get("bbox"))])
        if not candidates:
            poses = analysis.get("poses") if isinstance(analysis.get("poses"), list) else []
            candidates.extend([pose for pose in poses if self._valid_bbox(pose.get("bbox")) and float(pose.get("fall_score") or 0.0) > 0])
        if not candidates:
            return None
        best = max(candidates, key=lambda item: float(item.get("score") or item.get("fall_score") or item.get("confidence") or 0.0))
        bbox = [float(value) for value in best.get("bbox")]
        x1, y1, x2, y2 = bbox
        width = max(1.0, float(best.get("frame_width") or analysis.get("image_width") or 640))
        height = max(1.0, float(best.get("frame_height") or analysis.get("image_height") or 360))
        return {
            "bbox": [round(value, 1) for value in bbox],
            "center": [round(((x1 + x2) / 2.0) / width, 4), round(((y1 + y2) / 2.0) / height, 4)],
            "size": [round((x2 - x1) / width, 4), round((y2 - y1) / height, 4)],
            "bottom_y": round(y2 / height, 4),
            "source": best.get("source") or best.get("method") or "fall_candidate",
            "track_id": best.get("track_id"),
            "score": round(float(best.get("score") or best.get("fall_score") or best.get("confidence") or 0.0), 4),
            "posture": best.get("posture"),
            "normal_lying_zone": bool(best.get("normal_lying_zone")),
            "scene_zone_id": best.get("scene_zone_id"),
            "scene_zone_label": best.get("scene_zone_label"),
            "scene_zone_label_zh": best.get("scene_zone_label_zh"),
            "scene_zone_overlap": best.get("scene_zone_overlap"),
        }

    def _upright_targets(self, analysis: Dict[str, Any]) -> list[Dict[str, Any]]:
        width = max(1.0, float(analysis.get("image_width") or 640))
        height = max(1.0, float(analysis.get("image_height") or 360))
        targets = []
        poses = analysis.get("poses") if isinstance(analysis.get("poses"), list) else []
        for pose in poses:
            posture = str(pose.get("posture") or "")
            if posture not in {
                "standing", "sitting",
                "standing_or_sitting", "seated_or_half_body",
            }:
                continue
            if pose.get("person_evidence_eligible") is False or not self._valid_bbox(pose.get("bbox")):
                continue
            targets.append(self._normalized_target(pose, width, height, posture=posture))
        if targets:
            return targets
        people = analysis.get("people") if isinstance(analysis.get("people"), list) else []
        for person in people:
            if person.get("fall_candidate") or person.get("presence_candidate") or not self._valid_bbox(person.get("bbox")):
                continue
            if float(person.get("aspect_ratio") or 0.0) > 1.25:
                continue
            targets.append(self._normalized_target(person, width, height, posture="person_upright"))
        return targets

    def _record_upright_targets(
        self,
        camera_id: int,
        now: datetime,
        targets: list[Dict[str, Any]],
        rules: Dict[str, Any],
    ) -> None:
        window_seconds = max(5, int(rules.get("fall_transition_window_seconds") or 20))
        previous = self.fall_upright_states.get(camera_id) or {}
        fallback_observed_at = previous.get("observed_at")
        history = previous.get("targets") if isinstance(previous.get("targets"), list) else []
        retained = []
        for item in history:
            observed_at = item.get("_observed_at") if isinstance(item, dict) else None
            if not isinstance(observed_at, datetime):
                observed_at = fallback_observed_at
            if not isinstance(observed_at, datetime):
                continue
            if max(0.0, (now - observed_at).total_seconds()) <= window_seconds:
                retained.append({**item, "_observed_at": observed_at})
        retained.extend({**target, "_observed_at": now} for target in targets)
        self.fall_upright_states[camera_id] = {
            "observed_at": now,
            "targets": retained[-24:],
        }

    def _normalized_target(self, item: Dict[str, Any], width: float, height: float, *, posture: str) -> Dict[str, Any]:
        bbox = [float(value) for value in item.get("bbox")]
        x1, y1, x2, y2 = bbox
        return {
            "bbox": [round(value, 1) for value in bbox],
            "center": [round(((x1 + x2) / 2.0) / width, 4), round(((y1 + y2) / 2.0) / height, 4)],
            "bottom_y": round(y2 / height, 4),
            "posture": posture,
            "source": item.get("source") or "upright_history",
            "track_id": item.get("track_id"),
            "score": round(float(item.get("confidence") or 0.0), 4),
        }

    def _fall_transition(
        self,
        target: Dict[str, Any] | None,
        upright_state: Dict[str, Any],
        now: datetime,
        analysis: Dict[str, Any],
        rules: Dict[str, Any],
    ) -> Dict[str, Any]:
        window_seconds = max(5, int(rules.get("fall_transition_window_seconds") or 20))
        min_vertical_drop = max(0.05, float(rules.get("fall_min_vertical_drop") or 0.12))
        motion_threshold = max(0.01, float(rules.get("fall_transition_motion_score") or 0.02))
        result = {
            "confirmed": False,
            "reason": "no_recent_upright",
            "window_seconds": window_seconds,
            "min_vertical_drop": min_vertical_drop,
            "motion_threshold": motion_threshold,
            "age_seconds": None,
            "vertical_drop": None,
            "horizontal_distance": None,
            "motion_score": analysis.get("motion_score"),
            "upright_target": None,
        }
        upright_targets = upright_state.get("targets") if isinstance(upright_state.get("targets"), list) else []
        fallback_observed_at = upright_state.get("observed_at")
        if target is None or not upright_targets:
            return result
        recent_targets = []
        for item in upright_targets:
            if not isinstance(item, dict):
                continue
            observed_at = item.get("_observed_at")
            if not isinstance(observed_at, datetime):
                observed_at = fallback_observed_at
            if not isinstance(observed_at, datetime):
                continue
            age_seconds = max(0.0, (now - observed_at).total_seconds())
            if age_seconds <= window_seconds:
                recent_targets.append((item, observed_at, age_seconds))
        if not recent_targets:
            result["reason"] = "upright_too_old"
            return result
        target_center = target.get("center")
        if not isinstance(target_center, list) or len(target_center) != 2:
            result["reason"] = "missing_target_center"
            return result
        target_track_id = str(target.get("track_id") or "")
        same_track_candidates = [
            item for item in recent_targets
            if target_track_id and str(item[0].get("track_id") or "") == target_track_id
        ]
        if target_track_id and int(analysis.get("person_count") or 0) > 1 and not same_track_candidates:
            result["reason"] = "track_identity_missing"
            return result
        spatial_candidates = [
            item for item in recent_targets
            if abs(float((item[0].get("center") or [0, 0])[0]) - float(target_center[0])) <= 0.28
        ]
        candidates = same_track_candidates or spatial_candidates or recent_targets
        best, observed_at, age_seconds = max(
            candidates,
            key=lambda item: float(target_center[1]) - float((item[0].get("center") or [0, 0])[1]),
        )
        result["age_seconds"] = round(age_seconds, 3)
        upright_center = best.get("center") or [0, 0]
        horizontal_distance = abs(float(upright_center[0]) - float(target_center[0]))
        vertical_drop = float(target_center[1]) - float(upright_center[1])
        motion_score = float(analysis.get("motion_score") or 0.0)
        spatial_match = bool(spatial_candidates) and horizontal_distance <= 0.28
        descent = vertical_drop >= min_vertical_drop
        motion_ok = motion_score >= motion_threshold or vertical_drop >= min_vertical_drop * 1.5
        result.update({
            "confirmed": bool(spatial_match and descent and motion_ok),
            "reason": "confirmed" if spatial_match and descent and motion_ok else ("target_too_far" if not spatial_match else "insufficient_descent"),
            "vertical_drop": round(vertical_drop, 4),
            "horizontal_distance": round(horizontal_distance, 4),
            "upright_target": {key: value for key, value in best.items() if key != "_observed_at"},
        })
        return result

    def _same_fall_target(self, previous: Any, current: Any) -> bool:
        if not isinstance(previous, dict) or not isinstance(current, dict):
            return False
        prev_center = previous.get("center")
        curr_center = current.get("center")
        if not isinstance(prev_center, list) or not isinstance(curr_center, list) or len(prev_center) != 2 or len(curr_center) != 2:
            return False
        dx = float(prev_center[0]) - float(curr_center[0])
        dy = float(prev_center[1]) - float(curr_center[1])
        distance = math.sqrt(dx * dx + dy * dy)
        same_track = bool(previous.get("track_id") and previous.get("track_id") == current.get("track_id"))
        plausible_same_track = same_track and distance <= 0.38
        return plausible_same_track or distance <= 0.22 or self._bbox_overlap(previous.get("bbox"), current.get("bbox")) >= 0.20

    def _valid_bbox(self, bbox: Any) -> bool:
        if not isinstance(bbox, list) or len(bbox) != 4:
            return False
        try:
            x1, y1, x2, y2 = [float(value) for value in bbox]
        except (TypeError, ValueError):
            return False
        return x2 > x1 and y2 > y1

    def _bbox_overlap(self, first: Any, second: Any) -> float:
        if not self._valid_bbox(first) or not self._valid_bbox(second):
            return 0.0
        ax1, ay1, ax2, ay2 = [float(value) for value in first]
        bx1, by1, bx2, by2 = [float(value) for value in second]
        ix1 = max(ax1, bx1)
        iy1 = max(ay1, by1)
        ix2 = min(ax2, bx2)
        iy2 = min(ay2, by2)
        inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
        if inter <= 0:
            return 0.0
        first_area = max(1.0, (ax2 - ax1) * (ay2 - ay1))
        second_area = max(1.0, (bx2 - bx1) * (by2 - by1))
        return inter / min(first_area, second_area)


def build_event_evidence(
    *,
    event_type: str,
    summary: str,
    level: str,
    analysis: Dict[str, Any],
    rule: Dict[str, Any],
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    people = analysis.get("people") if isinstance(analysis.get("people"), list) else []
    pets = analysis.get("pets") if isinstance(analysis.get("pets"), list) else []
    poses = analysis.get("poses") if isinstance(analysis.get("poses"), list) else []
    algorithm_results = analysis.get("algorithm_results") if isinstance(analysis.get("algorithm_results"), dict) else {}
    relevant_algorithms = {
        "black_screen": ["quality"],
        "no_motion": ["quality", "activity"],
        "no_person": ["person", "pose"],
        "fall_candidate": ["person", "pose", "fall"],
        "prolonged_floor_lying": ["person", "pose", "fall"],
        "fire_candidate": ["quality", "fire"],
        "camera_offline": [],
    }.get(event_type, ["quality", "person", "pose", "activity", "fall", "fire"])

    return {
        "schema_version": "gohome-event-evidence-v1",
        "event_type": event_type,
        "event_category": event_category(event_type),
        "summary": summary,
        "level": level,
        "model": {
            "pipeline_version": analysis.get("pipeline_version") or analysis.get("model_version") or "",
            "detector_backend": analysis.get("detector_backend") or "",
            "model_name": analysis.get("model_name") or "",
            "pose_model_status": analysis.get("pose_model_status") or "",
            "pose_model_name": analysis.get("pose_model_name") or "",
        },
        "algorithms": {
            key: algorithm_results[key]
            for key in relevant_algorithms
            if key in algorithm_results
        },
        "pose_factor_graph": analysis.get("pose_factor_graph") or {},
        "temporal_evidence_bundle": analysis.get("temporal_evidence_bundle") or {},
        "metrics": {
            "brightness": analysis.get("brightness"),
            "contrast": analysis.get("contrast"),
            "motion_score": analysis.get("motion_score"),
            "person_count": analysis.get("person_count"),
            "pet_count": analysis.get("pet_count", len(pets)),
            "pose_count": analysis.get("pose_count"),
            "fall_score": analysis.get("fall_score"),
            "pose_fall_score": analysis.get("pose_fall_score"),
            "meal_score": analysis.get("meal_score"),
            "stillness_score": analysis.get("stillness_score"),
            "daze_score": analysis.get("daze_score"),
            "fire_score": analysis.get("fire_score"),
            "fire_temporal_score": analysis.get("fire_temporal_score"),
        },
        "flags": {
            "black_screen": bool(analysis.get("black_screen")),
            "motion_detected": bool(analysis.get("motion_detected")),
            "fall_candidate": bool(analysis.get("fall_candidate")),
            "pose_fall_candidate": bool(analysis.get("pose_fall_candidate")),
            "meal_candidate": bool(analysis.get("meal_candidate")),
            "stillness_candidate": bool(analysis.get("stillness_candidate")),
            "daze_candidate": bool(analysis.get("daze_candidate")),
            "fire_candidate": bool(analysis.get("fire_candidate")),
            "fire_event_candidate": bool(analysis.get("fire_event_candidate")),
        },
        "objects": {
            "people": [
                {
                    "bbox": person.get("bbox"),
                    "confidence": person.get("confidence"),
                    "source": person.get("source"),
                    "track_id": person.get("track_id"),
                    "posture": person.get("posture"),
                    "posture_confidence": person.get("posture_confidence"),
                    "fall_candidate": bool(person.get("fall_candidate")),
                    "presence_candidate": bool(person.get("presence_candidate")),
                }
                for person in people[:3]
            ],
            "pets": [
                {
                    "type": pet.get("type") or pet.get("label"),
                    "label_zh": pet.get("label_zh"),
                    "bbox": pet.get("bbox"),
                    "confidence": pet.get("confidence"),
                    "scene_zone_label": pet.get("scene_zone_label"),
                    "scene_zone_label_zh": pet.get("scene_zone_label_zh"),
                    "person_evidence_eligible": False,
                    "fall_evidence_eligible": False,
                }
                for pet in pets[:6]
            ],
            "poses": [
                {
                    "confidence": pose.get("confidence"),
                    "bbox": pose.get("bbox"),
                    "track_id": pose.get("track_id"),
                    "posture": pose.get("posture"),
                    "posture_confidence": pose.get("posture_confidence"),
                    "posture_factors": pose.get("posture_factors") or {},
                    "fall_score": pose.get("fall_score"),
                    "action_hints": pose.get("action_hints") or [],
                    "keypoint_count": len(pose.get("keypoints") or []),
                }
                for pose in poses[:2]
            ],
        },
        "rule": rule,
        "thresholds": analysis.get("thresholds") or {},
        "tags": analysis.get("tags") or [],
        "extra": extra or {},
    }
