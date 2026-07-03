from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
import socket
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .camera_agent import CameraAgent
from .object_storage_service import ObjectStorageService
from .settings import settings
from .storage import Storage
from .video_distribution_service import VideoDistributionService
from .video_service import VideoService, build_video_router


bearer_scheme = HTTPBearer(auto_error=False)


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return socket.gethostbyname(socket.gethostname())


def local_device_identity() -> Dict[str, Any]:
    device_id_path = settings.data_dir / "device_id.txt"
    if device_id_path.exists():
        device_id = device_id_path.read_text(encoding="utf-8").strip()
    else:
        device_id = f"edge-{uuid4().hex[:16]}"
        device_id_path.write_text(device_id, encoding="utf-8")
    return {
        "device_id": device_id,
        "device_name": socket.gethostname(),
        "device_type": "edge-agent",
        "lan_ip": local_ip(),
        "api_port": settings.port,
    }


def current_device_id() -> str:
    return str(local_device_identity()["device_id"])


settings.ensure_dirs()
storage = Storage(settings.db_path)
camera_agent = CameraAgent(settings.snapshot_dir)
video_distribution_service = VideoDistributionService(
    storage=storage,
    settings=settings,
    current_device_identity_resolver=local_device_identity,
)
object_storage_service = ObjectStorageService(storage=storage, settings=settings, distribution=video_distribution_service)
video_service = VideoService(
    storage=storage,
    settings=settings,
    camera_agent=camera_agent,
    object_storage=object_storage_service,
    distribution=video_distribution_service,
    current_device_id_resolver=current_device_id,
)


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> Dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required")
    user = storage.get_user_by_session_token(credentials.credentials)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


def current_user_for_media(
    access_token: str | None = Query(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Dict[str, Any]:
    token = access_token
    if credentials is not None and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = storage.get_user_by_session_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


def resolve_media_fallback_user(
    access_token: str | None,
    credentials: HTTPAuthorizationCredentials | None,
) -> Dict[str, Any]:
    return current_user_for_media(access_token=access_token, credentials=credentials)


app = FastAPI(title="gohome video-service", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(
    build_video_router(
        video_service,
        current_user_dep=current_user,
        bearer_scheme=bearer_scheme,
        media_user_resolver=resolve_media_fallback_user,
    )
)


@app.on_event("startup")
def on_startup() -> None:
    storage.init_schema()


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "gohome-video-service",
        "device_id": current_device_id(),
        "snapshot_dir": str(Path(settings.snapshot_dir)),
        "object_storage_dir": str(Path(settings.object_storage_dir)),
        "distribution": video_distribution_service.service_info(),
    }
