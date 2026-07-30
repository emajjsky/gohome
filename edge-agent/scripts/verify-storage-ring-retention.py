from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.storage import Storage


def iso_before(*, hours: int = 0, days: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours, days=days)).isoformat()


def insert_runtime_chain(
    storage: Storage,
    snapshot_dir: Path,
    *,
    age_hours: int,
    cloud_sync_status: str,
    event_age_days: int | None = None,
) -> tuple[int, int, int, int]:
    captured_at = iso_before(hours=age_hours)
    event_time = iso_before(days=event_age_days) if event_age_days is not None else captured_at
    relative_path = f"camera-1/{abs(hash((age_hours, event_age_days, cloud_sync_status)))}.jpg"
    target = snapshot_dir / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"evidence")
    with storage.connect() as conn:
        snapshot_id = int(conn.execute(
            """
            INSERT INTO snapshots (
                camera_id, image_path, captured_at, width, height,
                brightness, motion_score, person_count, tags, analysis_json
            ) VALUES (1, ?, ?, 640, 360, 80, 0.2, 1, '[]', ?)
            """,
            (relative_path, captured_at, '{"poses":[{"keypoints":[1,2,3]}]}'),
        ).lastrowid)
        detection_id = int(conn.execute(
            """
            INSERT INTO detection_results (
                camera_id, snapshot_id, captured_at, person_count,
                objects_json, quality_flags_json, raw_confidence_summary_json,
                analysis_json, created_at
            ) VALUES (1, ?, ?, 1, '[]', '[]', '{}', ?, ?)
            """,
            (snapshot_id, captured_at, '{"large":"payload"}', captured_at),
        ).lastrowid)
        evaluation_id = int(conn.execute(
            """
            INSERT INTO rule_evaluations (
                camera_id, snapshot_id, detection_result_id, evaluated_at,
                matched_rules_json, explanation, state_json, candidates_json, created_at
            ) VALUES (1, ?, ?, ?, '[]', '', '{}', '[]', ?)
            """,
            (snapshot_id, detection_id, captured_at, captured_at),
        ).lastrowid)
        event_id = int(conn.execute(
            """
            INSERT INTO events (
                camera_id, detection_result_id, rule_evaluation_id, type, room,
                summary, level, snapshot_id, occurred_at, payload,
                cloud_sync_status, cloud_synced_at
            ) VALUES (1, ?, ?, 'fall_candidate', '客厅', '跌倒事件', 'critical', ?, ?, '{}', ?, ?)
            """,
            (
                detection_id,
                evaluation_id,
                snapshot_id,
                event_time,
                cloud_sync_status,
                captured_at if cloud_sync_status == "completed" else None,
            ),
        ).lastrowid)
    return event_id, snapshot_id, detection_id, evaluation_id


def verify_legacy_cloud_sync_migration(root: Path) -> None:
    storage = Storage(root / "legacy-agent.db")
    storage.init_schema()
    timestamp = iso_before(days=2)
    with storage.connect() as conn:
        conn.execute(
            """
            INSERT INTO cameras (
                id, name, room, stream_url, enabled, status, created_at, updated_at
            ) VALUES (1, '客厅', '客厅', 'rtsp://camera', 1, 'online', ?, ?)
            """,
            (timestamp, timestamp),
        )
        event_ids = []
        for summary in ("uploaded", "unfinished", "pending", "local-only"):
            event_ids.append(int(conn.execute(
                """
                INSERT INTO events (
                    camera_id, type, room, summary, level, occurred_at, payload
                ) VALUES (1, 'fall_candidate', '客厅', ?, 'critical', ?, '{}')
                """,
                (summary, timestamp),
            ).lastrowid))

        def insert_job(event_id: int, key: str, job_type: str, status: str) -> int:
            completed_at = timestamp if status == "completed" else None
            return int(conn.execute(
                """
                INSERT INTO upload_jobs (
                    job_type, object_type, status, priority, idempotency_key,
                    event_id, payload_json, created_at, updated_at, completed_at
                ) VALUES (?, 'event', ?, 10, ?, ?, '{}', ?, ?, ?)
                """,
                (job_type, status, key, event_id, timestamp, timestamp, completed_at),
            ).lastrowid)

        insert_job(event_ids[0], "uploaded-event", "event_upload", "completed")
        insert_job(event_ids[1], "unfinished-event", "event_upload", "completed")
        unfinished_media_job_id = insert_job(event_ids[1], "unfinished-media", "media_upload", "failed")
        insert_job(event_ids[2], "pending-event", "event_upload", "pending")
        conn.execute("ALTER TABLE events DROP COLUMN cloud_synced_at")
        conn.execute("ALTER TABLE events DROP COLUMN cloud_sync_status")

    storage.init_schema()
    with storage.connect() as conn:
        rows = conn.execute(
            "SELECT id, cloud_sync_status, cloud_synced_at FROM events ORDER BY id"
        ).fetchall()
        statuses = [str(row["cloud_sync_status"]) for row in rows]
        if statuses != ["completed", "pending", "pending", "local_only"]:
            raise SystemExit(f"legacy event migration misclassified rows: {statuses}")
        if not rows[0]["cloud_synced_at"]:
            raise SystemExit("completed historical event has no cloud sync timestamp")
        if any(row["cloud_synced_at"] for row in rows[1:]):
            raise SystemExit("non-completed historical event received a cloud sync timestamp")
        conn.execute(
            "UPDATE events SET cloud_sync_status = 'pending' WHERE id = ?",
            (event_ids[3],),
        )

    storage.complete_upload_job(unfinished_media_job_id, {"recovered": True})
    with storage.connect() as conn:
        recovered = conn.execute(
            "SELECT cloud_sync_status, cloud_synced_at FROM events WHERE id = ?",
            (event_ids[1],),
        ).fetchone()
        if recovered["cloud_sync_status"] != "completed" or not recovered["cloud_synced_at"]:
            raise SystemExit("recovered historical upload did not complete event cloud sync state")

    storage.init_schema()
    with storage.connect() as conn:
        status = conn.execute(
            "SELECT cloud_sync_status FROM events WHERE id = ?",
            (event_ids[3],),
        ).fetchone()[0]
        if status != "local_only":
            raise SystemExit("startup reconciliation did not clear an impossible pending event")


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        verify_legacy_cloud_sync_migration(root)
        storage = Storage(root / "agent.db")
        storage.init_schema()
        with storage.connect() as conn:
            timestamp = iso_before(hours=72)
            conn.execute(
                """
                INSERT INTO cameras (
                    id, name, room, stream_url, enabled, status,
                    created_at, updated_at
                ) VALUES (1, '客厅', '客厅', 'rtsp://camera', 1, 'online', ?, ?)
                """,
                (timestamp, timestamp),
            )

        synced = insert_runtime_chain(
            storage, root / "snapshots", age_hours=48, cloud_sync_status="completed"
        )
        pending = insert_runtime_chain(
            storage, root / "snapshots", age_hours=48, cloud_sync_status="pending"
        )
        expired = insert_runtime_chain(
            storage,
            root / "snapshots",
            age_hours=24 * 40,
            cloud_sync_status="completed",
            event_age_days=40,
        )
        local_only = insert_runtime_chain(
            storage,
            root / "snapshots",
            age_hours=24 * 40,
            cloud_sync_status="local_only",
            event_age_days=40,
        )

        result = storage.prune_runtime_history(
            snapshot_dir=root / "snapshots",
            retention_hours=6,
            event_evidence_retention_hours=24,
            local_event_retention_days=30,
            batch_size=100,
        )

        with storage.connect() as conn:
            synced_event = conn.execute("SELECT * FROM events WHERE id = ?", (synced[0],)).fetchone()
            pending_event = conn.execute("SELECT * FROM events WHERE id = ?", (pending[0],)).fetchone()
            expired_event = conn.execute("SELECT * FROM events WHERE id = ?", (expired[0],)).fetchone()
            local_only_event = conn.execute("SELECT * FROM events WHERE id = ?", (local_only[0],)).fetchone()
            if synced_event is None or any(
                synced_event[key] is not None
                for key in ("snapshot_id", "detection_result_id", "rule_evaluation_id", "candidate_id")
            ):
                raise SystemExit("synced event did not release heavyweight runtime links")
            if pending_event is None or pending_event["snapshot_id"] is None:
                raise SystemExit("unsent event evidence was recycled")
            if expired_event is not None:
                raise SystemExit("expired cloud-synced event was not recycled")
            if local_only_event is not None:
                raise SystemExit("expired local-only event was not recycled")
            if conn.execute("SELECT 1 FROM snapshots WHERE id = ?", (synced[1],)).fetchone() is not None:
                raise SystemExit("detached synced snapshot was not recycled")
            if conn.execute("SELECT 1 FROM snapshots WHERE id = ?", (pending[1],)).fetchone() is None:
                raise SystemExit("pending snapshot was removed")

        if result["deleted"].get("event_runtime_links", 0) < 1:
            raise SystemExit(f"cleanup did not report detached events: {result}")
        print("storage ring retention verification passed")


if __name__ == "__main__":
    main()
