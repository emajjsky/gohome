from __future__ import annotations

from collections import deque
from threading import RLock
import time
from typing import Any

import numpy as np


class PrivacyBackgroundReconstructor:
    """Remove people using pixels from the current camera frame only."""

    version = "privacy-background-reconstructor-v3"

    def __init__(self, *, max_states: int = 6, max_inpaint_dimension: int = 192) -> None:
        self.max_states = max(1, int(max_states))
        self.max_inpaint_dimension = max(96, int(max_inpaint_dimension))
        self._lock = RLock()
        self._camera_metrics: dict[int, dict[str, Any]] = {}

    def reconstruct(
        self,
        cv2: Any,
        camera_id: int,
        frame: Any,
        person_mask: Any,
        *,
        clear_token: str = "",
        source_key: str = "",
    ) -> Any:
        del clear_token
        height, width = frame.shape[:2]
        mask = self._binary_mask(cv2, person_mask, width, height)
        if not bool(cv2.countNonZero(mask)):
            self._record(int(camera_id), "clear_frames", source_key=source_key)
            return frame.copy()

        started = time.monotonic()
        output = self._inpaint_current_frame(cv2, frame, mask)
        self._record(
            int(camera_id),
            "person_frames",
            source_key=source_key,
            latency_ms=(time.monotonic() - started) * 1000.0,
        )
        return output

    def reset_camera(self, camera_id: int) -> None:
        with self._lock:
            self._camera_metrics.pop(int(camera_id), None)

    def safe_scene(
        self,
        cv2: Any,
        camera_id: int,
        frame: Any,
        *,
        source_key: str = "",
    ) -> Any:
        """Return a non-revealing frame when synchronized person metadata is unavailable."""
        self._record(int(camera_id), "neutral_fallback_frames", source_key=source_key)
        height, width = frame.shape[:2]
        border = np.concatenate(
            (
                frame[: max(1, height // 18)].reshape(-1, 3),
                frame[-max(1, height // 18):].reshape(-1, 3),
                frame[:, : max(1, width // 24)].reshape(-1, 3),
                frame[:, -max(1, width // 24):].reshape(-1, 3),
            ),
            axis=0,
        )
        tone = np.median(border, axis=0).astype(np.uint8)
        return np.broadcast_to(tone, frame.shape).copy()

    def status(self) -> dict[str, Any]:
        with self._lock:
            cameras = []
            for camera_id, metrics in sorted(self._camera_metrics.items()):
                latencies = list(metrics.get("latencies_ms") or ())
                cameras.append({
                    "camera_id": camera_id,
                    "source_key": str(metrics.get("source_key") or ""),
                    "clear_frames": int(metrics.get("clear_frames") or 0),
                    "person_frames": int(metrics.get("person_frames") or 0),
                    "neutral_fallback_frames": int(metrics.get("neutral_fallback_frames") or 0),
                    "inpaint_latency_ms_p50": round(self._percentile(latencies, 0.50), 2),
                    "inpaint_latency_ms_p95": round(self._percentile(latencies, 0.95), 2),
                })
        return {
            "schema_version": self.version,
            "strategy": "current_frame_local_inpaint",
            "max_inpaint_dimension": self.max_inpaint_dimension,
            "retained_pixel_state": False,
            "state_count": 0,
            "max_states": self.max_states,
            "memory_bytes": 0,
            "cameras": cameras,
        }

    def _inpaint_current_frame(self, cv2: Any, frame: Any, mask: Any) -> Any:
        radius = max(3, min(9, int(round(min(frame.shape[:2]) * 0.015))))
        expanded = cv2.dilate(mask, np.ones((7, 7), dtype=np.uint8), iterations=1)
        points = cv2.findNonZero(expanded)
        if points is None:
            return frame.copy()
        x, y, width, height = cv2.boundingRect(points)
        margin = max(8, radius * 3)
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(frame.shape[1], x + width + margin)
        y2 = min(frame.shape[0], y + height + margin)
        crop = frame[y1:y2, x1:x2]
        crop_mask = expanded[y1:y2, x1:x2]
        crop_height, crop_width = crop.shape[:2]
        scale = min(1.0, self.max_inpaint_dimension / max(crop_width, crop_height))
        if scale < 1.0:
            working_size = (
                max(1, int(round(crop_width * scale))),
                max(1, int(round(crop_height * scale))),
            )
            working_crop = cv2.resize(crop, working_size, interpolation=cv2.INTER_AREA)
            working_mask = cv2.resize(crop_mask, working_size, interpolation=cv2.INTER_NEAREST)
            working_radius = max(2, int(round(radius * scale)))
            repaired = cv2.inpaint(working_crop, working_mask, working_radius, cv2.INPAINT_TELEA)
            repaired = cv2.resize(repaired, (crop_width, crop_height), interpolation=cv2.INTER_LINEAR)
        else:
            repaired = cv2.inpaint(crop, crop_mask, radius, cv2.INPAINT_TELEA)
        output = frame.copy()
        output[y1:y2, x1:x2] = repaired
        return output

    def _record(
        self,
        camera_id: int,
        field: str,
        *,
        source_key: str,
        latency_ms: float | None = None,
    ) -> None:
        with self._lock:
            metrics = self._camera_metrics.get(camera_id)
            if metrics is None:
                while len(self._camera_metrics) >= self.max_states:
                    self._camera_metrics.pop(next(iter(self._camera_metrics)))
                metrics = {
                    "source_key": str(source_key or ""),
                    "clear_frames": 0,
                    "person_frames": 0,
                    "neutral_fallback_frames": 0,
                    "latencies_ms": deque(maxlen=240),
                }
                self._camera_metrics[camera_id] = metrics
            elif source_key and source_key != metrics.get("source_key"):
                metrics["source_key"] = str(source_key)
            metrics[field] = int(metrics.get(field) or 0) + 1
            if latency_ms is not None:
                metrics["latencies_ms"].append(max(0.0, float(latency_ms)))

    def _percentile(self, values: list[float], quantile: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * quantile))))
        return float(ordered[index])

    def _binary_mask(self, cv2: Any, mask: Any, width: int, height: int) -> Any:
        array = np.asarray(mask, dtype=np.uint8)
        if array.shape != (height, width):
            array = cv2.resize(array, (width, height), interpolation=cv2.INTER_NEAREST)
        return np.where(array > 0, 255, 0).astype(np.uint8)
