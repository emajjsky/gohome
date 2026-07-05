from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict
import base64
import hashlib
import hmac
import json
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from .schemas import V1MediaPublicLinkCreate, V1MediaUploadSessionComplete, V1MediaUploadSessionCreate
from .storage import Storage
from .video_distribution_service import VideoDistributionService


def v1_video_asset_url(asset_id: int | None) -> str | None:
    if not asset_id:
        return None
    return f"/api/v1/video/assets/{int(asset_id)}"


def public_media_asset_path(asset_id: int | None) -> str | None:
    if not asset_id:
        return None
    return f"/api/public/media/assets/{int(asset_id)}"


class ObjectStorageService:
    def __init__(self, *, storage: Storage, settings: Any, distribution: VideoDistributionService) -> None:
        self.storage = storage
        self.settings = settings
        self.distribution = distribution

    def require_family_access(self, user: Dict[str, Any], family_id: int) -> None:
        if int(family_id) not in set(self.storage.list_user_family_ids(int(user["id"]))):
            raise HTTPException(status_code=403, detail="You do not have access to this family")

    def secret_path(self) -> Path:
        return self.settings.data_dir / "object_storage_secret.txt"

    def read_secret(self) -> str:
        path = self.secret_path()
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
        value = secrets.token_urlsafe(32)
        path.write_text(value, encoding="utf-8")
        return value

    def b64url_encode(self, data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")

    def b64url_decode(self, value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(f"{value}{padding}")

    def sign_payload(self, payload: Dict[str, Any]) -> str:
        payload_json = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = hmac.new(self.read_secret().encode("utf-8"), payload_json, hashlib.sha256).digest()
        return f"{self.b64url_encode(payload_json)}.{self.b64url_encode(signature)}"

    def verify_token(self, token: str) -> Dict[str, Any]:
        try:
            payload_part, signature_part = token.split(".", 1)
            payload_json = self.b64url_decode(payload_part)
            signature = self.b64url_decode(signature_part)
            expected = hmac.new(self.read_secret().encode("utf-8"), payload_json, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("signature")
            payload = json.loads(payload_json.decode("utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=401, detail="Invalid storage token") from exc
        expires_at = str(payload.get("expires_at") or "")
        try:
            expires_time = datetime.fromisoformat(expires_at)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="Storage token expired") from exc
        if expires_time <= datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Storage token expired")
        return payload

    def storage_token_hash(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def sanitize_filename(self, file_name: str) -> str:
        name = Path(str(file_name or "").strip()).name
        if not name:
            name = "upload.bin"
        clean = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
        return clean[:120] or "upload.bin"

    def build_object_key(self, *, family_id: int, file_name: str) -> str:
        safe_name = self.sanitize_filename(file_name)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d/%H%M%S")
        random_id = secrets.token_hex(4)
        return f"family_{int(family_id)}/uploads/{timestamp}_{random_id}_{safe_name}"

    def object_path_from_key(self, object_key: str) -> Path:
        relative = Path(str(object_key or "").strip().lstrip("/"))
        candidate = (self.settings.object_storage_dir / relative).resolve()
        storage_root = self.settings.object_storage_dir.resolve()
        try:
            candidate.relative_to(storage_root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid object key") from exc
        return candidate

    def asset_file_path(self, asset: Dict[str, Any]) -> Path:
        candidate = self.object_path_from_key(str(asset.get("object_key") or ""))
        if not candidate.is_file():
            raise HTTPException(status_code=404, detail="Stored media file not found")
        return candidate

    def checksum_sha256(self, file_path: Path) -> str:
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def media_asset_for_api(self, asset: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(asset)
        storage_path = v1_video_asset_url(int(data["id"]))
        public_asset_path_value = public_media_asset_path(int(data["id"]))
        family_id = int(data.get("family_id") or 0) or None
        service_info = self.distribution.scheduled_service_info(family_id=family_id, media=True)
        selected_service = service_info["service"]
        data["storage_path"] = storage_path
        data["storage_url"] = self.distribution.absolute_media_url_for_node(storage_path or "", selected_service)
        data["public_asset_path"] = public_asset_path_value
        data["public_asset_url"] = self.distribution.absolute_media_url_for_node(public_asset_path_value or "", selected_service)
        data["distribution_service"] = selected_service
        return data

    def create_upload_session(self, payload: V1MediaUploadSessionCreate, *, user: Dict[str, Any]) -> Dict[str, Any]:
        self.require_family_access(user, int(payload.family_id))
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        object_key = self.build_object_key(family_id=int(payload.family_id), file_name=payload.file_name)
        token = self.sign_payload(
            {
                "kind": "upload",
                "family_id": int(payload.family_id),
                "object_key": object_key,
                "expires_at": expires_at.isoformat(),
            }
        )
        session = self.storage.create_media_upload_session(
            family_id=int(payload.family_id),
            created_by_user_id=int(user["id"]),
            device_id=payload.device_id,
            file_name=payload.file_name,
            content_type=payload.content_type,
            byte_size=payload.byte_size,
            provider=self.settings.object_storage_provider,
            bucket=self.settings.object_storage_bucket,
            object_key=object_key,
            upload_token_hash=self.storage_token_hash(token),
            expires_at=expires_at.isoformat(),
            metadata=payload.metadata,
        )
        return {
            **session,
            "upload_token": token,
            "upload_url": f"/api/v1/media/upload-sessions/{session['id']}/content?upload_token={token}",
            "complete_url": f"/api/v1/media/upload-sessions/{session['id']}/complete?upload_token={token}",
        }

    def store_device_media_bytes(
        self,
        *,
        family_id: int,
        device_id: str,
        file_name: str,
        content_type: str,
        content_bytes: bytes,
        source_snapshot_path: str,
        snapshot_id: int | None = None,
        event_id: int | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        if not content_bytes:
            raise HTTPException(status_code=400, detail="Media body is empty")
        clean_source = str(source_snapshot_path or "").strip().lstrip("/")
        if not clean_source:
            raise HTTPException(status_code=400, detail="snapshot_path is required")
        object_key = self.build_object_key(family_id=int(family_id), file_name=file_name)
        target_path = self.object_path_from_key(object_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content_bytes)
        asset = self.storage.create_media_asset(
            family_id=int(family_id),
            device_id=str(device_id or "").strip(),
            event_id=event_id,
            snapshot_id=snapshot_id,
            source_snapshot_path=clean_source,
            object_key=object_key,
            content_type=str(content_type or "application/octet-stream").strip() or "application/octet-stream",
            byte_size=target_path.stat().st_size,
            checksum_sha256=self.checksum_sha256(target_path),
            provider=self.settings.object_storage_provider,
            bucket=self.settings.object_storage_bucket,
            metadata={
                "source": "device-media-upload",
                "file_name": self.sanitize_filename(file_name),
                **(metadata or {}),
            },
        )
        return self.media_asset_for_api(asset)

    def verify_upload_session_token(self, session_id: int, upload_token: str) -> Dict[str, Any]:
        payload = self.verify_token(upload_token)
        if payload.get("kind") != "upload":
            raise HTTPException(status_code=403, detail="Storage token scope mismatch")
        session = self.storage.get_media_upload_session(int(session_id))
        if session is None:
            raise HTTPException(status_code=404, detail="Upload session not found")
        if session["upload_token_hash"] != self.storage_token_hash(upload_token):
            raise HTTPException(status_code=403, detail="Upload session token mismatch")
        if str(payload.get("object_key") or "") != str(session.get("object_key") or ""):
            raise HTTPException(status_code=403, detail="Upload session object mismatch")
        return session

    def put_upload_content(
        self,
        session_id: int,
        *,
        upload_token: str,
        content_type: str,
        content_bytes: bytes,
    ) -> Dict[str, Any]:
        session = self.verify_upload_session_token(session_id, upload_token)
        if str(session.get("status") or "") == "completed":
            return session
        target_path = self.object_path_from_key(str(session["object_key"]))
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content_bytes)
        return self.storage.mark_media_upload_session_uploaded(
            int(session_id),
            byte_size=len(content_bytes),
            content_type=content_type or str(session.get("content_type") or ""),
        )

    def complete_upload_session(
        self,
        session_id: int,
        *,
        upload_token: str,
        payload: V1MediaUploadSessionComplete,
    ) -> Dict[str, Any]:
        session = self.verify_upload_session_token(session_id, upload_token)
        if session.get("asset_id"):
            asset = self.storage.get_media_asset(int(session["asset_id"]))
            if asset is None:
                raise HTTPException(status_code=500, detail="Upload session asset missing")
            return {
                "upload_session": session,
                "asset": self.media_asset_for_api(asset),
            }
        if str(session.get("status") or "") not in {"uploaded", "completed"}:
            raise HTTPException(status_code=409, detail="Upload content not received")
        target_path = self.object_path_from_key(str(session["object_key"]))
        if not target_path.is_file():
            raise HTTPException(status_code=404, detail="Uploaded object missing")
        source_marker = f"upload/session_{int(session['id'])}/{self.sanitize_filename(str(session.get('file_name') or 'upload.bin'))}"
        asset = self.storage.create_media_asset(
            family_id=int(session["family_id"]),
            device_id=str(session.get("device_id") or ""),
            snapshot_id=None,
            source_snapshot_path=source_marker,
            object_key=str(session["object_key"]),
            content_type=str(payload.content_type or session.get("content_type") or "application/octet-stream"),
            byte_size=target_path.stat().st_size,
            checksum_sha256=self.checksum_sha256(target_path),
            provider=str(session.get("provider") or self.settings.object_storage_provider),
            bucket=str(session.get("bucket") or self.settings.object_storage_bucket),
            status="uploaded",
            metadata={
                **(session.get("metadata") or {}),
                **(payload.metadata or {}),
                "source": "presigned-upload",
                "upload_session_id": int(session["id"]),
                "file_name": session.get("file_name"),
            },
        )
        completed = self.storage.complete_media_upload_session(int(session_id), asset_id=int(asset["id"]))
        return {
            "upload_session": completed,
            "asset": self.media_asset_for_api(asset),
        }

    def create_public_link(
        self,
        asset_id: int,
        *,
        user: Dict[str, Any],
        expires_in_seconds: int,
        family_id: int | None = None,
        preferred_region: str = "",
        require_public: bool = True,
    ) -> Dict[str, Any]:
        asset = self.storage.get_media_asset(int(asset_id))
        if asset is None:
            raise HTTPException(status_code=404, detail="Media asset not found")
        self.require_family_access(user, int(asset["family_id"]))
        target_family_id = int(asset["family_id"] or family_id or 0) or None
        service_info = self.distribution.scheduled_service_info(
            family_id=target_family_id,
            preferred_region=preferred_region,
            require_public=require_public,
            media=True,
        )
        selected_service = service_info["service"]
        public_path = f"{public_media_asset_path(int(asset_id))}?download_token={{token}}"
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(60, min(int(expires_in_seconds), 86400)))
        token = self.sign_payload(
            {
                "kind": "public-download",
                "asset_id": int(asset_id),
                "object_key": str(asset["object_key"]),
                "expires_at": expires_at.isoformat(),
            }
        )
        return {
            "asset_id": int(asset_id),
            "expires_at": expires_at.isoformat(),
            "public_path": public_path.format(token=token),
            "public_url": self.distribution.absolute_media_url_for_node(public_path.format(token=token), selected_service),
            "service": selected_service,
            "selection": service_info["selection"],
            "distribution": service_info["distribution"],
        }

    def public_asset_response(self, asset_id: int, *, download_token: str) -> FileResponse:
        asset = self.storage.get_media_asset(int(asset_id))
        if asset is None:
            raise HTTPException(status_code=404, detail="Media asset not found")
        payload = self.verify_token(download_token)
        if payload.get("kind") != "public-download":
            raise HTTPException(status_code=403, detail="Storage token scope mismatch")
        if int(payload.get("asset_id") or 0) != int(asset_id):
            raise HTTPException(status_code=403, detail="Storage token asset mismatch")
        if str(payload.get("object_key") or "") != str(asset.get("object_key") or ""):
            raise HTTPException(status_code=403, detail="Storage token object mismatch")
        file_path = self.asset_file_path(asset)
        return FileResponse(
            path=file_path,
            media_type=str(asset.get("content_type") or "application/octet-stream"),
            headers={
                "Cache-Control": "public, max-age=60",
                "X-GoHome-Media-Node": str(self.distribution.current_node()["node_id"]),
            },
        )


def build_object_storage_router(
    service: ObjectStorageService,
    *,
    current_user_dep: Callable[..., Dict[str, Any]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v1/media/upload-sessions")
    def v1_create_media_upload_session(
        payload: V1MediaUploadSessionCreate,
        user: Dict[str, Any] = Depends(current_user_dep),
    ) -> Dict[str, Any]:
        return service.create_upload_session(payload, user=user)

    @router.put("/api/v1/media/upload-sessions/{session_id}/content")
    async def v1_put_media_upload_content(
        session_id: int,
        request: Request,
        upload_token: str = Query(..., min_length=20),
    ) -> Dict[str, Any]:
        body = await request.body()
        content_type = request.headers.get("content-type", "")
        return service.put_upload_content(
            session_id,
            upload_token=upload_token,
            content_type=content_type,
            content_bytes=body,
        )

    @router.post("/api/v1/media/upload-sessions/{session_id}/complete")
    def v1_complete_media_upload_session(
        session_id: int,
        payload: V1MediaUploadSessionComplete,
        upload_token: str = Query(..., min_length=20),
    ) -> Dict[str, Any]:
        return service.complete_upload_session(
            session_id,
            upload_token=upload_token,
            payload=payload,
        )

    @router.post("/api/v1/media/assets/{asset_id}/public-links")
    def v1_create_media_public_link(
        asset_id: int,
        payload: V1MediaPublicLinkCreate,
        user: Dict[str, Any] = Depends(current_user_dep),
    ) -> Dict[str, Any]:
        return service.create_public_link(
            asset_id,
            user=user,
            expires_in_seconds=payload.expires_in_seconds,
            family_id=payload.family_id,
            preferred_region=payload.preferred_region,
            require_public=payload.require_public,
        )

    @router.get("/api/public/media/assets/{asset_id}")
    def public_media_asset_download(
        asset_id: int,
        download_token: str = Query(..., min_length=20),
    ) -> FileResponse:
        return service.public_asset_response(asset_id, download_token=download_token)

    return router
