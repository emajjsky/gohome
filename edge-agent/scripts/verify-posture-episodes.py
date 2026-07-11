from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.storage import Storage
from app.vision.temporal import TemporalObservationEngine


def analysis(posture: str, confidence: float = 0.90) -> dict:
    pose = {
        "bbox": [100, 50, 220, 340],
        "confidence": 0.92,
        "posture": posture,
        "posture_confidence": confidence,
        "normal_lying_zone": False,
    }
    return {
        "image_width": 640,
        "image_height": 360,
        "people": [{"bbox": [95, 45, 225, 345], "confidence": 0.91}],
        "poses": [pose],
        "motion_score": 0.02,
    }


def persist(storage: Storage, camera_id: int, result: dict, snapshot_id: int | None = None) -> None:
    for closure in result.get("posture_episode_closures") or []:
        storage.close_posture_episode(
            camera_id=camera_id,
            track_id=closure["track_id"],
            posture=closure["posture"],
            ended_at=closure["ended_at"],
            reason=closure["reason"],
        )
    for episode in result.get("posture_episode_updates") or []:
        storage.upsert_posture_episode(
            **episode,
            snapshot_id=snapshot_id,
            payload={"test": True},
        )


def main() -> None:
    engine = TemporalObservationEngine(posture_min_duration_seconds=3, posture_min_samples=2, track_ttl_seconds=10)
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Storage(Path(tmpdir) / "agent.db")
        storage.init_schema()
        camera = storage.create_camera({"name": "客厅", "room": "客厅", "stream_url": "demo:posture", "enabled": True})
        camera_id = int(camera["id"])

        first = engine.update(camera_id, analysis("standing"), observed_at="2026-07-11T10:00:00+00:00", monotonic_at=0)
        second = engine.update(camera_id, analysis("standing"), observed_at="2026-07-11T10:00:02+00:00", monotonic_at=2)
        third = engine.update(camera_id, analysis("standing"), observed_at="2026-07-11T10:00:04+00:00", monotonic_at=4)
        if first["posture_episode_updates"] or second["posture_episode_updates"]:
            raise SystemExit("posture must not stabilize before duration threshold")
        persist(storage, camera_id, third)
        open_episodes = storage.list_posture_episodes(status="open")
        if len(open_episodes) != 1 or open_episodes[0]["posture"] != "standing":
            raise SystemExit(f"standing episode missing: {open_episodes}")

        for mono, timestamp in [(5, "2026-07-11T10:00:05+00:00"), (7, "2026-07-11T10:00:07+00:00")]:
            result = engine.update(camera_id, analysis("sitting"), observed_at=timestamp, monotonic_at=mono)
            if result["posture_episode_closures"]:
                raise SystemExit("brief posture jitter must not close active episode")
        switched = engine.update(camera_id, analysis("sitting"), observed_at="2026-07-11T10:00:09+00:00", monotonic_at=9)
        persist(storage, camera_id, switched)
        open_episodes = storage.list_posture_episodes(status="open")
        closed_episodes = storage.list_posture_episodes(status="closed")
        if len(open_episodes) != 1 or open_episodes[0]["posture"] != "sitting":
            raise SystemExit(f"sitting episode missing after stable switch: {open_episodes}")
        if len(closed_episodes) != 1 or closed_episodes[0]["posture"] != "standing":
            raise SystemExit(f"standing episode was not closed: {closed_episodes}")

        expired = engine.update(camera_id, {"image_width": 640, "image_height": 360, "people": [], "poses": []}, observed_at="2026-07-11T10:00:25+00:00", monotonic_at=25)
        persist(storage, camera_id, expired)
        if storage.list_posture_episodes(status="open"):
            raise SystemExit("expired track must close active posture episode")

        print(json.dumps({"ok": True, "closed": [(item["posture"], item["close_reason"]) for item in storage.list_posture_episodes(status="closed")]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
