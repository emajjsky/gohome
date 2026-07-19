from __future__ import annotations

from pathlib import Path
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.upload_agent import UploadAgent


class Settings:
    upload_worker_enabled = True
    upload_worker_batch_size = 1
    upload_worker_interval_seconds = 1
    app_server_base_url = "https://example.invalid"
    device_api_token = "device-token"


class LockedStorage:
    def __init__(self) -> None:
        self.calls = 0

    def claim_next_upload_job(self):
        self.calls += 1
        raise sqlite3.OperationalError("database is locked")


def main() -> None:
    storage = LockedStorage()
    agent = UploadAgent(
        storage=storage,
        settings=Settings(),
        device_id_resolver=lambda: "edge-test",
        token_resolver=lambda: "device-token",
    )
    result = agent.process_once()
    if result.get("reason") != "database_locked" or storage.calls != 1:
        raise SystemExit(f"database lock was not converted to a retryable result: {result}")
    if agent.last_error != "upload_queue_busy: database is locked; retrying":
        raise SystemExit(f"upload lock diagnostic was not retained: {agent.last_error}")
    print({"ok": True, "reason": result["reason"], "daemon_survives_lock": True})


if __name__ == "__main__":
    main()
