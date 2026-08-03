from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EDGE_APP = ROOT / "edge-agent" / "app"
CLOUD_SERVER = ROOT / "local-app-server" / "server.js"
IOS_STREAM_CLIENT = ROOT / "ios-shell" / "GoHomeShell" / "Sources" / "Streaming" / "MJPEGStreamClient.swift"


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

    expected = {
        "/api/cameras/{camera_id}/stream.mjpg",
        "/api/cameras/{camera_id}/continual-pose/stream.mjpg",
        "/api/v1/device/cameras/{camera_id}/stream.mjpg",
    }
    missing = sorted(expected - set(routes))
    if missing:
        raise SystemExit(f"required edge privacy routes are missing: {missing}")

    management_calls = called_attribute_names(routes["/api/cameras/{camera_id}/stream.mjpg"])
    if "privacy_mjpeg_stream.mjpeg_frames" not in management_calls:
        raise SystemExit("management stream does not use the privacy composition owner")

    diagnostic_calls = called_attribute_names(routes["/api/cameras/{camera_id}/continual-pose/stream.mjpg"])
    if "synchronized_pose_stream.mjpeg_frames" not in diagnostic_calls:
        raise SystemExit("algorithm diagnostic stream does not use the current-frame pose renderer")
    if "privacy_mjpeg_stream.mjpeg_frames" in diagnostic_calls:
        raise SystemExit("algorithm diagnostic stream still changes with the user privacy mode")

    device_node = routes["/api/v1/device/cameras/{camera_id}/stream.mjpg"]
    direct_calls = {
        child.func.id
        for child in ast.walk(device_node)
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
    }
    if "camera_mjpeg_stream" not in direct_calls:
        raise SystemExit("cloud device stream does not delegate to the management privacy stream")

    cloud_source = CLOUD_SERVER.read_text(encoding="utf-8")
    required_cloud_contracts = (
        'pathname === "/api/v1/video/sessions"',
        "/api/v1/device/cameras/${localCameraId}/stream.mjpg",
        '"X-GoHome-Composition-Owner": "edge"',
    )
    missing_cloud_contracts = [item for item in required_cloud_contracts if item not in cloud_source]
    if missing_cloud_contracts:
        raise SystemExit(f"production cloud ownership contract is incomplete: {missing_cloud_contracts}")

    ios_source = IOS_STREAM_CLIENT.read_text(encoding="utf-8")
    required_ios_contracts = (
        'path: "/api/v1/video/sessions"',
        'fallbackPath: "/api/v1/video/cameras/\\(cameraID)/stream.mjpg"',
    )
    missing_ios_contracts = [item for item in required_ios_contracts if item not in ios_source]
    if missing_ios_contracts:
        raise SystemExit(f"formal iOS playback contract is incomplete: {missing_ios_contracts}")

    print({
        "ok": True,
        "composition_owner": "edge",
        "management_routes": 2,
        "diagnostic_stream_privacy_independent": True,
        "cloud_device_routes": 1,
        "obsolete_playback_routes": 0,
        "obsolete_video_services": 0,
        "production_cloud_owner": True,
        "formal_ios_cloud_only": True,
    })


if __name__ == "__main__":
    main()
