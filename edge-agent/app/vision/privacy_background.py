from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import RLock
import time
from typing import Any

import numpy as np


@dataclass
class _BackgroundState:
    frame: Any | None = None
    clean: bool = False
    last_used: float = 0.0
    clear_observations: int = 0
    candidate: Any | None = None
    candidate_observations: int = 0
    last_clear_token: str = ""


class PrivacyBackgroundReconstructor:
    """Keep bounded, camera-local clean scenes for skeleton-only privacy video."""

    version = "privacy-background-reconstructor-v1"

    def __init__(self, *, max_states: int = 6) -> None:
        self.max_states = max(1, int(max_states))
        self._states: OrderedDict[tuple[int, int, int], _BackgroundState] = OrderedDict()
        self._lock = RLock()

    def reconstruct(
        self,
        cv2: Any,
        camera_id: int,
        frame: Any,
        person_mask: Any,
        *,
        clear_token: str = "",
    ) -> Any:
        height, width = frame.shape[:2]
        key = (int(camera_id), int(width), int(height))
        mask = self._binary_mask(cv2, person_mask, width, height)
        has_person = bool(cv2.countNonZero(mask))

        if not has_person:
            self._observe_clear_frame(key, frame, clear_token=clear_token)
            return frame.copy()

        background = self._background_copy(key)
        if background is None:
            background = self._safe_fallback(cv2, frame, mask)
            self._store_provisional_background(key, background)

        background = self._match_illumination(cv2, background, frame, mask)
        return self._composite(cv2, frame, background, mask)

    def reset_camera(self, camera_id: int) -> None:
        camera_id = int(camera_id)
        with self._lock:
            for key in [item for item in self._states if item[0] == camera_id]:
                self._states.pop(key, None)

    def safe_scene(self, cv2: Any, camera_id: int, frame: Any) -> Any:
        """Return a retained person-free scene, or a non-revealing startup frame."""
        height, width = frame.shape[:2]
        background = self._camera_background_copy(int(camera_id), width, height)
        if background is not None:
            return background
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
            return {
                "schema_version": self.version,
                "state_count": len(self._states),
                "max_states": self.max_states,
                "memory_bytes": sum(
                    (int(state.frame.nbytes) if state.frame is not None else 0)
                    + (int(state.candidate.nbytes) if state.candidate is not None else 0)
                    for state in self._states.values()
                ),
                "states": [
                    {
                        "camera_id": key[0],
                        "width": key[1],
                        "height": key[2],
                        "clean": state.clean,
                        "clear_observations": state.clear_observations,
                        "candidate_observations": state.candidate_observations,
                    }
                    for key, state in self._states.items()
                ],
            }

    def _observe_clear_frame(
        self,
        key: tuple[int, int, int],
        frame: Any,
        *,
        clear_token: str = "",
    ) -> None:
        now = time.monotonic()
        with self._lock:
            state = self._state(key, now)
            token = str(clear_token or "")
            if token and token == state.last_clear_token:
                state.last_used = now
                return
            if token:
                state.last_clear_token = token
            if state.clean and state.frame is not None:
                state.frame = self._stable_update(state.frame, frame)
                state.clear_observations += 1
            else:
                if state.candidate is None or not self._frames_stable(state.candidate, frame):
                    state.candidate = frame.copy()
                    state.candidate_observations = 1
                else:
                    state.candidate = self._stable_update(state.candidate, frame)
                    state.candidate_observations += 1
                if state.candidate_observations >= 3:
                    state.frame = state.candidate.copy()
                    state.clean = True
                    state.clear_observations = state.candidate_observations
                    state.candidate = None
                    state.candidate_observations = 0
            state.last_used = now

    def _background_copy(self, key: tuple[int, int, int]) -> Any | None:
        now = time.monotonic()
        with self._lock:
            state = self._states.get(key)
            if state is None or state.frame is None:
                return None
            state.last_used = now
            self._states.move_to_end(key)
            return state.frame.copy()

    def _camera_background_copy(self, camera_id: int, width: int, height: int) -> Any | None:
        now = time.monotonic()
        with self._lock:
            exact_key = (camera_id, width, height)
            exact = self._states.get(exact_key)
            if exact is not None and exact.frame is not None:
                exact.last_used = now
                self._states.move_to_end(exact_key)
                return exact.frame.copy()
            candidates = [
                (key, state)
                for key, state in self._states.items()
                if key[0] == camera_id and state.frame is not None
            ]
            if not candidates:
                return None
            key, state = max(candidates, key=lambda item: item[1].last_used)
            state.last_used = now
            self._states.move_to_end(key)
            source = state.frame.copy()
        return cv2.resize(source, (width, height), interpolation=cv2.INTER_LINEAR)

    def _store_provisional_background(self, key: tuple[int, int, int], frame: Any) -> None:
        now = time.monotonic()
        with self._lock:
            state = self._state(key, now)
            if state.frame is None:
                state.frame = frame.copy()
                state.clean = False
            state.last_used = now

    def _state(self, key: tuple[int, int, int], now: float) -> _BackgroundState:
        state = self._states.get(key)
        if state is None:
            while len(self._states) >= self.max_states:
                self._states.popitem(last=False)
            state = _BackgroundState(last_used=now)
            self._states[key] = state
        self._states.move_to_end(key)
        return state

    def _stable_update(self, background: Any, frame: Any) -> Any:
        difference = np.max(
            np.abs(frame.astype(np.int16) - background.astype(np.int16)),
            axis=2,
        )
        stable = difference <= 24
        updated = background.copy()
        if np.any(stable):
            blended = (
                background[stable].astype(np.uint16) * 7
                + frame[stable].astype(np.uint16)
            ) // 8
            updated[stable] = blended.astype(np.uint8)
        return updated

    def _frames_stable(self, first: Any, second: Any) -> bool:
        difference = np.max(
            np.abs(second.astype(np.int16) - first.astype(np.int16)),
            axis=2,
        )
        return float(np.mean(difference <= 28)) >= 0.82

    def _safe_fallback(self, cv2: Any, frame: Any, mask: Any) -> Any:
        radius = max(3, min(11, int(round(min(frame.shape[:2]) * 0.018))))
        expanded = cv2.dilate(mask, np.ones((7, 7), dtype=np.uint8), iterations=1)
        return cv2.inpaint(frame, expanded, radius, cv2.INPAINT_TELEA)

    def _match_illumination(self, cv2: Any, background: Any, frame: Any, mask: Any) -> Any:
        visible = mask == 0
        if int(np.count_nonzero(visible)) < 256:
            return background
        current_mean = np.median(frame[visible], axis=0)
        background_mean = np.median(background[visible], axis=0)
        shift = np.clip(current_mean - background_mean, -28.0, 28.0)
        if float(np.max(np.abs(shift))) < 1.0:
            return background
        return np.clip(background.astype(np.int16) + np.rint(shift).astype(np.int16), 0, 255).astype(np.uint8)

    def _composite(self, cv2: Any, frame: Any, background: Any, mask: Any) -> Any:
        outer = cv2.dilate(mask, np.ones((9, 9), dtype=np.uint8), iterations=1)
        alpha = cv2.GaussianBlur(outer, (9, 9), 0)
        alpha[mask > 0] = 255
        alpha16 = alpha.astype(np.uint16)[..., None]
        output = (
            background.astype(np.uint16) * alpha16
            + frame.astype(np.uint16) * (255 - alpha16)
            + 127
        ) // 255
        return output.astype(np.uint8)

    def _binary_mask(self, cv2: Any, mask: Any, width: int, height: int) -> Any:
        array = np.asarray(mask, dtype=np.uint8)
        if array.shape != (height, width):
            array = cv2.resize(array, (width, height), interpolation=cv2.INTER_NEAREST)
        return np.where(array > 0, 255, 0).astype(np.uint8)
