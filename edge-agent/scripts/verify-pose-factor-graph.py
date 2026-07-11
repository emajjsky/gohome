from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.pose_factor_graph import PoseFactorGraphEngine


def frame(posture: str, bbox: list[float], *, normal_zone: bool = False, motion: float = 0.03) -> dict:
    pose = {
        "track_id": "c1-p1",
        "bbox": bbox,
        "confidence": 0.92,
        "posture": posture,
        "posture_confidence": 0.92,
        "posture_factors": {"body_aspect": (bbox[2] - bbox[0]) / (bbox[3] - bbox[1])},
        "normal_lying_zone": normal_zone,
        "scene_zone_id": "couch-1" if normal_zone else None,
        "scene_zone_label": "沙发" if normal_zone else None,
    }
    return {
        "image_width": 640,
        "image_height": 360,
        "motion_score": motion,
        "people": [],
        "poses": [pose],
    }


def main() -> None:
    engine = PoseFactorGraphEngine(prolonged_lying_seconds=180)
    engine.update(1, frame("standing", [250, 20, 340, 320]), monotonic_at=0.0)
    fall = frame("lying", [220, 220, 540, 350])
    result = engine.update(1, fall, monotonic_at=2.0)
    if not result["fast_fall_candidate"]:
        raise SystemExit(f"upright-to-floor transition must create a fast-fall factor candidate: {result}")
    track = result["fast_fall_track"] or {}
    if track.get("vertical_drop", 0) < 0.12 or track.get("normal_lying_zone"):
        raise SystemExit("fast-fall graph must preserve displacement and scene factors")

    prolonged = engine.update(1, frame("lying", [220, 220, 540, 350], motion=0.0), monotonic_at=183.0)
    if not prolonged["prolonged_floor_lying_candidate"]:
        raise SystemExit("continuous non-normal-zone lying must trigger after 180 seconds")

    engine.reset_camera(1)
    engine.update(1, frame("standing", [250, 20, 340, 320]), monotonic_at=0.0)
    suppressed = engine.update(1, frame("lying", [220, 220, 540, 350], normal_zone=True), monotonic_at=200.0)
    if suppressed["fast_fall_candidate"] or suppressed["prolonged_floor_lying_candidate"]:
        raise SystemExit("bed/couch lying must suppress both pose safety candidates")

    engine.reset_camera(1)
    engine.update(1, frame("lying", [220, 220, 540, 350], motion=0.0), monotonic_at=0.0)
    engine.update(1, frame("standing", [250, 20, 340, 320], motion=0.02), monotonic_at=181.0)
    recovered = engine.update(1, frame("standing", [252, 20, 342, 320], motion=0.01), monotonic_at=182.0)
    if recovered["prolonged_floor_lying_candidate"]:
        raise SystemExit("two upright recovery samples must close prolonged lying state")

    print(json.dumps({
        "ok": True,
        "fast_fall_score": track.get("fast_fall_score"),
        "prolonged_seconds": prolonged["prolonged_floor_lying_tracks"][0]["lying_duration_seconds"],
        "normal_zone_suppressed": True,
        "recovery_verified": True,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
