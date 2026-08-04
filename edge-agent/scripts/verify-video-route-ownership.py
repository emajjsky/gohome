from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EDGE_APP = ROOT / "edge-agent" / "app"
CLOUD_SERVER = ROOT / "local-app-server" / "server.js"
CLOUD_MEDIA_ACCESS = ROOT / "local-app-server" / "media-access.js"
IOS_STREAM_DIR = ROOT / "ios-shell" / "GoHomeShell" / "Sources" / "Streaming"
IOS_STREAM_CLIENT = IOS_STREAM_DIR / "WHEPStreamClient.swift"
IOS_STREAM_CONTRACT = IOS_STREAM_DIR / "CameraStreamClient.swift"


def decorated_routes(path: Path) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    routes: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
                continue
            route = decorator.args[0].value
            if isinstance(route, str):
                routes[route] = node
    return routes


def called_attribute_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
            names.add(ast.unparse(child.func))
    return names


def main() -> None:
    obsolete_files = (
        "video_app.py",
        "video_distribution_service.py",
        "video_profiles.py",
        "video_service.py",
    )
    existing_obsolete = [name for name in obsolete_files if (EDGE_APP / name).exists()]
    if existing_obsolete:
        raise SystemExit(f"obsolete edge video services still exist: {existing_obsolete}")

    routes = decorated_routes(EDGE_APP / "main.py")
    forbidden = sorted(
        route for route in routes
        if route == "/api/app" or route.startswith("/api/app/") or route.startswith("/api/v1/video/")
    )
    if forbidden:
        raise SystemExit(f"edge still owns cloud/app playback routes: {forbidden}")

    expected_local_routes = {
        "/api/cameras/{camera_id}/stream.mjpg",
        "/api/cameras/{camera_id}/continual-pose/stream.mjpg",
    }
    missing = sorted(expected_local_routes - set(routes))
    if missing:
        raise SystemExit(f"required edge privacy routes are missing: {missing}")
    forbidden_device_streams = sorted(
        route for route in routes
        if route.startswith("/api/v1/device/") and route.endswith("/stream.mjpg")
    )
    if forbidden_device_streams:
        raise SystemExit(f"retired public device MJPEG routes remain: {forbidden_device_streams}")

    management_calls = called_attribute_names(routes["/api/cameras/{camera_id}/stream.mjpg"])
    if "privacy_mjpeg_stream.mjpeg_frames" not in management_calls:
        raise SystemExit("management stream does not use the privacy composition owner")

    diagnostic_calls = called_attribute_names(routes["/api/cameras/{camera_id}/continual-pose/stream.mjpg"])
    if "synchronized_pose_stream.mjpeg_frames" not in diagnostic_calls:
        raise SystemExit("algorithm diagnostic stream does not use the current-frame pose renderer")
    if "privacy_mjpeg_stream.mjpeg_frames" in diagnostic_calls:
        raise SystemExit("algorithm diagnostic stream still changes with the user privacy mode")

    cloud_source = CLOUD_SERVER.read_text(encoding="utf-8")
    required_cloud_contracts = (
        'pathname === "/api/v1/video/sessions"',
        "mediaAccessService.issueReadSession",
    )
    missing_cloud_contracts = [item for item in required_cloud_contracts if item not in cloud_source]
    if missing_cloud_contracts:
        raise SystemExit(f"production cloud ownership contract is incomplete: {missing_cloud_contracts}")
    retired_cloud_contracts = (
        "/api/v1/device/cameras/${localCameraId}/stream.mjpg",
        "edge-composed-mjpeg-v1",
    )
    remaining_cloud_contracts = [item for item in retired_cloud_contracts if item in cloud_source]
    if remaining_cloud_contracts:
        raise SystemExit(f"retired cloud MJPEG contract remains: {remaining_cloud_contracts}")

    media_access_source = CLOUD_MEDIA_ACCESS.read_text(encoding="utf-8")
    required_media_contracts = (
        'display_transport: "whep-h264-v1"',
        'composition_owner: "edge"',
        "authorizePublish(request)",
        "authorizeRead(request)",
    )
    missing_media_contracts = [item for item in required_media_contracts if item not in media_access_source]
    if missing_media_contracts:
        raise SystemExit(f"cloud media access contract is incomplete: {missing_media_contracts}")

    publisher_source = (EDGE_APP / "h264_publisher.py").read_text(encoding="utf-8")
    relay_source = (EDGE_APP / "live_relay_agent.py").read_text(encoding="utf-8")
    required_edge_contracts = (
        (publisher_source, "class H264StreamPublisher"),
        (publisher_source, "build_rtsps_publish_url"),
        (relay_source, "H264StreamPublisher"),
        (relay_source, '"transport": "h264-rtsps"'),
    )
    missing_edge_contracts = [item for source, item in required_edge_contracts if item not in source]
    if missing_edge_contracts:
        raise SystemExit(f"edge H.264 publishing contract is incomplete: {missing_edge_contracts}")

    ios_source = IOS_STREAM_CLIENT.read_text(encoding="utf-8")
    ios_contract_source = IOS_STREAM_CONTRACT.read_text(encoding="utf-8")
    required_ios_contracts = (
        'path: "/api/v1/video/sessions"',
        "CameraDisplayTransport.whepH264",
        'playback.compositionOwner == "edge"',
    )
    missing_ios_contracts = [item for item in required_ios_contracts if item not in ios_source]
    if missing_ios_contracts:
        raise SystemExit(f"formal iOS playback contract is incomplete: {missing_ios_contracts}")
    if 'static let whepH264 = "whep-h264-v1"' not in ios_contract_source:
        raise SystemExit("formal iOS transport version is missing")
    if (IOS_STREAM_DIR / "MJPEGStreamClient.swift").exists() or "fallbackPath" in ios_source:
        raise SystemExit("formal iOS playback still contains an MJPEG fallback")

    print({
        "ok": True,
        "composition_owner": "edge",
        "management_routes": 2,
        "diagnostic_stream_privacy_independent": True,
        "public_device_mjpeg_routes": 0,
        "obsolete_playback_routes": 0,
        "obsolete_video_services": 0,
        "production_cloud_owner": True,
        "public_transport": "rtsps-whep-h264",
        "formal_ios_cloud_only": True,
    })


if __name__ == "__main__":
    main()
