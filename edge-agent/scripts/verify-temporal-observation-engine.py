from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.temporal import TemporalObservationEngine


def analysis(*people: dict) -> dict:
    return {
        "image_width": 640,
        "image_height": 360,
        "people": list(people),
        "poses": [],
        "motion_score": 0.02,
        "fall_candidate": False,
        "fire_candidate": False,
    }


def main() -> None:
    engine = TemporalObservationEngine(history_size=8, track_ttl_seconds=10)
    first = analysis({"bbox": [100, 60, 220, 330], "confidence": 0.91})
    first_result = engine.update(1, first, observed_at="2026-07-11T10:00:00+00:00", monotonic_at=1.0)
    track_id = first_result["current_track_ids"][0]

    second = analysis({"bbox": [108, 62, 228, 332], "confidence": 0.90})
    second_result = engine.update(1, second, observed_at="2026-07-11T10:00:01+00:00", monotonic_at=2.0)
    if second_result["current_track_ids"] != [track_id]:
        raise SystemExit("nearby detections must keep the same track id")
    if second["people"][0].get("track_id") != track_id:
        raise SystemExit("analysis person must be annotated with track id")

    third = analysis(
        {"bbox": [115, 64, 235, 334], "confidence": 0.89},
        {"bbox": [400, 80, 510, 338], "confidence": 0.87},
    )
    third_result = engine.update(1, third, observed_at="2026-07-11T10:00:02+00:00", monotonic_at=3.0)
    if len(set(third_result["current_track_ids"])) != 2 or track_id not in third_result["current_track_ids"]:
        raise SystemExit("second person must get a distinct stable track")

    for index in range(12):
        engine.update(1, analysis(), observed_at=f"2026-07-11T10:01:{index:02d}+00:00", monotonic_at=20.0 + index)
    history = engine.recent_history(1)
    if len(history) != 8:
        raise SystemExit(f"ring buffer must remain bounded, got {len(history)}")
    if engine.update(1, analysis(), monotonic_at=40.0)["active_tracks"]:
        raise SystemExit("expired tracks must be removed")

    engine.reset_camera(1)
    if engine.recent_history(1):
        raise SystemExit("camera reset must clear temporal history")

    print(json.dumps({"ok": True, "stable_track_id": track_id, "history_capacity": 8}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
