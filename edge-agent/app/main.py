from __future__ import annotations

from typing import Any, Dict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request as UrlRequest, urlopen
from importlib.util import find_spec
import ipaddress
import json
import re
import shutil
import socket
import subprocess
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

from .app_runtime_guard_service import AppRuntimeGuardService
from .apns_relay_service import APNSRelayService
from .app_push_service import AppPushService
from .box_init_service import ADMIN_SESSION_COOKIE, DEFAULT_ADMIN_PASSWORD, BoxInitService
from .camera_agent import CameraAgent, CameraError
from .config_sync_agent import ConfigSyncAgent
from .detect_agent import DetectAgent
from .edge_bootstrap_service import EdgeBootstrapService
from .event_agent import EventAgent
from .live_relay_agent import LiveRelayAgent
from .notifier import Notifier
from .object_storage_service import ObjectStorageService, build_object_storage_router
from .package_service import PackageService
from .public_pilot_service import PublicPilotService
from .schemas import (
    CalendarEventCreate,
    AdminLogin,
    AdminPasswordChange,
    CameraCreate,
    CameraUpdate,
    DeviceBindingCodeCreate,
    DeviceBindingCreate,
    DeviceHeartbeatIn,
    ElderProfileUpsert,
    DeviceTokenExchange,
    EventUpdate,
    FamilyCreate,
    MessageGenerateRequest,
    MessageStatusUpdate,
    NotificationTest,
    PlaybackSessionCreate,
    V1DeviceUpgradeRun,
    RulesUpdate,
    UserLogin,
    UserRegister,
    WifiConnectRequest,
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
from .upload_agent import UploadAgent
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
SETUP_NETWORK_PAGE = "/setup/network.html"
SETUP_HOTSPOT_ORIGIN = "http://10.42.0.1"
SETUP_HOTSPOT_NETWORK_PAGE = f"{SETUP_HOTSPOT_ORIGIN}{SETUP_NETWORK_PAGE}"
EDGE_STARTED_AT = datetime.now(timezone.utc)


def model_dump(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def vision_runtime_capabilities() -> Dict[str, bool]:
    yolo_available = find_spec("torch") is not None and find_spec("ultralytics") is not None
    pose_available = find_spec("onnxruntime") is not None and find_spec("rtmlib") is not None
    person_available = settings.detector_backend == "demo" or (
        settings.detector_backend in {"yolo", "rtmpose", "pose"} and yolo_available
    )
    return {
        "quality_detection": True,
        "motion_detection": True,
        "person_detection": person_available,
        "no_person_detection": person_available,
        "fall_candidate": person_available or pose_available,
        "activity_candidate": True,
        "fire_candidate": True,
        "pose_detection": pose_available,
        "yolo_runtime": yolo_available,
        "pose_runtime": pose_available,
    }


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


def run_setup_command(args: list[str], timeout: float = 6.0) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return 127, "", f"{args[0]} not found"
    except subprocess.TimeoutExpired:
        return 124, "", "command timed out"
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def network_permission_error(message: str) -> bool:
    return bool(re.search(r"insufficient privileges|not authorized|permission|not allowed", message, re.IGNORECASE))


def run_gohome_nmcli(args: list[str], timeout: float = 12.0) -> tuple[int, str, str]:
    wrapper = shutil.which("gohome-nmcli") or "/usr/local/sbin/gohome-nmcli"
    if not Path(wrapper).exists():
        return 127, "", "gohome-nmcli not installed"
    if shutil.which("sudo"):
        return run_setup_command(["sudo", "-n", wrapper, *args], timeout=timeout)
    return run_setup_command([wrapper, *args], timeout=timeout)


def forget_wifi_connection(ssid: str) -> None:
    if not nmcli_available() or not ssid:
        return
    run_setup_command(["nmcli", "connection", "delete", ssid], timeout=8)


def nmcli_available() -> bool:
    return shutil.which("nmcli") is not None


def clean_nmcli_field(value: str) -> str:
    return value.replace(r"\:", ":").replace(r"\\", "\\").strip()


def connected_wifi_ssid() -> str:
    if nmcli_available():
        code, stdout, _stderr = run_setup_command(["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"], timeout=4)
        if code == 0:
            for line in stdout.splitlines():
                parts = line.split(":", 1)
                if len(parts) == 2 and parts[0] == "yes":
                    return clean_nmcli_field(parts[1])
    if shutil.which("iwgetid"):
        code, stdout, _stderr = run_setup_command(["iwgetid", "-r"], timeout=3)
        if code == 0 and stdout.strip():
            return stdout.strip()
    return ""


def active_network_name() -> str:
    ssid = connected_wifi_ssid()
    if ssid:
        return ssid
    if nmcli_available():
        code, stdout, _stderr = run_setup_command(["nmcli", "-t", "-f", "NAME,DEVICE", "connection", "show", "--active"], timeout=4)
        if code == 0:
            for line in stdout.splitlines():
                name, _, device = line.partition(":")
                if device and device != "lo":
                    return clean_nmcli_field(name)
    return "家庭网络"


def setup_hotspot_name() -> str:
    suffix = re.sub(r"[^A-Za-z0-9]", "", socket.gethostname())[-4:] or local_device_identity()["device_id"][-4:]
    return f"GoHome-{suffix.upper()}"


def is_setup_hotspot_ssid(ssid: str) -> bool:
    return str(ssid or "").strip().startswith("GoHome-")


def request_is_setup_hotspot(request: Request) -> bool:
    host = request.url.hostname or ""
    return host.startswith("10.42.") or host == "10.42.0.1" or is_setup_hotspot_ssid(connected_wifi_ssid())


def setup_network_status() -> Dict[str, Any]:
    lan_ip = local_ip()
    ssid = connected_wifi_ssid()
    hotspot_mode = is_setup_hotspot_ssid(ssid)
    return {
        "connected": bool(lan_ip) and not hotspot_mode,
        "mode": "setup_hotspot" if hotspot_mode else "home_wifi" if ssid else "lan",
        "ssid": "" if hotspot_mode else ssid,
        "network_name": setup_hotspot_name() if hotspot_mode else ssid or active_network_name(),
        "lan_ip": lan_ip,
        "api_base_url": f"http://{lan_ip}:{settings.port}",
        "hotspot_ssid": setup_hotspot_name(),
        "hotspot_setup_url": "http://10.42.0.1/setup/network.html",
        "hotspot_setup_url_with_port": "http://10.42.0.1:8711/setup/network.html",
        "wifi_scan_supported": nmcli_available(),
        "wifi_connect_supported": nmcli_available(),
        "ble_provision_supported": False,
    }


def default_camera_host() -> str:
    parts = local_ip().split(".")
    if len(parts) == 4:
        return ".".join(parts[:3] + ["11"])
    return "192.168.1.11"


def camera_setup_presets() -> Dict[str, Any]:
    return {
        "default_room": "客厅",
        "default_name": "客厅摄像头",
        "default_host": default_camera_host(),
        "default_port": 554,
        "default_username": "admin",
        "default_channel": 1,
        "default_stream": 2,
        "default_path": "/1/2",
        "profiles": [
            {"key": "sub_stream", "label": "1 频道副码流", "path": "/1/2", "hint": "默认使用 1 频道副码流，适合 720p 低延迟预览。"},
            {"key": "main_stream", "label": "1 频道主码流", "path": "/1/1", "hint": "主码流画质更高，但延迟和解码压力更大。"},
            {"key": "hikvision", "label": "海康", "path": "/Streaming/Channels/102", "hint": "海康常见子码流，适合低延迟 720p 预览。"},
            {"key": "dahua", "label": "大华", "path": "/cam/realmonitor?channel=1&subtype=1", "hint": "大华常见子码流，适合低延迟 720p 预览。"},
            {"key": "custom", "label": "自定义", "path": "/1/2", "hint": "手动填写路径"},
        ],
    }


def scan_camera_host(host: str, timeout: float = 0.16) -> Dict[str, Any] | None:
    ports = [554, 8554, 80, 8000, 8080]
    open_ports: list[int] = []
    for port in ports:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                open_ports.append(port)
        except OSError:
            continue
    rtsp_ports = [port for port in open_ports if port in {554, 8554}]
    if not rtsp_ports:
        return None
    rtsp_port = 554 if 554 in rtsp_ports else rtsp_ports[0]
    return {
        "host": host,
        "port": rtsp_port,
        "open_ports": open_ports,
        "path": "/1/2",
        "stream_url": f"rtsp://{host}:{rtsp_port}/1/2",
        "label": f"{host}:{rtsp_port}",
    }


def discover_lan_cameras(limit: int = 24) -> list[Dict[str, Any]]:
    ip = local_ip()
    try:
        network = ipaddress.ip_network(f"{ip}/24", strict=False)
    except ValueError:
        return []
    hosts = [str(host) for host in network.hosts() if str(host) != ip]
    results: list[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=64) as executor:
        futures = [executor.submit(scan_camera_host, host) for host in hosts]
        for future in as_completed(futures):
            item = future.result()
            if item is not None:
                results.append(item)
                if len(results) >= limit:
                    break
    results.sort(key=lambda item: (554 not in item["open_ports"], item["host"]))
    return results[:limit]


def ensure_demo_camera_if_empty() -> None:
    if not settings.enable_demo_camera:
        cleanup_demo_cameras()
        return
    if storage.list_cameras():
        return
    storage.create_camera(
        {
            "name": "客厅演示摄像头",
            "room": "客厅",
            "stream_url": "demo:living_room",
            "username": None,
            "password": None,
            "enabled": True,
        }
    )


def cleanup_demo_cameras() -> None:
    for camera in storage.list_cameras():
        if str(camera.get("stream_url", "")).strip().lower() == "demo:living_room":
            storage.delete_camera(int(camera["id"]))


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


def remote_camera_id_for_local_camera(local_camera_id: int) -> str | int:
    state_path = settings.runtime_dir / "config-sync-state.json"
    if not state_path.exists():
        return local_camera_id
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return local_camera_id
    camera_map = state.get("camera_map") if isinstance(state, dict) else {}
    if not isinstance(camera_map, dict):
        return local_camera_id
    for remote_id, mapped_local_id in camera_map.items():
        if str(mapped_local_id) == str(local_camera_id):
            return str(remote_id)
    return local_camera_id


def write_local_device_token(token: str) -> None:
    local_device_token_path().write_text(token.strip(), encoding="utf-8")


def pairing_window_open() -> bool:
    elapsed = (datetime.now(timezone.utc) - EDGE_STARTED_AT).total_seconds()
    return elapsed <= max(60, settings.lan_pairing_window_seconds)


def validated_pair_return_url(raw_url: str) -> str:
    return_url = str(raw_url or "").strip()
    cloud_base = str(settings.app_server_base_url or "").strip().rstrip("/")
    if not return_url or not cloud_base:
        raise HTTPException(status_code=400, detail="Pairing return URL is missing")
    target = urlparse(return_url)
    allowed = urlparse(cloud_base)
    if target.scheme != allowed.scheme or target.netloc != allowed.netloc:
        raise HTTPException(status_code=400, detail="Pairing return URL is not allowed")
    return return_url


def cloud_pair_device(code: str) -> Dict[str, Any]:
    identity = local_device_identity()
    payload = json.dumps({
        "code": code,
        "device_id": identity["device_id"],
        "device_name": identity["device_name"],
        "device_type": identity["device_type"],
        "note": "LAN pairing",
        "metadata": {
            "lan_ip": identity["lan_ip"],
            "api_port": identity["api_port"],
            "pairing_method": "lan",
        },
    }, ensure_ascii=False).encode("utf-8")
    request = UrlRequest(
        f"{settings.app_server_base_url}/api/device/token/exchange",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=12) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(detail).get("error") or json.loads(detail).get("detail") or detail
        except json.JSONDecodeError:
            pass
        raise HTTPException(status_code=409 if exc.code == 409 else 400, detail=str(detail)) from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail="盒子暂时无法连接云端，请检查网络后重试") from exc
    token = str(result.get("device_token") or result.get("token") or "").strip()
    if not token:
        raise HTTPException(status_code=502, detail="云端没有返回设备凭证")
    write_local_device_token(token)
    return result


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
    if asset is None:
        asset = storage.get_media_asset_by_event(int(data["id"]))
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


def current_v1_device_stream_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_device_token: str | None = Header(default=None, alias="X-GoHome-Device-Token"),
) -> Dict[str, Any]:
    token = x_device_token
    if credentials is not None and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    if not token:
        raise HTTPException(status_code=401, detail="Device token required")
    session = storage.get_device_token_by_raw_token(token)
    if session is not None:
        return session
    settings_token = str(settings.device_api_token or "").strip()
    if settings_token and token == settings_token:
        identity = local_device_identity()
        return {
            "id": 0,
            "family_id": 1,
            "device_id": identity["device_id"],
            "device_name": identity["device_name"],
            "status": "settings_token",
        }
    raise HTTPException(status_code=401, detail="Invalid device token")


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
        "upload_agent": upload_agent.status(),
        "config_sync_agent": config_sync_agent.status(),
        "token": token,
    }


def v1_event_summary(event: Dict[str, Any]) -> Dict[str, Any]:
    data = event_for_v1(event)
    payload = data.get("payload") or {}
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
        "snapshot_path": data.get("snapshot_path") or "",
        "snapshot_url": data.get("snapshot_url"),
        "candidate_status": data.get("candidate_status"),
        "idempotency_key": payload.get("idempotency_key") or f"edge-event-{data['id']}",
        "evidence": payload.get("evidence") or {},
        "payload": payload,
        "media_asset": data.get("media_asset"),
    }


def event_server_payload(event: Dict[str, Any]) -> Dict[str, Any]:
    data = event_for_v1(event)
    payload = data.get("payload") or {}
    identity = local_device_identity()
    return {
        "idempotency_key": f"{identity['device_id']}:event:{data['id']}",
        "event_type": data["type"],
        "summary": data["summary"],
        "level": data["level"],
        "room": data.get("room") or "",
        "camera_id": data.get("camera_id"),
        "snapshot_path": data.get("snapshot_path") or "",
        "occurred_at": data["occurred_at"],
        "payload": {
            **payload,
            "schema_version": "gohome-device-event-v1",
            "edge_event_id": data["id"],
            "edge_device_id": identity["device_id"],
            "edge_device_name": identity["device_name"],
            "snapshot_url": data.get("snapshot_url") or "",
            "media_asset": data.get("media_asset"),
        },
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


def parse_iso_day(value: str) -> datetime | None:
    clean_value = str(value or "").strip()
    if not clean_value:
        return None
    try:
        return datetime.fromisoformat(clean_value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.fromisoformat(f"{clean_value}T00:00:00+08:00")
        except ValueError:
            return None


def build_mock_weather_signal(city: str, today: datetime | None = None) -> Dict[str, Any]:
    current = today or datetime.now(timezone.utc)
    signals = [
        {"condition": "thunderstorm", "alerts": ["雷暴雨"], "temperature_min": 24, "temperature_max": 31},
        {"condition": "cooling", "alerts": ["降温"], "temperature_min": 18, "temperature_max": 24},
        {"condition": "hot", "alerts": ["高温"], "temperature_min": 28, "temperature_max": 36},
        {"condition": "breezy", "alerts": ["大风"], "temperature_min": 22, "temperature_max": 29},
    ]
    signal = signals[current.day % len(signals)]
    return {
        "city": city or "苏州",
        "date": current.astimezone(timezone.utc).date().isoformat(),
        "condition": signal["condition"],
        "temperature_min": signal["temperature_min"],
        "temperature_max": signal["temperature_max"],
        "alerts": signal["alerts"],
        "source": "mock_weather_v1",
    }


def build_message_candidate_payloads(
    *,
    family_id: int,
    elder_id: str,
    device_id: str,
    elder_profile: Dict[str, Any] | None,
    calendar_events: list[Dict[str, Any]],
    weather_signal: Dict[str, Any],
    scenario_types: list[str],
) -> list[Dict[str, Any]]:
    requested = {item.strip() for item in scenario_types if str(item or "").strip()}
    now = datetime.now(timezone.utc)
    messages: list[Dict[str, Any]] = []
    display_name = str((elder_profile or {}).get("display_name") or "妈妈")
    likes = list((elder_profile or {}).get("likes") or [])
    like_text = likes[0] if likes else "你回家陪她吃顿饭"

    if not requested or "calendar" in requested:
        for calendar_event in calendar_events:
            event_type = str(calendar_event.get("type") or "").strip()
            event_date = parse_iso_day(str(calendar_event.get("start_at") or ""))
            if event_type != "birthday" or event_date is None:
                continue
            delta_days = (event_date.date() - now.date()).days
            if delta_days < 0 or delta_days > 7:
                continue
            prefix = "今天" if delta_days == 0 else "明天" if delta_days == 1 else f"{delta_days} 天后"
            messages.append(
                {
                    "message_id": f"msg_{uuid4().hex[:16]}",
                    "family_id": family_id,
                    "device_id": device_id,
                    "elder_id": elder_id,
                    "message_type": "gohome",
                    "priority": "warm",
                    "title": f"{prefix}是{display_name}生日",
                    "subtitle": f"她喜欢{like_text}，也会更想见到你。",
                    "body": "建议提前准备一个小心意，或者把回家时间先定下来。",
                    "facts": [
                        f"日历：{calendar_event.get('title') or '生日提醒'}",
                        f"日期：{str(calendar_event.get('start_at') or '')[:10]}",
                    ],
                    "image_mode": "generated",
                    "image_url": "",
                    "actions": [
                        {"key": "call", "label": "打电话"},
                        {"key": "schedule_visit", "label": "安排回家"},
                    ],
                    "source": ["elder_profile", "calendar"],
                    "source_event_ids": [],
                    "source_media_ids": [],
                    "generated_by": "calendar_rule_v1",
                    "status": "open",
                    "expires_at": (event_date + timedelta(days=1)).isoformat(),
                }
            )
            break

    if not requested or "weather" in requested:
        alerts = list(weather_signal.get("alerts") or [])
        if alerts:
            first_alert = str(alerts[0])
            messages.append(
                {
                    "message_id": f"msg_{uuid4().hex[:16]}",
                    "family_id": family_id,
                    "device_id": device_id,
                    "elder_id": elder_id,
                    "message_type": "accompany",
                    "priority": "warm",
                    "title": f"今天{weather_signal.get('city') or '家里那边'}有{first_alert}",
                    "subtitle": f"可以提醒{display_name}少出门，先把窗户和阳台看一眼。",
                    "body": "如果她今天要出门，建议先打个电话确认一下。",
                    "facts": [
                        f"天气：{first_alert}",
                        f"温度：{weather_signal.get('temperature_min')} - {weather_signal.get('temperature_max')}°C",
                    ],
                    "image_mode": "generated",
                    "image_url": "",
                    "actions": [
                        {"key": "call", "label": "打电话"},
                        {"key": "send_message", "label": "发消息"},
                    ],
                    "source": ["weather_signal", "elder_profile"],
                    "source_event_ids": [],
                    "source_media_ids": [],
                    "generated_by": "weather_rule_v1",
                    "status": "open",
                    "expires_at": "",
                }
            )

    if not requested or "event" in requested:
        latest_events = storage.list_events(limit=1, acknowledged=False)
        if latest_events:
            latest_event = latest_events[0]
            messages.append(
                {
                    "message_id": f"msg_{uuid4().hex[:16]}",
                    "family_id": family_id,
                    "device_id": device_id,
                    "elder_id": elder_id,
                    "message_type": "alert",
                    "priority": "warning",
                    "title": str(latest_event.get("summary") or "家里有一条需要确认的提醒"),
                    "subtitle": "这条消息来自盒子侧真实事件，不是情绪化猜测。",
                    "body": "建议先看一眼事件详情，再决定要不要打电话或标记已确认。",
                    "facts": [
                        f"类型：{latest_event.get('type') or ''}",
                        f"房间：{latest_event.get('room') or '未标记'}",
                    ],
                    "image_mode": "evidence" if latest_event.get("snapshot_path") else "none",
                    "image_url": latest_event.get("snapshot_url") or "",
                    "actions": [
                        {"key": "view_event", "label": "查看事件"},
                        {"key": "ack", "label": "标记已确认"},
                    ],
                    "source": ["vision_event"],
                    "source_event_ids": [int(latest_event["id"])],
                    "source_media_ids": [],
                    "generated_by": "event_rule_v1",
                    "status": "open",
                    "expires_at": "",
                }
            )

    return messages


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
box_init_service = BoxInitService(settings)
box_init_service.initialize_if_needed()
storage = Storage(settings.db_path)
camera_agent = CameraAgent(settings.snapshot_dir)
detect_agent = DetectAgent(
    black_brightness_threshold=settings.black_brightness_threshold,
    black_contrast_threshold=settings.black_contrast_threshold,
    motion_threshold=settings.motion_threshold,
    detector_backend=settings.detector_backend,
    yolo_model=settings.yolo_model,
    yolo_confidence=settings.yolo_confidence,
    yolo_imgsz=settings.yolo_imgsz,
    pose_enabled=settings.pose_enabled,
    pose_mode=settings.pose_mode,
    pose_runtime_backend=settings.pose_runtime_backend,
    pose_device=settings.pose_device,
    pose_fall_threshold=settings.pose_fall_threshold,
    pose_fall_min_confidence=settings.pose_fall_min_confidence,
    pose_fall_min_visible_keypoints=settings.pose_fall_min_visible_keypoints,
    pose_fall_min_core_keypoints=settings.pose_fall_min_core_keypoints,
    pose_det_frequency=settings.pose_det_frequency,
    pose_min_keypoint_confidence=settings.pose_min_keypoint_confidence,
    pose_max_poses=settings.pose_max_poses,
    pose_tracking=settings.pose_tracking,
    pose_cache_seconds=settings.pose_cache_seconds,
    pose_cache_max_motion=settings.pose_cache_max_motion,
    activity_window_seconds=settings.activity_window_seconds,
    activity_max_samples=settings.activity_max_samples,
)
notifier = Notifier(settings)
event_agent = EventAgent(storage, notifier, settings.event_throttle_seconds)
worker = EdgeWorker(
    storage,
    camera_agent,
    detect_agent,
    event_agent,
    live_frame_upload_enabled=(
        settings.live_frame_upload_enabled
        and settings.upload_worker_enabled
        and bool(settings.app_server_base_url)
    ),
    live_frame_upload_interval_seconds=settings.live_frame_upload_interval_seconds,
    remote_camera_id_resolver=remote_camera_id_for_local_camera,
    snapshot_dir=settings.snapshot_dir,
    history_retention_hours=settings.history_retention_hours,
    history_cleanup_interval_seconds=settings.history_cleanup_interval_seconds,
    history_cleanup_batch_size=settings.history_cleanup_batch_size,
    completed_upload_retention_days=settings.completed_upload_retention_days,
)
video_distribution_service = VideoDistributionService(
    storage=storage,
    settings=settings,
    current_device_identity_resolver=local_device_identity,
)
object_storage_service = ObjectStorageService(storage=storage, settings=settings, distribution=video_distribution_service)
upload_agent = UploadAgent(
    storage=storage,
    settings=settings,
    device_id_resolver=current_device_id,
    token_resolver=read_local_device_token,
    remote_camera_id_resolver=remote_camera_id_for_local_camera,
)
live_relay_agent = LiveRelayAgent(
    storage=storage,
    settings=settings,
    camera_agent=camera_agent,
    device_id_resolver=current_device_id,
    token_resolver=read_local_device_token,
    remote_camera_id_resolver=remote_camera_id_for_local_camera,
)
config_sync_agent = ConfigSyncAgent(
    storage=storage,
    settings=settings,
    camera_agent=camera_agent,
    device_id_resolver=current_device_id,
    token_resolver=read_local_device_token,
    runtime_status_resolver=lambda: {
        "worker_running": worker.is_running,
        "lan_url": f"http://{local_ip()}:{settings.port}",
        "service_url": f"http://{local_ip()}:{settings.port}",
        "detector_backend": settings.detector_backend,
        "yolo_model": settings.yolo_model if settings.detector_backend == "yolo" else "",
        "yolo_imgsz": settings.yolo_imgsz if settings.detector_backend == "yolo" else None,
        "pose_enabled": settings.pose_enabled,
        "pose_backend": settings.pose_backend,
        "vision_capabilities": vision_runtime_capabilities(),
        "worker": worker.runtime_status(),
        "storage": {
            **storage.runtime_storage_status(
                settings.snapshot_dir,
                retention_hours=settings.history_retention_hours,
            ),
            "last_cleanup": worker.last_history_cleanup_result,
        },
    },
)
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


@app.get("/favicon.ico", include_in_schema=False)
def empty_favicon() -> Response:
    return Response(status_code=204)


def admin_path_requires_auth(path: str) -> bool:
    if not path.startswith("/admin"):
        return False
    if path in {"/admin/login.html", "/admin/login.js", "/admin/styles.css"}:
        return False
    return path in {"/admin", "/admin/"} or path.endswith(".html")


def admin_api_requires_auth(path: str) -> bool:
    protected_prefixes = (
        "/api/cameras",
        "/api/events",
        "/api/event-candidates",
        "/api/event-log",
        "/api/summary",
        "/api/rules",
        "/api/notify",
        "/api/observation-logs",
        "/api/upload-jobs",
        "/api/cloud-verifications",
        "/snapshots",
    )
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in protected_prefixes)


def admin_login_redirect(request: Request) -> RedirectResponse:
    target = request.url.path
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return RedirectResponse(url=f"/admin/login.html?next={quote(target, safe='')}", status_code=303)


@app.middleware("http")
async def enforce_admin_session(request: Request, call_next: Any) -> Response:
    requires_page_auth = admin_path_requires_auth(request.url.path)
    requires_api_auth = admin_api_requires_auth(request.url.path)
    if requires_page_auth or requires_api_auth:
        token = request.cookies.get(ADMIN_SESSION_COOKIE, "")
        session = box_init_service.session_status(token)
        if not session:
            if requires_page_auth and request.method == "GET":
                return admin_login_redirect(request)
            return JSONResponse({"detail": "请先登录盒子管理端。"}, status_code=401)
        if box_init_service.status(token).get("must_change_password"):
            if requires_page_auth and request.method == "GET":
                return admin_login_redirect(request)
            return JSONResponse({"detail": "首次登录后必须修改管理密码。"}, status_code=403)
    return await call_next(request)


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
app.mount("/setup", StaticFiles(directory=str(settings.setup_dir), html=True), name="setup")
app.mount("/admin", StaticFiles(directory=str(settings.admin_dir), html=True), name="admin")
app.mount("/ui", StaticFiles(directory=str(settings.frontend_dir), html=True), name="ui")


@app.get("/", include_in_schema=False)
def root(request: Request) -> Response:
    if request_is_setup_hotspot(request):
        return captive_setup_page()
    cameras = storage.list_cameras()
    if not cameras or all(str(camera.get("stream_url", "")).startswith("demo:") for camera in cameras):
        return RedirectResponse(url=SETUP_NETWORK_PAGE)
    return RedirectResponse(url="/admin/index.html")


def setup_network_redirect() -> RedirectResponse:
    return RedirectResponse(url=SETUP_HOTSPOT_NETWORK_PAGE)


def captive_setup_page() -> Response:
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta http-equiv="refresh" content="0; url={SETUP_HOTSPOT_NETWORK_PAGE}">
  <title>连接回家盒子</title>
  <style>
    html, body {{
      min-height: 100%;
      margin: 0;
      background: #f5f5f7;
      color: #1d1d1f;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
    }}
    main {{
      min-height: 100vh;
      display: grid;
      align-content: center;
      gap: 16px;
      padding: 28px;
      box-sizing: border-box;
    }}
    h1 {{ margin: 0; font-size: 30px; line-height: 1.12; }}
    p {{ margin: 0; color: #6e6e73; font-size: 15px; line-height: 1.5; }}
    a {{
      min-height: 50px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      margin-top: 10px;
      border-radius: 12px;
      background: #1d1d1f;
      color: white;
      font-size: 16px;
      font-weight: 700;
      text-decoration: none;
    }}
  </style>
</head>
<body>
  <main>
    <h1>连接回家盒子</h1>
    <p>正在打开配网页。如果没有自动跳转，请点下面的按钮。</p>
    <a href="{SETUP_HOTSPOT_NETWORK_PAGE}">打开配网页</a>
  </main>
  <script>window.location.replace("{SETUP_HOTSPOT_NETWORK_PAGE}");</script>
</body>
</html>"""
    return Response(
        html,
        media_type="text/html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@app.get("/hotspot-detect.html", include_in_schema=False)
@app.get("/library/test/success.html", include_in_schema=False)
def apple_captive_portal(request: Request) -> Response:
    if request_is_setup_hotspot(request):
        return captive_setup_page()
    return Response(
        "<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>",
        media_type="text/html",
    )


@app.get("/generate_204", include_in_schema=False)
@app.get("/gen_204", include_in_schema=False)
def android_captive_portal(request: Request) -> Response:
    if request_is_setup_hotspot(request):
        return setup_network_redirect()
    return Response(status_code=204)


@app.get("/connecttest.txt", include_in_schema=False)
@app.get("/ncsi.txt", include_in_schema=False)
@app.get("/redirect", include_in_schema=False)
def windows_captive_portal(request: Request) -> Response:
    if request_is_setup_hotspot(request):
        return setup_network_redirect()
    return Response("Microsoft Connect Test", media_type="text/plain")


@app.on_event("startup")
def on_startup() -> None:
    storage.init_schema()
    ensure_demo_camera_if_empty()
    if not settings.disable_worker:
        worker.start()
    upload_agent.start()
    live_relay_agent.start()
    config_sync_agent.start()
    app_runtime_guard.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    app_runtime_guard.stop()
    config_sync_agent.stop()
    live_relay_agent.stop()
    upload_agent.stop()
    worker.stop()


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "gohome-edge-agent",
        "worker_running": worker.is_running,
        "config_sync_agent": config_sync_agent.status(),
        "live_relay_agent": live_relay_agent.status(),
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
        "yolo_imgsz": settings.yolo_imgsz if settings.detector_backend == "yolo" else None,
        "pose_enabled": settings.pose_enabled,
        "pose_backend": settings.pose_backend,
        "pose_model": f"RTMPose-{settings.pose_mode}",
        "pose_runtime_backend": settings.pose_runtime_backend,
        "pose_cache_seconds": settings.pose_cache_seconds,
        "pose_cache_max_motion": settings.pose_cache_max_motion,
        "activity_window_seconds": settings.activity_window_seconds,
        "activity_max_samples": settings.activity_max_samples,
        "vision_capabilities": vision_runtime_capabilities(),
        "worker_running": worker.is_running,
        "upload_agent": upload_agent.status(),
        "live_relay_agent": live_relay_agent.status(),
        "config_sync_agent": config_sync_agent.status(),
        "video_distribution": video_distribution_service.service_info(),
        "app_runtime": app_runtime_guard.status(),
    }


@app.get("/api/admin/auth/status")
def admin_auth_status(request: Request) -> Dict[str, Any]:
    return box_init_service.status(request.cookies.get(ADMIN_SESSION_COOKIE, ""))


@app.post("/api/admin/auth/login")
def admin_auth_login(payload: AdminLogin, response: Response) -> Dict[str, Any]:
    session = box_init_service.authenticate(payload.username.strip(), payload.password)
    if not session:
        raise HTTPException(status_code=401, detail="用户名或密码不正确。")
    response.set_cookie(
        ADMIN_SESSION_COOKIE,
        session["token"],
        max_age=12 * 60 * 60,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return {
        "authenticated": True,
        "username": session["username"],
        "must_change_password": session["must_change_password"],
        "expires_at": session["expires_at"],
    }


@app.post("/api/admin/auth/logout")
def admin_auth_logout(request: Request, response: Response) -> Dict[str, Any]:
    box_init_service.logout(request.cookies.get(ADMIN_SESSION_COOKIE, ""))
    response.delete_cookie(ADMIN_SESSION_COOKIE, path="/")
    return {"authenticated": False}


@app.post("/api/admin/auth/change-password")
def admin_auth_change_password(payload: AdminPasswordChange, request: Request, response: Response) -> Dict[str, Any]:
    if payload.new_password == payload.old_password or payload.new_password == DEFAULT_ADMIN_PASSWORD:
        raise HTTPException(status_code=400, detail="新密码不能继续使用初始密码。")
    changed = box_init_service.change_password(
        request.cookies.get(ADMIN_SESSION_COOKIE, ""),
        payload.old_password,
        payload.new_password,
    )
    if not changed:
        raise HTTPException(status_code=401, detail="旧密码不正确或登录已过期。")
    response.delete_cookie(ADMIN_SESSION_COOKIE, path="/")
    return {"changed": True, "message": "密码已修改，请重新登录。"}


@app.get("/api/setup/network")
def setup_network() -> Dict[str, Any]:
    return setup_network_status()


@app.get("/api/setup/wifi/networks")
def setup_wifi_networks() -> Dict[str, Any]:
    if not nmcli_available():
        return {"supported": False, "networks": [], "message": "当前系统未安装 NetworkManager，无法从页面扫描 Wi-Fi。"}
    code, stdout, stderr = run_setup_command(
        ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list", "--rescan", "yes"],
        timeout=10,
    )
    if code != 0 and network_permission_error(stderr or stdout):
        code, stdout, stderr = run_gohome_nmcli(["wifi-list"], timeout=14)
    if code != 0:
        return {"supported": True, "networks": [], "message": stderr or "Wi-Fi 扫描失败，请稍后重试。"}
    networks: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for line in stdout.splitlines():
        parts = line.split(":")
        if not parts:
            continue
        ssid = clean_nmcli_field(parts[0])
        if not ssid or ssid in seen:
            continue
        seen.add(ssid)
        signal = 0
        if len(parts) > 1:
            try:
                signal = int(parts[1] or "0")
            except ValueError:
                signal = 0
        security = clean_nmcli_field(":".join(parts[2:])) if len(parts) > 2 else ""
        networks.append({"ssid": ssid, "signal": signal, "security": security, "secured": bool(security)})
    networks.sort(key=lambda item: int(item["signal"]), reverse=True)
    return {"supported": True, "networks": networks[:20], "message": ""}


@app.post("/api/setup/wifi/connect")
def setup_wifi_connect(payload: WifiConnectRequest) -> Dict[str, Any]:
    if not nmcli_available():
        raise HTTPException(status_code=501, detail="当前系统未安装 NetworkManager，无法从页面连接 Wi-Fi。")
    ssid = payload.ssid.strip()
    if not ssid:
        raise HTTPException(status_code=400, detail="请选择家庭 Wi-Fi。")
    if payload.password:
        forget_wifi_connection(ssid)
    args = ["nmcli", "dev", "wifi", "connect", ssid]
    if payload.password:
        args.extend(["password", payload.password])
    code, stdout, stderr = run_setup_command(args, timeout=25)
    if code != 0 and network_permission_error(stderr or stdout):
        privileged_args = ["wifi-connect", ssid]
        if payload.password:
            privileged_args.append(payload.password)
        code, stdout, stderr = run_gohome_nmcli(privileged_args, timeout=30)
    if code != 0:
        detail = stderr or stdout or "Wi-Fi 连接失败，请检查密码。"
        if re.search(r"insufficient privileges|not authorized|permission", detail, re.IGNORECASE):
            detail = "盒子还没有配网权限，请重新运行安装脚本。"
        elif re.search(r"secrets were required|no secrets|password|key-mgmt|802-11-wireless-security", detail, re.IGNORECASE):
            detail = "请输入正确的 Wi-Fi 密码。"
        raise HTTPException(status_code=400, detail=detail)
    return {"connected": True, "message": "Wi-Fi 已连接", "network": setup_network_status()}


@app.get("/api/cameras/setup-presets")
def camera_presets() -> Dict[str, Any]:
    return camera_setup_presets()


@app.get("/api/cameras/discover")
async def discover_cameras(limit: int = 24) -> Dict[str, Any]:
    bounded_limit = max(1, min(int(limit), 48))
    cameras = await run_in_threadpool(discover_lan_cameras, bounded_limit)
    return {"cameras": cameras, "count": len(cameras), "subnet": ".".join(local_ip().split(".")[:3]) + ".0/24"}


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


@app.get("/api/v1/families/{family_id}/elders/{elder_id}/profile")
def v1_get_elder_profile(
    family_id: int,
    elder_id: str,
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    require_family_access(user, family_id)
    profile = storage.get_elder_profile(family_id=family_id, elder_id=elder_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Elder profile not found")
    return profile


@app.put("/api/v1/families/{family_id}/elders/{elder_id}/profile")
def v1_upsert_elder_profile(
    family_id: int,
    elder_id: str,
    payload: ElderProfileUpsert,
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    require_family_access(user, family_id)
    try:
        return storage.upsert_elder_profile(family_id=family_id, elder_id=elder_id, payload=model_dump(payload))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/families/{family_id}/calendar-events")
def v1_list_calendar_events(
    family_id: int,
    elder_id: str = Query(default=""),
    user: Dict[str, Any] = Depends(current_user),
) -> list[Dict[str, Any]]:
    require_family_access(user, family_id)
    return storage.list_calendar_events(family_id=family_id, elder_id=elder_id)


@app.post("/api/v1/families/{family_id}/calendar-events")
def v1_create_calendar_event(
    family_id: int,
    payload: CalendarEventCreate,
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    require_family_access(user, family_id)
    return storage.create_calendar_event(family_id=family_id, payload=model_dump(payload))


@app.get("/api/v1/families/{family_id}/weather-signals")
def v1_list_weather_signals(
    family_id: int,
    elder_id: str = Query(default="elder_primary"),
    city: str = Query(default=""),
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    require_family_access(user, family_id)
    resolved_city = city.strip()
    if not resolved_city:
        profile = storage.get_elder_profile(family_id=family_id, elder_id=elder_id)
        resolved_city = str((profile or {}).get("city") or "").strip()
    return build_mock_weather_signal(resolved_city)


@app.post("/api/v1/internal/messages/generate")
def v1_generate_messages(
    payload: MessageGenerateRequest,
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    family_id = resolve_user_family_id(user, payload.family_id)
    elder_id = str(payload.elder_id or "elder_primary").strip() or "elder_primary"
    elder_profile = storage.get_elder_profile(family_id=family_id, elder_id=elder_id)
    calendar_events = storage.list_calendar_events(family_id=family_id, elder_id=elder_id)
    weather_signal = build_mock_weather_signal(str((elder_profile or {}).get("city") or "").strip())
    if payload.clear_existing:
        storage.clear_message_candidates(family_id=family_id, elder_id=elder_id)
    generated_messages = []
    for message in build_message_candidate_payloads(
        family_id=family_id,
        elder_id=elder_id,
        device_id=current_device_id(),
        elder_profile=elder_profile,
        calendar_events=calendar_events,
        weather_signal=weather_signal,
        scenario_types=payload.scenario_types,
    ):
        generated_messages.append(storage.create_message_candidate(message))
    return {
        "family_id": family_id,
        "elder_id": elder_id,
        "weather_signal": weather_signal,
        "messages": generated_messages,
    }


@app.get("/api/v1/app/messages")
def v1_list_app_messages(
    family_id: int | None = Query(default=None),
    limit: int = 20,
    status: str = Query(default=""),
    user: Dict[str, Any] = Depends(current_user),
) -> list[Dict[str, Any]]:
    resolved_family_id = resolve_user_family_id(user, family_id)
    return storage.list_message_candidates(
        family_id=resolved_family_id,
        limit=max(1, min(limit, 100)),
        status=status or None,
    )


@app.get("/api/v1/app/messages/{message_id}")
def v1_get_app_message(
    message_id: str,
    family_id: int | None = Query(default=None),
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    resolved_family_id = resolve_user_family_id(user, family_id)
    message = storage.get_message_candidate(family_id=resolved_family_id, message_id=message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return message


@app.patch("/api/v1/app/messages/{message_id}")
def v1_update_app_message(
    message_id: str,
    patch: MessageStatusUpdate,
    family_id: int | None = Query(default=None),
    user: Dict[str, Any] = Depends(current_user),
) -> Dict[str, Any]:
    resolved_family_id = resolve_user_family_id(user, family_id)
    message = storage.update_message_candidate_status(
        family_id=resolved_family_id,
        message_id=message_id,
        status=patch.status,
    )
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return message


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


@app.get("/api/lan/discovery")
def lan_discovery() -> Dict[str, Any]:
    identity = local_device_identity()
    return {
        "product": "gohome-box",
        "device_id": identity["device_id"],
        "device_name": identity["device_name"],
        "lan_ip": identity["lan_ip"],
        "api_port": identity["api_port"],
        "pairing_window_open": pairing_window_open(),
    }


@app.get("/pair")
def pair_from_lan(code: str = Query(..., min_length=4, max_length=20), return_url: str = Query(...)) -> RedirectResponse:
    target = validated_pair_return_url(return_url)
    if not pairing_window_open():
        query = urlencode({
            "pair_status": "window_closed",
            "pair_message": "盒子的安全配对时间已结束，请重启盒子后在 15 分钟内重试。",
        })
        separator = "&" if "?" in target else "?"
        return RedirectResponse(f"{target}{separator}{query}", status_code=303)
    try:
        result = cloud_pair_device(code.strip())
    except HTTPException as exc:
        query = urlencode({"pair_status": "error", "pair_message": str(exc.detail)[:180]})
        separator = "&" if "?" in target else "?"
        return RedirectResponse(f"{target}{separator}{query}", status_code=303)
    query = urlencode({
        "pair_status": "success",
        "paired_device_id": str(result.get("device_id") or current_device_id()),
    })
    separator = "&" if "?" in target else "?"
    return RedirectResponse(f"{target}{separator}{query}", status_code=303)


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
    uploaded_asset = payload.payload.get("media_upload_result") if isinstance(payload.payload.get("media_upload_result"), dict) else {}
    uploaded_asset_id = None
    if isinstance(uploaded_asset.get("asset"), dict):
        uploaded_asset_id = uploaded_asset["asset"].get("id")
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
    if uploaded_asset_id:
        asset = storage.attach_media_asset_to_event(int(uploaded_asset_id), int(event["id"]))
        if asset is not None:
            media_asset = object_storage_service.media_asset_for_api(asset)
    if media_asset is None and snapshot is not None:
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
            title=f"回家提醒：{event['summary']}",
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
            title=f"回家提醒：{event['summary']}",
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


@app.post("/api/v1/device/media-assets/upload")
async def v1_upload_device_media_asset(
    request: Request,
    file_name: str = Query(default="snapshot.jpg", min_length=1, max_length=200),
    snapshot_path: str = Query(default="", max_length=300),
    content_type: str = Query(default="image/jpeg", max_length=120),
    edge_event_id: str = Query(default="", max_length=80),
    device_session: Dict[str, Any] = Depends(current_v1_device_session),
) -> Dict[str, Any]:
    normalized_snapshot_path = normalize_snapshot_reference(snapshot_path)
    if not normalized_snapshot_path:
        raise HTTPException(status_code=400, detail="snapshot_path is required")
    body = await request.body()
    snapshot = storage.get_snapshot_by_path(normalized_snapshot_path)
    asset = object_storage_service.store_device_media_bytes(
        family_id=int(device_session["family_id"]),
        device_id=str(device_session["device_id"]),
        file_name=file_name,
        content_type=content_type or request.headers.get("content-type", "image/jpeg"),
        content_bytes=body,
        source_snapshot_path=normalized_snapshot_path,
        snapshot_id=int(snapshot["id"]) if snapshot else None,
        metadata={
            "edge_event_id": edge_event_id,
            "uploaded_by_device_id": str(device_session["device_id"]),
        },
    )
    return {"created": True, "asset": asset}


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
    if len(storage.list_cameras()) >= 3:
        raise HTTPException(status_code=400, detail="最多只能接入 3 路摄像头")
    return storage.create_camera(model_dump(camera))


def capture_preview(camera_payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        rules = storage.get_rules()
        analysis_config = {
            **rules,
            "force_demo_vision": str(camera_payload.get("stream_url", "")).strip().lower().startswith("demo:"),
        }
        capture = camera_agent.capture_frame(camera_payload, prefer_cache=False)
        analysis = detect_agent.analyze_frame_with_config(capture["frame"], config=analysis_config)
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


def capture_and_store(
    camera_id: int,
    persist_detection: bool = False,
    *,
    store_snapshot: bool = True,
    prefer_cache: bool = True,
    cache_only: bool = False,
    max_cache_age_seconds: float = 6.0,
    analysis_overrides: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    camera = storage.get_camera(camera_id, include_secret=True)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    try:
        started_at = datetime.now(timezone.utc)
        rules = storage.get_rules()
        analysis_config = {
            **rules,
            "force_demo_vision": str(camera.get("stream_url", "")).strip().lower().startswith("demo:"),
            "camera_id": camera_id,
            **(analysis_overrides or {}),
        }
        if cache_only:
            capture = camera_agent.latest_cached_frame(camera, max_age_seconds=max_cache_age_seconds)
            if capture is None:
                raise CameraError("实时视频缓存未就绪，请先保持当前页面视频流打开。")
        else:
            capture = camera_agent.capture_frame(
                camera,
                prefer_cache=prefer_cache,
                max_cache_age_seconds=max_cache_age_seconds,
            )
        analysis = detect_agent.analyze_frame_with_config(capture["frame"], config=analysis_config)
        if store_snapshot:
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
        else:
            captured_at = started_at.isoformat()
            snapshot = {
                "id": None,
                "camera_id": camera_id,
                "image_path": "",
                "image_url": "",
                "width": capture["width"],
                "height": capture["height"],
                "brightness": analysis["brightness"],
                "motion_score": analysis["motion_score"],
                "tags": analysis["tags"],
                "person_count": analysis.get("person_count"),
                "analysis": analysis,
                "captured_at": captured_at,
                "created_at": captured_at,
            }
        detection_result = None
        if persist_detection and snapshot.get("id"):
            detection_result = storage.create_detection_result(
                camera_id=camera_id,
                snapshot_id=int(snapshot["id"]),
                captured_at=snapshot["captured_at"],
                width=capture["width"],
                height=capture["height"],
                analysis=analysis,
            )
        storage.update_camera_status(camera_id, "online")
        return {
            "ok": True,
            "camera_id": camera_id,
            "width": capture["width"],
            "height": capture["height"],
            "elapsed_ms": capture["elapsed_ms"],
            "analysis_elapsed_ms": int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000),
            "source": capture["source"],
            "snapshot": snapshot,
            "analysis": analysis,
            "detection_result": detection_result,
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
    return await run_in_threadpool(capture_and_store, camera_id, False, prefer_cache=False)


@app.post("/api/cameras/{camera_id}/capture")
async def capture_camera(camera_id: int) -> Dict[str, Any]:
    return await run_in_threadpool(capture_with_pipeline, camera_id)


@app.post("/api/cameras/{camera_id}/analysis/live")
async def live_camera_analysis(camera_id: int, algorithm: str = Query(default="person")) -> Dict[str, Any]:
    normalized_algorithm = str(algorithm or "person").strip().lower()
    pose_enabled = normalized_algorithm in {"unified", "person", "fall", "meal", "stillness"}
    reuse_cached_pose = normalized_algorithm in {"unified", "person", "night"}
    result = await run_in_threadpool(
        capture_and_store,
        camera_id,
        False,
        store_snapshot=False,
        prefer_cache=True,
        cache_only=True,
        max_cache_age_seconds=8.0,
        analysis_overrides={
            "preview_algorithm": normalized_algorithm,
            "pose_detection_enabled": pose_enabled,
            "pose_reuse_cache_only": reuse_cached_pose,
            "pose_cache_seconds": 8.0 if reuse_cached_pose else settings.pose_cache_seconds,
        },
    )
    result["algorithm"] = normalized_algorithm
    return result


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
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/v1/device/cameras/{camera_id}/stream.mjpg")
def v1_device_camera_mjpeg_stream(
    camera_id: int,
    fps: int = 5,
    width: int = 1280,
    height: int = 720,
    quality: int = 70,
    drop: int = 4,
    _device_session: Dict[str, Any] = Depends(current_v1_device_stream_session),
) -> StreamingResponse:
    return camera_mjpeg_stream(
        camera_id=camera_id,
        fps=fps,
        width=width,
        height=height,
        quality=quality,
        drop=drop,
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


@app.get("/api/event-log")
def event_log(limit: int = 80) -> Dict[str, Any]:
    resolved_limit = max(1, min(limit, 200))
    events = storage.list_events(limit=resolved_limit)
    jobs = storage.list_upload_jobs(limit=min(500, resolved_limit * 4))
    jobs_by_event: Dict[int, list[Dict[str, Any]]] = {}
    for job in jobs:
        if job.get("event_id"):
            jobs_by_event.setdefault(int(job["event_id"]), []).append(job)
    cloud_error = ""
    try:
        cloud_payload = upload_agent.event_log_status(limit=resolved_limit)
    except Exception as exc:
        cloud_payload = {"ok": False, "records": []}
        cloud_error = str(exc)
    cloud_records = cloud_payload.get("records") if isinstance(cloud_payload.get("records"), list) else []
    cloud_by_edge_id = {
        str(record.get("edge_event_id")): record
        for record in cloud_records
        if record.get("edge_event_id") not in (None, "")
    }
    rows = []
    for event in events:
        event_jobs = jobs_by_event.get(int(event["id"]), [])
        event_upload = next((job for job in event_jobs if job.get("job_type") == "event_upload"), None)
        media_upload = next((job for job in event_jobs if job.get("job_type") == "media_upload"), None)
        cloud = cloud_by_edge_id.get(str(event["id"]))
        if cloud:
            sync_status = "cloud_received"
        elif event_upload:
            sync_status = str(event_upload.get("status") or "pending")
        else:
            sync_status = "local_only"
        rows.append({
            "local_event": event,
            "sync": {
                "status": sync_status,
                "event_upload": event_upload,
                "media_upload": media_upload,
            },
            "cloud_event": cloud,
        })
    return {
        "ok": True,
        "cloud_ok": bool(cloud_payload.get("ok")),
        "cloud_error": cloud_error or str(cloud_payload.get("reason") or ""),
        "records": rows,
    }


@app.get("/api/event-candidates")
def list_event_candidates(limit: int = 20, status: str | None = None) -> list[Dict[str, Any]]:
    normalized_status = (status or "").strip().lower() or None
    return storage.list_event_candidates(limit=max(1, min(limit, 200)), status=normalized_status)


@app.get("/api/observation-logs")
def list_observation_logs(limit: int = 20, status: str | None = None) -> list[Dict[str, Any]]:
    normalized_status = (status or "").strip().lower() or None
    return storage.list_observation_logs(limit=max(1, min(limit, 200)), status=normalized_status)


@app.get("/api/presence-sessions")
def list_presence_sessions(limit: int = 50, status: str | None = None) -> list[Dict[str, Any]]:
    normalized_status = (status or "").strip().lower() or None
    return storage.list_presence_sessions(limit=max(1, min(limit, 500)), status=normalized_status)


@app.get("/api/posture-episodes")
def list_posture_episodes(limit: int = 100, status: str | None = None) -> list[Dict[str, Any]]:
    normalized_status = (status or "").strip().lower() or None
    return storage.list_posture_episodes(limit=max(1, min(limit, 1000)), status=normalized_status)


@app.get("/api/upload-jobs")
def list_upload_jobs(
    limit: int = 50,
    status: str | None = None,
    job_type: str | None = None,
) -> list[Dict[str, Any]]:
    return storage.list_upload_jobs(
        limit=max(1, min(limit, 200)),
        status=(status or "").strip().lower() or None,
        job_type=(job_type or "").strip().lower() or None,
    )


@app.get("/api/upload-jobs/summary")
def upload_jobs_summary() -> Dict[str, Any]:
    return storage.upload_queue_summary()


@app.get("/api/cloud-verifications")
def cloud_verification_status(limit: int = 12) -> Dict[str, Any]:
    try:
        return upload_agent.vision_verification_status(limit=max(1, min(limit, 50)))
    except Exception as exc:
        return {
            "ok": False,
            "configured": upload_agent.status().get("configured", False),
            "reason": str(exc),
            "records": [],
        }


@app.get("/api/events/{event_id}")
def get_event(event_id: int) -> Dict[str, Any]:
    event = storage.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@app.post("/api/events/{event_id}/false-positive")
def mark_event_false_positive(event_id: int) -> Dict[str, Any]:
    event = storage.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    try:
        cloud = upload_agent.submit_event_feedback(event_id, resolution="false_positive")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"云端误报反馈失败：{exc}") from exc
    updated = storage.update_event(event_id, {"acknowledged": True, "resolution": "false_positive"})
    return {"ok": True, "local_event": updated, "cloud_event": cloud.get("event") or cloud}


@app.get("/api/events/{event_id}/server-payload")
def get_event_server_payload(event_id: int) -> Dict[str, Any]:
    event = storage.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event_server_payload(event)


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
