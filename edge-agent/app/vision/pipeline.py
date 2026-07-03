from __future__ import annotations

from typing import Any, Dict

from .activity import ActivityAnalyzer
from .fall import FallAnalyzer
from .fire import FireAnalyzer
from .person_yolo import PersonDetector
from .quality import QualityAnalyzer


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
    ) -> None:
        self.default_config = {
            "black_brightness_threshold": black_brightness_threshold,
            "black_contrast_threshold": black_contrast_threshold,
            "motion_threshold": motion_threshold,
            "yolo_confidence": yolo_confidence,
            "yolo_imgsz": yolo_imgsz,
        }
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

    def analyze(
        self,
        frame: Any,
        previous_frame: Any | None = None,
        config: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        runtime_config = {**self.default_config, **(config or {})}

        quality = self.quality.analyze(frame, previous_frame, runtime_config)
        person = self.person.analyze(frame, runtime_config)
        people = list(person.get("people") or [])
        fall = self.fall.analyze(people, runtime_config)
        activity = self.activity.analyze(people, quality.get("motion_score"), runtime_config)
        fire = self.fire.analyze(quality["sample"], runtime_config)

        tags = self._dedupe_tags([
            *quality.get("tags", []),
            *person.get("tags", []),
            *fall.get("tags", []),
            *activity.get("tags", []),
            *fire.get("tags", []),
        ])

        algorithm_results = {
            "quality": quality["result"].to_dict(),
            "person": person["result"].to_dict(),
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
            "fire_score_threshold": float(runtime_config.get("fire_score_threshold", 0.035)),
        }

        return {
            "detector_backend": person.get("detector_backend") or "basic",
            "model_status": person.get("model_status") or "basic",
            "model_message": person.get("model_message") or "",
            "model_name": person.get("model_name") or "",
            "model_version": self.version,
            "pipeline_version": self.version,
            "brightness": quality["brightness"],
            "contrast": quality["contrast"],
            "black_screen": quality["black_screen"],
            "motion_score": quality["motion_score"],
            "motion_detected": quality["motion_detected"],
            "thresholds": thresholds,
            "person_count": person.get("person_count"),
            "people": people,
            "fall_candidate": fall["fall_candidate"],
            "fall_score": fall.get("fall_score"),
            "activity": activity["activity"],
            "meal_score": activity["meal_score"],
            "meal_candidate": activity["meal_candidate"],
            "stillness_candidate": activity["stillness_candidate"],
            "fire_score": fire["fire_score"],
            "fire_candidate": fire["fire_candidate"],
            "algorithm_results": algorithm_results,
            "tags": tags,
        }

    def _dedupe_tags(self, tags: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for tag in tags:
            if tag not in seen:
                result.append(tag)
                seen.add(tag)
        return result
