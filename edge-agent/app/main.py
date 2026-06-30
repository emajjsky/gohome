from __future__ import annotations

from typing import Any, Dict
from datetime import datetime, timezone
from pathlib import Path
import json
import socket
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

from .app_runtime_guard_service import AppRuntimeGuardService
from .apns_relay_service import APNSRelayService
from .app_push_service import AppPushService
from .camera_agent import CameraAgent, CameraError
from .detect_agent import DetectAgent
from .edge_bootstrap_service import EdgeBootstrapService
from .event_agent import EventAgent
from .notifier import Notifier
from .object_storage_service import ObjectStorageService, build_object_storage_router
from .package_service import PackageService
from .public_pilot_service import PublicPilotService
from .schemas import (
    CameraCreate,
    CameraUpdate,
    DeviceBindingCodeCreate,
    DeviceBindingCreate,
    DeviceHeartbeatIn,
    DeviceTokenExchange,
    EventUpdate,
    FamilyCreate,
    NotificationTest,
    PlaybackSessionCreate,
    V1DeviceUpgradeRun,
    RulesUpdate,
    UserLogin,
    UserRegister,
    V1AppPushTest,
    V1AppPushRelayRequest,
    V1AppPushTokenUpsert,
    V1MediaAssetCreate,
    V1MediaPublicLinkCreate,
    V1MediaUploadSessionComplete,
    V1MediaUploadSessionCreate,
    V1PackageDownloadLinkCreate,
    V1PackageReleaseCreate,
    V1DeviceRolloutCreate,
    V1DeviceRolloutPromote,
    V1DeviceRolloutRollback,
    V1DeviceEventIngest,
    V1DeviceSyncReport,
    V1DeviceSyncTargetUpdate,
)
from .settings import settings
from .storage import Storage
from .video_distribution_service import VideoDistributionService
from .video_service import (
    VideoService,
    app_snapshot_url,
    build_video_router,
    normalize_snapshot_reference,
    v1_video_snapshot_url,
)
from .worker import EdgeWorker

bearer_scheme = HTTPBearer(auto_error=False)


def model_dump(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


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


def current_device_id() -> str:
    return str(local_device_identity()["device_id"])


def local_device_token_path() -> Path:
    return settings.data_dir / "device_token.txt"


def read_local_device_token() -> str:
    path = local_device_token_path()
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def write_local_device_token(token: str) -> None:
    local_device_token_path().write_text(token.strip(), encoding="utf-8")


def require_device_access(user: Dict[str, Any]) -> str:
    device_id = current_device_id()
    if not storage.list_device_bound_family_ids(device_id):
        raise HTTPException(status_code=403, detail="Current device is not bound to any family")
    if not storage.user_has_device_access(int(user["id"]), device_id):
        raise HTTPException(status_code=403, detail="You do not have access to this device")
    return device_id


def require_family_access(user: Dict[str, Any], family_id: int) -> None:
    if int(family_id) not in set(storage.list_user_family_ids(int(user["id"]))):
        raise HTTPException(status_code=403, detail="You do not have access to this family")


def snapshot_for_app(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(snapshot)
    if data.get("image_path"):
        data["image_url"] = app_snapshot_url(data["image_path"])
    return data


def record_local_package_execution(device_id: str, family_id: int) -> None:
    state = storage.ensure_device_sync_state(device_id, family_id)
    status = dict(state.get("reported_status") or {})
    status["last_package_execution_at"] = datetime.now(timezone.utc).isoformat()
    latest_app = storage.get_latest_package_execution(family_id=family_id, device_id=device_id, package_type="app")
    latest_model = storage.get_latest_package_execution(family_id=family_id, device_id=device_id, package_type="model")
    status["package_execution"] = {
        "app": latest_app["status"] if latest_app else "",
        "model": latest_model["status"] if latest_model else "",
    }
    storage.report_device_sync(
        device_id=device_id,
        family_id=family_id,
        app_version=package_service.current_app_version(default_version=APP_VERSION),
        model_version=current_model_version(),
        applied_rule_version=str(state.get("applied_rule_version") or ""),
        status=status,
    )


def event_for_app(event: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(event)
    if data.get("snapshot_path"):
        data["snapshot_url"] = app_snapshot_url(data["snapshot_path"])
    return data


def event_for_v1(event: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(event)
    if data.get("snapshot_path"):
        data["snapshot_url"] = v1_video_snapshot_url(data["snapshot_path"])
    asset = storage.get_media_asset_by_snapshot(int(data["snapshot_id"])) if data.get("snapshot_id") else None
    if asset:
        data["media_asset"] = video_service.media_asset_for_api(asset)
    return data


def current_device_session(
    x_device_token: str | None = Header(default=None, alias="X-GoHome-Device-Token"),
) -> Dict[str, Any]:
    if not x_device_token:
        raise HTTPException(status_code=401, detail="Device token required")
    session = storage.get_device_token_by_raw_token(x_device_token)
    if session is None:
        raise HTTPException(status_code=401, detail="Invalid device token")
    return session


def current_v1_device_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_device_token: str | None = Header(default=None, alias="X-GoHome-Device-Token"),
) -> Dict[str, Any]:
    token = x_device_token
    if credentials is not None and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    if not token:
        raise HTTPException(status_code=401, detail="Device token required")
    session = storage.get_device_token_by_raw_token(token)
    if session is None:
        raise HTTPException(status_code=401, detail="Invalid device token")
    return session


def v1_device_summary() -> Dict[str, Any]:
    identity = local_device_identity()
    token = storage.get_active_device_token_by_device(identity["device_id"])
    return {
        "device_id": identity["device_id"],
        "device_name": identity["device_name"],
        "device_type": identity["device_type"],
        "lan_ip": identity["lan_ip"],
        "api_port": identity["api_port"],
        "worker_running": worker.is_running,
        "app_version": package_service.current_app_version(default_version=APP_VERSION),
        "model_version": current_model_version(),
        "detector_backend": settings.detector_backend,
        "token": token,
    }


def v1_event_summary(event: Dict[str, Any]) -> Dict[str, Any]:
    data = event_for_v1(event)
    return {
        "id": data["id"],
        "type": data["type"],
        "summary": data["summary"],
        "level": data["level"],
        "room": data.get("room") or "",
        "camera_id": data.get("camera_id"),
        "camera_name": data.get("camera_name"),
        "occurred_at": data["occurred_at"],
        "acknowledged": data["acknowledged"],
        "snapshot_url": data.get("snapshot_url"),
        "candidate_status": data.get("candidate_status"),
        "payload": data.get("payload") or {},
        "media_asset": data.get("media_asset"),
    }


def notification_delivery_status(result: Dict[str, Any]) -> str:
    if result.get("sent"):
        return "sent"
    if result.get("channel") == "off":
        return "skipped"
    return "failed"


def notification_recipient() -> str:
    channel = settings.notify_channel
    if channel == "webhook":
        return settings.generic_webhook_url
    if channel == "feishu":
        return settings.feishu_webhook
    if channel == "bark":
        return settings.bark_url
    if channel == "telegram":
        return settings.telegram_chat_id
    return ""


def dispatch_notification(
    *,
    family_id: int,
    title: str,
    body: str,
    extra: Dict[str, Any] | None = None,
    event_id: int | None = None,
) -> Dict[str, Any]:
    payload_extra = public_pilot_service.enrich_notification_extra(
        family_id=family_id,
        extra=extra or {},
        event_id=event_id,
        preferred_region=str((extra or {}).get("preferred_region") or ""),
    )
    result = notifier.send(title, body, payload_extra)
    result["links"] = payload_extra.get("public_links") or {}
    result["open_url"] = payload_extra.get("open_url") or ""
    status = notification_delivery_status(result)
    delivered_at = datetime.now(timezone.utc).isoformat() if status == "sent" else None
    delivery = storage.create_notification_delivery(
        family_id=family_id,
        event_id=event_id,
        channel=str(result.get("channel") or settings.notify_channel or "off"),
        title=title,
        body=body,
        recipient=notification_recipient(),
        status=status,
        response=result,
        delivered_at=delivered_at,
    )
    return delivery


def current_model_version() -> str:
    default_version = str(settings.yolo_model or "") if settings.detector_backend == "yolo" else str(settings.detector_backend or "")
    return package_service.current_model_version(default_version=default_version)


def resolve_accessible_family_id(user: Dict[str, Any], device_id: str) -> int:
    bound_family_ids = storage.list_device_bound_family_ids(device_id)
    user_family_ids = storage.list_user_family_ids(int(user["id"]))
    accessible_family_ids = sorted(set(bound_family_ids) & set(user_family_ids))
    if not accessible_family_ids:
        raise HTTPException(status_code=403, detail="You do not have access to this device")
    return int(accessible_family_ids[0])


def resolve_user_family_id(user: Dict[str, Any], requested_family_id: int | None = None) -> int:
    user_family_ids = sorted(set(storage.list_user_family_ids(int(user["id"]))))
    if requested_family_id is not None:
        family_id = int(requested_family_id)
        if family_id not in user_family_ids:
            raise HTTPException(status_code=403, detail="You are not a member of this family")
        return family_id
    if not user_family_ids:
        raise HTTPException(status_code=400, detail="Please create or join a family first")
    return int(user_family_ids[0])


def build_device_sync_view(device_id: str, family_id: int) -> Dict[str, Any]:
    state = storage.ensure_device_sync_state(device_id, family_id)
    current_rules = storage.get_rules()
    runtime = worker.runtime_status()
    latest_app_execution = package_service.execution_for_api(execution) if (execution := storage.get_latest_package_execution(
        family_id=family_id,
        device_id=device_id,
        package_type="app",
    )) else None
    latest_model_execution = package_service.execution_for_api(execution) if (execution := storage.get_latest_package_execution(
        family_id=family_id,
        device_id=device_id,
        package_type="model",
    )) else None
    return {
        "device_id": device_id,
        "family_id": int(family_id),
        "current": {
            "app_version": package_service.current_app_version(default_version=APP_VERSION),
            "model_version": current_model_version(),
            "rule_version": current_rules.get("updated_at", ""),
            "worker_running": worker.is_running,
            "runtime": runtime,
            "packages": {
                "app": package_service.read_current_manifest("app"),
                "model": package_service.read_current_manifest("model"),
            },
        },
        "target": {
            "app_version": state.get("desired_app_version", ""),
            "model_version": state.get("desired_model_version", ""),
            "rules": state.get("desired_rules") or {},
            "rule_version": state.get("desired_rule_version", ""),
            "config": state.get("desired_config") or {},
            "config_version": state.get("desired_config_version", ""),
        },
        "reported": {
            "app_version": state.get("reported_app_version", ""),
            "model_version": state.get("reported_model_version", ""),
            "applied_rule_version": state.get("applied_rule_version", ""),
            "status": state.get("reported_status") or {},
            "last_seen_at": state.get("last_seen_at"),
            "last_sync_at": state.get("last_sync_at"),
            "last_applied_at": state.get("last_applied_at"),
            "package_executions": {
                "app": latest_app_execution,
                "model": latest_model_execution,
            },
        },
    }


def sync_target_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "desired_app_version": str(state.get("desired_app_version") or ""),
        "desired_model_version": str(state.get("desired_model_version") or ""),
        "desired_rules": dict(state.get("desired_rules") or {}),
        "desired_rule_version": str(state.get("desired_rule_version") or ""),
        "desired_config": dict(state.get("desired_config") or {}),
        "desired_config_version": str(state.get("desired_config_version") or ""),
    }


def normalize_device_ids(values: list[str] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        clean = str(value or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def build_family_device_view(binding: Dict[str, Any], family_id: int) -> Dict[str, Any]:
    device_id = str(binding["device_id"])
    state = storage.ensure_device_sync_state(device_id, family_id)
    token = storage.get_active_device_token_by_device(device_id)
    return {
        "device_id": device_id,
        "device_name": binding.get("device_name") or device_id,
        "device_type": binding.get("device_type") or "edge-agent",
        "status": binding.get("status") or "unknown",
        "note": binding.get("note") or "",
        "bound_at": binding.get("bound_at"),
        "is_current_device": device_id == current_device_id(),
        "token": {
            "status": token.get("status") if token else "missing",
            "token_prefix": token.get("token_prefix") if token else "",
            "last_seen_at": token.get("last_seen_at") if token else None,
            "last_heartbeat_at": token.get("last_heartbeat_at") if token else None,
        },
        "sync": {
            "target": {
                "app_version": state.get("desired_app_version", ""),
                "model_version": state.get("desired_model_version", ""),
                "rules": state.get("desired_rules") or {},
                "rule_version": state.get("desired_rule_version", ""),
                "config": state.get("desired_config") or {},
                "config_version": state.get("desired_config_version", ""),
            },
            "reported": {
                "app_version": state.get("reported_app_version", ""),
                "model_version": state.get("reported_model_version", ""),
                "applied_rule_version": state.get("applied_rule_version", ""),
                "status": state.get("reported_status") or {},
                "last_seen_at": state.get("last_seen_at"),
                "last_sync_at": state.get("last_sync_at"),
                "last_applied_at": state.get("last_applied_at"),
            },
        },
    }


def list_family_devices_view(family_id: int, device_ids: list[str] | None = None) -> list[Dict[str, Any]]:
    allowed = set(normalize_device_ids(device_ids))
    devices: list[Dict[str, Any]] = []
    for binding in storage.list_family_device_bindings(family_id):
        device_id = str(binding["device_id"])
        if allowed and device_id not in allowed:
            continue
        devices.append(build_family_device_view(binding, family_id))
    return devices


def validate_rollout_patch(
    *,
    desired_app_version: str,
    desired_model_version: str,
    rules_patch: Dict[str, Any],
    config_patch: Dict[str, Any],
) -> None:
    if desired_app_version.strip() or desired_model_version.strip() or rules_patch or config_patch:
        return
    raise HTTPException(status_code=400, detail="Rollout target is empty")


def apply_rollout_to_devices(
    *,
    family_id: int,
    device_ids: list[str],
    rollout: Dict[str, Any],
    rollout_version: str,
) -> None:
    rules_patch = dict(rollout.get("rules_patch") or {})
    config_patch = dict(rollout.get("config_patch") or {})
    previous_targets = rollout.get("previous_targets") or {}
    for device_id in normalize_device_ids(device_ids):
        previous_target = dict(previous_targets.get(device_id) or sync_target_snapshot(storage.ensure_device_sync_state(device_id, family_id)))
        desired_rules = dict(previous_target.get("desired_rules") or {})
        desired_rule_version = str(previous_target.get("desired_rule_version") or "")
        if rules_patch:
            desired_rules = storage.merge_rules_patch(rules_patch, base=desired_rules or storage.get_rules())
            desired_rule_version = rollout_version
        desired_config = dict(previous_target.get("desired_config") or {})
        desired_config_version = str(previous_target.get("desired_config_version") or "")
        if config_patch:
            desired_config.update({key: value for key, value in config_patch.items() if value is not None})
            desired_config_version = rollout_version
        storage.set_device_sync_target(
            device_id=device_id,
            family_id=family_id,
            desired_app_version=str(rollout.get("target_app_version") or previous_target.get("desired_app_version") or ""),
            desired_model_version=str(rollout.get("target_model_version") or previous_target.get("desired_model_version") or ""),
            desired_rules=desired_rules,
            desired_rule_version=desired_rule_version,
            desired_config=desired_config,
            desired_config_version=desired_config_version,
        )


def rollback_rollout_devices(
    *,
    family_id: int,
    device_ids: list[str],
    rollout: Dict[str, Any],
) -> None:
    previous_targets = rollout.get("previous_targets") or {}
    for device_id in normalize_device_ids(device_ids):
        previous_target = dict(previous_targets.get(device_id) or {})
        if not previous_target:
            continue
        storage.set_device_sync_target(
            device_id=device_id,
            family_id=family_id,
            desired_app_version=str(previous_target.get("desired_app_version") or ""),
            desired_model_version=str(previous_target.get("desired_model_version") or ""),
            desired_rules=dict(previous_target.get("desired_rules") or {}),
            desired_rule_version=str(previous_target.get("desired_rule_version") or ""),
            desired_config=dict(previous_target.get("desired_config") or {}),
            desired_config_version=str(previous_target.get("desired_config_version") or ""),
        )


def device_rollout_for_api(rollout: Dict[str, Any]) -> Dict[str, Any]:
    family_id = int(rollout["family_id"])
    scope_device_ids = normalize_device_ids(rollout.get("scope_device_ids") or [])
    canary_device_ids = set(normalize_device_ids(rollout.get("canary_device_ids") or []))
    applied_device_ids = set(normalize_device_ids(rollout.get("applied_device_ids") or []))
    rolled_back_device_ids = set(normalize_device_ids(rollout.get("rolled_back_device_ids") or []))
    devices = list_family_devices_view(family_id, scope_device_ids)
    for device in devices:
        device_id = str(device["device_id"])
        if device_id in rolled_back_device_ids:
            rollout_status = "rolled_back"
        elif device_id in applied_device_ids:
            rollout_status = "applied"
        else:
            rollout_status = "pending"
        rollout_phase = "canary" if device_id in canary_device_ids else "remaining"
        if rollout_status == "applied" and rollout_phase != "canary":
            rollout_phase = "promoted"
        device["rollout"] = {
            "status": rollout_status,
            "phase": rollout_phase,
        }
    return {
        "id": int(rollout["id"]),
        "family_id": family_id,
        "title": rollout.get("title") or "",
        "rollout_mode": rollout.get("rollout_mode") or "canary",
        "status": rollout.get("status") or "draft",
        "patch": {
            "app_version": rollout.get("target_app_version") or "",
            "model_version": rollout.get("target_model_version") or "",
            "rules": rollout.get("rules_patch") or {},
            "config": rollout.get("config_patch") or {},
        },
        "scope_device_ids": scope_device_ids,
        "canary_device_ids": sorted(canary_device_ids),
        "applied_device_ids": sorted(applied_device_ids),
        "rolled_back_device_ids": sorted(rolled_back_device_ids),
        "summary": {
            "scope_count": len(scope_device_ids),
            "applied_count": len(applied_device_ids),
            "rolled_back_count": len(rolled_back_device_ids),
            "remaining_count": len([device_id for device_id in scope_device_ids if device_id not in applied_device_ids]),
        },
        "devices": devices,
        "created_by_user_id": int(rollout["created_by_user_id"]),
        "created_at": rollout.get("created_at"),
        "updated_at": rollout.get("updated_at"),
        "promoted_at": rollout.get("promoted_at"),
        "rolled_back_at": rollout.get("rolled_back_at"),
    }


def get_rollout_for_user(rollout_id: int, user: Dict[str, Any]) -> Dict[str, Any]:
    rollout = storage.get_device_rollout(rollout_id)
    if rollout is None:
        raise HTTPException(status_code=404, detail="Device rollout not found")
    if not storage.is_family_member(int(rollout["family_id"]), int(user["id"])):
        raise HTTPException(status_code=403, detail="You are not a member of this family")
    return rollout


settings.ensure_dirs()
storage = Storage(settings.db_path)
camera_agent = CameraAgent(settings.snapshot_dir)
detect_agent = DetectAgent(
    black_brightness_threshold=settings.black_brightness_threshold,
    black_contrast_threshold=settings.black_contrast_threshold,
    motion_threshold=settings.motion_threshold,
    detector_backend=settings.detector_backend,
    yolo_model=settings.yolo_model,
    yolo_confidence=settings.yolo_confidence,
)
notifier = Notifier(settings)
event_agent = EventAgent(storage, notifier, settings.event_throttle_seconds)
worker = EdgeWorker(storage, camera_agent, detect_agent, event_agent)
video_distribution_service = VideoDistributionService(
    storage=storage,
    settings=settings,
    current_device_identity_resolver=local_device_identity,
)
object_storage_service = ObjectStorageService(storage=storage, settings=settings, distribution=video_distribution_service)
package_service = PackageService(storage=storage, settings=settings, object_storage=object_storage_service)
app_runtime_guard = AppRuntimeGuardService(
    settings=settings,
    current_manifest_loader=lambda: package_service.read_current_manifest("app"),
)
edge_bootstrap_service = EdgeBootstrapService(settings=settings)
public_pilot_service = PublicPilotService(settings=settings, distribution=video_distribution_service)
apns_relay_service = APNSRelayService(settings=settings)
app_push_service = AppPushService(
    storage=storage,
    settings=settings,
    public_pilot=public_pilot_service,
    apns_relay=apns_relay_service,
)
package_service.runtime_guard = app_runtime_guard
video_service = VideoService(
    storage=storage,
    settings=settings,
    camera_agent=camera_agent,
    object_storage=object_storage_service,
    distribution=video_distribution_service,
    current_device_id_resolver=current_device_id,
)

APP_VERSION = "0.1.0"
app = FastAPI(title="gohome edge-agent", version=APP_VERSION)
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
        media_user_resolver=lambda access_token, credentials: current_user_for_media(
            access_token=access_token,
            credentials=credentials,
        ),
    )
)
app.include_router(
    build_object_storage_router(
        object_storage_service,
        current_user_dep=current_user,
    )
)
app.mount("/snapshots", StaticFiles(directory=str(settings.snapshot_dir)), name="snapshots")
app.mount("/admin", StaticFiles(directory=str(settings.admin_dir), html=True), name="admin")
app.mount("/ui", StaticFiles(directory=str(settings.frontend_dir), html=True), name="ui")


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/ui/index.html")


@app.on_event("startup")
def on_startup() -> None:
    storage.init_schema()
    if not settings.disable_worker:
        worker.start()
    app_runtime_guard.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    app_runtime_guard.stop()
    worker.stop()


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "gohome-edge-agent",
        "worker_running": worker.is_running,
        "lan_url": f"http://{local_ip()}:{settings.port}",
        "distribution": video_distribution_service.service_info(),
        "app_runtime": app_runtime_guard.status(),
    }


@app.get("/api/device")
def device() -> Dict[str, Any]:
    device_identity = local_device_identity()
    return {
        "device_id": device_identity["device_id"],
        "name": socket.gethostname(),
        "lan_ip": local_ip(),
        "api_port": settings.port,
        "api_base_url": f"http://{local_ip()}:{settings.port}",
        "data_dir": str(settings.data_dir),
        "db_path": str(settings.db_path),
        "snapshot_dir": str(settings.snapshot_dir),
        "notify_channel": settings.notify_channel,
        "detector_backend": settings.detector_backend,
        "yolo_model": settings.yolo_model if settings.detector_backend == "yolo" else None,
        "worker_running": worker.is_running,
        "video_distribution": video_distribution_service.service_info(),
        "app_runtime": app_runtime_guard.status(),
    }


@app.post("/api/auth/register")
def register_user(payload: UserRegister) -> Dict[str, Any]:
    try:
        user = storage.create_user(payload.email, payload.password, payload.display_name)
    except ValueError as exc:
        detail = str(exc)
        status_code = 409 if "already registered" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    session = storage.create_auth_session(int(user["id"]))
    return {"user": user, **session}


@app.post("/api/auth/login")
def login_user(payload: UserLogin) -> Dict[str, Any]:
    user = storage.authenticate_user(payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    session = storage.create_auth_session(int(user["id"]))
    return {"user": user, **session}


@app.get("/api/users/me")
def get_current_user(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    return user


@app.post("/api/v1/identity/register")
def v1_register_user(payload: UserRegister) -> Dict[str, Any]:
    return register_user(payload)


@app.post("/api/v1/identity/login")
def v1_login_user(payload: UserLogin) -> Dict[str, Any]:
    return login_user(payload)


@app.get("/api/v1/identity/me")
def v1_current_user(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    return user


@app.post("/api/families")
def create_family(payload: FamilyCreate, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    try:
        return storage.create_family(payload.name, int(user["id"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/families/mine")
def list_my_families(user: Dict[str, Any] = Depends(current_user)) -> list[Dict[str, Any]]:
    return storage.list_user_families(int(user["id"]))


@app.post("/api/v1/households")
def v1_create_household(payload: FamilyCreate, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    return create_family(payload, user)


@app.get("/api/v1/households/mine")
def v1_list_households(user: Dict[str, Any] = Depends(current_user)) -> list[Dict[str, Any]]:
    return list_my_families(user)


@app.post("/api/device-bindings")
def bind_device(
    payload: DeviceBindingCreate,
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    device_identity = local_device_identity()
    device_id = (payload.device_id or device_identity["device_id"]).strip()
    device_name = (payload.device_name or device_identity["device_name"]).strip()
    metadata = {
        **device_identity,
        **payload.metadata,
    }
    try:
        return storage.create_device_binding(
            family_id=payload.family_id,
            bound_by_user_id=int(user["id"]),
            device_id=device_id,
            device_name=device_name,
            device_type=payload.device_type,
            note=payload.note,
            metadata=metadata,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 403 if "not a member" in detail else 409 if "already bound" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@app.get("/api/device-bindings")
def list_device_bindings(family_id: int, user: Dict[str, Any] = Depends(current_user)) -> list[Dict[str, Any]]:
    if not storage.is_family_member(family_id, int(user["id"])):
        raise HTTPException(status_code=403, detail="You are not a member of this family")
    return storage.list_family_device_bindings(family_id)


@app.post("/api/device/binding-codes")
def create_device_binding_code(
    payload: DeviceBindingCodeCreate,
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    try:
        return storage.create_device_binding_code(
            family_id=payload.family_id,
            issued_by_user_id=int(user["id"]),
            expires_in_minutes=payload.expires_in_minutes,
            metadata={"note": payload.note},
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 403 if "not a member" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@app.get("/api/device/binding-codes")
def list_device_binding_codes(
    family_id: int,
    user: Dict[str, Any] = Depends(current_user),
) -> list[Dict[str, Any]]:
    if not storage.is_family_member(family_id, int(user["id"])):
        raise HTTPException(status_code=403, detail="You are not a member of this family")
    return storage.list_device_binding_codes(family_id)


@app.post("/api/device/token/exchange")
def exchange_device_token(payload: DeviceTokenExchange) -> Dict[str, Any]:
    device_identity = local_device_identity()
    device_id = (payload.device_id or device_identity["device_id"]).strip()
    device_name = (payload.device_name or device_identity["device_name"]).strip()
    device_type = payload.device_type.strip() or device_identity["device_type"]
    try:
        binding_code = storage.consume_device_binding_code(payload.code, device_id=device_id)
        family_id = int(binding_code["family_id"])
        if storage.get_device_binding(family_id, device_id) is None:
            storage.create_device_binding(
                family_id=family_id,
                bound_by_user_id=int(binding_code["issued_by_user_id"]),
                device_id=device_id,
                device_name=device_name,
                device_type=device_type,
                note=payload.note or binding_code.get("metadata", {}).get("note", ""),
                metadata={
                    **device_identity,
                    **payload.metadata,
                },
            )
        token = storage.issue_device_token(
            family_id=family_id,
            device_id=device_id,
            device_name=device_name,
            device_type=device_type,
            issued_by_code_id=int(binding_code["id"]),
            metadata={
                **device_identity,
                **payload.metadata,
            },
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 409 if "already bound" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc

    if device_id == current_device_id():
        write_local_device_token(str(token["device_token"]))

    return {
        "family_id": family_id,
        "device_id": device_id,
        "device_name": device_name,
        **token,
    }


@app.post("/api/device/heartbeat")
def device_heartbeat(
    payload: DeviceHeartbeatIn,
    request: Request,
    device_session: Dict[str, Any] = Depends(current_device_session),
) -> Dict[str, Any]:
    heartbeat = storage.record_device_heartbeat(
        token_id=int(device_session["id"]),
        heartbeat=model_dump(payload),
        remote_ip=request.client.host if request.client else None,
    )
    return {
        "ok": True,
        "device_id": heartbeat["device_id"],
        "family_id": heartbeat["family_id"],
        "last_heartbeat_at": heartbeat["last_heartbeat_at"],
    }


@app.post("/api/device/heartbeat/self")
def self_device_heartbeat(
    payload: DeviceHeartbeatIn,
    request: Request,
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    require_device_access(user)
    local_token = read_local_device_token()
    if not local_token:
        raise HTTPException(status_code=400, detail="Current device has no local device token")
    session = storage.get_device_token_by_raw_token(local_token)
    if session is None:
        raise HTTPException(status_code=401, detail="Local device token is invalid")
    heartbeat = storage.record_device_heartbeat(
        token_id=int(session["id"]),
        heartbeat=model_dump(payload),
        remote_ip=request.client.host if request.client else None,
    )
    return {
        "ok": True,
        "device_id": heartbeat["device_id"],
        "family_id": heartbeat["family_id"],
        "last_heartbeat_at": heartbeat["last_heartbeat_at"],
    }


@app.get("/api/device/auth-status")
def device_auth_status(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    device_id = current_device_id()
    token = storage.get_active_device_token_by_device(device_id)
    bound_family_ids = storage.list_device_bound_family_ids(device_id)
    user_family_ids = storage.list_user_family_ids(int(user["id"]))
    accessible_family_ids = sorted(set(bound_family_ids) & set(user_family_ids))
    return {
        "device_id": device_id,
        "device_name": local_device_identity()["device_name"],
        "bound_family_ids": bound_family_ids,
        "accessible_family_ids": accessible_family_ids,
        "local_token_saved": bool(read_local_device_token()),
        "token": token,
    }


@app.get("/api/v1/devices/current")
def v1_current_device(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    device_id = require_device_access(user)
    summary = v1_device_summary()
    summary["accessible_family_ids"] = sorted(
        set(storage.list_device_bound_family_ids(device_id)) & set(storage.list_user_family_ids(int(user["id"])))
    )
    return summary


@app.get("/api/v1/devices/current/sync-state")
def v1_current_device_sync_state(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    device_id = require_device_access(user)
    family_id = resolve_accessible_family_id(user, device_id)
    return build_device_sync_view(device_id, family_id)


@app.patch("/api/v1/devices/current/sync-target")
def v1_update_current_device_sync_target(
    payload: V1DeviceSyncTargetUpdate,
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    device_id = require_device_access(user)
    family_id = resolve_accessible_family_id(user, device_id)
    storage.update_device_sync_target(
        device_id=device_id,
        family_id=family_id,
        desired_app_version=payload.desired_app_version,
        desired_model_version=payload.desired_model_version,
        rules_patch=model_dump(payload.rules) if payload.rules is not None else None,
        config_patch=payload.config,
    )
    return build_device_sync_view(device_id, family_id)


@app.get("/api/v1/devices")
def v1_list_devices(family_id: int, user: Dict[str, Any] = Depends(current_user)) -> list[Dict[str, Any]]:
    if not storage.is_family_member(family_id, int(user["id"])):
        raise HTTPException(status_code=403, detail="You are not a member of this family")
    return list_family_devices_view(family_id)


@app.get("/api/v1/package-releases")
def v1_list_package_releases(
    family_id: int,
    package_type: str = "",
    limit: int = 20,
    user: Dict[str, Any] = Depends(current_user),
) -> list[Dict[str, Any]]:
    return package_service.list_releases(
        family_id=family_id,
        package_type=package_type,
        limit=max(1, min(limit, 100)),
        user=user,
    )


@app.post("/api/v1/package-releases")
def v1_create_package_release(
    payload: V1PackageReleaseCreate,
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    return package_service.create_release(payload, user=user)


@app.get("/api/v1/package-releases/{release_id}")
def v1_get_package_release(release_id: int, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    return package_service.package_release_for_api(package_service.get_release_for_user(release_id, user))


@app.post("/api/v1/package-releases/{release_id}/download-links")
def v1_create_package_download_link(
    release_id: int,
    payload: V1PackageDownloadLinkCreate,
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    return package_service.create_download_link(release_id, user=user, expires_in_seconds=payload.expires_in_seconds)


@app.get("/api/v1/package-executions")
def v1_list_package_executions(
    family_id: int,
    device_id: str = "",
    limit: int = 20,
    user: Dict[str, Any] = Depends(current_user),
) -> list[Dict[str, Any]]:
    return package_service.list_executions(
        family_id=family_id,
        device_id=device_id,
        limit=max(1, min(limit, 100)),
        user=user,
    )


@app.post("/api/v1/devices/current/upgrade-run")
def v1_run_current_device_upgrade(
    payload: V1DeviceUpgradeRun,
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    device_id = require_device_access(user)
    family_id = resolve_accessible_family_id(user, device_id)
    result = package_service.run_pending_upgrades(
        family_id=family_id,
        device_id=device_id,
        target=build_device_sync_view(device_id, family_id)["target"],
        package_types=payload.package_types,
    )
    record_local_package_execution(device_id, family_id)
    result["sync"] = build_device_sync_view(device_id, family_id)
    return result


@app.post("/api/v1/device/upgrade-run")
def v1_device_upgrade_run(
    payload: V1DeviceUpgradeRun,
    device_session: Dict[str, Any] = Depends(current_v1_device_session),
) -> Dict[str, Any]:
    device_id = str(device_session["device_id"])
    family_id = int(device_session["family_id"])
    result = package_service.run_pending_upgrades(
        family_id=family_id,
        device_id=device_id,
        target=build_device_sync_view(device_id, family_id)["target"],
        package_types=payload.package_types,
    )
    record_local_package_execution(device_id, family_id)
    result["sync"] = build_device_sync_view(device_id, family_id)
    return result


@app.get("/api/v1/runtime/app-status")
def v1_runtime_app_status(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    require_device_access(user)
    return app_runtime_guard.status()


@app.post("/api/v1/runtime/app/restart")
def v1_runtime_app_restart(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    require_device_access(user)
    try:
        return app_runtime_guard.restart_current()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/runtime/app/stop")
def v1_runtime_app_stop(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    require_device_access(user)
    return app_runtime_guard.stop_runtime(clear_should_run=True)


@app.get("/api/v1/runtime/edge-service")
def v1_runtime_edge_service_status(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    require_device_access(user)
    return edge_bootstrap_service.status()


@app.get("/api/v1/public-pilot/status")
def v1_public_pilot_status(
    preferred_region: str = Query(default=""),
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    device_id = require_device_access(user)
    family_id = resolve_accessible_family_id(user, device_id)
    return public_pilot_service.status(family_id=family_id, preferred_region=preferred_region)


@app.post("/api/v1/runtime/edge-service/install")
def v1_runtime_edge_service_install(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    require_device_access(user)
    try:
        return edge_bootstrap_service.install()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/runtime/edge-service/reload")
def v1_runtime_edge_service_reload(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    require_device_access(user)
    try:
        return edge_bootstrap_service.reload()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/runtime/edge-service/uninstall")
def v1_runtime_edge_service_uninstall(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    require_device_access(user)
    try:
        return edge_bootstrap_service.uninstall()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/device-rollouts")
def v1_list_device_rollouts(
    family_id: int,
    limit: int = 20,
    user: Dict[str, Any] = Depends(current_user),
) -> list[Dict[str, Any]]:
    if not storage.is_family_member(family_id, int(user["id"])):
        raise HTTPException(status_code=403, detail="You are not a member of this family")
    return [device_rollout_for_api(rollout) for rollout in storage.list_device_rollouts(family_id, limit=max(1, min(limit, 100)))]


@app.post("/api/v1/device-rollouts")
def v1_create_device_rollout(
    payload: V1DeviceRolloutCreate,
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    family_id = int(payload.family_id)
    if not storage.is_family_member(family_id, int(user["id"])):
        raise HTTPException(status_code=403, detail="You are not a member of this family")
    rules_patch = model_dump(payload.rules) if payload.rules is not None else {}
    config_patch = dict(payload.config or {})
    validate_rollout_patch(
        desired_app_version=payload.desired_app_version,
        desired_model_version=payload.desired_model_version,
        rules_patch=rules_patch,
        config_patch=config_patch,
    )
    family_bindings = storage.list_family_device_bindings(family_id)
    family_device_ids = [str(binding["device_id"]) for binding in family_bindings]
    scope_device_ids = normalize_device_ids(payload.device_ids) or family_device_ids
    if not scope_device_ids:
        raise HTTPException(status_code=400, detail="No devices available for rollout")
    invalid_scope_ids = [device_id for device_id in scope_device_ids if device_id not in family_device_ids]
    if invalid_scope_ids:
        raise HTTPException(status_code=400, detail=f"Unknown rollout devices: {', '.join(invalid_scope_ids)}")
    if payload.rollout_mode == "full":
        canary_device_ids = list(scope_device_ids)
    else:
        canary_device_ids = normalize_device_ids(payload.canary_device_ids) or [scope_device_ids[0]]
    invalid_canary_ids = [device_id for device_id in canary_device_ids if device_id not in scope_device_ids]
    if invalid_canary_ids:
        raise HTTPException(status_code=400, detail=f"Unknown canary devices: {', '.join(invalid_canary_ids)}")
    previous_targets = {
        device_id: sync_target_snapshot(storage.ensure_device_sync_state(device_id, family_id))
        for device_id in scope_device_ids
    }
    initial_applied_device_ids = list(canary_device_ids)
    rollout = storage.create_device_rollout(
        family_id=family_id,
        title=payload.title,
        rollout_mode=payload.rollout_mode,
        status="completed" if len(initial_applied_device_ids) == len(scope_device_ids) else "canary",
        target_app_version=payload.desired_app_version,
        target_model_version=payload.desired_model_version,
        rules_patch=rules_patch,
        config_patch=config_patch,
        scope_device_ids=scope_device_ids,
        canary_device_ids=canary_device_ids,
        applied_device_ids=initial_applied_device_ids,
        rolled_back_device_ids=[],
        previous_targets=previous_targets,
        created_by_user_id=int(user["id"]),
    )
    apply_rollout_to_devices(
        family_id=family_id,
        device_ids=initial_applied_device_ids,
        rollout=rollout,
        rollout_version=str(rollout.get("created_at") or datetime.now(timezone.utc).isoformat()),
    )
    return device_rollout_for_api(rollout)


@app.get("/api/v1/device-rollouts/{rollout_id}")
def v1_get_device_rollout(rollout_id: int, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    return device_rollout_for_api(get_rollout_for_user(rollout_id, user))


@app.post("/api/v1/device-rollouts/{rollout_id}/promote")
def v1_promote_device_rollout(
    rollout_id: int,
    payload: V1DeviceRolloutPromote,
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    rollout = get_rollout_for_user(rollout_id, user)
    scope_device_ids = normalize_device_ids(rollout.get("scope_device_ids") or [])
    applied_device_ids = normalize_device_ids(rollout.get("applied_device_ids") or [])
    remaining_device_ids = [device_id for device_id in scope_device_ids if device_id not in set(applied_device_ids)]
    target_device_ids = normalize_device_ids(payload.device_ids) or remaining_device_ids
    invalid_target_ids = [device_id for device_id in target_device_ids if device_id not in remaining_device_ids]
    if invalid_target_ids:
        raise HTTPException(status_code=400, detail=f"Devices are not promotable: {', '.join(invalid_target_ids)}")
    if not target_device_ids:
        raise HTTPException(status_code=400, detail="No devices left to promote")
    apply_rollout_to_devices(
        family_id=int(rollout["family_id"]),
        device_ids=target_device_ids,
        rollout=rollout,
        rollout_version=datetime.now(timezone.utc).isoformat(),
    )
    merged_applied_device_ids = normalize_device_ids(applied_device_ids + target_device_ids)
    updated_rollout = storage.update_device_rollout_state(
        rollout_id,
        status="completed" if len(merged_applied_device_ids) == len(scope_device_ids) else "promoting",
        applied_device_ids=merged_applied_device_ids,
        promoted_at=datetime.now(timezone.utc).isoformat(),
    )
    return device_rollout_for_api(updated_rollout)


@app.post("/api/v1/device-rollouts/{rollout_id}/rollback")
def v1_rollback_device_rollout(
    rollout_id: int,
    payload: V1DeviceRolloutRollback,
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    rollout = get_rollout_for_user(rollout_id, user)
    applied_device_ids = normalize_device_ids(rollout.get("applied_device_ids") or [])
    target_device_ids = normalize_device_ids(payload.device_ids) or applied_device_ids
    invalid_target_ids = [device_id for device_id in target_device_ids if device_id not in applied_device_ids]
    if invalid_target_ids:
        raise HTTPException(status_code=400, detail=f"Devices are not rollback targets: {', '.join(invalid_target_ids)}")
    if not target_device_ids:
        raise HTTPException(status_code=400, detail="No devices available to rollback")
    rollback_rollout_devices(
        family_id=int(rollout["family_id"]),
        device_ids=target_device_ids,
        rollout=rollout,
    )
    updated_rollout = storage.update_device_rollout_state(
        rollout_id,
        status="rolled_back" if len(target_device_ids) == len(applied_device_ids) else "partially_rolled_back",
        rolled_back_device_ids=normalize_device_ids((rollout.get("rolled_back_device_ids") or []) + target_device_ids),
        rolled_back_at=datetime.now(timezone.utc).isoformat(),
    )
    return device_rollout_for_api(updated_rollout)


@app.post("/api/v1/device/heartbeat")
def v1_device_heartbeat(
    payload: DeviceHeartbeatIn,
    request: Request,
    device_session: Dict[str, Any] = Depends(current_v1_device_session),
) -> Dict[str, Any]:
    heartbeat = storage.record_device_heartbeat(
        token_id=int(device_session["id"]),
        heartbeat=model_dump(payload),
        remote_ip=request.client.host if request.client else None,
    )
    return {
        "ok": True,
        "device_id": heartbeat["device_id"],
        "family_id": heartbeat["family_id"],
        "last_heartbeat_at": heartbeat["last_heartbeat_at"],
    }


@app.post("/api/v1/device/sync")
def v1_device_sync(
    payload: V1DeviceSyncReport,
    device_session: Dict[str, Any] = Depends(current_v1_device_session),
) -> Dict[str, Any]:
    device_id = str(device_session["device_id"])
    family_id = int(device_session["family_id"])
    runtime = payload.runtime or {}
    merged_status = {
        **(payload.status or {}),
        "worker_running": payload.worker_running,
        "runtime": runtime,
        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
    }
    state = storage.report_device_sync(
        device_id=device_id,
        family_id=family_id,
        app_version=payload.app_version,
        model_version=payload.model_version,
        applied_rule_version=payload.applied_rule_version,
        status=merged_status,
    )

    desired_rules = state.get("desired_rules") or {}
    desired_rule_version = str(state.get("desired_rule_version") or "")
    current_rules = storage.get_rules()
    applied_rules = current_rules
    rules_applied = False
    if desired_rules and desired_rule_version and desired_rule_version != str(current_rules.get("updated_at") or ""):
        applied_rules = persist_rules_update(desired_rules)
        state = storage.mark_device_sync_rules_applied(device_id, str(applied_rules.get("updated_at") or ""))
        storage.report_device_sync(
            device_id=device_id,
            family_id=family_id,
            app_version=payload.app_version,
            model_version=payload.model_version,
            applied_rule_version=str(applied_rules.get("updated_at") or ""),
            status={
                **merged_status,
                "applied_rule_version": str(applied_rules.get("updated_at") or ""),
            },
        )
        rules_applied = True

    return {
        "ok": True,
        "rules_applied": rules_applied,
        "sync": build_device_sync_view(device_id, family_id),
    }


@app.post("/api/v1/device/events")
def v1_ingest_device_event(
    payload: V1DeviceEventIngest,
    device_session: Dict[str, Any] = Depends(current_v1_device_session),
) -> Dict[str, Any]:
    device_id = str(device_session["device_id"])
    existing = storage.get_event_ingest(device_id, payload.idempotency_key)
    if existing is not None:
        event = storage.get_event(int(existing["event_id"]))
        if event is None:
            raise HTTPException(status_code=409, detail="Event ingest points to missing event")
        return {
            "accepted": True,
            "deduplicated": True,
            "idempotency_key": payload.idempotency_key,
            "event": v1_event_summary(event),
        }

    camera_id = payload.camera_id
    if camera_id is not None and storage.get_camera(int(camera_id)) is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    snapshot = None
    normalized_snapshot_path = normalize_snapshot_reference(payload.snapshot_path)
    if normalized_snapshot_path:
        snapshot = storage.get_snapshot_by_path(normalized_snapshot_path)

    event_payload = {
        **payload.payload,
        "source": "device-api-v1",
        "ingested_by_device_id": device_id,
        "ingested_family_id": int(device_session["family_id"]),
        "idempotency_key": payload.idempotency_key,
    }
    event = storage.create_event(
        event_type=payload.event_type,
        summary=payload.summary,
        level=payload.level,
        camera_id=camera_id,
        room=payload.room,
        snapshot_id=snapshot["id"] if snapshot else None,
        payload=event_payload,
        occurred_at=payload.occurred_at,
    )
    media_asset = None
    if snapshot is not None:
        media_asset = video_service.promote_snapshot_media_asset(
            family_id=int(device_session["family_id"]),
            device_id=device_id,
            snapshot=snapshot,
            event_id=int(event["id"]),
            metadata={"event_id": int(event["id"]), "source": "device-event-ingest"},
        )
    rules = storage.get_rules()
    notification_delivery = None
    app_push_delivery = None
    if bool(rules.get("notification_enabled")):
        notification_delivery = dispatch_notification(
            family_id=int(device_session["family_id"]),
            event_id=int(event["id"]),
            title=f"想家了吗提醒：{event['summary']}",
            body=f"{event.get('room') or '家中'} · {event['summary']}",
            extra={
                "event_id": int(event["id"]),
                "event_type": event.get("type"),
                "level": event.get("level"),
                "occurred_at": event.get("occurred_at"),
                "media_asset_url": media_asset.get("storage_url") if media_asset else None,
            },
        )
        app_push_delivery = app_push_service.send_to_family(
            family_id=int(device_session["family_id"]),
            event_id=int(event["id"]),
            camera_id=camera_id,
            preferred_region=str(payload.payload.get("preferred_region") or ""),
            title=f"想家了吗提醒：{event['summary']}",
            body=f"{event.get('room') or '家中'} · {event['summary']}",
            extra={
                "event_type": event.get("type"),
                "level": event.get("level"),
                "occurred_at": event.get("occurred_at"),
                "media_asset_url": media_asset.get("storage_url") if media_asset else None,
            },
        )
    storage.bind_event_ingest(device_id, payload.idempotency_key, int(event["id"]))
    return {
        "accepted": True,
        "deduplicated": False,
        "idempotency_key": payload.idempotency_key,
        "event": v1_event_summary(event),
        "media_asset": media_asset,
        "notification_delivery": notification_delivery,
        "app_push_delivery": app_push_delivery,
    }


@app.post("/api/v1/device/media-assets")
def v1_create_device_media_asset(
    payload: V1MediaAssetCreate,
    device_session: Dict[str, Any] = Depends(current_v1_device_session),
) -> Dict[str, Any]:
    normalized_snapshot_path = normalize_snapshot_reference(payload.snapshot_path)
    if not normalized_snapshot_path:
        raise HTTPException(status_code=400, detail="snapshot_path is required")
    snapshot = storage.get_snapshot_by_path(normalized_snapshot_path)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    if payload.event_id is not None:
        event = storage.get_event(int(payload.event_id))
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")
    asset = video_service.promote_snapshot_media_asset(
        family_id=int(device_session["family_id"]),
        device_id=str(device_session["device_id"]),
        snapshot=snapshot,
        event_id=payload.event_id,
        content_type=payload.content_type,
        metadata=payload.metadata,
    )
    return {"created": True, "asset": asset}


@app.get("/api/v1/events")
def v1_list_events(
    limit: int = 50,
    acknowledged: bool | None = None,
    user: Dict[str, Any] = Depends(current_user),
) -> list[Dict[str, Any]]:
    require_device_access(user)
    events = storage.list_events(limit=max(1, min(limit, 200)), acknowledged=acknowledged)
    return [v1_event_summary(event) for event in events]


@app.get("/api/v1/events/{event_id}")
def v1_get_event(event_id: int, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    require_device_access(user)
    event = storage.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return v1_event_summary(event)


@app.patch("/api/v1/events/{event_id}")
def v1_update_event(
    event_id: int,
    patch: EventUpdate,
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    require_device_access(user)
    event = storage.update_event(event_id, model_dump(patch))
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return v1_event_summary(event)


@app.get("/api/v1/summary/today")
def v1_today_summary(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    require_device_access(user)
    return storage.daily_summary()


@app.get("/api/v1/notifications/deliveries")
def v1_notification_deliveries(
    limit: int = 20,
    user: Dict[str, Any] = Depends(current_user),
) -> list[Dict[str, Any]]:
    device_id = require_device_access(user)
    family_id = resolve_accessible_family_id(user, device_id)
    return storage.list_notification_deliveries(family_id, limit=max(1, min(limit, 100)))


@app.post("/api/v1/notifications/test")
def v1_notification_test(message: NotificationTest, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    device_id = require_device_access(user)
    family_id = resolve_accessible_family_id(user, device_id)
    extra = model_dump(message).get("extra") or {}
    if message.camera_id is not None:
        extra["camera_id"] = int(message.camera_id)
    if message.preferred_region:
        extra["preferred_region"] = str(message.preferred_region)
    if not bool(message.include_public_links):
        extra["open_url"] = ""
        extra["event_url"] = ""
        extra["watch_url"] = ""
        extra["events_url"] = ""
        extra["app_shell_url"] = ""
        extra["public_links"] = {}
    delivery = dispatch_notification(
        family_id=family_id,
        title=message.title,
        body=message.body,
        extra=extra,
        event_id=message.event_id,
    )
    return {"ok": True, "delivery": delivery}


@app.get("/api/v1/app/push-tokens")
def v1_app_push_tokens(
    family_id: int | None = Query(default=None, ge=1),
    user: Dict[str, Any] = Depends(current_user),
) -> list[Dict[str, Any]]:
    resolved_family_id = resolve_user_family_id(user, family_id)
    return app_push_service.list_tokens(user_id=int(user["id"]), family_id=resolved_family_id)


@app.post("/api/v1/app/push-tokens")
def v1_upsert_app_push_token(payload: V1AppPushTokenUpsert, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    family_id = resolve_user_family_id(user, payload.family_id)
    token = app_push_service.register_token(
        family_id=family_id,
        user_id=int(user["id"]),
        app_install_id=payload.app_install_id,
        platform=payload.platform,
        provider=payload.provider,
        push_token=payload.push_token,
        device_name=payload.device_name,
        app_version=payload.app_version,
        environment=payload.environment,
        metadata=payload.metadata,
    )
    return {"ok": True, "token": token, "provider": app_push_service.provider_status()}


@app.delete("/api/v1/app/push-tokens/{app_install_id}")
def v1_delete_app_push_token(app_install_id: str, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    deleted = app_push_service.revoke_token(user_id=int(user["id"]), app_install_id=app_install_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="App push token not found")
    return {"ok": True, "token": deleted}


@app.post("/api/v1/app/push-test")
def v1_app_push_test(payload: V1AppPushTest, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    family_id = resolve_user_family_id(user, payload.family_id)
    delivery = app_push_service.send_to_family(
        family_id=family_id,
        title=payload.title,
        body=payload.body,
        event_id=payload.event_id,
        camera_id=payload.camera_id,
        preferred_region=payload.preferred_region,
        extra=payload.extra,
    )
    return {"ok": True, "delivery": delivery, "provider": app_push_service.provider_status()}


@app.get("/api/v1/runtime/app-push-relay")
def v1_app_push_relay_status(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    require_device_access(user)
    return apns_relay_service.status()


@app.post("/api/internal/app-push/relay")
def internal_app_push_relay(
    payload: V1AppPushRelayRequest,
    authorization: str | None = Header(default=None),
) -> Dict[str, Any]:
    if not apns_relay_service.verify_internal_secret(authorization or ""):
        raise HTTPException(status_code=401, detail="Invalid app push relay secret")
    result = apns_relay_service.deliver(model_dump(payload))
    return {"ok": bool(result.get("sent")), "result": result}


@app.get("/api/cameras")
def list_cameras() -> list[Dict[str, Any]]:
    return storage.list_cameras()


@app.post("/api/cameras")
def create_camera(camera: CameraCreate) -> Dict[str, Any]:
    return storage.create_camera(model_dump(camera))


def capture_preview(camera_payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        rules = storage.get_rules()
        capture = camera_agent.capture_frame(camera_payload)
        analysis = detect_agent.analyze_frame_with_config(capture["frame"], config=rules)
        relative_path = f"preview/{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
        camera_agent.save_frame(capture["frame"], relative_path)
        return {
            "ok": True,
            "width": capture["width"],
            "height": capture["height"],
            "elapsed_ms": capture["elapsed_ms"],
            "source": capture["source"],
            "snapshot": {
                "image_path": relative_path,
                "image_url": f"/snapshots/{relative_path}",
                "person_count": analysis.get("person_count"),
                "captured_at": datetime.now().isoformat(),
            },
            "analysis": analysis,
        }
    except CameraError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/cameras/test-connection")
async def test_camera_connection(camera: CameraCreate) -> Dict[str, Any]:
    return await run_in_threadpool(capture_preview, model_dump(camera))


@app.get("/api/cameras/{camera_id}")
def get_camera(camera_id: int) -> Dict[str, Any]:
    camera = storage.get_camera(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


@app.patch("/api/cameras/{camera_id}")
def update_camera(camera_id: int, patch: CameraUpdate) -> Dict[str, Any]:
    camera = storage.update_camera(camera_id, model_dump(patch))
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


@app.delete("/api/cameras/{camera_id}")
def delete_camera(camera_id: int) -> Dict[str, Any]:
    deleted = storage.delete_camera(camera_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Camera not found")
    return {"deleted": True, "camera_id": camera_id}


def capture_and_store(camera_id: int) -> Dict[str, Any]:
    camera = storage.get_camera(camera_id, include_secret=True)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    try:
        rules = storage.get_rules()
        capture = camera_agent.capture_frame(camera)
        analysis = detect_agent.analyze_frame_with_config(capture["frame"], config=rules)
        relative_path = camera_agent.snapshot_relative_path(camera_id)
        camera_agent.save_frame(capture["frame"], relative_path)
        snapshot = storage.create_snapshot(
            camera_id=camera_id,
            image_path=relative_path,
            width=capture["width"],
            height=capture["height"],
            brightness=analysis["brightness"],
            motion_score=analysis["motion_score"],
            tags=analysis["tags"],
            person_count=analysis.get("person_count"),
            analysis=analysis,
        )
        storage.update_camera_status(camera_id, "online")
        return {
            "ok": True,
            "camera_id": camera_id,
            "width": capture["width"],
            "height": capture["height"],
            "elapsed_ms": capture["elapsed_ms"],
            "source": capture["source"],
            "snapshot": snapshot,
            "analysis": analysis,
        }
    except CameraError as exc:
        storage.update_camera_status(camera_id, "offline", str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def capture_with_pipeline(camera_id: int) -> Dict[str, Any]:
    camera = storage.get_camera(camera_id, include_secret=True)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    rules = storage.get_rules()
    result = worker.process_camera(camera, rules)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "Capture failed")
    return {
        "ok": True,
        "camera_id": camera_id,
        "snapshot": result.get("snapshot"),
        "analysis": result.get("analysis"),
        "detection_result": result.get("detection_result"),
        "evaluation": result.get("evaluation"),
    }


@app.post("/api/cameras/{camera_id}/test")
async def test_camera(camera_id: int) -> Dict[str, Any]:
    return await run_in_threadpool(capture_and_store, camera_id)


@app.post("/api/cameras/{camera_id}/capture")
async def capture_camera(camera_id: int) -> Dict[str, Any]:
    return await run_in_threadpool(capture_with_pipeline, camera_id)


@app.get("/api/cameras/{camera_id}/snapshot/latest")
def latest_camera_snapshot(camera_id: int, allow_missing: bool = False) -> Dict[str, Any]:
    if storage.get_camera(camera_id) is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    snapshot = storage.latest_snapshot(camera_id)
    if snapshot is None:
        if allow_missing:
            return {"camera_id": camera_id, "available": False}
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snapshot


@app.get("/api/cameras/{camera_id}/stream.mjpg")
def camera_mjpeg_stream(
    camera_id: int,
    fps: int = 5,
    width: int = 1280,
    height: int = 720,
    quality: int = 70,
    drop: int = 4,
) -> StreamingResponse:
    camera = storage.get_camera(camera_id, include_secret=True)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    fps = max(1, min(int(fps), 15))
    width = max(320, min(int(width), 1920))
    height = max(180, min(int(height), 1080))
    quality = max(35, min(int(quality), 95))
    drop = max(0, min(int(drop), 12))
    return StreamingResponse(
        camera_agent.mjpeg_frames(
            camera,
            fps=fps,
            jpeg_quality=quality,
            max_width=width,
            max_height=height,
            drop_stale_frames=drop,
        ),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/cameras/{camera_id}/evaluation/latest")
def latest_camera_evaluation(camera_id: int) -> Dict[str, Any]:
    if storage.get_camera(camera_id) is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    evaluation = storage.latest_rule_evaluation(camera_id) or worker.latest_evaluations.get(camera_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="Rule evaluation not found")
    return evaluation


@app.get("/api/events")
def list_events(limit: int = 50, acknowledged: bool | None = None) -> list[Dict[str, Any]]:
    return storage.list_events(limit=max(1, min(limit, 200)), acknowledged=acknowledged)


@app.get("/api/event-candidates")
def list_event_candidates(limit: int = 20, status: str | None = None) -> list[Dict[str, Any]]:
    normalized_status = (status or "").strip().lower() or None
    return storage.list_event_candidates(limit=max(1, min(limit, 200)), status=normalized_status)


@app.get("/api/events/{event_id}")
def get_event(event_id: int) -> Dict[str, Any]:
    event = storage.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@app.patch("/api/events/{event_id}")
def update_event(event_id: int, patch: EventUpdate) -> Dict[str, Any]:
    event = storage.update_event(event_id, model_dump(patch))
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@app.delete("/api/events")
def clear_events(scope: str = "acknowledged") -> Dict[str, Any]:
    try:
        return storage.clear_events(scope=scope)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/app/device")
def app_device(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    require_device_access(user)
    return device()


@app.get("/api/app/cameras")
def app_list_cameras(user: Dict[str, Any] = Depends(current_user)) -> list[Dict[str, Any]]:
    require_device_access(user)
    return storage.list_cameras()


@app.get("/api/app/cameras/{camera_id}/snapshot/latest")
def app_latest_camera_snapshot(
    camera_id: int,
    allow_missing: bool = False,
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    require_device_access(user)
    snapshot = latest_camera_snapshot(camera_id=camera_id, allow_missing=allow_missing)
    if snapshot.get("available") is False:
        return snapshot
    return snapshot_for_app(snapshot)


@app.get("/api/app/cameras/{camera_id}/evaluation/latest")
def app_latest_camera_evaluation(camera_id: int, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    require_device_access(user)
    return latest_camera_evaluation(camera_id)


@app.post("/api/app/playback-sessions")
def create_app_playback_session(
    payload: PlaybackSessionCreate,
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    return video_service.create_playback_session(payload, user=user)


@app.get("/api/app/cameras/{camera_id}/stream.mjpg")
def app_camera_mjpeg_stream(
    camera_id: int,
    profile: str = "default",
    fps: int | None = None,
    width: int | None = None,
    height: int | None = None,
    quality: int | None = None,
    drop: int | None = None,
    playback_ticket: str | None = Query(default=None),
    access_token: str | None = Query(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> StreamingResponse:
    fallback_user = None if playback_ticket else current_user_for_media(
        access_token=access_token,
        credentials=credentials,
    )
    return video_service.stream_response(
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


@app.get("/api/app/events")
def app_list_events(
    limit: int = 50,
    acknowledged: bool | None = None,
    user: Dict[str, Any] = Depends(current_user),
) -> list[Dict[str, Any]]:
    require_device_access(user)
    events = storage.list_events(limit=max(1, min(limit, 200)), acknowledged=acknowledged)
    return [event_for_app(event) for event in events]


@app.get("/api/app/events/{event_id}")
def app_get_event(event_id: int, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    require_device_access(user)
    event = storage.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event_for_app(event)


@app.patch("/api/app/events/{event_id}")
def app_update_event(event_id: int, patch: EventUpdate, user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    require_device_access(user)
    event = storage.update_event(event_id, model_dump(patch))
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event_for_app(event)


@app.get("/api/app/summary/today")
def app_today_summary(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    require_device_access(user)
    return storage.daily_summary()


@app.get("/api/app/media/snapshots/{snapshot_path:path}")
def app_snapshot_media(
    snapshot_path: str,
    playback_ticket: str | None = Query(default=None),
    access_token: str | None = Query(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> FileResponse:
    fallback_user = None if playback_ticket else current_user_for_media(
        access_token=access_token,
        credentials=credentials,
    )
    return video_service.snapshot_response(
        snapshot_path=snapshot_path,
        playback_ticket=playback_ticket,
        fallback_user=fallback_user,
    )


@app.get("/api/summary/today")
def today_summary() -> Dict[str, Any]:
    return storage.daily_summary()


def persist_rules_update(rules_patch: Dict[str, Any]) -> Dict[str, Any]:
    updated_rules = storage.update_rules(rules_patch)
    worker.request_rules_reload()
    return updated_rules


@app.get("/api/rules")
def get_rules() -> Dict[str, Any]:
    return storage.get_rules()


@app.put("/api/rules")
def update_rules(rules: RulesUpdate) -> Dict[str, Any]:
    return persist_rules_update(model_dump(rules))


@app.get("/api/rules/runtime")
def rules_runtime() -> Dict[str, Any]:
    return worker.runtime_status()


@app.post("/api/notify/test")
def notify_test(message: NotificationTest) -> Dict[str, Any]:
    payload = model_dump(message)
    return notifier.send(payload["title"], payload["body"], payload.get("extra") or {})
