from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import ceil
from threading import Lock
from time import monotonic
from typing import Any, Callable, Dict


class PairingWindow:
    """Thread-safe, process-local authorization window for LAN device pairing."""

    def __init__(
        self,
        initial_seconds: int,
        *,
        monotonic_clock: Callable[[], float] = monotonic,
        wall_clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._monotonic_clock = monotonic_clock
        self._wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        self._lock = Lock()
        self._deadline = 0.0
        self._opened_at: datetime | None = None
        self._closes_at: datetime | None = None
        self.open(initial_seconds)

    def open(self, duration_seconds: int = 600) -> Dict[str, Any]:
        duration = max(60, min(int(duration_seconds), 3600))
        now_monotonic = self._monotonic_clock()
        now_wall = self._wall_clock()
        with self._lock:
            self._deadline = now_monotonic + duration
            self._opened_at = now_wall
            self._closes_at = now_wall + timedelta(seconds=duration)
        return self.status()

    def close(self) -> Dict[str, Any]:
        with self._lock:
            self._deadline = 0.0
            self._closes_at = self._wall_clock()
        return self.status()

    def is_open(self) -> bool:
        with self._lock:
            return self._deadline > self._monotonic_clock()

    def status(self) -> Dict[str, Any]:
        now = self._monotonic_clock()
        with self._lock:
            remaining = max(0, ceil(self._deadline - now))
            opened_at = self._opened_at
            closes_at = self._closes_at
        return {
            "open": remaining > 0,
            "remaining_seconds": remaining,
            "opened_at": opened_at.isoformat() if opened_at else None,
            "closes_at": closes_at.isoformat() if closes_at else None,
        }
