from __future__ import annotations

from pathlib import Path
import ast


ROOT = Path(__file__).resolve().parents[1]


def decorator_paths(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    paths: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not decorator.args:
                continue
            route = decorator.args[0]
            if isinstance(route, ast.Constant) and isinstance(route.value, str):
                paths.add(route.value)
    return paths


def main() -> None:
    app_dir = ROOT / "app"
    source_files = sorted(app_dir.glob("*.py"))
    source = "\n".join(path.read_text(encoding="utf-8") for path in source_files)
    routes = set().union(*(decorator_paths(path) for path in source_files))

    retired_routes = {
        "/api/v1/device/media-assets",
        "/api/v1/device/media-assets/upload",
        "/api/v1/media/assets/{asset_id}",
        "/api/v1/media/upload-sessions",
        "/api/v1/media/upload-sessions/{session_id}/content",
        "/api/v1/media/upload-sessions/{session_id}/complete",
        "/api/v1/media/assets/{asset_id}/public-links",
        "/api/public/media/assets/{asset_id}",
    }
    unexpected = sorted(retired_routes & routes)
    if unexpected:
        raise SystemExit(f"edge still exposes cloud media routes: {unexpected}")
    for symbol in ("ObjectStorageService", "build_object_storage_router", "store_device_media_bytes", "promote_snapshot_media_asset"):
        if symbol in source:
            raise SystemExit(f"retired edge media implementation remains: {symbol}")

    package_routes = (ROOT / "app" / "package_artifact_service.py").read_text(encoding="utf-8")
    if "/api/v1/package-artifacts/uploads" not in package_routes:
        raise SystemExit("signed package artifact upload route is missing")
    upload_agent = (ROOT / "app" / "upload_agent.py").read_text(encoding="utf-8")
    if "source.read_bytes()" in upload_agent:
        raise SystemExit("edge evidence upload still reads the complete file into memory")

    print("edge media ownership contract verified")


if __name__ == "__main__":
    main()
