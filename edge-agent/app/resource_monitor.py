from __future__ import annotations

from pathlib import Path
import time
from typing import Any, Callable


class SystemResourceMonitor:
    """Read low-cost thermal state for inference budgeting on edge hardware."""

    version = "eacp-resource-v1"

    def __init__(
        self,
        *,
        temperature_path: str | Path = "/sys/class/thermal/thermal_zone0/temp",
        warm_temperature_c: float = 72.0,
        hot_temperature_c: float = 76.0,
        critical_temperature_c: float = 80.0,
        sample_interval_seconds: float = 2.0,
        monotonic_clock: Callable[[], float] | None = None,
        temperature_reader: Callable[[], float | None] | None = None,
    ) -> None:
        self.temperature_path = Path(temperature_path)
        self.warm_temperature_c = float(warm_temperature_c)
        self.hot_temperature_c = float(hot_temperature_c)
        self.critical_temperature_c = float(critical_temperature_c)
        self.sample_interval_seconds = max(0.25, float(sample_interval_seconds))
        self._clock = monotonic_clock or time.monotonic
        self._temperature_reader = temperature_reader
        self._cached: dict[str, Any] | None = None
        self._cached_at = 0.0

    def snapshot(self, *, now: float | None = None) -> dict[str, Any]:
        current = self._clock() if now is None else float(now)
        if self._cached is not None and current - self._cached_at < self.sample_interval_seconds:
            return dict(self._cached)
        temperature_c = self._read_temperature()
        result = {
            "schema_version": self.version,
            "available": temperature_c is not None,
            "temperature_c": None if temperature_c is None else round(temperature_c, 2),
            "thermal_state": self._thermal_state(temperature_c),
            "thresholds_c": {
                "warm": self.warm_temperature_c,
                "hot": self.hot_temperature_c,
                "critical": self.critical_temperature_c,
            },
        }
        self._cached = result
        self._cached_at = current
        return dict(result)

    def _read_temperature(self) -> float | None:
        if self._temperature_reader is not None:
            try:
                value = self._temperature_reader()
                return None if value is None else float(value)
            except (OSError, TypeError, ValueError):
                return None
        try:
            raw = self.temperature_path.read_text(encoding="ascii").strip()
            value = float(raw)
            return value / 1000.0 if value > 200.0 else value
        except (OSError, TypeError, ValueError):
            return None

    def _thermal_state(self, temperature_c: float | None) -> str:
        if temperature_c is None:
            return "unknown"
        if temperature_c >= self.critical_temperature_c:
            return "critical"
        if temperature_c >= self.hot_temperature_c:
            return "hot"
        if temperature_c >= self.warm_temperature_c:
            return "warm"
        return "normal"
