from __future__ import annotations

from pathlib import Path
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.upload_agent import UploadAgent, UploadRequestError


class Settings:
    upload_worker_enabled = True
    upload_worker_batch_size = 1
    upload_worker_interval_seconds = 1
    app_server_base_url = "https://example.invalid"
    device_api_token = "device-token"


class LockedStorage:
    def __init__(self) -> None:
        self.calls = 0

    def claim_next_upload_job(self, **_: object):
        self.calls += 1
        raise sqlite3.OperationalError("database is locked")


class TerminalStorage:
    def __init__(self) -> None:
        self.claimed = False
        self.completed: list[dict[str, object]] = []
        self.failed = 0

    def claim_next_upload_job(self, **_: object):
        if self.claimed:
            return None
        self.claimed = True
        return {
            "id": 9,
            "job_type": "event_state_upload",
            "attempt_count": 947,
            "claim_token": "claim-9",
        }

    def complete_upload_job(self, job_id: int, result: dict[str, object], *, claim_token: str):
        self.completed.append({"job_id": job_id, "result": result, "claim_token": claim_token})
        return {"id": job_id, "status": "completed"}

    def fail_upload_job(self, *_: object, **__: object):
        self.failed += 1
        return None


class TerminalUploadAgent(UploadAgent):
    def _process_job(self, job: dict[str, object]):
        raise UploadRequestError("HTTP 400 invalid recovery evidence", status_code=400)


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

    terminal_storage = TerminalStorage()
    terminal_agent = TerminalUploadAgent(
        storage=terminal_storage,
        settings=Settings(),
        device_id_resolver=lambda: "edge-test",
        token_resolver=lambda: "device-token",
    )
    terminal_result = terminal_agent.process_once()
    if terminal_result.get("completed") != 1 or terminal_result.get("failed") != 0:
        raise SystemExit(f"terminal request rejection was retried: {terminal_result}")
    if terminal_storage.failed or len(terminal_storage.completed) != 1:
        raise SystemExit(f"terminal request rejection did not retain one audit result: {terminal_storage.__dict__}")
    audit_result = terminal_storage.completed[0]["result"]
    if not isinstance(audit_result, dict) or audit_result.get("http_status") != 400 or not audit_result.get("terminal"):
        raise SystemExit(f"terminal request audit result is incomplete: {audit_result}")
    if UploadRequestError("HTTP 503", status_code=503).retryable is not True:
        raise SystemExit("transient server errors must remain retryable")

    print({
        "ok": True,
        "reason": result["reason"],
        "daemon_survives_lock": True,
        "terminal_http_rejection_retried": False,
        "transient_http_error_retryable": True,
    })


if __name__ == "__main__":
    main()
