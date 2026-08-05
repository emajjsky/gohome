#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.pet_temporal import PetTemporalStabilizer


def detection(class_id: int, confidence: float, x: float = 20.0):
    raw_model_type = {15: "cat", 16: "dog"}[class_id]
    return {
        "class_id": class_id,
        "confidence": confidence,
        "bbox": [x, 30.0, x + 80.0, 130.0],
        "type": "pet",
        "label": "pet",
        "label_zh": "宠物",
        "species_status": "unverified",
        "raw_model_class_id": class_id,
        "raw_model_type": raw_model_type,
        "raw_model_label": raw_model_type,
        "raw_model_confidence": confidence,
    }


def main() -> int:
    stabilizer = PetTemporalStabilizer()

    first, first_status = stabilizer.update(
        1,
        [detection(15, 0.44), detection(16, 0.29, 21.0)],
        now=1.0,
    )
    assert first == []
    assert first_status["candidate_count"] == 2
    assert first_status["observation_count"] == 1

    confirmed, confirmed_status = stabilizer.update(1, [detection(15, 0.48, 23.0)], now=2.0)
    assert [item["class_id"] for item in confirmed] == [15]
    assert confirmed[0]["type"] == "pet"
    assert confirmed[0]["label_zh"] == "宠物"
    assert confirmed[0]["species_status"] == "unverified"
    assert confirmed[0]["raw_model_type"] == "cat"
    assert confirmed[0]["temporal_hits"] == 2
    assert confirmed_status["confirmed_count"] == 1
    camera_status = stabilizer.status(now=2.0)["cameras"][0]
    assert camera_status["camera_id"] == 1
    assert camera_status["confirmed_count"] == 1
    assert camera_status["tracks"] == [{
        "confirmed_class_id": 15,
        "confirmed_category": "cat",
        "confirmed_confidence": 0.462,
        "hits": 2,
        "last_seen_age_seconds": 0.0,
        "class_evidence": [
            {"class_id": 15, "category": "cat", "hits": 2, "confidence": 0.462},
            {"class_id": 16, "category": "dog", "hits": 1, "confidence": 0.29},
        ],
    }]

    uncertain = PetTemporalStabilizer()
    for index in range(5):
        low_confidence, low_status = uncertain.update(
            3,
            [detection(16, 0.31, 20.0 + index)],
            now=10.0 + index,
        )
        assert low_confidence == []
    assert low_status["confirmed_count"] == 0
    assert low_status["uncertain_count"] == 1
    assert uncertain.status()["uncertain_track_count"] == 1
    assert uncertain.status()["final_class_confidence"] == 0.40

    confused, _ = stabilizer.update(1, [detection(16, 0.55, 25.0)], now=3.0)
    assert [item["class_id"] for item in confused] == [15]

    other_camera, _ = stabilizer.update(2, [detection(16, 0.62)], now=3.0)
    assert other_camera == []
    other_confirmed, _ = stabilizer.update(2, [detection(16, 0.68, 22.0)], now=4.0)
    assert [item["class_id"] for item in other_confirmed] == [16]
    assert other_confirmed[0]["type"] == "pet"
    assert other_confirmed[0]["raw_model_type"] == "dog"

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
