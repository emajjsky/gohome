from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
import logging
import time
from typing import Any, Callable, Dict

import numpy as np

from .hailo_pose import HailoInferRuntime, HailoVDevicePool, preprocess_hailo_letterbox


logger = logging.getLogger(__name__)


@dataclass
class _TemporalMaskState:
    source_key: str
    width: int
    height: int
    frame_id: str
    frame_monotonic: float
    anchor_monotonic: float
    gray: Any
    mask: Any


class HailoPersonSegmentationDecoder:
    """Decode Hailo Model Zoo YOLO segmentation output for the person class only."""

    _STRIDES = (32, 16, 8)
    _ANCHORS = (
        ((116.0, 90.0), (156.0, 198.0), (373.0, 326.0)),
        ((30.0, 61.0), (62.0, 45.0), (59.0, 119.0)),
        ((10.0, 13.0), (16.0, 30.0), (33.0, 23.0)),
    )

    def __init__(
        self,
        *,
        input_size: int = 640,
        mask_channels: int = 32,
        confidence: float = 0.42,
        nms_iou: float = 0.55,
        mask_threshold: float = 0.34,
        maximum_candidates: int = 160,
        maximum_people: int = 4,
    ) -> None:
        self.input_size = int(input_size)
        self.mask_channels = int(mask_channels)
        self.confidence = float(confidence)
        self.nms_iou = float(nms_iou)
        self.mask_threshold = float(mask_threshold)
        self.maximum_candidates = max(8, int(maximum_candidates))
        self.maximum_people = max(1, int(maximum_people))

    def decode(
        self,
        outputs: Dict[str, Any],
        *,
        original_width: int,
        original_height: int,
        confidence: float | None = None,
    ) -> Dict[str, Any]:
        tensors = [self._batched(np.asarray(value, dtype=np.float32)) for value in outputs.values()]
        threshold = self.confidence if confidence is None else float(confidence)
        prototype = self._tensor_with_shape(tensors, (1, 160, 160, self.mask_channels))
        if any(tuple(tensor.shape) == (1, 20, 20, 351) for tensor in tensors):
            boxes, scores, coefficients = self._decode_v5_candidates(
                [self._tensor_with_shape(tensors, (1, grid, grid, 351)) for grid in (20, 40, 80)],
                threshold,
            )
            architecture = "yolov5_seg"
        else:
            boxes, scores, coefficients = self._decode_dfl_candidates(tensors, threshold)
            architecture = "yolo_dfl_seg"
        if not scores.size:
            return {**self._empty(original_width, original_height), "architecture": architecture}

        order = np.argsort(scores)[::-1][: self.maximum_candidates]
        boxes = boxes[order]
        scores = scores[order]
        coefficients = coefficients[order]
        keep = self._nms(boxes, scores, self.nms_iou, self.maximum_people)
        boxes = boxes[keep]
        scores = scores[keep]
        coefficients = coefficients[keep]

        masks = self._person_masks(prototype[0], coefficients, boxes)
        combined_model_mask = np.max(masks, axis=0) if masks.size else np.zeros((640, 640), dtype=np.float32)
        mask = self._unletterbox_mask(
            combined_model_mask,
            original_width=original_width,
            original_height=original_height,
        )
        image_boxes = self._unletterbox_boxes(
            boxes,
            original_width=original_width,
            original_height=original_height,
        )
        return {
            "mask": mask,
            "boxes": image_boxes,
            "scores": scores.astype(np.float32, copy=False),
            "person_count": int(len(scores)),
            "architecture": architecture,
        }

    def _decode_v5_candidates(
        self,
        branches: list[np.ndarray],
        threshold: float,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        all_boxes: list[np.ndarray] = []
        all_scores: list[np.ndarray] = []
        all_coefficients: list[np.ndarray] = []
        values_per_anchor = 5 + 80 + self.mask_channels
        for branch, stride, anchors in zip(branches, self._STRIDES, self._ANCHORS):
            grid_size = int(branch.shape[1])
            decoded = branch.transpose((0, 3, 1, 2)).reshape(
                (1, 3, values_per_anchor, grid_size, grid_size)
            ).transpose((0, 1, 3, 4, 2))[0]
            objectness = self._sigmoid(decoded[..., 4])
            person_probability = self._sigmoid(decoded[..., 5])
            scores = objectness * person_probability
            anchor_indices, grid_y, grid_x = np.nonzero(scores >= float(threshold))
            if not anchor_indices.size:
                continue
            selected = decoded[anchor_indices, grid_y, grid_x]
            selected_scores = scores[anchor_indices, grid_y, grid_x]
            centers = np.stack((grid_x, grid_y), axis=1).astype(np.float32) - 0.5
            xy = (self._sigmoid(selected[:, :2]) * 2.0 + centers) * float(stride)
            anchor_array = np.asarray(anchors, dtype=np.float32)[anchor_indices]
            wh = (self._sigmoid(selected[:, 2:4]) * 2.0) ** 2 * anchor_array
            boxes = np.concatenate((xy - wh / 2.0, xy + wh / 2.0), axis=1)
            all_boxes.append(boxes)
            all_scores.append(selected_scores.astype(np.float32, copy=False))
            all_coefficients.append(selected[:, 85:85 + self.mask_channels])

        if not all_scores:
            return (
                np.empty((0, 4), dtype=np.float32),
                np.empty((0,), dtype=np.float32),
                np.empty((0, self.mask_channels), dtype=np.float32),
            )
        return (
            np.concatenate(all_boxes, axis=0),
            np.concatenate(all_scores, axis=0),
            np.concatenate(all_coefficients, axis=0),
        )

    def _decode_dfl_candidates(
        self,
        tensors: list[np.ndarray],
        threshold: float,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        all_boxes: list[np.ndarray] = []
        all_scores: list[np.ndarray] = []
        all_coefficients: list[np.ndarray] = []
        regression_range = np.arange(16, dtype=np.float32)
        for grid_size, stride in ((20, 32), (40, 16), (80, 8)):
            box_tensor = self._tensor_with_shape(tensors, (1, grid_size, grid_size, 64))[0]
            score_tensor = self._tensor_with_shape(tensors, (1, grid_size, grid_size, 80))[0]
            coefficient_tensor = self._tensor_with_shape(
                tensors,
                (1, grid_size, grid_size, self.mask_channels),
            )[0]
            person_scores = score_tensor[..., 0]
            grid_y, grid_x = np.nonzero(person_scores >= float(threshold))
            if not grid_y.size:
                continue
            selected_distribution = box_tensor[grid_y, grid_x].reshape((-1, 4, 16))
            selected_distribution -= np.max(selected_distribution, axis=-1, keepdims=True)
            probabilities = np.exp(selected_distribution)
            probabilities /= np.sum(probabilities, axis=-1, keepdims=True)
            distances = np.sum(probabilities * regression_range, axis=-1) * float(stride)
            centers = np.stack((grid_x + 0.5, grid_y + 0.5), axis=1).astype(np.float32) * float(stride)
            boxes = np.concatenate((centers - distances[:, :2], centers + distances[:, 2:]), axis=1)
            all_boxes.append(boxes)
            all_scores.append(person_scores[grid_y, grid_x].astype(np.float32, copy=False))
            all_coefficients.append(coefficient_tensor[grid_y, grid_x])
        if not all_scores:
            return (
                np.empty((0, 4), dtype=np.float32),
                np.empty((0,), dtype=np.float32),
                np.empty((0, self.mask_channels), dtype=np.float32),
            )
        return (
            np.concatenate(all_boxes, axis=0),
            np.concatenate(all_scores, axis=0),
            np.concatenate(all_coefficients, axis=0),
        )

    def _person_masks(
        self,
        prototype: np.ndarray,
        coefficients: np.ndarray,
        boxes: np.ndarray,
    ) -> np.ndarray:
        import cv2

        proto_height, proto_width, channels = prototype.shape
        logits = coefficients @ prototype.reshape((-1, channels)).T
        masks = self._sigmoid(logits).reshape((-1, proto_height, proto_width))
        model_masks = np.empty(
            (masks.shape[0], self.input_size, self.input_size),
            dtype=np.float32,
        )
        proto_boxes = boxes.copy()
        proto_boxes[:, (0, 2)] *= proto_width / float(self.input_size)
        proto_boxes[:, (1, 3)] *= proto_height / float(self.input_size)
        for index, box in enumerate(proto_boxes):
            x1, y1, x2, y2 = self._clamped_box(box, proto_width, proto_height)
            cropped = np.zeros((proto_height, proto_width), dtype=np.float32)
            cropped[y1:y2, x1:x2] = masks[index, y1:y2, x1:x2]
            model_masks[index] = cv2.resize(
                cropped,
                (self.input_size, self.input_size),
                interpolation=cv2.INTER_LINEAR,
            )
        return model_masks

    def _unletterbox_mask(
        self,
        model_mask: np.ndarray,
        *,
        original_width: int,
        original_height: int,
    ) -> np.ndarray:
        import cv2

        scale, resized_width, resized_height, offset_x, offset_y = self._letterbox_geometry(
            original_width,
            original_height,
        )
        del scale
        content = model_mask[
            offset_y:offset_y + resized_height,
            offset_x:offset_x + resized_width,
        ]
        if content.size == 0:
            return np.zeros((original_height, original_width), dtype=np.uint8)
        probability = cv2.resize(
            content,
            (original_width, original_height),
            interpolation=cv2.INTER_LINEAR,
        )
        mask = np.where(probability >= self.mask_threshold, 255, 0).astype(np.uint8)
        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)),
        )
        return cv2.dilate(
            mask,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
            iterations=1,
        )

    def _unletterbox_boxes(
        self,
        boxes: np.ndarray,
        *,
        original_width: int,
        original_height: int,
    ) -> np.ndarray:
        scale, _resized_width, _resized_height, offset_x, offset_y = self._letterbox_geometry(
            original_width,
            original_height,
        )
        output = boxes.copy()
        output[:, (0, 2)] = (output[:, (0, 2)] - offset_x) / scale
        output[:, (1, 3)] = (output[:, (1, 3)] - offset_y) / scale
        output[:, (0, 2)] = np.clip(output[:, (0, 2)], 0, max(0, original_width - 1))
        output[:, (1, 3)] = np.clip(output[:, (1, 3)], 0, max(0, original_height - 1))
        return output.astype(np.float32, copy=False)

    def _letterbox_geometry(self, width: int, height: int) -> tuple[float, int, int, int, int]:
        scale = min(self.input_size / width, self.input_size / height)
        resized_width = max(1, int(width * scale))
        resized_height = max(1, int(height * scale))
        return (
            scale,
            resized_width,
            resized_height,
            (self.input_size - resized_width) // 2,
            (self.input_size - resized_height) // 2,
        )

    @staticmethod
    def _nms(boxes: np.ndarray, scores: np.ndarray, threshold: float, maximum: int) -> list[int]:
        x1, y1, x2, y2 = boxes.T
        areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
        order = np.argsort(scores)[::-1]
        keep: list[int] = []
        while order.size and len(keep) < maximum:
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
            order = rest[iou < float(threshold)]
        return keep

    @staticmethod
    def _sigmoid(values: np.ndarray) -> np.ndarray:
        clipped = np.clip(values, -60.0, 60.0)
        return 1.0 / (1.0 + np.exp(-clipped))

    @staticmethod
    def _batched(value: np.ndarray) -> np.ndarray:
        return value if value.ndim == 4 else np.expand_dims(value, axis=0)

    @staticmethod
    def _tensor_with_shape(tensors: list[np.ndarray], shape: tuple[int, ...]) -> np.ndarray:
        for tensor in tensors:
            if tuple(int(item) for item in tensor.shape) == shape:
                return tensor.reshape(shape)
        raise ValueError(f"Hailo segmentation output is missing tensor {shape}")

    @staticmethod
    def _clamped_box(box: np.ndarray, width: int, height: int) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = [int(round(float(value))) for value in box[:4]]
        x1 = max(0, min(width - 1, x1))
        y1 = max(0, min(height - 1, y1))
        x2 = max(x1 + 1, min(width, x2))
        y2 = max(y1 + 1, min(height, y2))
        return x1, y1, x2, y2

    @staticmethod
    def _empty(width: int, height: int) -> Dict[str, Any]:
        return {
            "mask": np.zeros((height, width), dtype=np.uint8),
            "boxes": np.empty((0, 4), dtype=np.float32),
            "scores": np.empty((0,), dtype=np.float32),
            "person_count": 0,
        }


class HailoPersonSegmentationBackend:
    """Anchor person masks on Hailo and propagate them across exact stream frames."""

    version = "hailo-yolov11s-person-segmentation-v2"

    def __init__(
        self,
        *,
        mode: str = "auto",
        model_path: str = "/usr/share/hailo-models/yolov11s_seg_h8.hef",
        confidence: float = 0.42,
        retry_seconds: float = 30.0,
        cache_size: int = 12,
        anchor_interval_seconds: float = 0.18,
        maximum_propagation_seconds: float = 0.35,
        flow_width: int = 320,
        runtime_factory: Callable[[Path], Any] | None = None,
    ) -> None:
        self.mode = str(mode or "auto").strip().lower()
        self.model_path = Path(model_path)
        self.confidence = float(confidence)
        self.retry_seconds = max(1.0, float(retry_seconds))
        self.cache_size = max(2, int(cache_size))
        self.anchor_interval_seconds = max(0.08, min(0.5, float(anchor_interval_seconds)))
        self.maximum_propagation_seconds = max(
            self.anchor_interval_seconds,
            min(0.8, float(maximum_propagation_seconds)),
        )
        self.flow_width = max(160, min(480, int(flow_width)))
        self.runtime_factory = runtime_factory or HailoInferRuntime
        self.decoder = HailoPersonSegmentationDecoder(confidence=confidence)
        self._runtime: Any | None = None
        self._runtime_lock = RLock()
        self._camera_locks: Dict[int, RLock] = {}
        self._cache: OrderedDict[tuple[int, str, str], Dict[str, Any]] = OrderedDict()
        self._temporal_states: Dict[int, _TemporalMaskState] = {}
        self._lock = RLock()
        self._retry_at = 0.0
        self._status = "disabled" if not self.enabled else "idle"
        self._last_error = ""
        self._last_latency_ms: float | None = None
        self._last_stage_latency_ms: Dict[str, float] = {}
        self._latency_history: deque[float] = deque(maxlen=240)
        self._successful_inferences = 0
        self._failed_inferences = 0
        self._cache_hits = 0
        self._anchor_inferences = 0
        self._propagated_frames = 0
        self._propagation_rejections = 0
        self._flow_latency_history: deque[float] = deque(maxlen=240)

    @property
    def enabled(self) -> bool:
        return self.mode not in {"off", "cpu", "disabled"}

    def segment(
        self,
        camera_id: int,
        frame: Any,
        *,
        frame_id: str,
        source_key: str,
        captured_monotonic: float | None = None,
        person_evidence: bool = False,
        force_anchor: bool = False,
    ) -> Dict[str, Any]:
        key = (int(camera_id), str(source_key or ""), str(frame_id or ""))
        if not key[2]:
            raise ValueError("person segmentation requires a source frame_id")
        now = time.monotonic()
        frame_monotonic = self._frame_time(captured_monotonic, now)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                self._cache_hits += 1
                return self._copy_result(cached, cache_hit=True)
            if not self.enabled:
                raise RuntimeError("Hailo person segmentation is disabled")
            if now < self._retry_at:
                raise RuntimeError(self._last_error or "Hailo person segmentation is retrying")
            camera_lock = self._camera_locks.setdefault(int(camera_id), RLock())

        with camera_lock:
            with self._lock:
                cached = self._cache.get(key)
                if cached is not None:
                    self._cache.move_to_end(key)
                    self._cache_hits += 1
                    return self._copy_result(cached, cache_hit=True)
                now = time.monotonic()
                state = self._temporal_states.get(int(camera_id))
            temporal = None if force_anchor else self._temporal_result(
                int(camera_id),
                frame,
                key=key,
                state=state,
                frame_monotonic=frame_monotonic,
                person_evidence=bool(person_evidence),
            )
            if temporal is not None:
                self._store_result(key, temporal)
                return self._copy_result(temporal, cache_hit=False)
            with self._lock:
                now = time.monotonic()
                if now < self._retry_at:
                    raise RuntimeError(self._last_error or "Hailo person segmentation is retrying")
            started_at = time.perf_counter()
            try:
                runtime = self._ensure_runtime()
                preprocess_started = time.perf_counter()
                model_input = preprocess_hailo_letterbox(frame, runtime.input_shape)
                preprocess_ms = (time.perf_counter() - preprocess_started) * 1000.0
                inference_started = time.perf_counter()
                with self._runtime_lock:
                    if runtime is not self._runtime:
                        raise RuntimeError("Hailo person segmentation runtime changed during inference")
                    outputs = runtime.infer(model_input)
                inference_ms = (time.perf_counter() - inference_started) * 1000.0
                decode_started = time.perf_counter()
                height, width = frame.shape[:2]
                result = self.decoder.decode(
                    outputs,
                    original_width=int(width),
                    original_height=int(height),
                    confidence=self.confidence,
                )
                decode_ms = (time.perf_counter() - decode_started) * 1000.0
                total_ms = (time.perf_counter() - started_at) * 1000.0
                stored = {
                    **result,
                    "camera_id": int(camera_id),
                    "source_key": key[1],
                    "frame_id": key[2],
                    "backend": "hailo",
                    "model_name": self.model_path.name,
                    "latency_ms": round(total_ms, 2),
                    "stage_latency_ms": {
                        "preprocess": round(preprocess_ms, 2),
                        "device_inference": round(inference_ms, 2),
                        "decode_mask": round(decode_ms, 2),
                        "total": round(total_ms, 2),
                    },
                    "cache_hit": False,
                    "temporal_mode": "anchor",
                    "anchor_age_ms": 0.0,
                }
                with self._lock:
                    self._store_result_locked(key, stored)
                    self._temporal_states[int(camera_id)] = self._new_temporal_state(
                        frame,
                        stored["mask"],
                        source_key=key[1],
                        frame_id=key[2],
                        frame_monotonic=frame_monotonic,
                    )
                    self._successful_inferences += 1
                    self._anchor_inferences += 1
                    self._last_latency_ms = round(total_ms, 2)
                    self._last_stage_latency_ms = dict(stored["stage_latency_ms"])
                    self._latency_history.append(total_ms)
                    was_ready = self._status == "ready"
                    self._status = "ready"
                    self._last_error = ""
                if not was_ready:
                    logger.info(
                        "Hailo person segmentation ready: model=%s latency_ms=%.2f",
                        self.model_path.name,
                        total_ms,
                    )
                return self._copy_result(stored, cache_hit=False)
            except Exception as exc:
                with self._lock:
                    self._failed_inferences += 1
                    self._status = "degraded"
                    self._last_error = str(exc)
                    self._retry_at = time.monotonic() + self.retry_seconds
                logger.warning("Hailo person segmentation degraded: %s", exc)
                self._close_runtime()
                raise

    def segment_anchor(
        self,
        camera_id: int,
        frame: Any,
        *,
        frame_id: str,
        source_key: str,
        captured_monotonic: float | None = None,
        person_evidence: bool = False,
    ) -> Dict[str, Any]:
        return self.segment(
            camera_id,
            frame,
            frame_id=frame_id,
            source_key=source_key,
            captured_monotonic=captured_monotonic,
            person_evidence=person_evidence,
            force_anchor=True,
        )

    def reset_camera(self, camera_id: int) -> None:
        camera_id = int(camera_id)
        with self._lock:
            for key in [item for item in self._cache if item[0] == camera_id]:
                self._cache.pop(key, None)
            self._camera_locks.pop(camera_id, None)
            self._temporal_states.pop(camera_id, None)

    def status(self) -> Dict[str, Any]:
        with self._runtime_lock:
            runtime_count = int(self._runtime is not None)
        with self._lock:
            values = sorted(float(value) for value in self._latency_history)
            return {
                "schema_version": self.version,
                "mode": self.mode,
                "status": self._status,
                "model_path": str(self.model_path),
                "model_present": self.model_path.is_file(),
                "last_error": self._last_error,
                "last_latency_ms": self._last_latency_ms,
                "last_stage_latency_ms": dict(self._last_stage_latency_ms),
                "latency_summary_ms": self._latency_summary(values),
                "successful_inferences": self._successful_inferences,
                "failed_inferences": self._failed_inferences,
                "cache_hits": self._cache_hits,
                "anchor_inferences": self._anchor_inferences,
                "propagated_frames": self._propagated_frames,
                "propagation_rejections": self._propagation_rejections,
                "anchor_interval_seconds": self.anchor_interval_seconds,
                "maximum_propagation_seconds": self.maximum_propagation_seconds,
                "flow_width": self.flow_width,
                "flow_latency_summary_ms": self._latency_summary(
                    sorted(float(value) for value in self._flow_latency_history)
                ),
                "cache_entries": len(self._cache),
                "runtime_count": runtime_count,
                "runtime_ownership": "shared_per_hef",
                "retry_in_seconds": round(max(0.0, self._retry_at - time.monotonic()), 2),
                "shared_vdevice": HailoVDevicePool.status(),
            }

    def close(self) -> None:
        self._close_runtime()
        with self._lock:
            self._cache.clear()
            self._camera_locks.clear()
            self._temporal_states.clear()

    def _ensure_runtime(self) -> Any:
        with self._runtime_lock:
            if self._runtime is not None:
                return self._runtime
            if not self.model_path.is_file():
                raise RuntimeError(f"Hailo person segmentation model not found: {self.model_path}")
            self._runtime = self.runtime_factory(self.model_path)
            return self._runtime

    def _close_runtime(self) -> None:
        with self._runtime_lock:
            runtime = self._runtime
            self._runtime = None
        if runtime is not None:
            try:
                runtime.close()
            except Exception:
                pass

    def _temporal_result(
        self,
        camera_id: int,
        frame: Any,
        *,
        key: tuple[int, str, str],
        state: _TemporalMaskState | None,
        frame_monotonic: float,
        person_evidence: bool,
    ) -> Dict[str, Any] | None:
        if state is None:
            return None
        height, width = frame.shape[:2]
        anchor_age = max(0.0, frame_monotonic - state.anchor_monotonic)
        if (
            state.source_key != key[1]
            or state.width != int(width)
            or state.height != int(height)
            or anchor_age >= self.anchor_interval_seconds
            or frame_monotonic <= state.frame_monotonic
            or (person_evidence and not bool(np.any(state.mask)))
        ):
            return None
        if anchor_age > self.maximum_propagation_seconds:
            return None

        import cv2

        gray = self._flow_gray(cv2, frame)
        frame_delta = cv2.absdiff(gray, state.gray)
        scene_delta = float(np.mean(frame_delta))
        motion_ratio = float(np.mean(frame_delta >= 18))
        if not bool(np.any(state.mask)) and motion_ratio >= 0.01:
            with self._lock:
                self._propagation_rejections += 1
            return None
        if scene_delta >= 38.0:
            with self._lock:
                self._propagation_rejections += 1
            return None
        started_at = time.perf_counter()
        flow = cv2.calcOpticalFlowFarneback(
            gray,
            state.gray,
            None,
            0.5,
            2,
            15,
            2,
            5,
            1.1,
            0,
        )
        grid_x, grid_y = np.meshgrid(
            np.arange(gray.shape[1], dtype=np.float32),
            np.arange(gray.shape[0], dtype=np.float32),
        )
        warped = cv2.remap(
            state.mask,
            grid_x + flow[..., 0],
            grid_y + flow[..., 1],
            cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        warped = np.where(warped >= 72, 255, 0).astype(np.uint8)
        if bool(np.any(warped)):
            warped = cv2.morphologyEx(
                warped,
                cv2.MORPH_CLOSE,
                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
            )
            warped = cv2.dilate(
                warped,
                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
                iterations=1,
            )
        mask = cv2.resize(warped, (int(width), int(height)), interpolation=cv2.INTER_NEAREST)
        flow_ms = (time.perf_counter() - started_at) * 1000.0
        stored = {
            "mask": mask,
            "boxes": np.empty((0, 4), dtype=np.float32),
            "scores": np.empty((0,), dtype=np.float32),
            "person_count": int(bool(np.any(mask))),
            "architecture": "temporal_mask_flow",
            "camera_id": int(camera_id),
            "source_key": key[1],
            "frame_id": key[2],
            "backend": "hailo_temporal",
            "model_name": self.model_path.name,
            "latency_ms": round(flow_ms, 2),
            "stage_latency_ms": {
                "optical_flow": round(flow_ms, 2),
                "total": round(flow_ms, 2),
            },
            "cache_hit": False,
            "temporal_mode": "propagated",
            "anchor_age_ms": round(anchor_age * 1000.0, 2),
            "scene_delta": round(scene_delta, 2),
            "motion_ratio": round(motion_ratio, 4),
        }
        with self._lock:
            self._temporal_states[int(camera_id)] = _TemporalMaskState(
                source_key=key[1],
                width=int(width),
                height=int(height),
                frame_id=key[2],
                frame_monotonic=frame_monotonic,
                anchor_monotonic=state.anchor_monotonic,
                gray=gray,
                mask=warped,
            )
            self._propagated_frames += 1
            self._flow_latency_history.append(flow_ms)
        return stored

    def _new_temporal_state(
        self,
        frame: Any,
        mask: Any,
        *,
        source_key: str,
        frame_id: str,
        frame_monotonic: float,
    ) -> _TemporalMaskState:
        import cv2

        height, width = frame.shape[:2]
        gray = self._flow_gray(cv2, frame)
        small_mask = cv2.resize(
            np.asarray(mask, dtype=np.uint8),
            (int(gray.shape[1]), int(gray.shape[0])),
            interpolation=cv2.INTER_NEAREST,
        )
        return _TemporalMaskState(
            source_key=str(source_key),
            width=int(width),
            height=int(height),
            frame_id=str(frame_id),
            frame_monotonic=float(frame_monotonic),
            anchor_monotonic=float(frame_monotonic),
            gray=gray,
            mask=small_mask,
        )

    def _flow_gray(self, cv2: Any, frame: Any) -> Any:
        height, width = frame.shape[:2]
        target_width = min(int(width), self.flow_width)
        target_height = max(1, int(round(height * target_width / max(1, width))))
        resized = (
            frame
            if target_width == int(width)
            else cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)
        )
        return cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

    def _store_result(self, key: tuple[int, str, str], result: Dict[str, Any]) -> None:
        with self._lock:
            self._store_result_locked(key, result)

    def _store_result_locked(self, key: tuple[int, str, str], result: Dict[str, Any]) -> None:
        self._cache[key] = result
        self._cache.move_to_end(key)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)

    @staticmethod
    def _frame_time(value: float | None, now: float) -> float:
        try:
            resolved = float(value)
        except (TypeError, ValueError):
            return float(now)
        if not np.isfinite(resolved) or resolved <= 0.0 or abs(float(now) - resolved) > 3600.0:
            return float(now)
        return resolved

    @staticmethod
    def _copy_result(result: Dict[str, Any], *, cache_hit: bool) -> Dict[str, Any]:
        boxes = result.get("boxes")
        scores = result.get("scores")
        return {
            **result,
            "mask": np.asarray(result["mask"], dtype=np.uint8).copy(),
            "boxes": np.asarray(boxes if boxes is not None else [], dtype=np.float32).reshape((-1, 4)).copy(),
            "scores": np.asarray(scores if scores is not None else [], dtype=np.float32).reshape((-1,)).copy(),
            "stage_latency_ms": dict(result.get("stage_latency_ms") or {}),
            "cache_hit": bool(cache_hit),
        }

    @staticmethod
    def _latency_summary(values: list[float]) -> Dict[str, float | int | None]:
        if not values:
            return {"samples": 0, "median": None, "p95": None, "max": None}
        return {
            "samples": len(values),
            "median": round(float(np.percentile(values, 50)), 2),
            "p95": round(float(np.percentile(values, 95)), 2),
            "max": round(values[-1], 2),
        }
