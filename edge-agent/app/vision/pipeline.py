from __future__ import annotations

from copy import deepcopy
from collections import deque
import time
from typing import Any, Dict

from .activity import ActivityAnalyzer
from .fall import FallAnalyzer
from .fire import FireAnalyzer
from .person_yolo import PersonDetector
from .pose_rtmpose import RtmposeAnalyzer
from .quality import QualityAnalyzer
from .scene_context import SceneContextTracker


class VisionPipeline:
    version = "vision-pipeline-v1"

    def __init__(
        self,
        *,
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
        self.default_config = {
            "black_brightness_threshold": black_brightness_threshold,
            "black_contrast_threshold": black_contrast_threshold,
            "motion_threshold": motion_threshold,
            "yolo_confidence": yolo_confidence,
            "yolo_imgsz": yolo_imgsz,
            "pose_detection_enabled": pose_enabled,
            "pose_fall_threshold": pose_fall_threshold,
            "pose_fall_min_confidence": pose_fall_min_confidence,
            "pose_fall_min_visible_keypoints": pose_fall_min_visible_keypoints,
            "pose_fall_min_core_keypoints": pose_fall_min_core_keypoints,
            "pose_cache_seconds": pose_cache_seconds,
            "pose_cache_max_motion": pose_cache_max_motion,
            "activity_window_seconds": activity_window_seconds,
            "activity_max_samples": activity_max_samples,
        }
        self._pose_cache: dict[str, Dict[str, Any]] = {}
        self._activity_history: dict[str, deque[Dict[str, Any]]] = {}
        self.scene = SceneContextTracker()
        self.quality = QualityAnalyzer()
        self.person = PersonDetector(
            detector_backend=detector_backend,
            yolo_model=yolo_model,
            yolo_confidence=yolo_confidence,
            yolo_imgsz=yolo_imgsz,
        )
        self.fall = FallAnalyzer()
        self.activity = ActivityAnalyzer()
        self.fire = FireAnalyzer()
        self.pose = RtmposeAnalyzer(
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

    def analyze(
        self,
        frame: Any,
        previous_frame: Any | None = None,
        config: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        runtime_config = {**self.default_config, **(config or {})}

        quality = self.quality.analyze(frame, previous_frame, runtime_config)
        person = self.person.analyze(frame, runtime_config)
        raw_people = list(person.get("people") or [])
        raw_pose = self.pose.analyze(frame, runtime_config)
        pose = self._pose_with_short_cache(raw_pose, runtime_config, quality)
        scene_candidates = self._scene_objects_without_human_overlap(
            list(person.get("scene_objects") or []),
            raw_people,
            list(pose.get("poses") or []),
        )
        scene = self.scene.update(scene_candidates, runtime_config)
        raw_people, annotated_poses = self.scene.annotate(
            raw_people,
            list(pose.get("poses") or []),
            list(scene.get("scene_zones") or []),
        )
        pose = self._pose_with_scene_context(pose, annotated_poses)
        person_poses = self._poses_for_person_evidence(pose.get("poses") or [])
        people = self._refine_people_with_pose(raw_people, person_poses, frame, runtime_config)
        if (
            runtime_config.get("pose_detection_enabled")
            and pose.get("pose_model_status") in {"ready", "not_visible"}
            and not person_poses
        ):
            people = [person for person in people if not person.get("presence_candidate")]
        self._update_person_result_after_pose_refine(person, people, pose.get("poses") or [])
        self._update_person_scene_context(person, scene)
        fall = self.fall.analyze(self._people_for_fall_alerts(people, raw_people, runtime_config), runtime_config)
        pose_fall_candidate = bool(pose.get("pose_fall_candidate"))
        if pose_fall_candidate and not fall["fall_candidate"]:
            fall = {
                **fall,
                "fall_candidate": True,
                "fall_score": max(float(fall.get("fall_score") or 0.0), float(pose.get("pose_fall_score") or 0.0)),
                "tags": self._dedupe_tags([*fall.get("tags", []), "fall_candidate", "pose_fall_candidate"]),
            }
            fall["result"].status = "candidate"
            fall["result"].score = fall["fall_score"]
            fall["result"].level = "critical"
            fall["result"].summary = "RTMPose 骨架姿态命中疑似跌倒候选。"
            fall["result"].tags = fall["tags"]
            fall["result"].data = {
                **fall["result"].data,
                "fall_candidate": True,
                "candidate_count": max(1, int(fall["result"].data.get("candidate_count") or 0)),
                "method": "pose_fall_candidate",
                "pose_fall_candidate": True,
                "pose_fall_score": pose.get("pose_fall_score"),
            }
        activity_temporal = self._activity_temporal_features(people, pose.get("poses") or [], quality, pose, runtime_config)
        activity = self.activity.analyze(people, pose.get("poses") or [], quality.get("motion_score"), runtime_config, temporal=activity_temporal)
        fire = self.fire.analyze(
            quality["sample"],
            runtime_config,
            previous_sample=quality.get("previous_sample"),
            motion_score=quality.get("motion_score"),
        )

        tags = self._dedupe_tags([
            *quality.get("tags", []),
            *person.get("tags", []),
            *pose.get("tags", []),
            *fall.get("tags", []),
            *activity.get("tags", []),
            *fire.get("tags", []),
            *(["scene_normal_lying_surface"] if scene.get("normal_lying_zones") else []),
        ])

        algorithm_results = {
            "quality": quality["result"].to_dict(),
            "person": person["result"].to_dict(),
            "pose": pose["result"].to_dict(),
            "fall": fall["result"].to_dict(),
            "activity": activity["result"].to_dict(),
            "fire": fire["result"].to_dict(),
        }

        thresholds = {
            "black_brightness_threshold": float(runtime_config["black_brightness_threshold"]),
            "black_contrast_threshold": float(runtime_config["black_contrast_threshold"]),
            "motion_threshold": float(runtime_config["motion_threshold"]),
            "yolo_confidence": float(runtime_config["yolo_confidence"]),
            "yolo_imgsz": int(runtime_config.get("yolo_imgsz", 640)),
            "pose_fall_threshold": float(runtime_config.get("pose_fall_threshold", 0.90)),
            "pose_cache_seconds": float(runtime_config.get("pose_cache_seconds", 1.8)),
            "fire_score_threshold": float(runtime_config.get("fire_score_threshold", 0.035)),
            "fire_event_score_threshold": float(runtime_config.get("fire_event_score_threshold", 0.12)),
            "fire_motion_threshold": float(runtime_config.get("fire_motion_threshold", 0.035)),
            "fire_temporal_threshold": float(runtime_config.get("fire_temporal_threshold", 0.018)),
            "fire_confirm_frames": int(runtime_config.get("fire_confirm_frames", 5)),
        }

        return {
            "detector_backend": person.get("detector_backend") or "basic",
            "model_status": person.get("model_status") or "basic",
            "model_message": person.get("model_message") or "",
            "model_name": person.get("model_name") or "",
            "pose_model_status": pose.get("pose_model_status") or "disabled",
            "pose_model_message": pose.get("pose_model_message") or "",
            "pose_model_name": pose.get("pose_model_name") or "",
            "model_version": self.version,
            "pipeline_version": self.version,
            "image_width": int(frame.shape[1]),
            "image_height": int(frame.shape[0]),
            "brightness": quality["brightness"],
            "contrast": quality["contrast"],
            "black_screen": quality["black_screen"],
            "motion_score": quality["motion_score"],
            "motion_detected": quality["motion_detected"],
            "thresholds": thresholds,
            "person_count": person.get("person_count"),
            "people": people,
            "scene_objects": scene.get("scene_objects") or [],
            "scene_zones": scene.get("scene_zones") or [],
            "normal_lying_zones": scene.get("normal_lying_zones") or [],
            "scene_map_status": scene.get("scene_map_status") or "empty",
            "pose_count": pose.get("pose_count"),
            "poses": pose.get("poses") or [],
            "pose_skeleton_edges": pose.get("pose_skeleton_edges") or [],
            "pose_action_hints": pose.get("pose_action_hints") or [],
            "pose_tracking_state": pose.get("pose_tracking_state") or "disabled",
            "pose_track_age_seconds": pose.get("pose_track_age_seconds"),
            "pose_fall_score": pose.get("pose_fall_score"),
            "raw_pose_fall_score": pose.get("raw_pose_fall_score"),
            "pose_fall_candidate": pose_fall_candidate,
            "pose_fall_rejected_low_quality": pose.get("pose_fall_rejected_low_quality"),
            "fall_candidate": fall["fall_candidate"],
            "fall_score": fall.get("fall_score"),
            "activity": activity["activity"],
            "activity_temporal": activity_temporal,
            "meal_score": activity["meal_score"],
            "meal_candidate": activity["meal_candidate"],
            "stillness_score": activity.get("stillness_score"),
            "stillness_candidate": activity["stillness_candidate"],
            "daze_score": activity.get("daze_score"),
            "daze_candidate": activity.get("daze_candidate"),
            "fire_score": fire["fire_score"],
            "fire_candidate": fire["fire_candidate"],
            "fire_event_candidate": fire.get("fire_event_candidate", False),
            "fire_temporal_candidate": fire.get("fire_temporal_candidate", False),
            "fire_temporal_score": fire.get("fire_temporal_score"),
            "fire_features": fire.get("fire_features") or {},
            "algorithm_results": algorithm_results,
            "tags": tags,
        }

    def _activity_temporal_features(
        self,
        people: list[Dict[str, Any]],
        poses: list[Dict[str, Any]],
        quality: Dict[str, Any],
        pose_result: Dict[str, Any],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        camera_key = str(config.get("camera_id") or "__default__")
        now = time.monotonic()
        window_seconds = max(5.0, float(config.get("activity_window_seconds") or 30.0))
        max_samples = max(8, int(config.get("activity_max_samples") or 90))
        history = self._activity_history.setdefault(camera_key, deque())
        current_hints = self._dedupe_tags([
            hint
            for pose in poses
            for hint in (pose.get("action_hints") or [])
        ])
        postures = [str(pose.get("posture") or "") for pose in poses]
        motion_score = quality.get("motion_score")
        motion = None if motion_score is None else float(motion_score)
        low_motion_threshold = float(config.get("activity_low_motion_threshold", 0.006))
        active_motion_min = float(config.get("activity_active_motion_min", 0.006))
        active_motion_max = float(config.get("activity_active_motion_max", 0.080))
        sample = {
            "t": now,
            "person_present": bool(people) or bool(poses),
            "pose_present": bool(poses),
            "pose_fresh": any((pose.get("tracking_state") or "fresh") == "fresh" for pose in poses),
            "hand_near_face": "hand_near_face" in current_hints,
            "seated_or_upper_body": any(posture in {"seated_or_half_body", "upper_body", "standing_or_sitting"} for posture in postures) or "seated_or_upper_body" in current_hints,
            "lying": any(posture == "lying" for posture in postures),
            "motion_score": motion,
            "low_motion": motion is not None and motion <= low_motion_threshold,
            "active_motion": motion is not None and active_motion_min <= motion <= active_motion_max,
            "pose_tracking_state": pose_result.get("pose_tracking_state") or "none",
            "current_action_hints": current_hints,
        }
        history.append(sample)
        while history and (now - float(history[0].get("t") or now) > window_seconds or len(history) > max_samples):
            history.popleft()

        samples = list(history)
        count = len(samples)
        if not count:
            return {
                "window_seconds": window_seconds,
                "duration_seconds": 0.0,
                "sample_count": 0,
                "current_action_hints": current_hints,
            }

        def ratio(key: str) -> float:
            return sum(1 for item in samples if item.get(key)) / max(1, count)

        motion_values = [float(item["motion_score"]) for item in samples if item.get("motion_score") is not None]
        duration_seconds = max(0.0, float(samples[-1]["t"]) - float(samples[0]["t"]))
        return {
            "window_seconds": window_seconds,
            "duration_seconds": round(duration_seconds, 3),
            "sample_count": count,
            "person_visible_ratio": round(ratio("person_present"), 4),
            "pose_visible_ratio": round(ratio("pose_present"), 4),
            "fresh_pose_ratio": round(ratio("pose_fresh"), 4),
            "hand_near_face_ratio": round(ratio("hand_near_face"), 4),
            "seated_or_upper_body_ratio": round(ratio("seated_or_upper_body"), 4),
            "lying_ratio": round(ratio("lying"), 4),
            "low_motion_ratio": round(ratio("low_motion"), 4),
            "active_motion_ratio": round(ratio("active_motion"), 4),
            "mean_motion_score": round(sum(motion_values) / max(1, len(motion_values)), 5) if motion_values else None,
            "current_action_hints": current_hints,
            "pose_tracking_state": pose_result.get("pose_tracking_state") or "none",
        }

    def _pose_with_short_cache(
        self,
        pose: Dict[str, Any],
        config: Dict[str, Any],
        quality: Dict[str, Any],
    ) -> Dict[str, Any]:
        camera_key = str(config.get("camera_id") or "__default__")
        cache_seconds = max(0.0, float(config.get("pose_cache_seconds") or 0.0))
        cache_only = bool(config.get("pose_reuse_cache_only"))
        poses = list(pose.get("poses") or [])
        now = time.monotonic()

        if poses:
            fresh = deepcopy(pose)
            fresh_poses = [self._mark_pose_tracking_state(item, "fresh", 0.0) for item in poses]
            fresh["poses"] = fresh_poses
            fresh["pose_count"] = len(fresh_poses)
            fresh["pose_tracking_state"] = "fresh"
            fresh["pose_track_age_seconds"] = 0.0
            result = fresh.get("result")
            if result is not None:
                result.data = {
                    **result.data,
                    "poses": fresh_poses,
                    "pose_count": len(fresh_poses),
                    "pose_tracking_state": "fresh",
                    "pose_track_age_seconds": 0.0,
                }
            self._pose_cache[camera_key] = {"poses": deepcopy(fresh_poses), "updated_at": now}
            return fresh

        if cache_seconds <= 0 or (not cache_only and pose.get("pose_model_status") not in {"ready", "not_visible"}):
            self._pose_cache.pop(camera_key, None)
            return {**pose, "pose_tracking_state": "none", "pose_track_age_seconds": None}
        if quality.get("black_screen"):
            self._pose_cache.pop(camera_key, None)
            return {**pose, "pose_tracking_state": "none", "pose_track_age_seconds": None}
        motion_score = quality.get("motion_score")
        max_motion = float(config.get("pose_cache_max_motion") or 0.06)
        if motion_score is not None and float(motion_score) > max_motion:
            self._pose_cache.pop(camera_key, None)
            return {**pose, "pose_tracking_state": "none", "pose_track_age_seconds": None}

        cached = self._pose_cache.get(camera_key)
        if not cached:
            return {**pose, "pose_tracking_state": "none", "pose_track_age_seconds": None}
        age = now - float(cached.get("updated_at") or 0.0)
        if age > cache_seconds:
            self._pose_cache.pop(camera_key, None)
            return {**pose, "pose_tracking_state": "none", "pose_track_age_seconds": None}

        cached_poses = [self._mark_pose_tracking_state(item, "cached", age) for item in deepcopy(cached.get("poses") or [])]
        cached_pose = {**pose}
        cached_pose["poses"] = cached_poses
        cached_pose["pose_count"] = len(cached_poses)
        cached_pose["pose_tracking_state"] = "cached"
        cached_pose["pose_track_age_seconds"] = round(age, 3)
        cached_pose["pose_model_status"] = "cached"
        cached_pose["pose_model_message"] = f"短暂沿用上一组可信骨架，跟踪 {age:.1f} 秒。"
        cached_pose["pose_fall_score"] = 0.0
        cached_pose["pose_fall_candidate"] = False
        cached_pose["pose_action_hints"] = [hint for hint in cached_pose.get("pose_action_hints", []) if hint != "fall_candidate"]
        cached_pose["tags"] = self._dedupe_tags([*pose.get("tags", []), "pose_tracked"])
        result = cached_pose.get("result")
        if result is not None:
            result.status = "tracked"
            result.score = max([float(item.get("confidence") or 0.0) for item in cached_poses], default=None)
            result.summary = f"短暂沿用上一组可信骨架，跟踪 {age:.1f} 秒。"
            result.tags = cached_pose["tags"]
            result.data = {
                **result.data,
                "poses": cached_poses,
                "pose_count": len(cached_poses),
                "pose_fall_score": 0.0,
                "pose_fall_candidate": False,
                "pose_model_status": "cached",
                "pose_model_message": cached_pose["pose_model_message"],
                "pose_tracking_state": "cached",
                "pose_track_age_seconds": round(age, 3),
            }
        return cached_pose

    def _mark_pose_tracking_state(self, pose: Dict[str, Any], state: str, age_seconds: float) -> Dict[str, Any]:
        tracked = {
            **pose,
            "tracking_state": state,
            "track_age_seconds": round(age_seconds, 3),
        }
        if state == "cached":
            tracked["fall_score"] = 0.0
            tracked["action_hints"] = [hint for hint in tracked.get("action_hints", []) if hint != "fall_candidate"]
        return tracked

    def _fresh_people_for_alerts(self, people: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        return [person for person in people if person.get("pose_tracking_state") != "cached"]

    def _poses_for_person_evidence(self, poses: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        return [pose for pose in poses if pose.get("person_evidence_eligible", True)]

    def _scene_objects_without_human_overlap(
        self,
        scene_objects: list[Dict[str, Any]],
        people: list[Dict[str, Any]],
        poses: list[Dict[str, Any]],
    ) -> list[Dict[str, Any]]:
        human_boxes = [
            item.get("bbox")
            for item in [*people, *poses]
            if self._valid_box(item.get("bbox"))
        ]
        filtered = []
        for scene_object in scene_objects:
            scene_box = scene_object.get("bbox")
            if not self._valid_box(scene_box):
                continue
            overlap = max(
                [self._box_intersection_ratio(scene_box, human_box) for human_box in human_boxes],
                default=0.0,
            )
            if overlap < 0.55:
                filtered.append(scene_object)
        return filtered

    def _box_intersection_ratio(self, base: Any, other: Any) -> float:
        if not self._valid_box(base) or not self._valid_box(other):
            return 0.0
        ax1, ay1, ax2, ay2 = [float(value) for value in base]
        bx1, by1, bx2, by2 = [float(value) for value in other]
        intersection = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(0.0, min(ay2, by2) - max(ay1, by1))
        base_area = max(1.0, (ax2 - ax1) * (ay2 - ay1))
        return intersection / base_area

    def _pose_with_scene_context(self, pose: Dict[str, Any], poses: list[Dict[str, Any]]) -> Dict[str, Any]:
        updated = {**pose, "poses": poses, "pose_count": len(poses)}
        result = updated.get("result")
        if result is not None:
            result.data = {**result.data, "poses": poses, "pose_count": len(poses)}
        return updated

    def _update_person_scene_context(self, person: Dict[str, Any], scene: Dict[str, Any]) -> None:
        person["scene_objects"] = scene.get("scene_objects") or []
        person["scene_zones"] = scene.get("scene_zones") or []
        person["normal_lying_zones"] = scene.get("normal_lying_zones") or []
        person["scene_map_status"] = scene.get("scene_map_status") or "empty"
        result = person.get("result")
        if result is not None:
            result.data = {
                **result.data,
                "scene_objects": person["scene_objects"],
                "scene_zones": person["scene_zones"],
                "normal_lying_zones": person["normal_lying_zones"],
                "scene_map_status": person["scene_map_status"],
            }

    def _people_for_fall_alerts(
        self,
        people: list[Dict[str, Any]],
        raw_people: list[Dict[str, Any]],
        config: Dict[str, Any],
    ) -> list[Dict[str, Any]]:
        alert_people = self._fresh_people_for_alerts(people)
        min_confidence = float(config.get("fall_box_min_confidence", 0.30))
        for person in raw_people:
            if person.get("presence_candidate"):
                continue
            confidence = person.get("confidence")
            if confidence is None or float(confidence) < min_confidence:
                continue
            if any(self._box_overlap_ratio(person.get("bbox"), existing.get("bbox")) >= 0.34 for existing in alert_people):
                continue
            alert_people.append({**person, "pose_validated": False, "fall_evidence_source": "raw_yolo_fall_box"})
        return alert_people

    def _dedupe_tags(self, tags: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for tag in tags:
            if tag not in seen:
                result.append(tag)
                seen.add(tag)
        return result

    def _refine_people_with_pose(
        self,
        people: list[Dict[str, Any]],
        poses: list[Dict[str, Any]],
        frame: Any,
        config: Dict[str, Any],
    ) -> list[Dict[str, Any]]:
        if not poses or not config.get("pose_refine_person_enabled", True):
            return people

        refined: list[Dict[str, Any]] = []
        min_overlap = float(config.get("pose_person_min_overlap", 0.30))
        strict_when_pose_visible = bool(config.get("pose_refine_strict_when_pose_visible", True))

        for person in people:
            bbox = person.get("bbox")
            matching_pose = self._matching_pose_for_person(bbox, poses, min_overlap=min_overlap)
            overlaps_pose = matching_pose is not None
            if strict_when_pose_visible and not overlaps_pose:
                continue
            if person.get("presence_candidate") and not overlaps_pose:
                continue
            refined.append({
                **person,
                "pose_validated": bool(overlaps_pose),
                "pose_tracking_state": matching_pose.get("tracking_state") if matching_pose else person.get("pose_tracking_state"),
                "pose_track_age_seconds": matching_pose.get("track_age_seconds") if matching_pose else person.get("pose_track_age_seconds"),
                "normal_lying_zone": matching_pose.get("normal_lying_zone", person.get("normal_lying_zone", False)) if matching_pose else person.get("normal_lying_zone", False),
                "scene_zone_id": matching_pose.get("scene_zone_id") if matching_pose else person.get("scene_zone_id"),
                "scene_zone_label": matching_pose.get("scene_zone_label") if matching_pose else person.get("scene_zone_label"),
                "scene_zone_label_zh": matching_pose.get("scene_zone_label_zh") if matching_pose else person.get("scene_zone_label_zh"),
                "scene_zone_bbox": matching_pose.get("scene_zone_bbox") if matching_pose else person.get("scene_zone_bbox"),
                "scene_zone_overlap": matching_pose.get("scene_zone_overlap") if matching_pose else person.get("scene_zone_overlap"),
            })

        for pose in poses:
            pose_box = pose.get("bbox")
            if not self._valid_box(pose_box):
                continue
            if any(self._box_overlap_ratio(person.get("bbox"), pose_box) >= 0.34 for person in refined):
                continue
            refined.append(self._person_from_pose(pose, frame))

        refined.sort(key=lambda person: (1 if person.get("pose_validated") else 0, float(person.get("confidence") or 0.0)), reverse=True)
        max_count = int(config.get("person_max_count", 3))
        return refined[: max(1, max_count)]

    def _update_person_result_after_pose_refine(
        self,
        person: Dict[str, Any],
        people: list[Dict[str, Any]],
        poses: list[Dict[str, Any]],
    ) -> None:
        raw_people = list(person.get("people") or [])
        raw_count = len(raw_people)
        person_count = len(people)
        presence_candidate_count = len([item for item in people if item.get("presence_candidate")])
        pose_validated_count = len([item for item in people if item.get("pose_validated") or item.get("source") == "pose_person"])
        presence_enhanced = presence_candidate_count > 0
        tags: list[str] = []
        tags.append("person_detected" if person_count > 0 else "no_person_detected")
        if presence_enhanced:
            tags.append("person_presence_candidate")
        if pose_validated_count:
            tags.append("pose_validated_person")

        person["people"] = people
        person["person_count"] = person_count
        person["presence_candidate_count"] = presence_candidate_count
        person["presence_enhanced"] = presence_enhanced
        person["pose_validated_person_count"] = pose_validated_count
        person["raw_person_count"] = raw_count
        person["tags"] = tags

        result = person.get("result")
        if result is None:
            return
        result.status = "visible" if person_count else "not_visible"
        result.score = max([float(item.get("confidence") or 0.0) for item in people], default=None)
        if pose_validated_count:
            result.summary = f"骨架确认 {pose_validated_count} 人，过滤弱候选 {max(0, raw_count - person_count)} 个。"
        elif person_count:
            result.summary = f"检测到 {person_count} 人。"
        else:
            result.summary = "当前帧未检测到可信人形。"
        result.tags = tags
        result.data = {
            **result.data,
            "people": people,
            "person_count": person_count,
            "presence_enhanced": presence_enhanced,
            "presence_candidate_count": presence_candidate_count,
            "pose_validated_person_count": pose_validated_count,
            "raw_person_count": raw_count,
            "pose_count": len(poses),
        }

    def _person_from_pose(self, pose: Dict[str, Any], frame: Any) -> Dict[str, Any]:
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = [float(value) for value in pose.get("bbox") or [0, 0, 0, 0]]
        x1 = max(0.0, min(float(width - 1), x1))
        y1 = max(0.0, min(float(height - 1), y1))
        x2 = max(x1 + 1.0, min(float(width), x2))
        y2 = max(y1 + 1.0, min(float(height), y2))
        box_width = max(1.0, x2 - x1)
        box_height = max(1.0, y2 - y1)
        return {
            "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
            "confidence": round(float(pose.get("confidence") or 0.0), 4),
            "source": "pose_person",
            "label": "骨架确认人形",
            "presence_candidate": False,
            "pose_validated": True,
            "pose_tracking_state": pose.get("tracking_state") or "fresh",
            "pose_track_age_seconds": pose.get("track_age_seconds"),
            "method": "rtmpose_bbox",
            "aspect_ratio": round(box_width / box_height, 3),
            "area_ratio": round((box_width * box_height) / max(1, width * height), 4),
            "height_ratio": round(box_height / max(1, height), 3),
            "center_y_ratio": round(((y1 + y2) / 2.0) / max(1, height), 3),
            "frame_width": width,
            "frame_height": height,
            "fall_candidate": False,
            "normal_lying_zone": bool(pose.get("normal_lying_zone")),
            "scene_zone_id": pose.get("scene_zone_id"),
            "scene_zone_label": pose.get("scene_zone_label"),
            "scene_zone_label_zh": pose.get("scene_zone_label_zh"),
            "scene_zone_bbox": pose.get("scene_zone_bbox"),
            "scene_zone_overlap": pose.get("scene_zone_overlap"),
        }

    def _valid_box(self, bbox: Any) -> bool:
        if not bbox or len(bbox) != 4:
            return False
        x1, y1, x2, y2 = [float(value) for value in bbox]
        return x2 > x1 and y2 > y1

    def _matching_pose_for_person(
        self,
        person_bbox: Any,
        poses: list[Dict[str, Any]],
        *,
        min_overlap: float,
    ) -> Dict[str, Any] | None:
        if not self._valid_box(person_bbox):
            return None
        for pose in poses:
            pose_bbox = pose.get("bbox")
            if not self._valid_box(pose_bbox):
                continue
            overlap = self._box_overlap_ratio(person_bbox, pose_bbox)
            if overlap >= min_overlap and self._boxes_share_center(person_bbox, pose_bbox):
                return pose
        return None

    def _boxes_share_center(self, first: Any, second: Any) -> bool:
        ax1, ay1, ax2, ay2 = [float(value) for value in first]
        bx1, by1, bx2, by2 = [float(value) for value in second]
        first_center = ((ax1 + ax2) / 2.0, (ay1 + ay2) / 2.0)
        second_center = ((bx1 + bx2) / 2.0, (by1 + by2) / 2.0)
        return self._point_in_box(first_center, second) or self._point_in_box(second_center, first)

    def _point_in_box(self, point: tuple[float, float], bbox: Any) -> bool:
        x, y = point
        x1, y1, x2, y2 = [float(value) for value in bbox]
        return x1 <= x <= x2 and y1 <= y <= y2

    def _box_overlap_ratio(self, first: Any, second: Any) -> float:
        if not self._valid_box(first) or not self._valid_box(second):
            return 0.0
        ax1, ay1, ax2, ay2 = [float(value) for value in first]
        bx1, by1, bx2, by2 = [float(value) for value in second]
        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)
        inter_area = max(0.0, inter_x2 - inter_x1) * max(0.0, inter_y2 - inter_y1)
        if inter_area <= 0:
            return 0.0
        first_area = max(1.0, (ax2 - ax1) * (ay2 - ay1))
        second_area = max(1.0, (bx2 - bx1) * (by2 - by1))
        return inter_area / min(first_area, second_area)
