from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.storage import Storage, now_iso


def old_iso(*, hours: int = 48) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def insert_snapshot(storage: Storage, camera_id: int, image_path: str, captured_at: str) -> int:
    with storage.connect() as conn:
        return int(conn.execute(
            """
            INSERT INTO snapshots (
                camera_id, image_path, captured_at, width, height,
                brightness, motion_score, person_count, tags, analysis_json
            ) VALUES (?, ?, ?, 640, 360, 80, 0, 0, '[]', '{}')
            """,
            (camera_id, image_path, captured_at),
        ).lastrowid)


def insert_media_asset(
    storage: Storage,
    *,
    family_id: int,
    device_id: str,
    source_snapshot_path: str,
    object_key: str,
    byte_size: int,
    retention_class: str,
    metadata: dict | None = None,
) -> int:
    timestamp = now_iso()
    with storage.connect() as conn:
        return int(conn.execute(
            """
            INSERT INTO media_assets (
                family_id, device_id, source_snapshot_path, object_key,
                byte_size, retention_class, retention_status, metadata_json,
                created_at, uploaded_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
            """,
            (
                family_id,
                device_id,
                source_snapshot_path,
                object_key,
                byte_size,
                retention_class,
                json.dumps(metadata or {}, ensure_ascii=False),
                timestamp,
                timestamp,
                timestamp,
            ),
        ).lastrowid)


def insert_lifecycle_family(storage: Storage) -> int:
    timestamp = now_iso()
    with storage.connect() as conn:
        user_id = int(conn.execute(
            """
            INSERT INTO users (
                email, password_salt, password_hash, display_name, created_at, updated_at
            ) VALUES ('lifecycle@gohome.test', 'fixture-salt', 'fixture-hash', 'Lifecycle', ?, ?)
            """,
            (timestamp, timestamp),
        ).lastrowid)
        family_id = int(conn.execute(
            """
            INSERT INTO families (name, created_by, created_at, updated_at)
            VALUES ('Lifecycle family', ?, ?, ?)
            """,
            (user_id, timestamp, timestamp),
        ).lastrowid)
        conn.execute(
            """
            INSERT INTO family_members (family_id, user_id, role, status, created_at, updated_at)
            VALUES (?, ?, 'owner', 'active', ?, ?)
            """,
            (family_id, user_id, timestamp, timestamp),
        )
    return family_id


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        data_dir = Path(temp_dir)
        snapshot_dir = data_dir / "snapshots"
        object_dir = data_dir / "object_storage"
        runtime_dir = data_dir / "runtime"
        storage = Storage(data_dir / "agent.db")
        storage.init_schema()
        with storage.connect() as conn:
            conn.execute("ALTER TABLE media_lifecycle_jobs RENAME TO media_lifecycle_jobs_current")
            conn.execute(
                """
                CREATE TABLE media_lifecycle_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_type TEXT NOT NULL,
                    target_id INTEGER NOT NULL,
                    snapshot_id INTEGER,
                    asset_id INTEGER,
                    provider TEXT NOT NULL DEFAULT 'localfs',
                    bucket TEXT NOT NULL DEFAULT 'local',
                    storage_path TEXT NOT NULL DEFAULT '',
                    object_key TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    next_attempt_at TEXT,
                    claim_token TEXT NOT NULL DEFAULT '',
                    claimed_at TEXT,
                    lease_expires_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    UNIQUE(target_type, target_id),
                    FOREIGN KEY(snapshot_id) REFERENCES snapshots(id),
                    FOREIGN KEY(asset_id) REFERENCES media_assets(id)
                )
                """
            )
            conn.execute("DROP TABLE media_lifecycle_jobs_current")
        storage.init_schema()
        with storage.connect() as conn:
            lifecycle_foreign_keys = {
                str(row["from"]): str(row["on_delete"]).upper()
                for row in conn.execute("PRAGMA foreign_key_list(media_lifecycle_jobs)").fetchall()
            }
        if lifecycle_foreign_keys != {"asset_id": "SET NULL", "snapshot_id": "SET NULL"}:
            raise SystemExit(f"media lifecycle foreign key migration failed: {lifecycle_foreign_keys}")
        family_id = insert_lifecycle_family(storage)
        camera = storage.create_camera({
            "name": "客厅",
            "room": "客厅",
            "stream_url": "demo:lifecycle",
            "enabled": True,
        })
        camera_id = int(camera["id"])

        failed_path = snapshot_dir / "camera-1" / "failed.jpg"
        failed_path.mkdir(parents=True)
        failed_snapshot_id = insert_snapshot(storage, camera_id, "camera-1/failed.jpg", old_iso())

        forced_path = snapshot_dir / "camera-1" / "forced.jpg"
        forced_path.parent.mkdir(parents=True, exist_ok=True)
        forced_path.write_bytes(b"forced")
        forced_snapshot_id = insert_snapshot(
            storage,
            camera_id,
            "camera-1/forced.jpg",
            datetime.now(timezone.utc).isoformat(),
        )

        latest_path = snapshot_dir / "camera-1" / "latest.jpg"
        latest_path.write_bytes(b"latest")
        latest_snapshot_id = insert_snapshot(
            storage,
            camera_id,
            "camera-1/latest.jpg",
            (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
        )

        event_asset_path = object_dir / f"family_{family_id}" / "event.jpg"
        event_asset_path.parent.mkdir(parents=True, exist_ok=True)
        event_asset_path.write_bytes(b"event-evidence")
        event_asset_id = insert_media_asset(
            storage,
            family_id=family_id,
            device_id="box-1",
            source_snapshot_path="event/evidence.jpg",
            object_key=f"family_{family_id}/event.jpg",
            retention_class="event_evidence",
            byte_size=event_asset_path.stat().st_size,
        )

        protected_asset_path = object_dir / f"family_{family_id}" / "memory.jpg"
        protected_asset_path.write_bytes(b"family-memory")
        protected_asset_id = insert_media_asset(
            storage,
            family_id=family_id,
            device_id="box-1",
            source_snapshot_path="memory/photo.jpg",
            object_key=f"family_{family_id}/memory.jpg",
            retention_class="user_upload",
            byte_size=protected_asset_path.stat().st_size,
            metadata={"purpose": "family_memory"},
        )
        with storage.connect() as conn:
            timestamp = old_iso(hours=24 * 10)
            conn.execute(
                "UPDATE media_assets SET created_at = ?, uploaded_at = ?, updated_at = ? WHERE id IN (?, ?)",
                (timestamp, timestamp, timestamp, event_asset_id, protected_asset_id),
            )

        first = storage.prune_runtime_history(
            snapshot_dir=snapshot_dir,
            object_storage_dir=object_dir,
            retention_hours=24,
            completed_upload_retention_days=7,
            batch_size=100,
            force_oldest=True,
        )
        if storage.latest_snapshot(camera_id)["id"] != latest_snapshot_id:
            raise SystemExit("critical retention removed the newest camera snapshot")
        if storage.get_snapshot_by_path("camera-1/forced.jpg") is not None or forced_path.exists():
            raise SystemExit("critical retention did not remove the oldest unprotected recent snapshot")
        if storage.get_snapshot_by_path("camera-1/failed.jpg") is None:
            raise SystemExit("failed physical deletion removed the snapshot database row")
        if first["media_lifecycle"]["failed"] < 1:
            raise SystemExit(f"failed deletion was not recorded: {first}")
        if event_asset_path.exists():
            raise SystemExit("expired event asset bytes were not deleted")
        deleted_asset = storage.get_media_asset(event_asset_id)
        if deleted_asset is None or deleted_asset.get("retention_status") != "deleted":
            raise SystemExit("expired event asset did not retain a deletion tombstone")
        if not protected_asset_path.exists():
            raise SystemExit("user-uploaded family media entered automatic retention")

        failed_path.rmdir()
        failed_path.write_bytes(b"retry")
        with storage.connect() as conn:
            conn.execute(
                """
                UPDATE media_lifecycle_jobs
                SET status = 'failed', next_attempt_at = ?, lease_expires_at = NULL
                WHERE target_type = 'snapshot' AND target_id = ?
                """,
                (old_iso(hours=1), failed_snapshot_id),
            )
        retried = storage.process_media_lifecycle_jobs(
            snapshot_dir=snapshot_dir,
            object_storage_dir=object_dir,
            limit=10,
        )
        if retried["completed_by_type"].get("snapshot") != 1:
            raise SystemExit(f"failed lifecycle job did not retry: {retried}")
        if storage.get_snapshot_by_path("camera-1/failed.jpg") is not None or failed_path.exists():
            raise SystemExit("retried snapshot deletion did not complete")

        runtime_file = runtime_dir / "logs" / "edge.log"
        runtime_file.parent.mkdir(parents=True, exist_ok=True)
        runtime_file.write_bytes(b"runtime")
        status = storage.runtime_storage_status(
            snapshot_dir,
            object_storage_dir=object_dir,
            runtime_dir=runtime_dir,
        )
        if status["object_storage_bytes"] < protected_asset_path.stat().st_size:
            raise SystemExit(f"object storage was omitted from capacity accounting: {status}")
        if status["runtime_files_bytes"] != runtime_file.stat().st_size:
            raise SystemExit(f"runtime files were omitted from capacity accounting: {status}")

        with storage.connect() as conn:
            dangling = conn.execute("PRAGMA foreign_key_check").fetchall()
        if dangling:
            raise SystemExit(f"media lifecycle left dangling references: {dangling}")

        archived = storage.create_camera({
            "name": "待归档摄像头",
            "room": "书房",
            "stream_url": "rtsp://camera.local/archive",
            "username": "camera-user",
            "password": "camera-password",
            "enabled": True,
        })
        archived_id = int(archived["id"])
        insert_snapshot(storage, archived_id, "archive/evidence.jpg", old_iso())
        if not storage.delete_camera(archived_id):
            raise SystemExit("camera archive did not report success")
        if storage.get_camera(archived_id) is not None:
            raise SystemExit("archived camera remained in active camera reads")
        with storage.connect() as conn:
            archived_row = conn.execute("SELECT * FROM cameras WHERE id = ?", (archived_id,)).fetchone()
            archived_fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if (
            archived_row is None
            or archived_row["deleted_at"] is None
            or archived_row["username"] is not None
            or archived_row["password"] is not None
            or archived_row["stream_url"] != f"archived:{archived_id}"
        ):
            raise SystemExit("camera archive retained credentials or lost its history anchor")
        if archived_fk:
            raise SystemExit(f"camera archive broke foreign keys: {archived_fk}")

        legacy = storage.create_camera({
            "name": "历史缺失摄像头",
            "room": "卧室",
            "stream_url": "rtsp://camera.local/legacy",
            "enabled": True,
        })
        legacy_id = int(legacy["id"])
        insert_snapshot(storage, legacy_id, "legacy/evidence.jpg", old_iso())
        raw = sqlite3.connect(storage.db_path)
        try:
            raw.execute("PRAGMA foreign_keys = OFF")
            raw.execute("DELETE FROM cameras WHERE id = ?", (legacy_id,))
            raw.commit()
        finally:
            raw.close()
        storage.init_schema()
        with storage.connect() as conn:
            restored = conn.execute("SELECT * FROM cameras WHERE id = ?", (legacy_id,)).fetchone()
            restored_fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        if restored is None or restored["deleted_at"] is None or restored["stream_url"] != f"archived:{legacy_id}":
            raise SystemExit("legacy camera reference was not restored as a credential-free archive")
        if restored_fk:
            raise SystemExit(f"legacy camera repair left foreign key violations: {restored_fk}")
        print({
            "ok": True,
            "forced_snapshot_id": forced_snapshot_id,
            "latest_snapshot_id": latest_snapshot_id,
            "retried_snapshot_id": failed_snapshot_id,
            "protected_asset_id": protected_asset_id,
            "archived_camera_id": archived_id,
            "restored_camera_id": legacy_id,
        })


if __name__ == "__main__":
    main()
