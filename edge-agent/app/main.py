from __future__ import annotations

from typing import Any, Dict
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request as UrlRequest, urlopen
from importlib.util import find_spec
import ipaddress
import json
import logging
import re
import shutil
import socket
import subprocess
import time
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

from .app_runtime_guard_service import AppRuntimeGuardService
from .box_init_service import ADMIN_SESSION_COOKIE, AdminLoginThrottled, BoxInitService
from .camera_agent import CameraAgent, CameraError, bounded_stream_fps
from .camera_config_authority import camera_config_authority
from .config_sync_agent import ConfigSyncAgent
from .detect_agent import DetectAgent
from .device_binding_state import DeviceBindingState
from .event_agent import EventAgent
from .live_relay_agent import LiveRelayAgent
from .package_artifact_service import PackageArtifactService, build_package_artifact_router
from .package_service import PackageService
from .pairing_window import PairingWindow
from .resource_monitor import SystemResourceMonitor
from .schemas import (
    AdminLogin,
    AdminPasswordChange,
    CameraCreate,
    CameraUpdate,
    DeviceHeartbeatIn,
    EventUpdate,
    V1DeviceUpgradeRun,
    RulesUpdate,
    WifiConnectRequest,
    V1PackageDownloadLinkCreate,
    V1PackageReleaseCreate,
    V1DeviceRolloutCreate,
    V1DeviceRolloutPromote,
    V1DeviceRolloutRollback,
    V1DeviceEventIngest,
    V1DeviceSyncReport,
    V1DeviceSyncTargetUpdate,
    VideoPrivacyUpdate,
)
from .settings import settings
from .storage import Storage
from .upload_agent import UploadAgent
from .video_privacy import normalize_privacy_mode, stricter_privacy_mode
from .vision.privacy_stream import PrivacyFrameRenderer, PrivacyMjpegStream
from .vision.privacy_background import PrivacyBackgroundReconstructor, PrivacyCalibrationRequired
from .vision.hailo_segmentation import HailoPersonSegmentationBackend
from .adaptive_inference_scheduler import AdaptiveInferenceScheduler
from .eacp_acceptance import EacpAcceptanceService
from .worker import EdgeWorker
from .vision.synchronized_pose_stream import SynchronizedPoseStream
from .runtime_lifecycle import stop_components

bearer_scheme = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)
SETUP_NETWORK_PAGE = "/setup/network.html"
SETUP_HOTSPOT_ORIGIN = "http://10.42.0.1"
SETUP_HOTSPOT_NETWORK_PAGE = f"{SETUP_HOTSPOT_ORIGIN}{SETUP_NETWORK_PAGE}"
ADMIN_AUTH_ASSET_REVISION = "20260803-auth-5"
ADMIN_AUTH_CACHE_CONTROL = "no-store, no-cache, must-revalidate, max-age=0"


def model_dump(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def normalize_snapshot_reference(snapshot_path: str) -> str:
    value = str(snapshot_path or "").strip()
    for prefix in ("/api/app/media/snapshots/", "/api/v1/video/media/snapshots/", "/snapshots/"):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    return value.lstrip("/")


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


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> Dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required")
    user = storage.get_user_by_session_token(credentials.credentials)
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


def pairing_window_open() -> bool:
    return pairing_window.is_open()


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
    bootstrap_cameras = [
        {
            "local_camera_id": camera.get("id"),
            "name": camera.get("name") or "摄像头",
            "room": camera.get("room") or "",
            "stream_url": camera.get("stream_url") or "",
            "username": camera.get("username"),
            "password": camera.get("password"),
            "enabled": bool(camera.get("enabled", True)),
        }
        for camera in storage.list_cameras(include_secret=True)
        if str(camera.get("stream_url") or "").strip()
    ]
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
        "bootstrap_cameras": bootstrap_cameras,
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
    binding_state.write(result.get("binding_summary"))
    pairing_window.close()
    return result


def require_device_access(user: Dict[str, Any]) -> str:
    device_id = current_device_id()
    if not storage.list_device_bound_family_ids(device_id):
        raise HTTPException(status_code=403, detail="Current device is not bound to any family")
    if not storage.user_has_device_access(int(user["id"]), device_id):
        raise HTTPException(status_code=403, detail="You do not have access to this device")
    return device_id


def current_camera_config_authority() -> Dict[str, Any]:
    return camera_config_authority(
        settings,
        storage,
        current_device_id(),
        cloud_claimed=bool(read_local_device_token()),
    )


def require_local_camera_mutation() -> None:
    authority = current_camera_config_authority()
    if not authority["local_mutation_allowed"]:
        raise HTTPException(
            status_code=409,
            detail="摄像头配置由回家 App 统一管理，请在 App 中添加、删除或启停摄像头。",
        )


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


def event_for_v1(event: Dict[str, Any]) -> Dict[str, Any]:
    return dict(event)


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
        "upload_agent": upload_agent.status(),
        "config_sync_agent": config_sync_agent.status(),
        "camera_config_authority": current_camera_config_authority(),
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
            "media_asset": data.get("media_asset"),
        },
    }


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
binding_state = DeviceBindingState(settings.data_dir / "device-binding-summary.json")
pairing_window = PairingWindow(settings.lan_pairing_window_seconds)
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
    inference_backend=settings.inference_backend,
    hailo_pose_model=settings.hailo_pose_model,
    hailo_pose_confidence=settings.hailo_pose_confidence,
    hailo_pose_nms_iou=settings.hailo_pose_nms_iou,
    hailo_object_mode=settings.hailo_object_mode,
    hailo_object_model=settings.hailo_object_model,
    hailo_object_confidence=settings.hailo_object_confidence,
    hailo_object_interval_seconds=settings.hailo_object_interval_seconds,
    hailo_retry_seconds=settings.hailo_retry_seconds,
    context_detection_interval_seconds=settings.context_detection_interval_seconds,
)
event_agent = EventAgent(storage, settings.event_throttle_seconds)
resource_monitor = (
    SystemResourceMonitor(
        warm_temperature_c=settings.thermal_warm_temperature_c,
        hot_temperature_c=settings.thermal_hot_temperature_c,
        critical_temperature_c=settings.thermal_critical_temperature_c,
        sample_interval_seconds=settings.thermal_sample_interval_seconds,
    )
    if settings.thermal_monitor_enabled
    else None
)
worker = EdgeWorker(
    storage,
    camera_agent,
    detect_agent,
    event_agent,
    snapshot_dir=settings.snapshot_dir,
    object_storage_dir=settings.object_storage_dir,
    runtime_dir=settings.runtime_dir,
    history_retention_hours=settings.history_retention_hours,
    history_cleanup_interval_seconds=settings.history_cleanup_interval_seconds,
    history_cleanup_batch_size=settings.history_cleanup_batch_size,
    completed_upload_retention_days=settings.completed_upload_retention_days,
    event_evidence_retention_hours=settings.event_evidence_retention_hours,
    local_event_retention_days=settings.local_event_retention_days,
    local_runtime_budget_mb=settings.local_runtime_budget_mb,
    activity_log_interval_seconds=settings.activity_log_interval_seconds,
    activity_posture_stability_seconds=settings.activity_posture_stability_seconds,
    activity_absence_stability_seconds=settings.activity_absence_stability_seconds,
    risk_evidence_interval_seconds=settings.risk_evidence_interval_seconds,
    local_storage_high_watermark_percent=settings.local_storage_high_watermark_percent,
    local_storage_critical_percent=settings.local_storage_critical_percent,
    inference_scheduler=AdaptiveInferenceScheduler(
        idle_interval_seconds=settings.inference_idle_interval_seconds,
        active_interval_seconds=settings.inference_active_interval_seconds,
        risk_interval_seconds=settings.inference_risk_interval_seconds,
        accelerated_idle_interval_seconds=settings.inference_accelerated_idle_interval_seconds,
        accelerated_active_interval_seconds=settings.inference_accelerated_active_interval_seconds,
        accelerated_risk_interval_seconds=settings.inference_accelerated_risk_interval_seconds,
        resource_monitor=resource_monitor,
        max_starvation_seconds=settings.inference_max_starvation_seconds,
    ),
)
synchronized_pose_stream = SynchronizedPoseStream(camera_agent, worker.continual_pose_tracker)
package_artifact_service = PackageArtifactService(storage=storage, settings=settings)
config_sync_agent = ConfigSyncAgent(
    storage=storage,
    settings=settings,
    camera_agent=camera_agent,
    device_id_resolver=current_device_id,
    token_resolver=read_local_device_token,
    binding_summary_writer=binding_state.write,
    event_state_handler=worker.apply_event_state_command,
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
                object_storage_dir=settings.object_storage_dir,
                runtime_dir=settings.runtime_dir,
                retention_hours=settings.history_retention_hours,
            ),
            "last_cleanup": worker.last_history_cleanup_result,
        },
    },
    live_status_resolver=lambda camera_id: live_relay_agent.camera_delivery_status(camera_id),
    presence_status_resolver=worker.camera_presence_status,
)
upload_agent = UploadAgent(
    storage=storage,
    settings=settings,
    device_id_resolver=current_device_id,
    token_resolver=read_local_device_token,
    remote_camera_id_resolver=config_sync_agent.remote_camera_id_for_local_camera,
)
eacp_acceptance_service = EacpAcceptanceService(
    state_path=settings.data_dir / "eacp_acceptance.json",
    runtime_resolver=worker.runtime_status,
    events_resolver=lambda: storage.list_events(limit=200),
    candidates_resolver=lambda: storage.list_event_candidates(limit=200),
    uploads_resolver=lambda: storage.list_upload_jobs(limit=500),
    cloud_verification_resolver=lambda: upload_agent.vision_verification_status(limit=50),
)
person_segmentation_backend = HailoPersonSegmentationBackend(
    mode=settings.hailo_segmentation_mode,
    model_path=settings.hailo_segmentation_model,
    confidence=settings.hailo_segmentation_confidence,
    anchor_interval_seconds=settings.hailo_segmentation_anchor_interval_seconds,
    maximum_propagation_seconds=settings.hailo_segmentation_maximum_propagation_seconds,
    flow_width=settings.hailo_segmentation_flow_width,
)
privacy_frame_renderer = PrivacyFrameRenderer(
    worker.continual_pose_tracker,
    background_reconstructor=PrivacyBackgroundReconstructor(
        storage_dir=settings.data_dir / "privacy-calibrations",
    ),
    segmentation_backend=person_segmentation_backend,
)
privacy_mjpeg_stream = PrivacyMjpegStream(camera_agent, privacy_frame_renderer)
live_relay_agent = LiveRelayAgent(
    storage=storage,
    settings=settings,
    camera_agent=camera_agent,
    device_id_resolver=current_device_id,
    token_resolver=read_local_device_token,
    remote_camera_id_resolver=config_sync_agent.remote_camera_id_for_local_camera,
    privacy_mode_resolver=config_sync_agent.video_privacy_mode,
    privacy_renderer=privacy_frame_renderer,
)
live_relay_agent.set_delivery_status_callback(config_sync_agent.wake)


def handle_camera_source_transition(transition: Dict[str, Any]) -> None:
    live_relay_agent.handle_camera_source_transition(transition)
    worker.handle_camera_source_transition(transition)
    privacy_frame_renderer.reset_camera(int(transition.get("camera_id") or 0))


camera_agent.add_source_change_listener(handle_camera_source_transition)
package_service = PackageService(storage=storage, settings=settings, artifact_store=package_artifact_service)
app_runtime_guard = AppRuntimeGuardService(
    settings=settings,
    current_manifest_loader=lambda: package_service.read_current_manifest("app"),
)
package_service.runtime_guard = app_runtime_guard

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
        "/api/admin/pairing-window",
        "/api/admin/video-privacy",
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
        "/api/eacp-acceptance",
        "/snapshots",
    )
    return path == "/api/device" or any(path == prefix or path.startswith(f"{prefix}/") for prefix in protected_prefixes)


def request_from_private_lan(request: Request) -> bool:
    host = request.client.host if request.client else ""
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return False


def private_lan_camera_discovery(request: Request) -> bool:
    return (
        request.method == "GET"
        and request.url.path == "/api/cameras/discover"
        and request_from_private_lan(request)
    )


def admin_login_redirect(request: Request) -> RedirectResponse:
    target = request.url.path
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return RedirectResponse(
        url=f"/admin/login.html?v={ADMIN_AUTH_ASSET_REVISION}&next={quote(target, safe='')}",
        status_code=303,
    )


def admin_auth_response_requires_no_store(path: str) -> bool:
    return path.startswith("/api/admin/auth/") or path in {
        "/admin/login.html",
        "/admin/login.js",
        "/admin/styles.css",
    }


@app.middleware("http")
async def enforce_admin_session(request: Request, call_next: Any) -> Response:
    requires_page_auth = admin_path_requires_auth(request.url.path)
    requires_api_auth = admin_api_requires_auth(request.url.path) and not private_lan_camera_discovery(request)
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
    response = await call_next(request)
    if admin_auth_response_requires_no_store(request.url.path):
        response.headers["Cache-Control"] = ADMIN_AUTH_CACHE_CONTROL
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


app.include_router(
    build_package_artifact_router(
        package_artifact_service,
        current_user_dep=current_user,
    )
)
app.mount("/snapshots", StaticFiles(directory=str(settings.snapshot_dir)), name="snapshots")
app.mount("/setup", StaticFiles(directory=str(settings.setup_dir), html=True), name="setup")
app.mount("/admin", StaticFiles(directory=str(settings.admin_dir), html=True), name="admin")


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
    if not settings.disable_worker:
        worker.start()
    upload_agent.start()
    live_relay_agent.start()
    config_sync_agent.start()
    app_runtime_guard.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    result = stop_components(
        [
            ("app-runtime-guard", app_runtime_guard.stop),
            ("config-sync", config_sync_agent.stop),
            ("live-relay", live_relay_agent.stop),
            ("privacy-renderer", privacy_frame_renderer.close),
            ("upload", upload_agent.stop),
            ("worker", worker.stop),
        ],
        timeout_seconds=7.0,
    )
    if result["unfinished"] or result["errors"]:
        logger.error("Edge shutdown incomplete: %s", result)
    else:
        logger.info("Edge shutdown completed: %s", result)


@app.get("/health")
def health() -> Dict[str, Any]:
    worker_status = worker.runtime_status()
    vision_status = worker_status.get("vision_runtime") or {}
    pose_status = vision_status.get("inference_backend") or {}
    context_status = vision_status.get("context_inference_backend") or {}
    return {
        "status": "ok",
        "service": "gohome-edge-agent",
        "worker_running": worker.is_running,
        "vision_runtime": {
            "pose_inference_service": vision_status.get("pose_inference_service") or {},
            "pose": {
                key: pose_status.get(key)
                for key in (
                    "schema_version", "mode", "status", "last_latency_ms",
                    "latency_summary_ms", "successful_inferences", "failed_inferences",
                )
            },
            "context": {
                key: context_status.get(key)
                for key in (
                    "schema_version", "mode", "status", "last_latency_ms",
                    "latency_summary_ms", "successful_inferences", "failed_inferences", "cache_count",
                    "pet_temporal",
                )
            },
            "pipeline_latency_ms": vision_status.get("pipeline_latency_ms") or {},
            "human_evidence": vision_status.get("human_evidence") or {},
        },
        "persistence": worker_status.get("persistence") or {},
        "camera_streams": worker_status.get("camera_streams") or {},
        "inference_scheduler": worker_status.get("inference_scheduler") or {},
        "pose_inference_coordinator": worker_status.get("pose_inference_coordinator") or {},
        "pose_candidate_validation": worker_status.get("pose_candidate_validation") or {},
        "continual_pose": worker_status.get("continual_pose") or {},
        "continual_pose_error": str(worker_status.get("continual_pose_error") or ""),
        "config_sync_agent": config_sync_agent.status(),
        "live_relay_agent": live_relay_agent.status(),
        "lan_url": f"http://{local_ip()}:{settings.port}",
        "app_runtime": app_runtime_guard.status(),
    }


@app.get("/api/device")
def device() -> Dict[str, Any]:
    device_identity = local_device_identity()
    pairing = pairing_window.status()
    binding = binding_state.read()
    return {
        "device_id": device_identity["device_id"],
        "name": socket.gethostname(),
        "lan_ip": local_ip(),
        "api_port": settings.port,
        "api_base_url": f"http://{local_ip()}:{settings.port}",
        "data_dir": str(settings.data_dir),
        "db_path": str(settings.db_path),
        "snapshot_dir": str(settings.snapshot_dir),
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
        "app_runtime": app_runtime_guard.status(),
        "binding": binding,
        "pairing": pairing,
    }


@app.get("/api/admin/auth/status")
def admin_auth_status(request: Request) -> Dict[str, Any]:
    return box_init_service.status(request.cookies.get(ADMIN_SESSION_COOKIE, ""))


@app.post("/api/admin/auth/login")
def admin_auth_login(payload: AdminLogin, request: Request, response: Response) -> Dict[str, Any]:
    client_ip = request.client.host if request.client else "unknown"
    try:
        session = box_init_service.authenticate(
            payload.username.strip(),
            payload.password,
            client_ip=client_ip,
        )
    except AdminLoginThrottled as exc:
        raise HTTPException(
            status_code=429,
            detail=f"登录尝试过于频繁，请在 {exc.retry_after_seconds} 秒后重试。",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
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


@app.post("/api/admin/pairing-window")
def admin_open_pairing_window() -> Dict[str, Any]:
    if binding_state.read().get("status") == "bound":
        raise HTTPException(status_code=409, detail="盒子已经绑定家庭，请先由家庭创建者在 App 中解除绑定。")
    return {
        "ok": True,
        "pairing": pairing_window.open(600),
    }


@app.get("/api/admin/video-privacy")
def admin_video_privacy() -> Dict[str, Any]:
    relay = live_relay_agent.status()
    return {
        "ok": True,
        "minimum_mode": config_sync_agent.video_privacy_mode(),
        "camera_modes": dict(relay.get("camera_privacy_modes") or {}),
        "calibrations": privacy_calibration_status(),
        "synced": not bool(config_sync_agent.last_video_privacy_error),
        "updated_at": config_sync_agent.last_video_privacy_sync_at or "",
        "sync_error": config_sync_agent.last_video_privacy_error,
    }


@app.put("/api/admin/video-privacy")
def update_admin_video_privacy(payload: VideoPrivacyUpdate) -> Dict[str, Any]:
    if normalize_privacy_mode(payload.minimum_mode) == "skeleton":
        calibration = privacy_calibration_status()
        unavailable = [item for item in calibration if item.get("enabled") and not item.get("ready")]
        if unavailable:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "calibration_required",
                    "message": "请先完成所有启用摄像头的空房校准。",
                    "cameras": unavailable,
                },
            )
    result = config_sync_agent.update_video_privacy(payload.minimum_mode)
    live_relay_agent.wake()
    return {
        **result,
        "camera_modes": dict(live_relay_agent.status().get("camera_privacy_modes") or {}),
        "calibrations": privacy_calibration_status(),
    }


def privacy_calibration_status() -> list[Dict[str, Any]]:
    cameras = storage.list_cameras(include_secret=True)
    discovered_by_camera: Dict[int, list[Dict[str, Any]]] = {}
    for camera in cameras:
        camera_id = int(camera["id"])
        discovered_by_camera[camera_id] = privacy_frame_renderer.discover_calibrations(
            camera_id,
            source_key=camera_agent.active_frame_source_key(camera),
        )
    runtime = privacy_frame_renderer.background_reconstructor.status()
    states = runtime.get("states") if isinstance(runtime.get("states"), list) else []
    state_by_camera: Dict[int, Dict[str, Any]] = {}
    for camera in cameras:
        camera_id = int(camera["id"])
        candidates = discovered_by_camera.get(camera_id) or [
            dict(item) for item in states
            if int(item.get("camera_id") or 0) == camera_id
        ]
        if candidates:
            state_by_camera[camera_id] = max(
                candidates,
                key=lambda item: (
                    bool(item.get("ready")),
                    bool(item.get("calibrated")),
                    int(item.get("width") or 0) * int(item.get("height") or 0),
                ),
            )
    result: list[Dict[str, Any]] = []
    for camera in cameras:
        camera_id = int(camera["id"])
        item = {
            "camera_id": camera_id,
            "name": str(camera.get("name") or f"摄像头 {camera_id}"),
            "room": str(camera.get("room") or ""),
            "enabled": bool(camera.get("enabled", True)),
            "ready": False,
            "status": "calibration_required",
            **state_by_camera.get(camera_id, {}),
        }
        result.append(item)
    return result


def require_privacy_stream_ready(camera_id: int, privacy_mode: str) -> None:
    if privacy_mode != "skeleton":
        return
    calibration = next(
        (item for item in privacy_calibration_status() if int(item.get("camera_id") or 0) == int(camera_id)),
        None,
    )
    if calibration and calibration.get("ready"):
        return
    if (
        calibration
        and calibration.get("calibrated")
        and calibration.get("baseline_retained")
        and calibration.get("status") == "revalidating"
    ):
        return
    reason = str((calibration or {}).get("status") or "calibration_required")
    raise HTTPException(
        status_code=409,
        detail={
            "code": reason,
            "message": (
                "场景发生变化，请重新完成空房校准。"
                if reason == "scene_review_required"
                else "纯骨架画面需要先完成空房校准。"
            ),
            "camera_id": int(camera_id),
            "calibration": calibration or {},
        },
    )


def calibrate_privacy_background(camera_id: int) -> Dict[str, Any]:
    camera = storage.get_camera(camera_id, include_secret=True)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    if not bool(camera.get("enabled", True)):
        raise HTTPException(status_code=409, detail="摄像头已停用，无法校准。")

    deadline = time.monotonic() + 12.0
    calibration_id = f"cal-{uuid4().hex}"
    started = False
    finalized = False
    calibration_source_key = ""
    calibration_width = 0
    calibration_height = 0
    failure_reason = "calibration_timeout"
    last_status: Dict[str, Any] = {}

    def cancel_started_calibration(reason: str) -> Dict[str, Any]:
        nonlocal finalized, last_status
        if not started or finalized:
            return last_status
        last_status = privacy_frame_renderer.cancel_calibration(
            camera_id,
            source_key=calibration_source_key,
            width=calibration_width,
            height=calibration_height,
            reason=str(reason or "calibration_cancelled"),
        )
        finalized = True
        return last_status

    try:
        for capture in camera_agent.raw_frames(
            camera,
            fps=15,
            max_width=640,
            max_height=360,
        ):
            frame = capture.get("frame") if isinstance(capture, dict) else None
            if frame is None:
                if time.monotonic() >= deadline:
                    break
                continue
            source_key = str(capture.get("source_key") or "")
            frame_id = str(capture.get("frame_id") or "")
            if not started:
                height, width = frame.shape[:2]
                calibration_source_key = source_key
                calibration_width = int(width)
                calibration_height = int(height)
                privacy_frame_renderer.begin_calibration(
                    camera_id,
                    source_key=source_key,
                    width=width,
                    height=height,
                    calibration_id=calibration_id,
                )
                started = True
            last_status = privacy_frame_renderer.observe_calibration_frame(
                camera_id,
                frame,
                source_key=source_key,
                frame_id=frame_id,
                captured_at=str(capture.get("captured_at") or ""),
                captured_monotonic=capture.get("captured_monotonic"),
            )
            if last_status.get("ready"):
                finalized = True
                live_relay_agent.wake()
                return {"ok": True, "calibration": last_status}
            if time.monotonic() >= deadline:
                break
    except PrivacyCalibrationRequired as exc:
        failure_reason = exc.reason
        cancel_started_calibration(failure_reason)
        raise HTTPException(
            status_code=409,
            detail={
                "code": exc.reason,
                "message": "校准暂时无法完成，请确认画面无人后重试。",
                "calibration": last_status,
            },
        ) from exc
    except OSError as exc:
        failure_reason = "calibration_persistence_failed"
        cancel_started_calibration(failure_reason)
        raise HTTPException(
            status_code=503,
            detail={
                "code": failure_reason,
                "message": "校准背景暂时无法安全保存，请检查盒子存储后重试。",
                "calibration": last_status,
            },
        ) from exc
    finally:
        if started and not finalized:
            failure_reason = str(last_status.get("last_error") or failure_reason)
            cancel_started_calibration(failure_reason)

    raise HTTPException(
        status_code=409,
        detail={
            "code": str(last_status.get("last_error") or failure_reason),
            "message": "未取得连续稳定的空房画面，请确认画面无人且摄像头固定后重试。",
            "calibration": last_status,
        },
    )


@app.post("/api/admin/cameras/{camera_id}/privacy-calibration")
async def start_privacy_calibration(camera_id: int) -> Dict[str, Any]:
    return await run_in_threadpool(calibrate_privacy_background, camera_id)


@app.post("/api/admin/auth/change-password")
def admin_auth_change_password(payload: AdminPasswordChange, request: Request, response: Response) -> Dict[str, Any]:
    if payload.new_password == payload.old_password:
        raise HTTPException(status_code=400, detail="新密码不能与当前密码相同。")
    changed = box_init_service.change_password(
        request.cookies.get(ADMIN_SESSION_COOKIE, ""),
        payload.old_password,
        payload.new_password,
        client_ip=request.client.host if request.client else "unknown",
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


@app.get("/api/lan/discovery")
def lan_discovery() -> Dict[str, Any]:
    identity = local_device_identity()
    return {
        "product": "gohome-box",
        "device_id": identity["device_id"],
        "device_name": identity["device_name"],
        "lan_ip": identity["lan_ip"],
        "api_port": identity["api_port"],
        "pairing_window_open": pairing_window_open() and binding_state.read().get("status") != "bound",
    }


@app.post("/api/lan/config-sync/wake", status_code=202)
def wake_config_sync_from_lan(request: Request) -> Dict[str, Any]:
    if not request_from_private_lan(request):
        raise HTTPException(status_code=403, detail="仅允许家庭局域网唤醒配置同步。")
    return {"ok": True, "queued": config_sync_agent.wake()}


@app.get("/pair")
def pair_from_lan(code: str = Query(..., min_length=4, max_length=20), return_url: str = Query(...)) -> RedirectResponse:
    target = validated_pair_return_url(return_url)
    if binding_state.read().get("status") == "bound":
        query = urlencode({
            "pair_status": "error",
            "pair_message": "盒子已经绑定家庭，请先由家庭创建者在 App 中解除绑定。",
        })
        separator = "&" if "?" in target else "?"
        return RedirectResponse(f"{target}{separator}{query}", status_code=303)
    if not pairing_window_open():
        query = urlencode({
            "pair_status": "window_closed",
            "pair_message": "安全配对时间已结束，请在盒子管理端开启 10 分钟安全配对后重试。",
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

    normalized_snapshot_path = normalize_snapshot_reference(payload.snapshot_path)
    snapshot = storage.get_snapshot_by_path(normalized_snapshot_path) if normalized_snapshot_path else None

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
    storage.bind_event_ingest(device_id, payload.idempotency_key, int(event["id"]))
    return {
        "accepted": True,
        "deduplicated": False,
        "idempotency_key": payload.idempotency_key,
        "event": v1_event_summary(event),
    }


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


@app.get("/api/cameras")
def list_cameras() -> list[Dict[str, Any]]:
    return storage.list_cameras()


@app.post("/api/cameras")
def create_camera(camera: CameraCreate) -> Dict[str, Any]:
    require_local_camera_mutation()
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
    require_local_camera_mutation()
    camera = storage.update_camera(camera_id, model_dump(patch))
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


@app.delete("/api/cameras/{camera_id}")
def delete_camera(camera_id: int) -> Dict[str, Any]:
    require_local_camera_mutation()
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
    include_frame_data: bool = False,
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
            captured_at = str(capture.get("captured_at") or started_at.isoformat())
            snapshot = {
                "id": None,
                "camera_id": camera_id,
                "image_path": "",
                "image_url": camera_agent.frame_data_url(capture["frame"]) if include_frame_data else "",
                "frame_id": str(capture.get("frame_id") or ""),
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
            "frame_id": str(capture.get("frame_id") or snapshot.get("frame_id") or ""),
            "captured_at": str(capture.get("captured_at") or snapshot.get("captured_at") or ""),
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
    result = await run_in_threadpool(
        capture_and_store,
        camera_id,
        False,
        store_snapshot=False,
        prefer_cache=True,
        cache_only=True,
        max_cache_age_seconds=1.5,
        include_frame_data=True,
        analysis_overrides={
            "preview_algorithm": normalized_algorithm,
            "pose_detection_enabled": pose_enabled,
            "pose_reuse_cache_only": False,
            "pose_cache_seconds": 0.0,
        },
    )
    result["algorithm"] = normalized_algorithm
    return result


def continual_pose_live_snapshot(camera_id: int, *, include_frame: bool = True) -> Dict[str, Any]:
    camera = storage.get_camera(camera_id, include_secret=True)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    tracker = worker.continual_pose_tracker
    if not include_frame:
        metadata = tracker.latest_metadata(camera_id) if tracker is not None else {}
        tracking = metadata.get("tracking") if isinstance(metadata.get("tracking"), dict) else {
            "state": "empty",
            "reason": "tracker_disabled",
            "frame_id": "",
            "captured_at": "",
            "age_seconds": None,
            "pose_count": 0,
            "poses": [],
            "quality": {},
            "formal_evidence_eligible": False,
        }
        display_poses = (
            list(tracking.get("poses") or [])
            if tracking.get("state") in {"observed", "tracked"}
            and not bool(tracking.get("display_only_stale"))
            else []
        )
        display_people = [
            {
                "bbox": pose.get("bbox") or [],
                "confidence": pose.get("confidence"),
                "track_id": pose.get("track_id"),
                "source": "continual_pose",
                "pose_tracking_state": tracking.get("state"),
                "display_only": tracking.get("state") != "observed",
            }
            for pose in display_poses
            if pose.get("bbox")
        ]
        width = int(metadata.get("image_width") or 0)
        height = int(metadata.get("image_height") or 0)
        analysis = dict(metadata.get("analysis_context") or {})
        analysis.update({
            "image_width": width,
            "image_height": height,
            "people": display_people,
            "person_count": len(display_people),
            "poses": display_poses,
            "pose_count": len(display_poses),
            "pose_tracking_state": tracking.get("state"),
            "continual_pose": tracking,
        })
        pose_display_available = bool(display_poses)
        captured_at = str(tracking.get("captured_at") or "")
        snapshot = {
            "id": None,
            "camera_id": camera_id,
            "frame_id": str(tracking.get("frame_id") or ""),
            "width": width,
            "height": height,
            "person_count": len(display_people),
            "analysis": analysis,
            "captured_at": captured_at,
            "created_at": captured_at,
        }
        return {
            "ok": True,
            "available": pose_display_available,
            "frame_available": pose_display_available,
            "camera_id": camera_id,
            "tracking": tracking,
            "snapshot": snapshot,
        }

    capture = camera_agent.latest_cached_frame(camera, max_age_seconds=1.5)
    if capture is None:
        tracking = tracker.latest(camera_id) if tracker is not None else {
            "state": "empty",
            "reason": "tracker_disabled",
            "frame_id": "",
            "captured_at": "",
            "age_seconds": None,
            "pose_count": 0,
            "poses": [],
            "quality": {},
            "formal_evidence_eligible": False,
        }
        return {
            "ok": True,
            "available": False,
            "camera_id": camera_id,
            "tracking": tracking,
        }

    frame = capture["frame"]
    source = str(capture.get("source") or "camera_cache")
    frame_id = str(capture.get("frame_id") or "")
    captured_at = str(capture.get("captured_at") or "")
    source_key = str(capture.get("source_key") or "")
    metadata = (
        tracker.metadata_for_frame(camera_id, frame_id=frame_id, source_key=source_key)
        if tracker is not None and frame_id
        else None
    )
    if isinstance(metadata, dict):
        tracking = dict(metadata.get("tracking") or {})
        analysis = dict(metadata.get("analysis_context") or {})
    else:
        tracking = {
            "camera_id": camera_id,
            "state": "empty",
            "reason": "pose_frame_unavailable",
            "frame_id": frame_id,
            "captured_at": str(capture.get("captured_at") or ""),
            "source_key": source_key,
            "poses": [],
            "pose_count": 0,
            "formal_evidence_eligible": False,
        }
        analysis = {}

    height, width = frame.shape[:2]
    display_poses = (
        list(tracking.get("poses") or [])
        if tracking.get("state") in {"observed", "tracked"}
        and not bool(tracking.get("display_only_stale"))
        else []
    )
    display_people = [
        {
            "bbox": pose.get("bbox") or [],
            "confidence": pose.get("confidence"),
            "track_id": pose.get("track_id"),
            "source": "continual_pose",
            "pose_tracking_state": tracking.get("state"),
            "display_only": tracking.get("state") != "observed",
        }
        for pose in display_poses
        if pose.get("bbox")
    ]
    analysis.update({
        "image_width": width,
        "image_height": height,
        "people": display_people,
        "person_count": len(display_people),
        "poses": display_poses,
        "pose_count": len(display_poses),
        "pose_tracking_state": tracking.get("state"),
        "continual_pose": tracking,
    })
    snapshot = {
        "id": None,
        "camera_id": camera_id,
        "image_url": camera_agent.frame_data_url(frame, jpeg_quality=62, max_width=960),
        "frame_id": frame_id,
        "width": width,
        "height": height,
        "person_count": len(display_people),
        "analysis": analysis,
        "captured_at": captured_at,
        "created_at": captured_at,
    }
    return {
        "ok": True,
        "available": True,
        "camera_id": camera_id,
        "source": source,
        "frame_id": frame_id,
        "captured_at": captured_at,
        "tracking": tracking,
        "snapshot": snapshot,
    }


@app.get("/api/cameras/{camera_id}/continual-pose/live")
async def live_continual_pose(camera_id: int, include_frame: bool = Query(default=False)) -> Dict[str, Any]:
    return await run_in_threadpool(continual_pose_live_snapshot, camera_id, include_frame=include_frame)


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
    privacy_mode: str = "original",
) -> StreamingResponse:
    camera = storage.get_camera(camera_id, include_secret=True)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    fps = bounded_stream_fps(fps)
    width = max(320, min(int(width), 1920))
    height = max(180, min(int(height), 1080))
    quality = max(35, min(int(quality), 95))
    resolved_privacy_mode = stricter_privacy_mode(
        config_sync_agent.video_privacy_mode(),
        normalize_privacy_mode(privacy_mode, config_sync_agent.video_privacy_mode()),
    )
    require_privacy_stream_ready(camera_id, resolved_privacy_mode)
    frames = privacy_mjpeg_stream.mjpeg_frames(
        camera,
        privacy_mode=privacy_mode,
        privacy_mode_resolver=config_sync_agent.video_privacy_mode,
        fps=fps,
        jpeg_quality=quality,
        max_width=width,
        max_height=height,
    )
    return StreamingResponse(
        frames,
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Accel-Buffering": "no",
            "X-GoHome-Privacy-Mode": resolved_privacy_mode,
            "X-GoHome-Display-Transport": "edge-composed-mjpeg-v1",
            "X-GoHome-Composition-Owner": "edge",
        },
    )


@app.get("/api/cameras/{camera_id}/continual-pose/stream.mjpg")
def synchronized_camera_pose_stream(
    camera_id: int,
    fps: int = 12,
    width: int = 960,
    height: int = 540,
    quality: int = 72,
) -> StreamingResponse:
    camera = storage.get_camera(camera_id, include_secret=True)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    fps = bounded_stream_fps(fps)
    width = max(320, min(int(width), 1280))
    height = max(180, min(int(height), 720))
    quality = max(40, min(int(quality), 90))
    source_frames = synchronized_pose_stream.mjpeg_frames(
        camera,
        fps=fps,
        jpeg_quality=quality,
        max_width=width,
        max_height=height,
    )

    return StreamingResponse(
        source_frames,
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Accel-Buffering": "no",
            "X-GoHome-Pose-Stream": "synchronized",
            "X-GoHome-Stream-Purpose": "algorithm-diagnostic",
            "X-GoHome-Composition": "diagnostic-pose-overlay",
            "X-GoHome-Pose-Owner": "edge",
        },
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


@app.get("/api/eacp-acceptance")
def eacp_acceptance_status() -> Dict[str, Any]:
    return eacp_acceptance_service.status()


@app.post("/api/eacp-acceptance/start")
def start_eacp_acceptance(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return eacp_acceptance_service.start(
            scenario=str(payload.get("scenario") or "custom"),
            camera_id=int(payload.get("camera_id") or 0),
            label=str(payload.get("label") or ""),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/eacp-acceptance/finish")
def finish_eacp_acceptance() -> Dict[str, Any]:
    try:
        return eacp_acceptance_service.finish()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/api/eacp-acceptance")
def clear_eacp_acceptance() -> Dict[str, Any]:
    return eacp_acceptance_service.clear()


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
    return {
        **worker.runtime_status(),
        "live_relay_agent": live_relay_agent.status(),
    }
