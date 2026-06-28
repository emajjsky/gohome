from __future__ import annotations

from typing import Any, Dict, Optional


class DetectAgent:
    def __init__(
        self,
        black_brightness_threshold: float,
        black_contrast_threshold: float,
        motion_threshold: float,
        detector_backend: str = "basic",
        yolo_model: str = "yolov8n.pt",
        yolo_confidence: float = 0.35,
    ) -> None:
        self.black_brightness_threshold = black_brightness_threshold
        self.black_contrast_threshold = black_contrast_threshold
        self.motion_threshold = motion_threshold
        self.detector_backend = detector_backend
        self.yolo_model_name = yolo_model
        self.yolo_confidence = yolo_confidence
        self._yolo_model: Any = None

    def analyze_frame(self, frame: Any, previous_frame: Optional[Any] = None) -> Dict[str, Any]:
        return self.analyze_frame_with_config(frame, previous_frame=previous_frame)

    def analyze_frame_with_config(
        self,
        frame: Any,
        previous_frame: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        try:
            import numpy as np  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError("NumPy is not installed. Run: python -m pip install -r requirements.txt") from exc

        black_brightness_threshold = float(
            (config or {}).get("black_brightness_threshold", self.black_brightness_threshold)
        )
        black_contrast_threshold = float(
            (config or {}).get("black_contrast_threshold", self.black_contrast_threshold)
        )
        motion_threshold = float((config or {}).get("motion_threshold", self.motion_threshold))
        self.yolo_confidence = float((config or {}).get("yolo_confidence", self.yolo_confidence))

        sample = frame[::8, ::8].astype("float32")
        brightness = float(sample.mean())
        contrast = float(sample.std())
        black_screen = (
            brightness < black_brightness_threshold
            and contrast < black_contrast_threshold
        )

        motion_score = None
        if previous_frame is not None:
            previous_sample = previous_frame[::8, ::8].astype("float32")
            if previous_sample.shape == sample.shape:
                motion_score = float(np.abs(sample - previous_sample).mean() / 255.0)

        tags = []
        if black_screen:
            tags.append("black_screen")
        if motion_score is not None and motion_score < motion_threshold:
            tags.append("low_motion")

        person_count = None
        people = []
        fall_candidate = False
        if self.detector_backend == "yolo":
            people = self._detect_people_with_yolo(frame)
            person_count = len(people)
            if person_count > 0:
                tags.append("person_detected")
            else:
                tags.append("no_person_detected")
            fall_candidate = any(person["fall_candidate"] for person in people)
            if fall_candidate:
                tags.append("fall_candidate")

        return {
            "detector_backend": self.detector_backend,
            "brightness": brightness,
            "contrast": contrast,
            "black_screen": black_screen,
            "motion_score": motion_score,
            "motion_detected": motion_score is None or motion_score >= motion_threshold,
            "thresholds": {
                "black_brightness_threshold": black_brightness_threshold,
                "black_contrast_threshold": black_contrast_threshold,
                "motion_threshold": motion_threshold,
                "yolo_confidence": self.yolo_confidence,
            },
            "person_count": person_count,
            "people": people,
            "fall_candidate": fall_candidate,
            "tags": tags,
        }

    def _detect_people_with_yolo(self, frame: Any) -> list[Dict[str, Any]]:
        if self._yolo_model is None:
            try:
                from ultralytics import YOLO  # type: ignore
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "YOLO backend requested but ultralytics is not installed. "
                    "Run: python -m pip install -r requirements-yolo.txt"
                ) from exc
            self._yolo_model = YOLO(self.yolo_model_name)

        results = self._yolo_model(frame, conf=self.yolo_confidence, verbose=False)
        if not results:
            return []

        boxes = getattr(results[0], "boxes", None)
        if boxes is None or getattr(boxes, "cls", None) is None:
            return []

        people = []
        height, width = frame.shape[:2]
        for index, cls in enumerate(boxes.cls):
            if int(cls) == 0:
                xyxy = boxes.xyxy[index].tolist()
                confidence = float(boxes.conf[index]) if getattr(boxes, "conf", None) is not None else None
                x1, y1, x2, y2 = [float(value) for value in xyxy]
                box_width = max(1.0, x2 - x1)
                box_height = max(1.0, y2 - y1)
                aspect_ratio = box_width / box_height
                area_ratio = (box_width * box_height) / max(1, width * height)
                height_ratio = box_height / max(1, height)
                center_y_ratio = ((y1 + y2) / 2.0) / max(1, height)
                people.append(
                    {
                        "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                        "confidence": None if confidence is None else round(confidence, 4),
                        "aspect_ratio": round(aspect_ratio, 3),
                        "area_ratio": round(area_ratio, 4),
                        "height_ratio": round(height_ratio, 3),
                        "center_y_ratio": round(center_y_ratio, 3),
                        "fall_candidate": (
                            aspect_ratio >= 1.65
                            and area_ratio >= 0.04
                            and area_ratio <= 0.26
                            and height_ratio <= 0.72
                            and center_y_ratio >= 0.45
                        ),
                    }
                )
        return people
