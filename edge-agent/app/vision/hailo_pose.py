from __future__ import annotations

from collections import deque
from pathlib import Path
from threading import RLock
import logging
import time
from typing import Any, Callable, Dict


logger = logging.getLogger(__name__)


class HailoPoseDecoder:
    def __init__(self, *, input_size: int = 640, nms_iou: float = 0.70) -> None:
        self.input_size = int(input_size)
        self.nms_iou = float(nms_iou)

    def decode(
        self,
        outputs: Dict[str, Any],
        *,
        original_width: int,
        original_height: int,
        confidence: float,
        max_poses: int,
    ) -> Dict[str, Any]:
        import numpy as np

        tensors = {self._shape(value): np.asarray(value, dtype=np.float32) for value in outputs.values()}
        decoded_boxes = []
        decoded_keypoints = []
        decoded_scores = []
        for grid_size, stride in ((20, 32), (40, 16), (80, 8)):
            box_tensor = self._required(tensors, (1, grid_size, grid_size, 64))
            score_tensor = self._required(tensors, (1, grid_size, grid_size, 1))
            keypoint_tensor = self._required(tensors, (1, grid_size, grid_size, 51))
            scale_scores = score_tensor.reshape(-1)
            scale_indices = np.flatnonzero(scale_scores >= float(confidence))
            if scale_indices.size == 0:
                continue
            if scale_indices.size > 1000:
                ranked = np.argsort(scale_scores[scale_indices])[::-1][:1000]
                scale_indices = scale_indices[ranked]
            boxes, keypoints = self._decode_scale(
                box_tensor,
                keypoint_tensor,
                stride,
                scale_indices,
            )
            decoded_boxes.append(boxes)
            decoded_keypoints.append(keypoints)
            decoded_scores.append(scale_scores[scale_indices])

        if not decoded_scores:
            return self._empty(np)

        boxes = np.concatenate(decoded_boxes, axis=0)
        keypoints = np.concatenate(decoded_keypoints, axis=0)
        scores = np.concatenate(decoded_scores, axis=0)
        candidate_indices = np.argsort(scores)[::-1][:1000]
        boxes = boxes[candidate_indices]
        keypoints = keypoints[candidate_indices]
        scores = scores[candidate_indices]
        keep = self._nms(boxes, scores, self.nms_iou, max_poses=max_poses)
        boxes = boxes[keep]
        keypoints = keypoints[keep]
        scores = scores[keep]

        scale = min(self.input_size / original_width, self.input_size / original_height)
        resized_width = int(original_width * scale)
        resized_height = int(original_height * scale)
        offset_x = (self.input_size - resized_width) // 2
        offset_y = (self.input_size - resized_height) // 2
        boxes[:, (0, 2)] = (boxes[:, (0, 2)] - offset_x) / scale
        boxes[:, (1, 3)] = (boxes[:, (1, 3)] - offset_y) / scale
        boxes[:, (0, 2)] = np.clip(boxes[:, (0, 2)], 0, original_width - 1)
        boxes[:, (1, 3)] = np.clip(boxes[:, (1, 3)], 0, original_height - 1)
        keypoints[..., 0] = (keypoints[..., 0] - offset_x) / scale
        keypoints[..., 1] = (keypoints[..., 1] - offset_y) / scale
        keypoints[..., 0] = np.clip(keypoints[..., 0], 0, original_width - 1)
        keypoints[..., 1] = np.clip(keypoints[..., 1], 0, original_height - 1)

        return {
            "boxes": boxes.astype(np.float32, copy=False),
            "keypoints": keypoints[..., :2].astype(np.float32, copy=False),
            "keypoint_scores": self._sigmoid(keypoints[..., 2]).astype(np.float32, copy=False),
            "scores": scores.astype(np.float32, copy=False),
        }

    @staticmethod
    def _shape(value: Any) -> tuple[int, ...]:
        shape = tuple(int(item) for item in getattr(value, "shape", ()))
        return shape if len(shape) == 4 else (1, *shape)

    @staticmethod
    def _required(tensors: Dict[tuple[int, ...], Any], shape: tuple[int, ...]) -> Any:
        tensor = tensors.get(shape)
        if tensor is None:
            raise ValueError(f"Hailo pose output is missing tensor {shape}")
        return tensor.reshape(shape)

    def _decode_scale(
        self,
        boxes: Any,
        keypoints: Any,
        stride: int,
        indices: Any,
    ) -> tuple[Any, Any]:
        import numpy as np

        grid_size = int(boxes.shape[1])
        selected_indices = np.asarray(indices, dtype=np.int64).reshape(-1)
        grid_y = selected_indices // grid_size
        grid_x = selected_indices % grid_size
        centers = np.stack((grid_x + 0.5, grid_y + 0.5), axis=-1).astype(np.float32) * stride

        distribution = boxes.reshape(-1, 4, 16)[selected_indices].copy()
        distribution -= distribution.max(axis=-1, keepdims=True)
        distribution = np.exp(distribution)
        distribution /= distribution.sum(axis=-1, keepdims=True)
        distances = (distribution * np.arange(16, dtype=np.float32)).sum(axis=-1) * stride
        decoded_boxes = np.concatenate((centers - distances[:, :2], centers + distances[:, 2:]), axis=1)

        decoded_keypoints = keypoints.reshape(-1, 17, 3)[selected_indices].copy()
        decoded_keypoints[..., :2] = (
            stride * (decoded_keypoints[..., :2] * 2.0 - 0.5)
            + centers[:, None, :]
        )
        return decoded_boxes, decoded_keypoints

    @staticmethod
    def _sigmoid(values: Any) -> Any:
        import numpy as np

        clipped = np.clip(values, -60.0, 60.0)
        return 1.0 / (1.0 + np.exp(-clipped))

    @staticmethod
    def _nms(boxes: Any, scores: Any, threshold: float, *, max_poses: int) -> list[int]:
        import numpy as np

        x1, y1, x2, y2 = boxes.T
        areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
        order = np.argsort(scores)[::-1]
        keep: list[int] = []
        while order.size and len(keep) < max(1, int(max_poses)):
            current = int(order[0])
            keep.append(current)
            if order.size == 1:
                break
            rest = order[1:]
            intersection_width = np.maximum(0.0, np.minimum(x2[current], x2[rest]) - np.maximum(x1[current], x1[rest]))
            intersection_height = np.maximum(0.0, np.minimum(y2[current], y2[rest]) - np.maximum(y1[current], y1[rest]))
            intersection = intersection_width * intersection_height
            union = areas[current] + areas[rest] - intersection
            iou = np.divide(intersection, union, out=np.zeros_like(intersection), where=union > 0)
            order = rest[iou < threshold]
        return keep

    @staticmethod
    def _empty(np: Any) -> Dict[str, Any]:
        return {
            "boxes": np.empty((0, 4), dtype=np.float32),
            "keypoints": np.empty((0, 17, 2), dtype=np.float32),
            "keypoint_scores": np.empty((0, 17), dtype=np.float32),
            "scores": np.empty((0,), dtype=np.float32),
        }


class HailoInferRuntime:
    def __init__(self, model_path: Path) -> None:
        import numpy as np
        from hailo_platform import FormatType, HailoSchedulingAlgorithm, HEF, VDevice

        params = VDevice.create_params()
        params.scheduling_algorithm = HailoSchedulingAlgorithm.ROUND_ROBIN
        params.group_id = "GOHOME_SHARED"
        self._device = VDevice(params)
        self._hef = HEF(str(model_path))
        input_info = self._hef.get_input_vstream_infos()[0]
        self.input_name = input_info.name
        self.input_shape = tuple(int(item) for item in input_info.shape)
        self._infer_model = self._device.create_infer_model(str(model_path))
        self._infer_model.set_batch_size(1)
        self._infer_model.input().set_format_type(FormatType.UINT8)
        self._output_dtypes: Dict[str, Any] = {}
        for output_info in self._hef.get_output_vstream_infos():
            self._infer_model.output(output_info.name).set_format_type(FormatType.FLOAT32)
            self._output_dtypes[output_info.name] = np.float32
        self._config_context = self._infer_model.configure()
        self._configured_model = self._config_context.__enter__()
        self._output_buffers = {
            name: np.empty(self._infer_model.output(name).shape, dtype=dtype)
            for name, dtype in self._output_dtypes.items()
        }
        self._bindings = self._configured_model.create_bindings(
            output_buffers=self._output_buffers,
        )

    def infer(self, image: Any) -> Dict[str, Any]:
        import numpy as np

        if tuple(int(item) for item in image.shape) != self.input_shape:
            raise ValueError(
                f"Hailo pose input shape mismatch: expected {self.input_shape}, got {image.shape}"
            )
        self._bindings.input().set_buffer(np.ascontiguousarray(image))
        self._configured_model.wait_for_async_ready(timeout_ms=3000)
        job = self._configured_model.run_async([self._bindings])
        job.wait(3000)
        return {
            name: np.expand_dims(self._bindings.output(name).get_buffer(), axis=0)
            for name in self._output_buffers
        }

    def close(self) -> None:
        context = getattr(self, "_config_context", None)
        if context is not None:
            context.__exit__(None, None, None)
            self._config_context = None
        device = getattr(self, "_device", None)
        if device is not None:
            device.release()
            self._device = None


class HailoPoseBackend:
    version = "hailo-yolov8s-pose-v1"

    def __init__(
        self,
        *,
        mode: str = "auto",
        model_path: str = "/usr/share/hailo-models/yolov8s_pose_h8.hef",
        confidence: float = 0.25,
        nms_iou: float = 0.70,
        max_poses: int = 3,
        retry_seconds: float = 30.0,
        runtime_factory: Callable[[Path], Any] | None = None,
    ) -> None:
        self.mode = str(mode or "auto").strip().lower()
        self.model_path = Path(model_path)
        self.confidence = float(confidence)
        self.max_poses = max(1, int(max_poses))
        self.retry_seconds = max(1.0, float(retry_seconds))
        self.decoder = HailoPoseDecoder(nms_iou=nms_iou)
        self.runtime_factory = runtime_factory or HailoInferRuntime
        self._runtime: Any | None = None
        self._lock = RLock()
        self._retry_at = 0.0
        self._status = "disabled" if self.mode in {"off", "cpu", "disabled"} else "idle"
        self._last_error = ""
        self._last_latency_ms: float | None = None
        self._last_stage_latency_ms: Dict[str, float] = {}
        self._latency_history: deque[float] = deque(maxlen=240)
        self._successful_inferences = 0
        self._failed_inferences = 0

    @property
    def enabled(self) -> bool:
        return self.mode not in {"off", "cpu", "disabled"}

    def analyze(self, frame: Any, config: Dict[str, Any]) -> Dict[str, Any] | None:
        if not self.enabled or config.get("force_demo_vision"):
            return None
        now = time.monotonic()
        with self._lock:
            if now < self._retry_at:
                return None
            started_at = time.perf_counter()
            try:
                runtime = self._ensure_runtime()
                preprocess_started_at = time.perf_counter()
                model_input = self._preprocess(frame, runtime.input_shape)
                preprocess_ms = (time.perf_counter() - preprocess_started_at) * 1000.0
                inference_started_at = time.perf_counter()
                outputs = runtime.infer(model_input)
                inference_ms = (time.perf_counter() - inference_started_at) * 1000.0
                height, width = frame.shape[:2]
                decode_started_at = time.perf_counter()
                result = self.decoder.decode(
                    outputs,
                    original_width=width,
                    original_height=height,
                    confidence=float(config.get("hailo_pose_confidence", self.confidence)),
                    max_poses=int(config.get("pose_max_poses", self.max_poses)),
                )
                decode_ms = (time.perf_counter() - decode_started_at) * 1000.0
                total_ms = (time.perf_counter() - started_at) * 1000.0
                self._last_latency_ms = round(total_ms, 2)
                self._last_stage_latency_ms = {
                    "preprocess": round(preprocess_ms, 2),
                    "device_inference": round(inference_ms, 2),
                    "decode_nms": round(decode_ms, 2),
                    "total": self._last_latency_ms,
                }
                self._latency_history.append(total_ms)
                self._successful_inferences += 1
                if self._status != "ready":
                    logger.info(
                        "Hailo pose backend ready: model=%s latency_ms=%.2f",
                        self.model_path.name,
                        self._last_latency_ms,
                    )
                self._status = "ready"
                self._last_error = ""
                return {
                    **result,
                    "backend": "hailo",
                    "model_name": self.model_path.name,
                    "model_path": str(self.model_path),
                    "latency_ms": self._last_latency_ms,
                    "stage_latency_ms": dict(self._last_stage_latency_ms),
                }
            except Exception as exc:
                self._failed_inferences += 1
                self._status = "degraded"
                self._last_error = str(exc)
                self._retry_at = now + self.retry_seconds
                logger.warning(
                    "Hailo pose backend degraded; CPU fallback active for %.1fs: %s",
                    self.retry_seconds,
                    exc,
                )
                self._close_runtime()
                return None

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "schema_version": self.version,
                "mode": self.mode,
                "status": self._status,
                "model_path": str(self.model_path),
                "model_present": self.model_path.is_file(),
                "last_error": self._last_error,
                "last_latency_ms": self._last_latency_ms,
                "last_stage_latency_ms": dict(self._last_stage_latency_ms),
                "latency_summary_ms": self._latency_summary(),
                "successful_inferences": self._successful_inferences,
                "failed_inferences": self._failed_inferences,
                "retry_in_seconds": round(max(0.0, self._retry_at - time.monotonic()), 2),
            }

    def _latency_summary(self) -> Dict[str, float | int | None]:
        values = sorted(float(value) for value in self._latency_history)
        if not values:
            return {"samples": 0, "median": None, "p95": None, "p99": None, "max": None}
        return {
            "samples": len(values),
            "median": round(self._percentile(values, 0.50), 2),
            "p95": round(self._percentile(values, 0.95), 2),
            "p99": round(self._percentile(values, 0.99), 2),
            "max": round(values[-1], 2),
        }

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float:
        if len(values) == 1:
            return values[0]
        position = max(0.0, min(1.0, percentile)) * (len(values) - 1)
        lower = int(position)
        upper = min(len(values) - 1, lower + 1)
        fraction = position - lower
        return values[lower] * (1.0 - fraction) + values[upper] * fraction

    def close(self) -> None:
        with self._lock:
            self._close_runtime()

    def _ensure_runtime(self) -> Any:
        if self._runtime is not None:
            return self._runtime
        if not self.model_path.is_file():
            raise RuntimeError(f"Hailo pose model not found: {self.model_path}")
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

    @staticmethod
    def _preprocess(frame: Any, input_shape: tuple[int, ...]) -> Any:
        import cv2
        import numpy as np

        model_height, model_width, channels = input_shape
        if channels != 3:
            raise ValueError(f"Unsupported Hailo pose input shape: {input_shape}")
        height, width = frame.shape[:2]
        scale = min(model_width / width, model_height / height)
        resized_width = max(1, int(width * scale))
        resized_height = max(1, int(height * scale))
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR)
        output = np.full((model_height, model_width, 3), 114, dtype=np.uint8)
        offset_x = (model_width - resized_width) // 2
        offset_y = (model_height - resized_height) // 2
        output[offset_y:offset_y + resized_height, offset_x:offset_x + resized_width] = resized
        return output
