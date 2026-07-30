from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.storage import Storage


def verify_legacy_claim_migration(root: Path) -> None:
    db_path = root / "legacy-agent.db"
    storage = Storage(db_path)
    storage.init_schema()
    job = storage.enqueue_upload_job(
        job_type="event_upload",
        object_type="event",
        idempotency_key="legacy-uploading-job",
    )
    with storage.connect() as conn:
        conn.execute(
            "UPDATE upload_jobs SET status = 'uploading', last_error = '' WHERE id = ?",
            (int(job["id"]),),
        )
        conn.execute("ALTER TABLE upload_jobs DROP COLUMN lease_expires_at")
        conn.execute("ALTER TABLE upload_jobs DROP COLUMN claimed_at")
        conn.execute("ALTER TABLE upload_jobs DROP COLUMN claim_token")

    storage.init_schema()
    with storage.connect() as conn:
        migrated = conn.execute(
            """
            SELECT status, last_error, next_attempt_at, claim_token, claimed_at, lease_expires_at
            FROM upload_jobs WHERE id = ?
            """,
            (int(job["id"]),),
        ).fetchone()
        assert migrated["status"] == "failed"
        assert migrated["last_error"] == "legacy_upload_claim_recovered"
        assert migrated["next_attempt_at"]
        assert migrated["claim_token"] == ""
        assert migrated["claimed_at"] is None
        assert migrated["lease_expires_at"] is None

    storage.init_schema()
    with storage.connect() as conn:
        status = conn.execute(
            "SELECT status FROM upload_jobs WHERE id = ?",
            (int(job["id"]),),
        ).fetchone()[0]
        assert status == "failed"


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        verify_legacy_claim_migration(root)
        db_path = root / "agent.db"
        storage = Storage(db_path)
        storage.init_schema()
        job = storage.enqueue_upload_job(
            job_type="activity_interval_upload",
            object_type="activity_interval",
            idempotency_key="lease-recovery-test",
            payload={"source_interval_id": "test-1"},
        )

        first_claim = storage.claim_next_upload_job(lease_seconds=30, worker_id="worker-a")
        assert first_claim is not None
        assert first_claim["id"] == job["id"]
        assert first_claim["status"] == "uploading"
        assert first_claim["attempt_count"] == 1
        assert str(first_claim["claim_token"]).startswith("worker-a:")
        assert first_claim["claimed_at"] and first_claim["lease_expires_at"]
        assert storage.claim_next_upload_job(lease_seconds=30, worker_id="worker-b") is None

        expired_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        with storage.connect() as conn:
            conn.execute(
                "UPDATE upload_jobs SET lease_expires_at = ? WHERE id = ?",
                (expired_at, int(job["id"])),
            )

        restarted_storage = Storage(db_path)
        second_claim = restarted_storage.claim_next_upload_job(lease_seconds=30, worker_id="worker-b")
        assert second_claim is not None
        assert second_claim["id"] == job["id"]
        assert second_claim["attempt_count"] == 2
        assert second_claim["claim_token"] != first_claim["claim_token"]
        assert second_claim["last_error"] == "upload_lease_expired; reclaimed"

        stale_completion = storage.complete_upload_job(
            int(job["id"]),
            {"stale": True},
            claim_token=str(first_claim["claim_token"]),
        )
        assert stale_completion is None
        completed = restarted_storage.complete_upload_job(
            int(job["id"]),
            {"ok": True},
            claim_token=str(second_claim["claim_token"]),
        )
        assert completed is not None
        assert completed["status"] == "completed"
        assert completed["claim_token"] == ""
        assert completed["lease_expires_at"] is None

        legacy = storage.enqueue_upload_job(
            job_type="media_upload",
            object_type="snapshot",
            idempotency_key="legacy-no-lease-test",
        )
        with storage.connect() as conn:
            conn.execute(
                "UPDATE upload_jobs SET status = 'uploading', claim_token = '', lease_expires_at = NULL WHERE id = ?",
                (int(legacy["id"]),),
            )
        assert restarted_storage.claim_next_upload_job(lease_seconds=30, worker_id="worker-c") is None

        print({
            "ok": True,
            "reclaimed_attempt_count": second_claim["attempt_count"],
            "stale_completion_rejected": True,
            "legacy_upload_left_for_audit": True,
        })


if __name__ == "__main__":
    main()
