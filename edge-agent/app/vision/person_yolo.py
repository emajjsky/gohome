from __future__ import annotations

from threading import RLock
from typing import Any, Dict

from .base import AlgorithmResult, clamp


class PersonDetector:
    def __init__(
        self,
        detector_backend: str = "basic",
        yolo_model: str = "yolo11n.pt",
        yolo_confidence: float = 0.20,
        yolo_imgsz: int = 960,
    ) -> None:
        self.detector_backend = detector_backend
        self.yolo_model_name = yolo_model
        self.yolo_confidence = yolo_confidence
        self.yolo_imgsz = yolo_imgsz
        self._yolo_model: Any = None
        self._yolo_lock = RLock()
        self._cascade_cache: dict[str, Any | None] = {}

    def analyze(self, frame: Any, config: Dict[str, Any]) -> Dict[str, Any]:
        backend = self.detector_backend
        model_status = "basic"
        model_message = ""
        people: list[Dict[str, Any]] = []
        self.yolo_confidence = float(config.get("yolo_confidence", self.yolo_confidence))
        self.yolo_imgsz = int(config.get("yolo_imgsz", self.yolo_imgsz))

        if config.get("force_demo_vision"):
            people = self._detect_people_demo(frame)
            backend = "demo"
            model_status = "demo_fallback"
            model_message = "演示摄像头使用内置视觉效果，真实摄像头会走正式模型。"
        elif self.detector_backend == "yolo":
            try:
                presence_yolo_confidence = float(config.get("presence_yolo_confidence", 0.18))
                raw_people = self._detect_people_with_yolo(frame, confidence=min(self.yolo_confidence, presence_yolo_confidence))
                people = [person for person in raw_people if float(person.get("confidence") or 0.0) >= self.yolo_confidence]
                if not people and config.get("presence_enhancement_enabled", True):
                    low_confidence_people = [
                        self._mark_presence_candidate(person, source="presence_yolo", method="yolo_low_confidence")
                        for person in raw_people
                        if self._is_plausible_presence_box(person)
                    ]
                    classical_candidates = (
                        self._detect_presence_enhancement(frame)
                        if config.get("presence_classical_enhancement_enabled", False)
                        else []
                    )
                    people = self._merge_people([*low_confidence_people, *classical_candidates], max_count=3)
                    if people:
                        model_status = "ready_presence_enhanced"
                        model_message = (
                            "YOLO 未命中高置信人形，当前仅保留待姿态复核的低置信候选。"
                            if low_confidence_people
                            else "经典存在增强已显式启用，当前结果仅为启发式候选。"
                        )
                    else:
                        model_status = "ready"
                else:
                    model_status = "ready"
            except RuntimeError as exc:
                people = []
                backend = "yolo"
                model_status = "model_error"
                model_message = str(exc)

        person_count = len(people) if people or backend in {"yolo", "demo"} else None
        presence_candidate_count = len([person for person in people if person.get("presence_candidate")])
        presence_enhanced = presence_candidate_count > 0
        tags: list[str] = []
        if person_count is not None:
            tags.append("person_detected" if person_count > 0 else "no_person_detected")
        if presence_enhanced:
            tags.append("person_presence_candidate")

        if person_count is None:
            summary = "当前后端未启用人形检测。"
        elif presence_enhanced and presence_candidate_count == person_count:
            summary = f"检测到人体存在候选 {person_count} 个。"
        elif presence_enhanced:
            summary = f"检测到 {person_count} 人，其中包含人体存在增强候选。"
        else:
            summary = f"检测到 {person_count} 人。"

        result = AlgorithmResult(
            algorithm_id="person",
            label="人形 / 无人",
            status="visible" if person_count else "not_visible" if person_count == 0 else "disabled",
            score=max([float(person.get("confidence") or 0.0) for person in people], default=None),
            level="info",
            summary=summary,
            tags=tags,
            data={
                "people": people,
                "person_count": person_count,
                "presence_enhanced": presence_enhanced,
                "presence_candidate_count": presence_candidate_count,
                "detector_backend": backend,
                "model_status": model_status,
                "model_name": self.yolo_model_name if self.detector_backend == "yolo" else "",
                "model_message": model_message,
            },
        )
        return {
            "detector_backend": backend,
            "model_status": model_status,
            "model_message": model_message,
            "model_name": self.yolo_model_name if self.detector_backend == "yolo" else "",
            "person_count": person_count,
            "presence_enhanced": presence_enhanced,
            "presence_candidate_count": presence_candidate_count,
            "people": people,
            "tags": tags,
            "result": result,
        }

    def _detect_people_demo(self, frame: Any) -> list[Dict[str, Any]]:
        try:
            import cv2  # type: ignore
        except ModuleNotFoundError:
            cv2 = None

        height, width = frame.shape[:2]
        people: list[Dict[str, Any]] = []
        if cv2 is not None:
            try:
                hog = cv2.HOGDescriptor()
                hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
                target_width = min(width, 640)
                resized = cv2.resize(frame, (target_width, max(1, int(height * target_width / max(1, width)))))
                boxes, weights = hog.detectMultiScale(resized, winStride=(8, 8), padding=(8, 8), scale=1.05)
                scale_x = width / max(1, resized.shape[1])
                scale_y = height / max(1, resized.shape[0])
                for index, box in enumerate(boxes[:3]):
                    x, y, w, h = [float(value) for value in box]
                    confidence = float(weights[index]) if index < len(weights) else 0.45
                    people.append(
                        self.person_box(
                            x * scale_x,
                            y * scale_y,
                            (x + w) * scale_x,
                            (y + h) * scale_y,
                            width,
                            height,
                            confidence=max(0.35, min(0.92, confidence)),
                        )
                    )
            except Exception:
                people = []

        if people:
            return people

        sample = frame[::12, ::12]
        if float(sample.mean()) < 35 or float(sample.std()) < 4:
            return []
        x1 = width * 0.42
        y1 = height * 0.12
        x2 = width * 0.78
        y2 = height * 0.86
        return [self.person_box(x1, y1, x2, y2, width, height, confidence=0.62)]

    def person_box(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        width: int,
        height: int,
        confidence: float | None = None,
        source: str = "yolo",
        label: str = "人形",
        presence_candidate: bool = False,
        method: str = "",
    ) -> Dict[str, Any]:
        x1 = max(0.0, min(float(width - 1), x1))
        y1 = max(0.0, min(float(height - 1), y1))
        x2 = max(x1 + 1.0, min(float(width), x2))
        y2 = max(y1 + 1.0, min(float(height), y2))
        box_width = max(1.0, x2 - x1)
        box_height = max(1.0, y2 - y1)
        aspect_ratio = box_width / box_height
        area_ratio = (box_width * box_height) / max(1, width * height)
        height_ratio = box_height / max(1, height)
        center_y_ratio = ((y1 + y2) / 2.0) / max(1, height)
        fall_candidate = (
            not presence_candidate
            and aspect_ratio >= 1.65
            and area_ratio >= 0.04
            and area_ratio <= 0.26
            and height_ratio <= 0.72
            and center_y_ratio >= 0.45
        )
        return {
            "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
            "confidence": None if confidence is None else round(confidence, 4),
            "source": source,
            "label": label,
            "presence_candidate": presence_candidate,
            "method": method,
            "aspect_ratio": round(aspect_ratio, 3),
            "area_ratio": round(area_ratio, 4),
            "height_ratio": round(height_ratio, 3),
            "center_y_ratio": round(center_y_ratio, 3),
            "frame_width": width,
            "frame_height": height,
            "fall_candidate": fall_candidate,
        }

    def _detect_people_with_yolo(self, frame: Any, confidence: float | None = None) -> list[Dict[str, Any]]:
        with self._yolo_lock:
            return self._detect_people_with_yolo_locked(frame, confidence=confidence)

    def _detect_people_with_yolo_locked(self, frame: Any, confidence: float | None = None) -> list[Dict[str, Any]]:
        if self._yolo_model is None:
            try:
                from ultralytics import YOLO  # type: ignore
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "YOLO backend requested but ultralytics is not installed. "
                    "Run: python -m pip install -r requirements-yolo.txt"
                ) from exc
            self._yolo_model = YOLO(self.yolo_model_name)

        results = self._yolo_model.predict(
            frame,
            conf=max(0.05, min(0.9, float(confidence if confidence is not None else self.yolo_confidence))),
            imgsz=self.yolo_imgsz,
            classes=[0],
            device="cpu",
            verbose=False,
        )
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
                people.append(
                    self.person_box(
                        x1,
                        y1,
                        x2,
                        y2,
                        width,
                        height,
                        confidence=confidence,
                        source="yolo",
                        label="人形命中",
                    )
                )
        return self._merge_people(people, max_count=3)

    def _mark_presence_candidate(self, person: Dict[str, Any], *, source: str, method: str) -> Dict[str, Any]:
        raw_confidence = float(person.get("confidence") or 0.0)
        candidate = {**person}
        candidate["source"] = source
        candidate["label"] = "人体存在"
        candidate["presence_candidate"] = True
        candidate["method"] = method
        candidate["model_confidence"] = round(raw_confidence, 4)
        candidate["confidence"] = round(raw_confidence, 4)
        candidate["confidence_kind"] = "model"
        candidate["fall_candidate"] = False
        return candidate

    def _detect_presence_enhancement(self, frame: Any) -> list[Dict[str, Any]]:
        candidates: list[Dict[str, Any]] = []
        candidates.extend(self._detect_presence_by_cascade(frame))
        candidates.extend(self._detect_presence_by_skin_regions(frame))
        candidates = [person for person in candidates if self._is_plausible_presence_box(person)]
        return self._merge_people(candidates, max_count=3)

    def _detect_presence_by_cascade(self, frame: Any) -> list[Dict[str, Any]]:
        try:
            import cv2  # type: ignore
        except ModuleNotFoundError:
            return []

        height, width = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        candidates: list[Dict[str, Any]] = []

        face_cascade = self._load_cascade(cv2, "haarcascade_frontalface_default.xml")
        profile_cascade = self._load_cascade(cv2, "haarcascade_profileface.xml")
        upperbody_cascade = self._load_cascade(cv2, "haarcascade_upperbody.xml")

        min_face = max(24, int(min(width, height) * 0.045))
        for cascade, source, method in [
            (face_cascade, "presence_face", "haar_frontal_face"),
            (profile_cascade, "presence_profile", "haar_profile_face"),
        ]:
            if cascade is None:
                continue
            faces = cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=4, minSize=(min_face, min_face))
            if source == "presence_profile":
                flipped = cv2.flip(gray, 1)
                flipped_faces = cascade.detectMultiScale(flipped, scaleFactor=1.08, minNeighbors=4, minSize=(min_face, min_face))
                for x, y, w, h in flipped_faces:
                    faces = list(faces) + [(width - x - w, y, w, h)]
            for x, y, w, h in faces[:4]:
                candidates.append(self._presence_box_from_head(x, y, w, h, width, height, source=source, method=method))

        if upperbody_cascade is not None:
            min_upper = (max(44, int(width * 0.08)), max(52, int(height * 0.12)))
            bodies = upperbody_cascade.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=3, minSize=min_upper)
            for x, y, w, h in bodies[:3]:
                confidence = self._presence_confidence(0.53, (w * h) / max(1, width * height))
                candidates.append(
                    self._mark_heuristic_candidate(self.person_box(
                        x - w * 0.12,
                        y - h * 0.08,
                        x + w * 1.12,
                        y + h * 1.08,
                        width,
                        height,
                        confidence=confidence,
                        source="presence_upperbody",
                        label="人体存在",
                        presence_candidate=True,
                        method="haar_upperbody",
                    ))
                )
        return candidates

    def _detect_presence_by_skin_regions(self, frame: Any) -> list[Dict[str, Any]]:
        try:
            import cv2  # type: ignore
            import numpy as np  # type: ignore
        except ModuleNotFoundError:
            return []

        height, width = frame.shape[:2]
        if height < 80 or width < 80:
            return []

        scale = min(1.0, 640 / max(width, height))
        if scale < 1.0:
            work = cv2.resize(frame, (max(1, int(width * scale)), max(1, int(height * scale))))
        else:
            work = frame

        work_h, work_w = work.shape[:2]
        ycrcb = cv2.cvtColor(work, cv2.COLOR_BGR2YCrCb)
        hsv = cv2.cvtColor(work, cv2.COLOR_BGR2HSV)
        y_channel, cr_channel, cb_channel = cv2.split(ycrcb)
        h_channel, s_channel, v_channel = cv2.split(hsv)

        skin_ycrcb = (
            (y_channel > 35)
            & (cr_channel >= 132)
            & (cr_channel <= 182)
            & (cb_channel >= 72)
            & (cb_channel <= 138)
        )
        skin_hsv = (
            (v_channel > 45)
            & (s_channel > 18)
            & (((h_channel <= 26) & (s_channel <= 190)) | (h_channel >= 168))
        )
        mask = np.where(skin_ycrcb & skin_hsv, 255, 0).astype("uint8")

        # Ignore the very top/bottom strips where walls, lamps, floors and timestamp overlays often appear.
        mask[: int(work_h * 0.05), :] = 0
        mask[int(work_h * 0.92) :, :] = 0

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        candidates: list[Dict[str, Any]] = []
        min_area = max(24.0, work_w * work_h * 0.0007)
        max_area = work_w * work_h * 0.22
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:8]:
            area = float(cv2.contourArea(contour))
            if area < min_area or area > max_area:
                continue
            x, y, w, h = [float(value) for value in cv2.boundingRect(contour)]
            if h < work_h * 0.025 or w < work_w * 0.018:
                continue
            aspect = w / max(1.0, h)
            if aspect > 4.2 or aspect < 0.15:
                continue
            seed_center_y = (y + h / 2) / max(1.0, work_h)
            if seed_center_y > 0.82:
                continue

            x /= scale
            y /= scale
            w /= scale
            h /= scale
            seed_area_ratio = (w * h) / max(1, width * height)
            if seed_area_ratio >= 0.035 or h >= height * 0.16:
                candidates.append(
                    self._presence_box_from_region(x, y, w, h, width, height, source="presence_skin", method="skin_upperbody_region")
                )
            else:
                candidates.append(self._presence_box_from_head(x, y, w, h, width, height, source="presence_skin", method="skin_region"))

        return candidates

    def _presence_box_from_head(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        width: int,
        height: int,
        *,
        source: str,
        method: str,
    ) -> Dict[str, Any]:
        center_x = x + w / 2.0
        body_width = max(w * 3.15, width * 0.14)
        body_height = max(h * 5.2, height * 0.28)
        confidence = self._presence_confidence(0.48, (w * h) / max(1, width * height))
        return self._mark_heuristic_candidate(self.person_box(
            center_x - body_width / 2.0,
            y - h * 0.75,
            center_x + body_width / 2.0,
            y + body_height,
            width,
            height,
            confidence=confidence,
            source=source,
            label="人体存在",
            presence_candidate=True,
            method=method,
        ))

    def _presence_box_from_region(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        width: int,
        height: int,
        *,
        source: str,
        method: str,
    ) -> Dict[str, Any]:
        confidence = self._presence_confidence(0.50, (w * h) / max(1, width * height))
        return self._mark_heuristic_candidate(self.person_box(
            x - w * 0.10,
            y - h * 0.12,
            x + w * 1.10,
            y + h * 1.08,
            width,
            height,
            confidence=confidence,
            source=source,
            label="人体存在",
            presence_candidate=True,
            method=method,
        ))

    def _mark_heuristic_candidate(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        score = float(candidate.get("confidence") or 0.0)
        candidate["candidate_score"] = round(score, 4)
        candidate["confidence"] = None
        candidate["confidence_kind"] = "heuristic"
        return candidate

    def _presence_confidence(self, base: float, seed_area_ratio: float) -> float:
        return round(clamp(base + seed_area_ratio * 8.0, 0.42, 0.72), 4)

    def _load_cascade(self, cv2: Any, filename: str) -> Any | None:
        if filename not in self._cascade_cache:
            path = f"{cv2.data.haarcascades}{filename}"
            cascade = cv2.CascadeClassifier(path)
            self._cascade_cache[filename] = None if cascade.empty() else cascade
        return self._cascade_cache[filename]

    def _is_plausible_presence_box(self, person: Dict[str, Any]) -> bool:
        area_ratio = float(person.get("area_ratio") or 0.0)
        height_ratio = float(person.get("height_ratio") or 0.0)
        aspect_ratio = float(person.get("aspect_ratio") or 0.0)
        center_y_ratio = float(person.get("center_y_ratio") or 0.0)
        return (
            0.018 <= area_ratio <= 0.72
            and 0.16 <= height_ratio <= 0.96
            and 0.18 <= aspect_ratio <= 2.4
            and 0.10 <= center_y_ratio <= 0.86
        )

    def _merge_people(self, people: list[Dict[str, Any]], max_count: int = 3) -> list[Dict[str, Any]]:
        merged: list[Dict[str, Any]] = []
        ordered = sorted(
            people,
            key=lambda person: float(person.get("confidence") or person.get("candidate_score") or 0.0),
            reverse=True,
        )
        for person in ordered:
            if any(self._box_iou(person.get("bbox"), existing.get("bbox")) >= 0.34 for existing in merged):
                continue
            merged.append(person)
            if len(merged) >= max_count:
                break
        return merged

    def _box_iou(self, first: Any, second: Any) -> float:
        if not first or not second or len(first) != 4 or len(second) != 4:
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
        first_area = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
        second_area = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
        return inter_area / max(1.0, first_area + second_area - inter_area)
