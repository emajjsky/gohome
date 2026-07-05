from __future__ import annotations

from pathlib import Path
from threading import Event, Thread
from typing import Any, Callable, Dict
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import time


class UploadAgent:
    def __init__(
        self,
        *,
        storage: Any,
        settings: Any,
        device_id_resolver: Callable[[], str],
        token_resolver: Callable[[], str],
    ) -> None:
        self.storage = storage
        self.settings = settings
        self.device_id_resolver = device_id_resolver
        self.token_resolver = token_resolver
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

    def process_once(self, *, max_jobs: int | None = None) -> Dict[str, Any]:
        configured, reason = self._configured()
        if not configured:
            return {"ok": False, "processed": 0, "reason": reason}
        limit = max(1, int(max_jobs or getattr(self.settings, "upload_worker_batch_size", 4)))
        processed = 0
        completed = 0
        failed = 0
        for _ in range(limit):
            job = self.storage.claim_next_upload_job()
            if job is None:
                break
            processed += 1
            try:
                result = self._process_job(job)
            except Exception as exc:
                failed += 1
                retry_after = self._retry_delay_seconds(int(job.get("attempt_count") or 1))
                self.storage.fail_upload_job(int(job["id"]), str(exc), retry_after_seconds=retry_after)
                self.last_error = str(exc)
                continue
            completed += 1
            self.storage.complete_upload_job(int(job["id"]), result)
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
                self.process_once()
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
        if job_type == "media_upload":
            return self._upload_media(job)
        if job_type == "event_upload":
            return self._upload_event(job)
        raise ValueError(f"Unsupported upload job type: {job_type}")

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
        content = source.read_bytes()
        params = {
            "file_name": source.name,
            "snapshot_path": snapshot_path,
            "content_type": str(payload.get("content_type") or "image/jpeg"),
        }
        if payload.get("event_id"):
            params["edge_event_id"] = str(payload["event_id"])
        response = self._request_json(
            "POST",
            f"/api/v1/device/media-assets/upload?{urlencode(params)}",
            body=content,
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
        media_job = self.storage.latest_completed_upload_job(event_id=event_id, job_type="media_upload") if event_id else None
        media_result = (media_job or {}).get("payload", {}).get("upload_result") if media_job else None
        event_payload = dict(payload.get("payload") or {})
        event_payload["edge_upload"] = {
            "job_id": int(job["id"]),
            "edge_event_id": event_id or None,
            "edge_device_id": self.device_id_resolver(),
        }
        if media_result:
            event_payload["media_upload_result"] = media_result
        request_payload = {
            "idempotency_key": str(job.get("idempotency_key") or f"event:{event_id}"),
            "event_type": str(payload.get("event_type") or job.get("event_type") or "event"),
            "summary": str(payload.get("summary") or job.get("event_summary") or "回家事件"),
            "level": str(payload.get("level") or job.get("event_level") or "warning"),
            "room": str(payload.get("room") or ""),
            "camera_id": payload.get("camera_id") or job.get("camera_id"),
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
            raise RuntimeError(f"{method} {url} failed: HTTP {exc.code} {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"{method} {url} failed: {exc.reason}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{method} {url} returned non-json response") from exc

    def _base_url(self) -> str:
        return str(getattr(self.settings, "app_server_base_url", "") or "").strip().rstrip("/")

    def _device_token(self) -> str:
        return str(getattr(self.settings, "device_api_token", "") or "").strip() or str(self.token_resolver() or "").strip()

    def _retry_delay_seconds(self, attempt_count: int) -> int:
        return min(900, max(15, 15 * (2 ** max(0, min(int(attempt_count), 6) - 1))))

    def _utc_iso(self) -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()
