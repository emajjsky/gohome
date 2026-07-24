from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.vision.temporal import TemporalObservationEngine
from app.worker import EdgeWorker


class Tracker:
    def latest(self, camera_id: int) -> dict:
        assert camera_id == 24
        return {
            "state": "tracked",
            "formal_evidence_eligible": False,
            "poses": [{
                "track_id": "c24-p1",
                "bbox": [190.0, 62.0, 300.0, 334.0],
                "tracking_state": "tracked",
                "formal_evidence_eligible": False,
            }],
        }


def analysis(bbox: list[float]) -> dict:
    return {
        "image_width": 640,
        "image_height": 360,
        "people": [{"bbox": bbox, "confidence": 0.91, "posture": "standing"}],
        "poses": [],
        "motion_score": 0.02,
        "fall_candidate": False,
        "fire_candidate": False,
    }


def main() -> None:
    worker = EdgeWorker(None, None, None, None)
    worker.continual_pose_tracker = Tracker()
    engine = TemporalObservationEngine(history_size=12, track_ttl_seconds=10)

    first = analysis([80.0, 50.0, 180.0, 330.0])
    engine.update(24, first, monotonic_at=1.0)
    track_id = str(first["people"][0]["track_id"])
    if track_id != "c24-p1":
        raise SystemExit(f"unexpected initial track id: {track_id}")

    moved = analysis([194.0, 65.0, 304.0, 336.0])
    worker._attach_continual_identity_hints(24, moved)
    if worker.continual_identity_bridge_count != 1:
        raise SystemExit("identity bridge did not record its accepted KLT match")
    if moved["people"][0].get("_continual_track_id_hint") != track_id:
        raise SystemExit(f"credible KLT continuation did not attach an identity hint: {moved}")
    engine.update(24, moved, monotonic_at=1.7)
    if moved["people"][0].get("track_id") != track_id:
        raise SystemExit(f"model anchor ignored the credible KLT identity bridge: {moved}")
    if "_continual_track_id_hint" in moved["people"][0]:
        raise SystemExit("internal identity hint leaked into persisted analysis")

    far = analysis([500.0, 30.0, 620.0, 340.0])
    worker._attach_continual_identity_hints(24, far)
    if far["people"][0].get("_continual_track_id_hint"):
        raise SystemExit("distant person inherited an unrelated KLT identity")

    print({
        "ok": True,
        "bridged_track_id": track_id,
        "klt_used_for_identity_only": True,
        "distant_replacement_rejected": True,
        "internal_hint_removed": True,
    })


if __name__ == "__main__":
    main()
