from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict
import base64
import hashlib
import hmac
import json
import os
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from .schemas import (
    V1PackageArtifactPublicLinkCreate,
    V1PackageArtifactUploadComplete,
    V1PackageArtifactUploadCreate,
)
from .storage import Storage


def package_artifact_path(asset_id: int) -> str:
    return f"/api/v1/package-artifacts/{int(asset_id)}"


def public_package_artifact_path(asset_id: int) -> str:
    return f"/api/public/package-artifacts/{int(asset_id)}"


class PackageArtifactService:
    def __init__(self, *, storage: Storage, settings: Any) -> None:
        self.storage = storage
        self.settings = settings

    def require_family_access(self, user: Dict[str, Any], family_id: int) -> None:
        if int(family_id) not in set(self.storage.list_user_family_ids(int(user["id"]))):
            raise HTTPException(status_code=403, detail="You do not have access to this family")

    def read_secret(self) -> str:
        path = self.settings.data_dir / "package_artifact_secret.txt"
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
        value = secrets.token_urlsafe(32)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            existing = path.read_text(encoding="utf-8").strip()
            if existing:
                return existing
            raise RuntimeError("Package artifact secret is empty")
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        return value

    @staticmethod
    def _b64encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

    @staticmethod
    def _b64decode(value: str) -> bytes:
        return base64.urlsafe_b64decode(f"{value}{'=' * (-len(value) % 4)}")

    def sign_payload(self, payload: Dict[str, Any]) -> str:
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = hmac.new(self.read_secret().encode("utf-8"), encoded, hashlib.sha256).digest()
        return f"{self._b64encode(encoded)}.{self._b64encode(signature)}"

    def verify_token(self, token: str) -> Dict[str, Any]:
        try:
            payload_part, signature_part = token.split(".", 1)
            encoded = self._b64decode(payload_part)
            signature = self._b64decode(signature_part)
            expected = hmac.new(self.read_secret().encode("utf-8"), encoded, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("signature")
            payload = json.loads(encoded.decode("utf-8"))
            expires_at = datetime.fromisoformat(str(payload.get("expires_at") or ""))
        except Exception as exc:
            raise HTTPException(status_code=401, detail="Invalid package artifact token") from exc
        if expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Package artifact token expired")
        return payload

    @staticmethod
    def token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def sanitize_filename(file_name: str) -> str:
        name = Path(str(file_name or "").strip()).name or "package.bin"
        return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:120] or "package.bin"

    def build_object_key(self, family_id: int, file_name: str) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d/%H%M%S")
        return f"package-artifacts/family_{int(family_id)}/{timestamp}_{secrets.token_hex(4)}_{self.sanitize_filename(file_name)}"

    def object_path_from_key(self, object_key: str) -> Path:
        candidate = (self.settings.object_storage_dir / str(object_key or "").strip().lstrip("/")).resolve()
        root = self.settings.object_storage_dir.resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid package artifact key") from exc
        return candidate

    def asset_file_path(self, asset: Dict[str, Any]) -> Path:
        if str(asset.get("retention_class") or "") != "package_artifact":
            raise HTTPException(status_code=404, detail="Package artifact not found")
        if str(asset.get("retention_status") or "active") != "active" or str(asset.get("status") or "") == "deleted":
            raise HTTPException(status_code=404, detail="Package artifact not found")
        path = self.object_path_from_key(str(asset.get("object_key") or ""))
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Package artifact not found")
        return path

    @staticmethod
    def checksum_sha256(file_path: Path) -> str:
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def absolute_public_url(self, path: str) -> str:
        base_url = str(getattr(self.settings, "media_public_base_url", "") or "").strip().rstrip("/")
        return f"{base_url}{path}" if base_url else path

    def artifact_for_api(self, asset: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(asset)
        data["storage_path"] = package_artifact_path(int(data["id"]))
        data["storage_url"] = data["storage_path"]
        return data

    def asset_response(self, asset_id: int, *, user: Dict[str, Any]) -> FileResponse:
        asset = self.storage.get_media_asset(int(asset_id))
        if asset is None:
            raise HTTPException(status_code=404, detail="Package artifact not found")
        self.require_family_access(user, int(asset["family_id"]))
        return FileResponse(self.asset_file_path(asset), media_type=str(asset.get("content_type") or "application/octet-stream"))

    def create_upload(self, payload: V1PackageArtifactUploadCreate, *, user: Dict[str, Any]) -> Dict[str, Any]:
        self.require_family_access(user, int(payload.family_id))
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        object_key = self.build_object_key(int(payload.family_id), payload.file_name)
        token = self.sign_payload({
            "kind": "package-upload",
            "object_key": object_key,
            "byte_size": int(payload.byte_size),
            "expires_at": expires_at.isoformat(),
        })
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
            upload_token_hash=self.token_hash(token),
            expires_at=expires_at.isoformat(),
            metadata={**payload.metadata, "purpose": "package_artifact"},
        )
        return {
            **session,
            "upload_token": token,
            "upload_url": f"/api/v1/package-artifacts/uploads/{session['id']}/content?upload_token={token}",
            "complete_url": f"/api/v1/package-artifacts/uploads/{session['id']}/complete?upload_token={token}",
        }

    def verify_upload(self, session_id: int, upload_token: str) -> Dict[str, Any]:
        payload = self.verify_token(upload_token)
        session = self.storage.get_media_upload_session(int(session_id))
        if payload.get("kind") != "package-upload" or session is None:
            raise HTTPException(status_code=404, detail="Package upload not found")
        if session["upload_token_hash"] != self.token_hash(upload_token):
            raise HTTPException(status_code=403, detail="Package upload token mismatch")
        if str(payload.get("object_key") or "") != str(session.get("object_key") or ""):
            raise HTTPException(status_code=403, detail="Package upload object mismatch")
        if int(payload.get("byte_size") or 0) != int(session.get("byte_size") or 0):
            raise HTTPException(status_code=403, detail="Package upload size mismatch")
        return session

    async def put_upload_content(self, session_id: int, *, upload_token: str, request: Request) -> Dict[str, Any]:
        session = self.verify_upload(session_id, upload_token)
        if str(session.get("status") or "") == "completed":
            return session
        expected = int(session.get("byte_size") or 0)
        target = self.object_path_from_key(str(session["object_key"]))
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{secrets.token_hex(6)}.upload")
        received = 0
        try:
            with temporary.open("xb") as handle:
                async for chunk in request.stream():
                    received += len(chunk)
                    if received > expected:
                        raise HTTPException(status_code=413, detail="Package artifact exceeds declared size")
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            if received != expected:
                raise HTTPException(status_code=400, detail="Package artifact size mismatch")
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return self.storage.mark_media_upload_session_uploaded(
            int(session_id),
            byte_size=received,
            content_type=request.headers.get("content-type", "") or str(session.get("content_type") or ""),
        )

    def complete_upload(self, session_id: int, *, upload_token: str, payload: V1PackageArtifactUploadComplete) -> Dict[str, Any]:
        session = self.verify_upload(session_id, upload_token)
        if session.get("asset_id"):
            asset = self.storage.get_media_asset(int(session["asset_id"]))
            if asset is None:
                raise HTTPException(status_code=500, detail="Package artifact record missing")
            return {"upload": session, "asset": self.artifact_for_api(asset)}
        if str(session.get("status") or "") != "uploaded":
            raise HTTPException(status_code=409, detail="Package artifact content not received")
        target = self.object_path_from_key(str(session["object_key"]))
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Package artifact content missing")
        asset = self.storage.create_media_asset(
            family_id=int(session["family_id"]),
            device_id=str(session.get("device_id") or ""),
            snapshot_id=None,
            source_snapshot_path=f"package/upload_{int(session['id'])}/{self.sanitize_filename(str(session.get('file_name') or 'package.bin'))}",
            object_key=str(session["object_key"]),
            content_type=str(payload.content_type or session.get("content_type") or "application/octet-stream"),
            byte_size=target.stat().st_size,
            checksum_sha256=self.checksum_sha256(target),
            provider=str(session.get("provider") or self.settings.object_storage_provider),
            bucket=str(session.get("bucket") or self.settings.object_storage_bucket),
            status="uploaded",
            retention_class="package_artifact",
            metadata={**(session.get("metadata") or {}), **payload.metadata, "file_name": session.get("file_name")},
        )
        upload = self.storage.complete_media_upload_session(int(session_id), asset_id=int(asset["id"]))
        return {"upload": upload, "asset": self.artifact_for_api(asset)}

    def create_public_link(self, asset_id: int, *, user: Dict[str, Any], expires_in_seconds: int) -> Dict[str, Any]:
        asset = self.storage.get_media_asset(int(asset_id))
        if asset is None:
            raise HTTPException(status_code=404, detail="Package artifact not found")
        self.require_family_access(user, int(asset["family_id"]))
        self.asset_file_path(asset)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(60, min(int(expires_in_seconds), 86400)))
        token = self.sign_payload({
            "kind": "package-download",
            "asset_id": int(asset_id),
            "object_key": str(asset["object_key"]),
            "expires_at": expires_at.isoformat(),
        })
        path = f"{public_package_artifact_path(int(asset_id))}?download_token={token}"
        return {"asset_id": int(asset_id), "expires_at": expires_at.isoformat(), "public_path": path, "public_url": self.absolute_public_url(path)}

    def public_asset_response(self, asset_id: int, *, download_token: str) -> FileResponse:
        asset = self.storage.get_media_asset(int(asset_id))
        if asset is None:
            raise HTTPException(status_code=404, detail="Package artifact not found")
        payload = self.verify_token(download_token)
        if payload.get("kind") != "package-download" or int(payload.get("asset_id") or 0) != int(asset_id):
            raise HTTPException(status_code=403, detail="Package artifact token mismatch")
        if str(payload.get("object_key") or "") != str(asset.get("object_key") or ""):
            raise HTTPException(status_code=403, detail="Package artifact object mismatch")
        return FileResponse(self.asset_file_path(asset), media_type=str(asset.get("content_type") or "application/octet-stream"))


def build_package_artifact_router(service: PackageArtifactService, *, current_user_dep: Callable[..., Dict[str, Any]]) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v1/package-artifacts/{asset_id}")
    def get_artifact(asset_id: int, user: Dict[str, Any] = Depends(current_user_dep)) -> FileResponse:
        return service.asset_response(asset_id, user=user)

    @router.post("/api/v1/package-artifacts/uploads")
    def create_upload(payload: V1PackageArtifactUploadCreate, user: Dict[str, Any] = Depends(current_user_dep)) -> Dict[str, Any]:
        return service.create_upload(payload, user=user)

    @router.put("/api/v1/package-artifacts/uploads/{session_id}/content")
    async def put_content(session_id: int, request: Request, upload_token: str = Query(..., min_length=20)) -> Dict[str, Any]:
        return await service.put_upload_content(session_id, upload_token=upload_token, request=request)

    @router.post("/api/v1/package-artifacts/uploads/{session_id}/complete")
    def complete_upload(
        session_id: int,
        payload: V1PackageArtifactUploadComplete,
        upload_token: str = Query(..., min_length=20),
    ) -> Dict[str, Any]:
        return service.complete_upload(session_id, upload_token=upload_token, payload=payload)

    @router.post("/api/v1/package-artifacts/{asset_id}/download-links")
    def create_download_link(
        asset_id: int,
        payload: V1PackageArtifactPublicLinkCreate,
        user: Dict[str, Any] = Depends(current_user_dep),
    ) -> Dict[str, Any]:
        return service.create_public_link(asset_id, user=user, expires_in_seconds=payload.expires_in_seconds)

    @router.get("/api/public/package-artifacts/{asset_id}")
    def public_download(asset_id: int, download_token: str = Query(..., min_length=20)) -> FileResponse:
        return service.public_asset_response(asset_id, download_token=download_token)

    return router
