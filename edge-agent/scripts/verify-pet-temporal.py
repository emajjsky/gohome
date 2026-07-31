#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.pet_temporal import PetTemporalStabilizer


def detection(class_id: int, confidence: float, x: float = 20.0):
    return {
        "class_id": class_id,
        "confidence": confidence,
        "bbox": [x, 30.0, x + 80.0, 130.0],
    }


def main() -> int:
    stabilizer = PetTemporalStabilizer()

    first, first_status = stabilizer.update(
        1,
        [detection(15, 0.36), detection(16, 0.29, 21.0)],
        now=1.0,
    )
    assert first == []
    assert first_status["candidate_count"] == 2
    assert first_status["observation_count"] == 1

    confirmed, confirmed_status = stabilizer.update(1, [detection(15, 0.42, 23.0)], now=2.0)
    assert [item["class_id"] for item in confirmed] == [15]
    assert confirmed[0]["temporal_hits"] == 2
    assert confirmed_status["confirmed_count"] == 1

    confused, _ = stabilizer.update(1, [detection(16, 0.55, 25.0)], now=3.0)
    assert [item["class_id"] for item in confused] == [15]

    other_camera, _ = stabilizer.update(2, [detection(16, 0.62)], now=3.0)
    assert other_camera == []
    other_confirmed, _ = stabilizer.update(2, [detection(16, 0.68, 22.0)], now=4.0)
    assert [item["class_id"] for item in other_confirmed] == [16]

    held, _ = stabilizer.update(1, [], now=4.5)
    assert [item["class_id"] for item in held] == [15]
    assert held[0]["temporal_cached"] is True
    expired, expired_status = stabilizer.update(1, [], now=6.0)
    assert expired == []
    assert expired_status["track_count"] == 0

    stabilizer.reset_camera(2)
    assert stabilizer.status()["camera_count"] == 1
    print("pet temporal stabilizer verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
