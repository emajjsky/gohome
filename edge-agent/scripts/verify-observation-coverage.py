from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.observation_coverage import ObservationCoverageTracker


class Clock:
    def __init__(self, value: float) -> None:
        self.value = float(value)

    def __call__(self) -> float:
        return self.value


def main() -> None:
    clock = Clock(100.0)
    tracker = ObservationCoverageTracker(window_seconds=3600, monotonic_clock=clock)
    tracker.observe(
        24,
        observed_at="2026-07-28T08:00:00+08:00",
        person_present=False,
    )
    clock.value = 105.0
    tracker.observe(
        24,
        observed_at="2026-07-28T08:00:05+08:00",
        person_present=True,
    )
    status = tracker.status(
        24,
        expected_interval_seconds=5,
        historical={"last_person_seen_at": "2026-07-27T23:00:00+00:00", "pet_types": ["cat"]},
    )
    assert status["observed_samples"] == 2
    assert status["expected_samples"] == 2
    assert status["observation_coverage"] == 1.0
    assert status["last_person_seen_at"] == "2026-07-28T00:00:05+00:00"
    assert status["pet_types"] == ["cat"]

    clock.value = 110.0
    tracker.observe(
        24,
        observed_at="2026-07-28T08:00:10+08:00",
        person_present=False,
        valid=False,
    )
    degraded = tracker.status(24, expected_interval_seconds=5)
    assert degraded["observed_samples"] == 2
    assert degraded["expected_samples"] == 3
    assert degraded["observation_coverage"] == 0.6667

    tracker.reset_camera(24)
    reset = tracker.status(24, expected_interval_seconds=5)
    assert reset["observed_samples"] == 0
    assert reset["observation_coverage"] == 0.0
    print({"ok": True, "status": status, "degraded": degraded})


if __name__ == "__main__":
    main()
