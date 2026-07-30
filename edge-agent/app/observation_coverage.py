from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable, Deque, Dict
import time


class ObservationCoverageTracker:
    """Tracks valid camera observations without turning routine frames into disk writes."""

    def __init__(
        self,
        *,
        window_seconds: float = 3600.0,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        self.window_seconds = max(60.0, float(window_seconds))
        self.monotonic_clock = monotonic_clock or time.monotonic
        self._observations: Dict[int, Deque[tuple[float, str, bool]]] = defaultdict(deque)
        self._first_observed_at: Dict[int, float] = {}
        self._last_observed_at: Dict[int, str] = {}
        self._last_person_seen_at: Dict[int, str] = {}
        self._lock = Lock()

    def observe(
        self,
        camera_id: int,
        *,
        observed_at: str,
        person_present: bool,
        valid: bool = True,
        now: float | None = None,
    ) -> None:
        if not valid:
            return
        camera_id = int(camera_id)
        monotonic_now = self.monotonic_clock() if now is None else float(now)
        normalized_at = self._normalize_iso(observed_at)
        with self._lock:
            observations = self._observations[camera_id]
            observations.append((monotonic_now, normalized_at, bool(person_present)))
            self._first_observed_at.setdefault(camera_id, monotonic_now)
            self._last_observed_at[camera_id] = normalized_at
            if person_present:
                self._last_person_seen_at[camera_id] = normalized_at
            self._prune(observations, monotonic_now)

    def status(
        self,
        camera_id: int,
        *,
        expected_interval_seconds: float,
        historical: Dict[str, Any] | None = None,
        now: float | None = None,
    ) -> Dict[str, Any]:
        camera_id = int(camera_id)
        monotonic_now = self.monotonic_clock() if now is None else float(now)
        interval = max(0.25, float(expected_interval_seconds))
        history = dict(historical or {})
        with self._lock:
            observations = self._observations[camera_id]
            self._prune(observations, monotonic_now)
            first_observed = self._first_observed_at.get(camera_id)
            elapsed = 0.0 if first_observed is None else min(
                self.window_seconds,
                max(0.0, monotonic_now - first_observed) + interval,
            )
            expected_samples = max(1, int(elapsed / interval)) if observations else 0
            bucket_ids = {int(item[0] / interval) for item in observations}
            person_bucket_ids = {int(item[0] / interval) for item in observations if item[2]}
            observed_samples = len(bucket_ids)
            person_samples = len(person_bucket_ids)
            current_last_person = self._last_person_seen_at.get(camera_id)
            current_last_observed = self._last_observed_at.get(camera_id)

        historical_last_person = history.get("last_person_seen_at")
        return {
            "last_observed_at": current_last_observed,
            "last_person_seen_at": self._latest_iso(current_last_person, historical_last_person),
            "observation_window_minutes": max(1, int(self.window_seconds // 60)),
            "observed_samples": observed_samples,
            "person_samples": person_samples,
            "last_pet_seen_at": history.get("last_pet_seen_at"),
            "last_pet_count": int(history.get("last_pet_count") or 0),
            "pet_types": list(history.get("pet_types") or []),
            "expected_samples": expected_samples,
            "observation_coverage": round(
                min(1.0, observed_samples / expected_samples) if expected_samples else 0.0,
                4,
            ),
            "source": "worker_memory",
        }

    def reset_camera(self, camera_id: int) -> None:
        camera_id = int(camera_id)
        with self._lock:
            self._observations.pop(camera_id, None)
            self._first_observed_at.pop(camera_id, None)
            self._last_observed_at.pop(camera_id, None)
            self._last_person_seen_at.pop(camera_id, None)

    def _prune(self, observations: Deque[tuple[float, str, bool]], now: float) -> None:
        cutoff = float(now) - self.window_seconds
        while observations and observations[0][0] < cutoff:
            observations.popleft()

    @staticmethod
    def _normalize_iso(value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return datetime.now(timezone.utc).isoformat()
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()

    @classmethod
    def _latest_iso(cls, *values: Any) -> str | None:
        parsed: list[tuple[datetime, str]] = []
        for value in values:
            text = str(value or "").strip()
            if not text:
                continue
            try:
                normalized = cls._normalize_iso(text)
                parsed.append((datetime.fromisoformat(normalized), normalized))
            except ValueError:
                continue
        return max(parsed, key=lambda item: item[0])[1] if parsed else None
