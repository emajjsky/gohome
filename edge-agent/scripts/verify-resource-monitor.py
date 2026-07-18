from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.resource_monitor import SystemResourceMonitor


class Clock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


def main() -> None:
    clock = Clock()
    values = iter([71.0, 74.0, 77.0, 81.0, None])
    monitor = SystemResourceMonitor(
        monotonic_clock=clock,
        temperature_reader=lambda: next(values),
        sample_interval_seconds=2.0,
        warm_temperature_c=72.0,
        hot_temperature_c=76.0,
        critical_temperature_c=80.0,
    )

    normal = monitor.snapshot()
    if normal["thermal_state"] != "normal" or normal["temperature_c"] != 71.0:
        raise SystemExit(f"normal thermal state is incorrect: {normal}")
    clock.value = 101.0
    if monitor.snapshot() != normal:
        raise SystemExit("thermal sample cache was not reused")

    states = []
    for expected in ["warm", "hot", "critical", "unknown"]:
        clock.value += 2.1
        sample = monitor.snapshot()
        states.append(sample["thermal_state"])
        if sample["thermal_state"] != expected:
            raise SystemExit(f"expected {expected}, got {sample}")

    print({"ok": True, "states": ["normal", *states], "cached": True})


if __name__ == "__main__":
    main()
