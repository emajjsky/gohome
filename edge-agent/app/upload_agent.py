from __future__ import annotations

from pathlib import Path
from threading import Event, Thread
from typing import Any, Callable, Dict
from http.client import HTTPConnection, HTTPSConnection
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
import json
import secrets
import sqlite3
import time


TERMINAL_UPLOAD_HTTP_STATUS_CODES = {400, 405, 410, 413, 415, 422}


class UploadRequestError(RuntimeError):
    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = int(status_code)

    @property
    def retryable(self) -> bool:
        return self.status_code not in TERMINAL_UPLOAD_HTTP_STATUS_CODES


class UploadAgent:
    def __init__(
        self,
        *,
        storage: Any,
        settings: Any,
        device_id_resolver: Callable[[], str],
        token_resolver: Callable[[], str],
        remote_camera_id_resolver: Callable[[int], Any] | None = None,
    ) -> None:
        self.storage = storage
        self.settings = settings
        self.device_id_resolver = device_id_resolver
        self.token_resolver = token_resolver
        self.remote_camera_id_resolver = remote_camera_id_resolver or (lambda camera_id: camera_id)
        self._worker_id = f"upload-agent-{secrets.token_hex(6)}"
        self._stop = Event()
        self._wake = Event()
        self._thread: Thread | None = None
        self.last_loop_started_at: str | None = None
        self.last_error = ""
        self.last_uploaded_at: str | None = None
        self.last_result: Dict[str, Any] = {}

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._wake.clear()
        self._thread = Thread(target=self._run, name="gohome-upload-agent", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5)

    def wake(self) -> None:
        self._wake.set()

    def status(self) -> Dict[str, Any]:
        configured, reason = self._configured()
        return {
            "enabled": bool(getattr(self.settings, "upload_worker_enabled", True)),
            "running": self.is_running,
            "configured": configured,
            "reason": reason,
            "app_server_base_url": getattr(self.settings, "app_server_base_url", ""),
            "last_loop_started_at": self.last_loop_started_at,
            "last_uploaded_at": self.last_uploaded_at,
            "last_error": self.last_error,
            "last_result": self.last_result,
        }

    def vision_verification_status(self, *, limit: int = 12) -> Dict[str, Any]:
        configured, reason = self._configured()
        if not configured:
            return {
                "ok": False,
                "configured": False,
                "reason": reason,
                "records": [],
            }
        return self._request_json(
            "GET",
            f"/api/v1/device/vision-verifications?{urlencode({'limit': max(1, min(int(limit), 50))})}",
        )

    def event_log_status(self, *, limit: int = 80) -> Dict[str, Any]:
        configured, reason = self._configured()
        if not configured:
            return {
                "ok": False,
                "configured": False,
                "reason": reason,
                "records": [],
            }
        return self._request_json(
            "GET",
            f"/api/v1/device/event-log?{urlencode({'limit': max(1, min(int(limit), 200))})}",
        )

    def submit_event_feedback(self, edge_event_id: int | str, *, resolution: str) -> Dict[str, Any]:
        configured, reason = self._configured()
        if not configured:
            raise RuntimeError(reason)
        if resolution != "false_positive":
            raise ValueError("only false_positive feedback is supported")
        return self._request_json(
            "POST",
            f"/api/v1/device/events/{edge_event_id}/feedback",
            json_body={"resolution": resolution},
        )

    def process_once(self, *, max_jobs: int | None = None) -> Dict[str, Any]:
        configured, reason = self._configured()
        if not configured:
            return {"ok": False, "processed": 0, "reason": reason}
        limit = max(1, int(max_jobs or getattr(self.settings, "upload_worker_batch_size", 4)))
        processed = 0
        completed = 0
        failed = 0
        for _ in range(limit):
            try:
                job = self.storage.claim_next_upload_job(
                    lease_seconds=max(30, int(getattr(self.settings, "upload_job_lease_seconds", 120))),
                    worker_id=self._worker_id,
                )
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
                self.last_error = "upload_queue_busy: database is locked; retrying"
                return {
                    "ok": False,
                    "processed": processed,
                    "completed": completed,
                    "failed": failed,
                    "reason": "database_locked",
                }
            if job is None:
                break
            processed += 1
            try:
                result = self._process_job(job)
            except UploadRequestError as exc:
                if not exc.retryable:
                    result = {
                        "uploaded": False,
                        "terminal": True,
                        "reason": "request_rejected",
                        "http_status": exc.status_code,
                        "error": str(exc)[:1000],
                    }
                    persisted = self.storage.complete_upload_job(
                        int(job["id"]),
                        result,
                        claim_token=str(job.get("claim_token") or ""),
                    )
                    if persisted is None:
                        failed += 1
                        self.last_error = "upload_job_lease_lost"
                        continue
                    completed += 1
                    self.last_error = ""
                    self.last_result = {
                        "job_id": int(job["id"]),
                        "job_type": job.get("job_type"),
                        "result": result,
                    }
                    continue
                failed += 1
                retry_after = self._retry_delay_seconds(int(job.get("attempt_count") or 1))
                self.storage.fail_upload_job(
                    int(job["id"]),
                    str(exc),
                    retry_after_seconds=retry_after,
                    claim_token=str(job.get("claim_token") or ""),
                )
                self.last_error = str(exc)
                continue
            except Exception as exc:
                failed += 1
                retry_after = self._retry_delay_seconds(int(job.get("attempt_count") or 1))
                self.storage.fail_upload_job(
                    int(job["id"]),
                    str(exc),
                    retry_after_seconds=retry_after,
                    claim_token=str(job.get("claim_token") or ""),
                )
                self.last_error = str(exc)
                continue
            completed += 1
            persisted = self.storage.complete_upload_job(
                int(job["id"]),
                result,
                claim_token=str(job.get("claim_token") or ""),
            )
            if persisted is None:
                failed += 1
                completed -= 1
                self.last_error = "upload_job_lease_lost"
                continue
            self.last_error = ""
            self.last_uploaded_at = self._utc_iso()
            self.last_result = {
                "job_id": int(job["id"]),
                "job_type": job.get("job_type"),
                "result": result,
            }
        return {"ok": failed == 0, "processed": processed, "completed": completed, "failed": failed}

    def _run(self) -> None:
        while not self._stop.is_set():
            self.last_loop_started_at = self._utc_iso()
            if bool(getattr(self.settings, "upload_worker_enabled", True)):
                try:
                    self.process_once()
                except Exception as exc:
                    # A transient storage or network failure must not kill the
                    # daemon thread; the next interval retries the queue.
                    self.last_error = str(exc)
                    self.last_result = {"ok": False, "error": str(exc)}
            interval = max(1.0, float(getattr(self.settings, "upload_worker_interval_seconds", 5)))
            self._wake.wait(interval)
            self._wake.clear()

    def _configured(self) -> tuple[bool, str]:
        if not bool(getattr(self.settings, "upload_worker_enabled", True)):
            return False, "upload_worker_disabled"
        if not self._base_url():
            return False, "app_server_base_url_missing"
        if not self._device_token():
            return False, "device_token_missing"
        return True, "ready"

    def _process_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        job_type = str(job.get("job_type") or "")
        if job_type == "event_evidence_finalize":
            return self._finalize_event_evidence(job)
        if job_type == "media_upload":
            return self._upload_media(job)
        if job_type == "event_upload":
            return self._upload_event(job)
        if job_type == "event_state_upload":
            return self._upload_event_state(job)
        if job_type == "activity_interval_upload":
            return self._upload_activity_interval(job)
        raise ValueError(f"Unsupported upload job type: {job_type}")

    def _finalize_event_evidence(self, job: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(job.get("payload") or {})
        event_id = int(payload.get("event_id") or job.get("event_id") or 0)
        if not event_id:
            raise ValueError("event evidence finalization job has no event_id")
        event = self.storage.finalize_event_evidence(
            event_id,
            settle_seconds=float(payload.get("settle_seconds") or 0.8),
            max_wait_seconds=float(payload.get("max_wait_seconds") or 2.5),
        )
        queued = self.storage.enqueue_event_upload_jobs(event)
        finalization = event.get("payload", {}).get("evidence_finalization") or {}
        return {
            "finalized": True,
            "target": "event_evidence",
            "event_id": event_id,
            "reason": str(finalization.get("reason") or ""),
            "selected_snapshot_id": finalization.get("selected_snapshot_id"),
            "queued_job_ids": [int(item["id"]) for item in queued],
        }

    def _upload_media(self, job: Dict[str, Any]) -> Dict[str, Any]:
        payload = job.get("payload") or {}
        snapshot_path = str(payload.get("snapshot_path") or job.get("snapshot_path") or "").strip().lstrip("/")
        if not snapshot_path:
            raise ValueError("media upload job has no snapshot_path")
        source = (Path(getattr(self.settings, "snapshot_dir")) / snapshot_path).resolve()
        snapshot_root = Path(getattr(self.settings, "snapshot_dir")).resolve()
        try:
            source.relative_to(snapshot_root)
        except ValueError as exc:
            raise ValueError("snapshot_path escapes snapshot directory") from exc
        if not source.is_file():
            raise FileNotFoundError(f"snapshot file not found: {snapshot_path}")
        params = {
            "file_name": source.name,
            "snapshot_path": snapshot_path,
            "content_type": str(payload.get("content_type") or "image/jpeg"),
            "idempotency_key": str(job.get("idempotency_key") or f"media:{int(job['id'])}"),
        }
        camera_id, local_camera_id = self._camera_ids(job, payload)
        if camera_id:
            params["camera_id"] = str(camera_id)
        if local_camera_id:
            params["local_camera_id"] = str(local_camera_id)
        if payload.get("event_id"):
            params["edge_event_id"] = str(payload["event_id"])
        if payload.get("captured_at"):
            params["captured_at"] = str(payload["captured_at"])
        if payload.get("purpose"):
            params["purpose"] = str(payload["purpose"])
        if payload.get("evidence_frame_role"):
            params["evidence_frame_role"] = str(payload["evidence_frame_role"])
        response = self._request_file_json(
            "POST",
            f"/api/v1/device/media-assets/upload?{urlencode(params)}",
            source=source,
            content_type=str(payload.get("content_type") or "image/jpeg"),
        )
        return {
            "uploaded": True,
            "target": "app_server_media",
            "snapshot_path": snapshot_path,
            "asset": response.get("asset") or response,
        }

    def _upload_event(self, job: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(job.get("payload") or {})
        event_id = int(payload.get("event_id") or job.get("event_id") or 0)
        camera_id, local_camera_id = self._camera_ids(job, payload)
        all_media_jobs = self.storage.upload_jobs_for_event(event_id=event_id, job_type="media_upload") if event_id else []
        incomplete_media_jobs = [item for item in all_media_jobs if item.get("status") != "completed"]
        if incomplete_media_jobs:
            raise RuntimeError(
                "event evidence uploads are incomplete: "
                + ",".join(f"{item.get('id')}:{item.get('status')}" for item in incomplete_media_jobs)
            )
        media_jobs = all_media_jobs
        primary_job = next(
            (
                item for item in media_jobs
                if str(item.get("payload", {}).get("evidence_frame_role") or "") == "current"
            ),
            media_jobs[-1] if media_jobs else None,
        )
        media_result = (primary_job or {}).get("payload", {}).get("upload_result") if primary_job else None
        evidence_media_assets = []
        for media_job in media_jobs:
            media_payload = media_job.get("payload") or {}
            upload_result = media_payload.get("upload_result") or {}
            asset = upload_result.get("asset") if isinstance(upload_result, dict) else None
            if not isinstance(asset, dict) or not asset.get("id"):
                continue
            evidence_media_assets.append({
                "asset": asset,
                "role": str(media_payload.get("evidence_frame_role") or "evidence"),
                "captured_at": str(media_payload.get("captured_at") or ""),
                "snapshot_id": media_payload.get("snapshot_id"),
                "postures": media_payload.get("postures") if isinstance(media_payload.get("postures"), list) else [],
            })
        event_payload = dict(payload.get("payload") or {})
        event_payload["edge_upload"] = {
            "job_id": int(job["id"]),
            "edge_event_id": event_id or None,
            "edge_device_id": self.device_id_resolver(),
            "local_camera_id": local_camera_id,
            "app_camera_id": camera_id,
        }
        if media_result:
            event_payload["media_upload_result"] = media_result
        if evidence_media_assets:
            event_payload["evidence_media_assets"] = evidence_media_assets
        request_payload = {
            "idempotency_key": str(job.get("idempotency_key") or f"event:{event_id}"),
            "event_type": str(payload.get("event_type") or job.get("event_type") or "event"),
            "summary": str(payload.get("summary") or job.get("event_summary") or "回家事件"),
            "level": str(payload.get("level") or job.get("event_level") or "warning"),
            "room": str(payload.get("room") or ""),
            "camera_id": camera_id,
            "snapshot_path": str(payload.get("snapshot_path") or job.get("snapshot_path") or ""),
            "occurred_at": str(payload.get("occurred_at") or ""),
            "payload": event_payload,
        }
        response = self._request_json(
            "POST",
            str(payload.get("endpoint") or "/api/v1/device/events"),
            json_body=request_payload,
        )
        return {
            "uploaded": True,
            "target": "app_server_event",
            "event": response.get("event") or response,
            "media_asset": response.get("media_asset") or (media_result or {}).get("asset"),
        }

    def _upload_event_state(self, job: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(job.get("payload") or {})
        event_id = int(payload.get("event_id") or job.get("event_id") or 0)
        if not event_id:
            raise ValueError("event state upload has no event_id")
        response = self._request_json(
            "POST",
            f"/api/v1/device/events/{event_id}/state",
            json_body={
                "state": str(payload.get("state") or ""),
                "resolution": str(payload.get("resolution") or ""),
                "observed_at": str(payload.get("observed_at") or ""),
                "evidence": payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {},
            },
        )
        return {
            "uploaded": True,
            "target": "app_server_event_state",
            "event": response.get("event") or response,
        }

    def _upload_activity_interval(self, job: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(job.get("payload") or {})
        local_camera_id = payload.get("local_camera_id") or job.get("camera_id")
        remote_camera_id = self.remote_camera_id_resolver(int(local_camera_id)) if local_camera_id else None
        interval = {
            "source_interval_id": str(payload.get("source_interval_id") or ""),
            "camera_id": str(remote_camera_id or local_camera_id or ""),
            "room": str(payload.get("room") or ""),
            "started_at": str(payload.get("started_at") or ""),
            "ended_at": str(payload.get("ended_at") or ""),
            "person_count_max": max(1, int(payload.get("person_count_max") or 1)),
            "postures": payload.get("postures") if isinstance(payload.get("postures"), list) else [],
            "confidence": payload.get("confidence"),
            "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        }
        if not interval["source_interval_id"] or not interval["started_at"] or not interval["ended_at"]:
            raise ValueError("activity interval upload is incomplete")
        response = self._request_json(
            "POST",
            "/api/v1/device/activity-intervals",
            json_body={
                "device_id": self.device_id_resolver(),
                "intervals": [interval],
            },
        )
        return {
            "uploaded": True,
            "target": "app_server_activity_intervals",
            "source_interval_id": interval["source_interval_id"],
            "accepted": int(response.get("accepted") or 0),
            "inserted": int(response.get("inserted") or 0),
            "skipped": int(response.get("skipped") or 0),
            "reason": str(response.get("reason") or ""),
        }

    def _camera_ids(self, job: Dict[str, Any], payload: Dict[str, Any]) -> tuple[Any, Any]:
        local_camera_id = payload.get("local_camera_id") or job.get("camera_id") or payload.get("camera_id")
        remote_camera_id = payload.get("app_camera_id") or payload.get("remote_camera_id")
        if remote_camera_id in (None, "") and local_camera_id not in (None, ""):
            remote_camera_id = self.remote_camera_id_resolver(int(local_camera_id))
        if remote_camera_id in (None, ""):
            remote_camera_id = payload.get("camera_id") or job.get("camera_id")
        return remote_camera_id, local_camera_id

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: Dict[str, Any] | None = None,
        body: bytes | None = None,
        content_type: str = "application/json",
    ) -> Dict[str, Any]:
        normalized_path = path if path.startswith("/") else f"/{path}"
        url = f"{self._base_url()}{normalized_path}"
        request_body = body
        if json_body is not None:
            request_body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            content_type = "application/json"
        request = Request(
            url,
            data=request_body,
            method=method.upper(),
            headers={
                "Authorization": f"Bearer {self._device_token()}",
                "Content-Type": content_type,
                "Accept": "application/json",
            },
        )
        timeout = max(2.0, float(getattr(self.settings, "upload_request_timeout_seconds", 12)))
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise UploadRequestError(
                f"{method} {url} failed: HTTP {exc.code} {detail}",
                status_code=int(exc.code),
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"{method} {url} failed: {exc.reason}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{method} {url} returned non-json response") from exc

    def _request_file_json(
        self,
        method: str,
        path: str,
        *,
        source: Path,
        content_type: str,
    ) -> Dict[str, Any]:
        normalized_path = path if path.startswith("/") else f"/{path}"
        url = f"{self._base_url()}{normalized_path}"
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise RuntimeError(f"Invalid upload URL: {url}")
        connection_type = HTTPSConnection if parsed.scheme == "https" else HTTPConnection
        timeout = max(2.0, float(getattr(self.settings, "upload_request_timeout_seconds", 12)))
        connection = connection_type(parsed.hostname, parsed.port, timeout=timeout)
        target = parsed.path or "/"
        if parsed.query:
            target = f"{target}?{parsed.query}"
        try:
            with source.open("rb") as handle:
                connection.request(
                    method.upper(),
                    target,
                    body=handle,
                    headers={
                        "Authorization": f"Bearer {self._device_token()}",
                        "Content-Type": content_type,
                        "Content-Length": str(source.stat().st_size),
                        "Accept": "application/json",
                    },
                )
                response = connection.getresponse()
                raw = response.read().decode("utf-8", errors="replace")
        except OSError as exc:
            raise RuntimeError(f"{method} {url} failed: {exc}") from exc
        finally:
            connection.close()
        if response.status < 200 or response.status >= 300:
            raise UploadRequestError(
                f"{method} {url} failed: HTTP {response.status} {raw}",
                status_code=int(response.status),
            )
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{method} {url} returned non-json response") from exc

    def _base_url(self) -> str:
        return str(getattr(self.settings, "app_server_base_url", "") or "").strip().rstrip("/")

    def _device_token(self) -> str:
        issued_token = str(self.token_resolver() or "").strip()
        if bool(getattr(self.settings, "require_issued_device_token", False)):
            return issued_token
        return issued_token or str(getattr(self.settings, "device_api_token", "") or "").strip()

    def _retry_delay_seconds(self, attempt_count: int) -> int:
        return min(900, max(15, 15 * (2 ** max(0, min(int(attempt_count), 6) - 1))))

    def _utc_iso(self) -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()
