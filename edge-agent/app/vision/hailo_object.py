from __future__ import annotations

from collections import deque
from copy import deepcopy
from pathlib import Path
from threading import RLock
import logging
import time
from typing import Any, Callable, Dict

from .hailo_pose import HailoInferRuntime, HailoVDevicePool, preprocess_hailo_letterbox
from .pet_temporal import PetTemporalStabilizer


logger = logging.getLogger(__name__)


class HailoObjectNmsDecoder:
    """Decode Hailo NMS-by-class output into image-space COCO detections."""

    def __init__(self, *, input_size: int = 640, class_count: int = 80) -> None:
        self.input_size = int(input_size)
        self.class_count = int(class_count)

    def decode(
        self,
        outputs: Dict[str, Any],
        *,
        original_width: int,
        original_height: int,
        class_thresholds: Dict[int, float],
        max_detections: int = 24,
    ) -> list[Dict[str, Any]]:
        import numpy as np

        if not outputs:
            return []
        raw_output = next(iter(outputs.values()))
        if isinstance(raw_output, (list, tuple)) and len(raw_output) == self.class_count:
            class_rows = {
                class_id: self._rows(np.asarray(raw_output[class_id], dtype=np.float32))
                for class_id in class_thresholds
                if 0 <= class_id < len(raw_output)
            }
            return self._decode_class_rows(
                class_rows,
                original_width=original_width,
                original_height=original_height,
                class_thresholds=class_thresholds,
                max_detections=max_detections,
            )

        tensor = np.asarray(raw_output, dtype=np.float32)
        while tensor.ndim > 3 and tensor.shape[0] == 1:
            tensor = tensor[0]
        if tensor.shape == (self.class_count, 100, 5):
            tensor = np.transpose(tensor, (0, 2, 1))
        if tensor.ndim != 3 or tensor.shape[0] != self.class_count or tensor.shape[1] != 5:
            raise ValueError(f"Unsupported Hailo object NMS output shape: {tensor.shape}")

        class_rows = {
            class_id: np.transpose(tensor[class_id], (1, 0))
            for class_id in class_thresholds
            if 0 <= class_id < tensor.shape[0]
        }
        return self._decode_class_rows(
            class_rows,
            original_width=original_width,
            original_height=original_height,
            class_thresholds=class_thresholds,
            max_detections=max_detections,
        )

    def _decode_class_rows(
        self,
        class_rows: Dict[int, Any],
        *,
        original_width: int,
        original_height: int,
        class_thresholds: Dict[int, float],
        max_detections: int,
    ) -> list[Dict[str, Any]]:
        scale = min(self.input_size / original_width, self.input_size / original_height)
        resized_width = int(original_width * scale)
        resized_height = int(original_height * scale)
        offset_x = (self.input_size - resized_width) // 2
        offset_y = (self.input_size - resized_height) // 2
        detections: list[Dict[str, Any]] = []
        for class_id, threshold in class_thresholds.items():
            for row in class_rows.get(class_id, []):
                score = float(row[4])
                if score < float(threshold):
                    continue
                y1, x1, y2, x2 = [float(row[index]) for index in range(4)]
                if max(abs(x1), abs(y1), abs(x2), abs(y2)) <= 2.0:
                    x1, x2 = x1 * self.input_size, x2 * self.input_size
                    y1, y2 = y1 * self.input_size, y2 * self.input_size
                x1, x2 = (x1 - offset_x) / scale, (x2 - offset_x) / scale
                y1, y2 = (y1 - offset_y) / scale, (y2 - offset_y) / scale
                bbox = [
                    max(0.0, min(float(original_width - 1), x1)),
                    max(0.0, min(float(original_height - 1), y1)),
                    max(0.0, min(float(original_width - 1), x2)),
                    max(0.0, min(float(original_height - 1), y2)),
                ]
                if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                    continue
                detections.append({"class_id": int(class_id), "confidence": score, "bbox": bbox})
        detections.sort(key=lambda item: float(item["confidence"]), reverse=True)
        return detections[:max(1, int(max_detections))]

    @staticmethod
    def _rows(value: Any) -> Any:
        import numpy as np

        array = np.asarray(value, dtype=np.float32)
        if array.size == 0:
            return np.empty((0, 5), dtype=np.float32)
        if array.ndim == 1:
            if array.size % 5:
                raise ValueError(f"Invalid Hailo NMS class output shape: {array.shape}")
            return array.reshape(-1, 5)
        if array.ndim != 2:
            raise ValueError(f"Invalid Hailo NMS class output shape: {array.shape}")
        if array.shape[1] == 5:
            return array
        if array.shape[0] == 5:
            return array.T
        raise ValueError(f"Invalid Hailo NMS class output shape: {array.shape}")


class HailoObjectBackend:
    version = "hailo-yolov8s-object-v1"

    def __init__(
        self,
        *,
        mode: str = "auto",
        model_path: str = "/usr/share/hailo-models/yolov8s_h8.hef",
        confidence: float = 0.30,
        retry_seconds: float = 30.0,
        runtime_factory: Callable[[Path], Any] | None = None,
    ) -> None:
        self.mode = str(mode or "auto").strip().lower()
        self.model_path = Path(model_path)
        self.confidence = float(confidence)
        self.retry_seconds = max(1.0, float(retry_seconds))
        self.runtime_factory = runtime_factory or HailoInferRuntime
        self.decoder = HailoObjectNmsDecoder()
        self._runtime: Any | None = None
        self._lock = RLock()
        self._retry_at = 0.0
        self._cache: dict[str, Dict[str, Any]] = {}
        self._status = "disabled" if self.mode in {"off", "cpu", "disabled"} else "idle"
        self._last_error = ""
        self._last_latency_ms: float | None = None
        self._latency_history: deque[float] = deque(maxlen=120)
        self._successful_inferences = 0
        self._failed_inferences = 0
        self.pet_temporal = PetTemporalStabilizer()

    @property
    def enabled(self) -> bool:
        return self.mode not in {"off", "cpu", "disabled"}

    def analyze(self, frame: Any, config: Dict[str, Any]) -> Dict[str, Any] | None:
        if not self.enabled or config.get("force_demo_vision"):
            return None
        now = time.monotonic()
        cache_key = str(config.get("camera_id") or "__default__")
        interval = max(0.5, float(config.get("hailo_object_interval_seconds") or 1.0))
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached is not None and now - float(cached["stored_at"]) < interval:
                return self._cached_result(cached, now)
            if now < self._retry_at:
                return self._cached_result(cached, now) if cached is not None else None
            started_at = time.perf_counter()
            try:
                runtime = self._ensure_runtime()
                model_input = preprocess_hailo_letterbox(frame, runtime.input_shape)
                outputs = runtime.infer(model_input)
                height, width = frame.shape[:2]
                raw_detections = self.decoder.decode(
                    outputs,
                    original_width=width,
                    original_height=height,
                    class_thresholds=self._class_thresholds(config),
                )
                detections, pet_temporal = self.pet_temporal.update(cache_key, raw_detections, now=now)
                latency_ms = (time.perf_counter() - started_at) * 1000.0
                result = {
                    "detections": detections,
                    "raw_pet_candidate_count": sum(
                        1 for detection in raw_detections if int(detection.get("class_id") or -1) in {15, 16}
                    ),
                    "pet_temporal": pet_temporal,
                    "backend": "hailo",
                    "model_name": self.model_path.name,
                    "latency_ms": round(latency_ms, 2),
                    "cached": False,
                    "age_seconds": 0.0,
                }
                self._cache[cache_key] = {"stored_at": now, "result": deepcopy(result)}
                self._last_latency_ms = result["latency_ms"]
                self._latency_history.append(latency_ms)
                self._successful_inferences += 1
                if self._status != "ready":
                    logger.info(
                        "Hailo object backend ready: model=%s latency_ms=%.2f detections=%d",
                        self.model_path.name,
                        latency_ms,
                        len(detections),
                    )
                self._status = "ready"
                self._last_error = ""
                return result
            except Exception as exc:
                self._failed_inferences += 1
                self._status = "degraded"
                self._last_error = str(exc)
                self._retry_at = now + self.retry_seconds
                logger.warning("Hailo object backend degraded; CPU context fallback active: %s", exc)
                self._close_runtime()
                return self._cached_result(cached, now) if cached is not None else None

    def status(self) -> Dict[str, Any]:
        with self._lock:
            values = sorted(self._latency_history)
            return {
                "schema_version": self.version,
                "mode": self.mode,
                "status": self._status,
                "model_path": str(self.model_path),
                "model_present": self.model_path.is_file(),
                "last_error": self._last_error,
                "last_latency_ms": self._last_latency_ms,
                "latency_summary_ms": {
                    "samples": len(values),
                    "median": round(values[len(values) // 2], 2) if values else None,
                    "p95": round(values[min(len(values) - 1, int(len(values) * 0.95))], 2) if values else None,
                },
                "successful_inferences": self._successful_inferences,
                "failed_inferences": self._failed_inferences,
                "cache_count": len(self._cache),
                "retry_in_seconds": round(max(0.0, self._retry_at - time.monotonic()), 2),
                "shared_vdevice": HailoVDevicePool.status(),
                "pet_temporal": self.pet_temporal.status(),
            }

    def close(self) -> None:
        with self._lock:
            self._close_runtime()
            self._cache.clear()
            self.pet_temporal.reset()

    def _ensure_runtime(self) -> Any:
        if self._runtime is not None:
            return self._runtime
        if not self.model_path.is_file():
            raise RuntimeError(f"Hailo object model not found: {self.model_path}")
        self._runtime = self.runtime_factory(self.model_path)
        return self._runtime

    def _close_runtime(self) -> None:
        runtime = self._runtime
        self._runtime = None
        if runtime is not None:
            try:
                runtime.close()
            except Exception:
                pass

    def _class_thresholds(self, config: Dict[str, Any]) -> Dict[int, float]:
        thresholds = {0: max(0.20, float(config.get("yolo_confidence") or self.confidence))}
        if config.get("pet_detection_enabled", True):
            pet_threshold = min(
                float(config.get("pet_yolo_confidence") or 0.40),
                float(config.get("pet_candidate_confidence") or 0.28),
            )
            thresholds.update({15: pet_threshold, 16: pet_threshold})
        if config.get("scene_context_enabled", True):
            scene_threshold = float(config.get("scene_object_confidence") or 0.30)
            thresholds.update({class_id: scene_threshold for class_id in (56, 57, 59, 60, 62)})
        return thresholds

    @staticmethod
    def _cached_result(cached: Dict[str, Any] | None, now: float) -> Dict[str, Any] | None:
        if cached is None:
            return None
        result = deepcopy(cached["result"])
        result["cached"] = True
        result["age_seconds"] = round(max(0.0, now - float(cached["stored_at"])), 3)
        return result
