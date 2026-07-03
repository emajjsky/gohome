from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict
import base64
import hashlib
import hmac
import json
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .camera_agent import CameraAgent
from .object_storage_service import ObjectStorageService
from .schemas import PlaybackSessionCreate, V1VideoServiceNodeUpsert
from .storage import Storage
from .video_distribution_service import VideoDistributionService
from .video_profiles import list_stream_profiles, resolve_stream_profile


def app_snapshot_url(image_path: str | None) -> str | None:
    if not image_path:
        return None
    return f"/api/app/media/snapshots/{image_path}"


def v1_video_snapshot_url(image_path: str | None) -> str | None:
    if not image_path:
        return None
    return f"/api/v1/video/media/snapshots/{image_path}"


def v1_video_asset_url(asset_id: int | None) -> str | None:
    if not asset_id:
        return None
    return f"/api/v1/video/assets/{int(asset_id)}"


def normalize_snapshot_reference(snapshot_path: str) -> str:
    value = str(snapshot_path or "").strip()
    if value.startswith("/api/app/media/snapshots/"):
        value = value[len("/api/app/media/snapshots/"):]
    elif value.startswith("/api/v1/video/media/snapshots/"):
        value = value[len("/api/v1/video/media/snapshots/"):]
    elif value.startswith("/snapshots/"):
        value = value[len("/snapshots/"):]
    return value.lstrip("/")


class VideoService:
    def __init__(
        self,
        *,
        storage: Storage,
        settings: Any,
        camera_agent: CameraAgent,
        object_storage: ObjectStorageService,
        distribution: VideoDistributionService,
        current_device_id_resolver: Callable[[], str],
    ) -> None:
        self.storage = storage
        self.settings = settings
        self.camera_agent = camera_agent
        self.object_storage = object_storage
        self.distribution = distribution
        self.current_device_id = current_device_id_resolver

    def require_device_access(self, user: Dict[str, Any]) -> str:
        device_id = self.current_device_id()
        if not self.storage.list_device_bound_family_ids(device_id):
            raise HTTPException(status_code=403, detail="Current device is not bound to any family")
        if not self.storage.user_has_device_access(int(user["id"]), device_id):
            raise HTTPException(status_code=403, detail="You do not have access to this device")
        return device_id

    def require_family_access(self, user: Dict[str, Any], family_id: int) -> None:
        if int(family_id) not in set(self.storage.list_user_family_ids(int(user["id"]))):
            raise HTTPException(status_code=403, detail="You do not have access to this family")

    def resolve_distribution_family_id(
        self,
        *,
        user: Dict[str, Any],
        requested_family_id: int | None = None,
        asset_family_id: int | None = None,
    ) -> int | None:
        if asset_family_id:
            self.require_family_access(user, int(asset_family_id))
            return int(asset_family_id)
        if requested_family_id:
            self.require_family_access(user, int(requested_family_id))
            return int(requested_family_id)
        device_id = self.current_device_id()
        user_family_ids = set(self.storage.list_user_family_ids(int(user["id"])))
        device_family_ids = set(self.storage.list_device_bound_family_ids(device_id))
        intersection = sorted(user_family_ids & device_family_ids)
        return int(intersection[0]) if intersection else None

    def playback_secret_path(self) -> Path:
        return self.settings.data_dir / "playback_secret.txt"

    def read_playback_secret(self) -> str:
        path = self.playback_secret_path()
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

    def media_asset_for_api(self, asset: Dict[str, Any]) -> Dict[str, Any]:
        return self.object_storage.media_asset_for_api(asset)

    def resolve_snapshot_file(self, snapshot_path: str) -> Path:
        relative = Path(snapshot_path)
        candidate = (self.settings.snapshot_dir / relative).resolve()
        snapshot_root = self.settings.snapshot_dir.resolve()
        try:
            candidate.relative_to(snapshot_root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid snapshot path") from exc
        if not candidate.is_file():
            raise HTTPException(status_code=404, detail="Snapshot file not found")
        return candidate

    def asset_file_path(self, asset: Dict[str, Any]) -> Path:
        return self.object_storage.asset_file_path(asset)

    def promote_snapshot_media_asset(
        self,
        *,
        family_id: int,
        device_id: str,
        snapshot: Dict[str, Any],
        event_id: int | None = None,
        content_type: str = "image/jpeg",
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        existing = self.storage.get_media_asset_by_snapshot(int(snapshot["id"])) if snapshot.get("id") else None
        if existing is not None:
            return self.media_asset_for_api(existing)
        source_path = self.resolve_snapshot_file(str(snapshot["image_path"]))
        safe_name = f"{int(snapshot['id'])}_{Path(str(snapshot['image_path'])).name}"
        object_key = f"family_{int(family_id)}/snapshots/{safe_name}"
        target_path = self.object_storage.object_path_from_key(object_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(source_path.read_bytes())
        asset = self.storage.create_media_asset(
            family_id=family_id,
            device_id=device_id,
            event_id=event_id,
            snapshot_id=int(snapshot["id"]),
            source_snapshot_path=str(snapshot["image_path"]),
            object_key=object_key,
            content_type=content_type,
            byte_size=target_path.stat().st_size,
            checksum_sha256=self.object_storage.checksum_sha256(target_path),
            provider=self.settings.object_storage_provider,
            bucket=self.settings.object_storage_bucket,
            metadata={
                "snapshot_id": snapshot.get("id"),
                "camera_id": snapshot.get("camera_id"),
                "captured_at": snapshot.get("captured_at"),
                **(metadata or {}),
            },
        )
        return self.media_asset_for_api(asset)

    def create_playback_ticket(
        self,
        *,
        user_id: int,
        device_id: str,
        resource_type: str,
        expires_in_seconds: int = 120,
        camera_id: int | None = None,
        snapshot_path: str = "",
        asset_id: int | None = None,
    ) -> Dict[str, Any]:
        ttl_seconds = max(30, min(int(expires_in_seconds), 600))
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        payload = {
            "user_id": int(user_id),
            "device_id": device_id,
            "resource_type": resource_type,
            "camera_id": int(camera_id) if camera_id else None,
            "snapshot_path": normalize_snapshot_reference(snapshot_path),
            "asset_id": int(asset_id) if asset_id else None,
            "expires_at": expires_at.isoformat(),
        }
        payload_json = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = hmac.new(self.read_playback_secret().encode("utf-8"), payload_json, hashlib.sha256).digest()
        return {
            "ticket": f"{self.b64url_encode(payload_json)}.{self.b64url_encode(signature)}",
            "expires_at": expires_at.isoformat(),
            "resource_type": resource_type,
            "camera_id": payload["camera_id"],
            "snapshot_path": payload["snapshot_path"],
            "asset_id": payload["asset_id"],
        }

    def create_playback_session(self, payload: PlaybackSessionCreate, *, user: Dict[str, Any]) -> Dict[str, Any]:
        device_id = self.require_device_access(user)
        resource_type = payload.resource_type.strip()
        snapshot_path = normalize_snapshot_reference(payload.snapshot_path)
        family_id = self.resolve_distribution_family_id(user=user, requested_family_id=payload.family_id)
        if resource_type == "stream":
            if payload.camera_id is None:
                raise HTTPException(status_code=400, detail="camera_id is required for stream playback")
            if self.storage.get_camera(int(payload.camera_id)) is None:
                raise HTTPException(status_code=404, detail="Camera not found")
        elif resource_type == "snapshot":
            if not snapshot_path:
                raise HTTPException(status_code=400, detail="snapshot_path is required for snapshot playback")
            self.resolve_snapshot_file(snapshot_path)
        elif resource_type == "asset":
            if payload.asset_id is None:
                raise HTTPException(status_code=400, detail="asset_id is required for asset playback")
            asset = self.storage.get_media_asset(int(payload.asset_id))
            if asset is None:
                raise HTTPException(status_code=404, detail="Media asset not found")
            self.require_family_access(user, int(asset["family_id"]))
            family_id = int(asset["family_id"])
            self.asset_file_path(asset)
        else:
            raise HTTPException(status_code=400, detail="Unsupported playback resource type")
        session = self.create_playback_ticket(
            user_id=int(user["id"]),
            device_id=device_id,
            resource_type=resource_type,
            camera_id=payload.camera_id,
            snapshot_path=snapshot_path,
            asset_id=payload.asset_id,
            expires_in_seconds=payload.expires_in_seconds,
        )
        session["family_id"] = family_id
        session["preferred_region"] = str(payload.preferred_region or "")
        session["require_public"] = bool(payload.require_public)
        return session

    def build_v1_video_session(self, payload: PlaybackSessionCreate, *, user: Dict[str, Any]) -> Dict[str, Any]:
        session = self.create_playback_session(payload, user=user)
        resource_type = str(session["resource_type"])
        service_info = self.distribution.scheduled_service_info(
            family_id=session.get("family_id"),
            preferred_region=str(session.get("preferred_region") or ""),
            require_public=bool(session.get("require_public")),
            media=resource_type in {"snapshot", "asset"},
        )
        selected_service = service_info["service"]
        session["service"] = selected_service
        session["selection"] = service_info["selection"]
        if resource_type == "stream":
            session["stream_path"] = f"/api/v1/video/cameras/{session['camera_id']}/stream.mjpg"
            session["stream_url"] = self.distribution.absolute_video_url_for_node(session["stream_path"], selected_service)
        elif resource_type == "snapshot":
            session["media_path"] = f"/api/v1/video/media/snapshots/{session['snapshot_path']}"
            session["media_url"] = self.distribution.absolute_media_url_for_node(session["media_path"], selected_service)
        elif resource_type == "asset":
            session["asset_path"] = f"/api/v1/video/assets/{session['asset_id']}"
            session["asset_url"] = self.distribution.absolute_media_url_for_node(session["asset_path"], selected_service)
        return session

    def service_info(
        self,
        *,
        family_id: int | None = None,
        preferred_region: str = "",
        require_public: bool = False,
    ) -> Dict[str, Any]:
        return self.distribution.scheduled_service_info(
            family_id=family_id,
            preferred_region=preferred_region,
            require_public=require_public,
        )

    def list_service_nodes(self, *, family_id: int, user: Dict[str, Any], include_inactive: bool = False) -> Dict[str, Any]:
        self.require_family_access(user, int(family_id))
        nodes = self.distribution.list_nodes(int(family_id), include_inactive=include_inactive)
        return {
            "family_id": int(family_id),
            "nodes": nodes,
            "distribution": str(self.settings.video_distribution_name or "single-origin"),
        }

    def register_service_node(self, payload: V1VideoServiceNodeUpsert, *, user: Dict[str, Any]) -> Dict[str, Any]:
        self.require_family_access(user, int(payload.family_id))
        node = self.distribution.register_node(
            family_id=int(payload.family_id),
            node_id=payload.node_id,
            device_id=payload.device_id,
            node_name=payload.node_name,
            role=payload.role,
            region=payload.region,
            service_url=payload.service_url,
            media_url=payload.media_url,
            public_base_url=payload.public_base_url,
            health_status=payload.health_status,
            priority=payload.priority,
            heartbeat_expires_in_seconds=payload.heartbeat_expires_in_seconds,
            capabilities=payload.capabilities,
            metadata=payload.metadata,
        )
        return {
            "family_id": int(payload.family_id),
            "node": node,
            "distribution": str(self.settings.video_distribution_name or "single-origin"),
        }

    def validate_playback_ticket(
        self,
        ticket: str,
        *,
        resource_type: str,
        camera_id: int | None = None,
        snapshot_path: str = "",
        asset_id: int | None = None,
    ) -> Dict[str, Any]:
        try:
            payload_part, signature_part = ticket.split(".", 1)
            payload_json = self.b64url_decode(payload_part)
            signature = self.b64url_decode(signature_part)
            expected = hmac.new(self.read_playback_secret().encode("utf-8"), payload_json, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("signature")
            payload = json.loads(payload_json.decode("utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=401, detail="Invalid playback ticket") from exc
        if payload.get("resource_type") != resource_type:
            raise HTTPException(status_code=403, detail="Playback ticket scope mismatch")
        expires_at = payload.get("expires_at")
        if not expires_at:
            raise HTTPException(status_code=401, detail="Playback ticket expired")
        try:
            expires_time = datetime.fromisoformat(expires_at)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="Playback ticket expired") from exc
        if expires_time <= datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Playback ticket expired")
        if payload.get("device_id") != self.current_device_id():
            raise HTTPException(status_code=403, detail="Playback ticket device mismatch")
        if resource_type == "stream" and camera_id and int(payload.get("camera_id") or 0) != int(camera_id):
            raise HTTPException(status_code=403, detail="Playback ticket camera mismatch")
        if resource_type == "snapshot":
            expected_path = normalize_snapshot_reference(snapshot_path)
            if payload.get("snapshot_path") != expected_path:
                raise HTTPException(status_code=403, detail="Playback ticket snapshot mismatch")
        if resource_type == "asset" and int(payload.get("asset_id") or 0) != int(asset_id or 0):
            raise HTTPException(status_code=403, detail="Playback ticket asset mismatch")
        user = self.storage.get_user(int(payload.get("user_id") or 0))
        if user is None:
            raise HTTPException(status_code=401, detail="Playback user not found")
        return user

    def resolve_media_user(
        self,
        *,
        resource_type: str,
        camera_id: int | None = None,
        snapshot_path: str = "",
        asset_id: int | None = None,
        playback_ticket: str | None = None,
        fallback_user: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        if playback_ticket:
            return self.validate_playback_ticket(
                playback_ticket,
                resource_type=resource_type,
                camera_id=camera_id,
                snapshot_path=snapshot_path,
                asset_id=asset_id,
            )
        if fallback_user is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        return fallback_user

    def stream_response(
        self,
        *,
        camera_id: int,
        profile: str | None = None,
        fps: int | None = None,
        width: int | None = None,
        height: int | None = None,
        quality: int | None = None,
        drop: int | None = None,
        playback_ticket: str | None = None,
        fallback_user: Dict[str, Any] | None = None,
    ) -> StreamingResponse:
        user = self.resolve_media_user(
            resource_type="stream",
            camera_id=camera_id,
            playback_ticket=playback_ticket,
            fallback_user=fallback_user,
        )
        self.require_device_access(user)
        camera = self.storage.get_camera(camera_id, include_secret=True)
        if camera is None:
            raise HTTPException(status_code=404, detail="Camera not found")
        config = resolve_stream_profile(
            profile,
            overrides={
                "fps": fps,
                "width": width,
                "height": height,
                "quality": quality,
                "drop": drop,
            },
        )
        return StreamingResponse(
            self.camera_agent.mjpeg_frames(
                camera,
                fps=int(config["fps"]),
                jpeg_quality=int(config["quality"]),
                max_width=int(config["width"]),
                max_height=int(config["height"]),
                drop_stale_frames=int(config["drop"]),
            ),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Cache-Control": "no-store",
                "X-GoHome-Video-Profile": str(config["id"]),
                "X-GoHome-Video-Distribution": str(config.get("distribution") or "mjpeg"),
                "X-GoHome-Video-Node": str(self.distribution.current_node()["node_id"]),
            },
        )

    def snapshot_response(
        self,
        *,
        snapshot_path: str,
        playback_ticket: str | None = None,
        fallback_user: Dict[str, Any] | None = None,
    ) -> FileResponse:
        normalized_snapshot_path = normalize_snapshot_reference(snapshot_path)
        user = self.resolve_media_user(
            resource_type="snapshot",
            snapshot_path=normalized_snapshot_path,
            playback_ticket=playback_ticket,
            fallback_user=fallback_user,
        )
        self.require_device_access(user)
        file_path = self.resolve_snapshot_file(normalized_snapshot_path)
        return FileResponse(path=file_path, headers={"Cache-Control": "no-store"})

    def asset_response(
        self,
        *,
        asset_id: int,
        playback_ticket: str | None = None,
        fallback_user: Dict[str, Any] | None = None,
    ) -> FileResponse:
        asset = self.storage.get_media_asset(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Media asset not found")
        user = self.resolve_media_user(
            resource_type="asset",
            asset_id=asset_id,
            playback_ticket=playback_ticket,
            fallback_user=fallback_user,
        )
        self.require_family_access(user, int(asset["family_id"]))
        file_path = self.asset_file_path(asset)
        return FileResponse(
            path=file_path,
            media_type=str(asset.get("content_type") or "image/jpeg"),
            headers={"Cache-Control": "no-store"},
        )


def build_video_router(
    service: VideoService,
    *,
    current_user_dep: Callable[..., Dict[str, Any]],
    bearer_scheme: HTTPBearer,
    media_user_resolver: Callable[[str | None, HTTPAuthorizationCredentials | None], Dict[str, Any]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v1/video/profiles")
    def v1_video_profiles(
        family_id: int | None = Query(default=None, ge=1),
        preferred_region: str = Query(default=""),
        require_public: bool = Query(default=False),
        user: Dict[str, Any] = Depends(current_user_dep),
    ) -> Dict[str, Any]:
        service.require_device_access(user)
        service_info = service.service_info(
            family_id=family_id,
            preferred_region=preferred_region,
            require_public=require_public,
        )
        return {
            "distribution": "mjpeg",
            "profiles": list_stream_profiles(),
            "service": service_info["service"],
            "selection": service_info["selection"],
        }

    @router.get("/api/v1/video/service-nodes")
    def v1_video_service_nodes(
        family_id: int = Query(..., ge=1),
        include_inactive: bool = Query(default=False),
        user: Dict[str, Any] = Depends(current_user_dep),
    ) -> Dict[str, Any]:
        service.require_device_access(user)
        return service.list_service_nodes(family_id=family_id, user=user, include_inactive=include_inactive)

    @router.post("/api/v1/video/service-nodes")
    def v1_upsert_video_service_node(
        payload: V1VideoServiceNodeUpsert,
        user: Dict[str, Any] = Depends(current_user_dep),
    ) -> Dict[str, Any]:
        service.require_device_access(user)
        return service.register_service_node(payload, user=user)

    @router.get("/api/v1/video/service-info")
    def v1_video_service_info(
        family_id: int | None = Query(default=None, ge=1),
        preferred_region: str = Query(default=""),
        require_public: bool = Query(default=False),
        user: Dict[str, Any] = Depends(current_user_dep),
    ) -> Dict[str, Any]:
        service.require_device_access(user)
        return service.service_info(
            family_id=family_id,
            preferred_region=preferred_region,
            require_public=require_public,
        )

    @router.post("/api/v1/video/sessions")
    def create_v1_video_session(
        payload: PlaybackSessionCreate,
        user: Dict[str, Any] = Depends(current_user_dep),
    ) -> Dict[str, Any]:
        return service.build_v1_video_session(payload, user=user)

    @router.get("/api/v1/video/cameras/{camera_id}/stream.mjpg")
    def v1_video_camera_mjpeg_stream(
        camera_id: int,
        profile: str = Query(default="default"),
        fps: int | None = Query(default=None),
        width: int | None = Query(default=None),
        height: int | None = Query(default=None),
        quality: int | None = Query(default=None),
        drop: int | None = Query(default=None),
        playback_ticket: str | None = Query(default=None),
        access_token: str | None = Query(default=None),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    ) -> StreamingResponse:
        fallback_user = None if playback_ticket else media_user_resolver(access_token, credentials)
        return service.stream_response(
            camera_id=camera_id,
            profile=profile,
            fps=fps,
            width=width,
            height=height,
            quality=quality,
            drop=drop,
            playback_ticket=playback_ticket,
            fallback_user=fallback_user,
        )

    @router.get("/api/v1/video/media/snapshots/{snapshot_path:path}")
    def v1_video_snapshot_media(
        snapshot_path: str,
        playback_ticket: str | None = Query(default=None),
        access_token: str | None = Query(default=None),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    ) -> FileResponse:
        fallback_user = None if playback_ticket else media_user_resolver(access_token, credentials)
        return service.snapshot_response(
            snapshot_path=snapshot_path,
            playback_ticket=playback_ticket,
            fallback_user=fallback_user,
        )

    @router.get("/api/v1/video/assets/{asset_id}")
    def v1_video_asset_media(
        asset_id: int,
        playback_ticket: str | None = Query(default=None),
        access_token: str | None = Query(default=None),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    ) -> FileResponse:
        fallback_user = None if playback_ticket else media_user_resolver(access_token, credentials)
        return service.asset_response(
            asset_id=asset_id,
            playback_ticket=playback_ticket,
            fallback_user=fallback_user,
        )

    return router
