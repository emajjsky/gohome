from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.storage import Storage


def analysis() -> dict:
    return {
        "brightness": 100.0,
        "contrast": 20.0,
        "motion_score": 0.0,
        "person_count": 0,
        "tags": [],
    }


def create_chain(storage: Storage, camera_id: int, image_path: str) -> tuple[dict, dict, dict]:
    snapshot = storage.create_snapshot(
        camera_id=camera_id,
        image_path=image_path,
        width=320,
        height=240,
        brightness=100.0,
        motion_score=0.0,
        tags=[],
        person_count=0,
        analysis=analysis(),
    )
    detection = storage.create_detection_result(
        camera_id=camera_id,
        snapshot_id=int(snapshot["id"]),
        captured_at=snapshot["captured_at"],
        width=320,
        height=240,
        analysis=analysis(),
    )
    evaluation = storage.create_rule_evaluation(
        camera_id=camera_id,
        snapshot_id=int(snapshot["id"]),
        detection_result_id=int(detection["id"]),
        evaluation={
            "camera_id": camera_id,
            "snapshot_id": int(snapshot["id"]),
            "evaluated_at": snapshot["captured_at"],
            "state": {},
            "candidates": [],
        },
        rule_set_version="test",
    )
    return snapshot, detection, evaluation


def main() -> None:
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        snapshot_dir = root / "snapshots"
        storage = Storage(root / "agent.db")
        storage.init_schema()
        camera = storage.create_camera({
            "name": "测试摄像头",
            "room": "客厅",
            "stream_url": "demo:test",
            "enabled": True,
        })

        old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        routine = create_chain(storage, int(camera["id"]), "camera_1/routine.jpg")
        protected = create_chain(storage, int(camera["id"]), "camera_1/event.jpg")
        recent = create_chain(storage, int(camera["id"]), "camera_1/recent.jpg")
        for name in ("routine.jpg", "event.jpg", "recent.jpg"):
            path = snapshot_dir / "camera_1" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"test")

        with storage.connect() as conn:
            for snapshot, detection, evaluation in (routine, protected):
                conn.execute("UPDATE snapshots SET captured_at = ? WHERE id = ?", (old, snapshot["id"]))
                conn.execute("UPDATE detection_results SET captured_at = ?, created_at = ? WHERE id = ?", (
                    old, old, detection["id"],
                ))
                conn.execute("UPDATE rule_evaluations SET evaluated_at = ?, created_at = ? WHERE id = ?", (
                    old, old, evaluation["id"],
                ))

        event = storage.create_event(
            event_type="fall_candidate",
            summary="保留事件证据",
            level="critical",
            camera_id=int(camera["id"]),
            snapshot_id=int(protected[0]["id"]),
            detection_result_id=int(protected[1]["id"]),
            rule_evaluation_id=int(protected[2]["id"]),
            occurred_at=old,
        )
        assert event["snapshot_id"] == protected[0]["id"]

        storage.upsert_presence_session(
            camera_id=int(camera["id"]),
            observed_at=old,
            person_count=1,
            snapshot_id=int(routine[0]["id"]),
        )
        storage.close_presence_session(camera_id=int(camera["id"]), ended_at=old)
        storage.upsert_posture_episode(
            camera_id=int(camera["id"]),
            track_id="expired-track",
            posture="standing",
            started_at=old,
            confirmed_at=old,
            last_seen_at=old,
            sample_count=2,
            mean_confidence=0.8,
            max_confidence=0.9,
            snapshot_id=int(routine[0]["id"]),
        )
        storage.close_posture_episode(
            camera_id=int(camera["id"]),
            track_id="expired-track",
            ended_at=old,
        )
        with storage.connect() as conn:
            conn.execute("UPDATE presence_sessions SET created_at = ?, updated_at = ?", (old, old))
            conn.execute("UPDATE posture_episodes SET created_at = ?, updated_at = ?", (old, old))

        result = storage.prune_runtime_history(
            snapshot_dir=snapshot_dir,
            retention_hours=24,
            batch_size=100,
        )
        assert result["deleted"]["snapshots"] == 1, result
        assert result["deleted"]["presence_sessions"] == 1, result
        assert result["deleted"]["posture_episodes"] == 1, result
        assert not (snapshot_dir / "camera_1/routine.jpg").exists()
        assert (snapshot_dir / "camera_1/event.jpg").exists()
        assert (snapshot_dir / "camera_1/recent.jpg").exists()
        assert storage.get_event(int(event["id"])) is not None
        assert storage.latest_snapshot(int(camera["id"]))["id"] == recent[0]["id"]

        with storage.connect() as conn:
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert journal_mode == "wal"
        try:
            conn.execute("SELECT 1")
            raise AssertionError("connection remained open after context exit")
        except sqlite3.ProgrammingError:
            pass

        print("runtime retention verification passed")


if __name__ == "__main__":
    main()
