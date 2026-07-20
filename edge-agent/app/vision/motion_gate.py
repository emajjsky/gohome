from __future__ import annotations

from threading import RLock
from typing import Any, Dict


class MotionGate:
    """Cheap frame-difference gate used only to wake formal person inference."""

    version = "eacp-motion-gate-v1"

    def __init__(self, *, threshold: float = 0.02, sample_step: int = 8) -> None:
        self.threshold = max(0.002, float(threshold))
        self.sample_step = max(2, int(sample_step))
        self._states: dict[int, Dict[str, Any]] = {}
        self._lock = RLock()

    def update(self, camera_id: int, frame: Any, *, frame_id: str = "") -> Dict[str, Any]:
        try:
            import numpy as np  # type: ignore

            sample = frame[:: self.sample_step, :: self.sample_step]
            if sample.ndim == 3:
                sample = sample.astype(np.float32).mean(axis=2)
            else:
                sample = sample.astype(np.float32)
        except (AttributeError, IndexError, TypeError, ValueError):
            return self._payload(camera_id, frame_id, 0.0, False, "invalid_frame")

        camera_id = int(camera_id)
        with self._lock:
            previous = self._states.get(camera_id)
            if previous and frame_id and frame_id == previous.get("frame_id"):
                return dict(previous["payload"])
            score = 0.0
            if previous is not None and previous["sample"].shape == sample.shape:
                score = float(np.mean(np.abs(sample - previous["sample"])) / 255.0)
            detected = previous is not None and score >= self.threshold
            payload = self._payload(camera_id, frame_id, score, detected, "frame_difference")
            self._states[camera_id] = {
                "frame_id": str(frame_id or ""),
                "sample": sample,
                "payload": payload,
            }
            return dict(payload)

    def reset_camera(self, camera_id: int) -> None:
        with self._lock:
            self._states.pop(int(camera_id), None)

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "schema_version": self.version,
                "threshold": self.threshold,
                "camera_count": len(self._states),
            }

    def _payload(
        self,
        camera_id: int,
        frame_id: str,
        score: float,
        detected: bool,
        reason: str,
    ) -> Dict[str, Any]:
        return {
            "camera_id": int(camera_id),
            "frame_id": str(frame_id or ""),
            "motion_score": round(max(0.0, float(score)), 6),
            "detected": bool(detected),
            "threshold": self.threshold,
            "reason": reason,
        }
