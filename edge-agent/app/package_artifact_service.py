from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import HTTPException

from .storage import Storage


def package_artifact_path(asset_id: int) -> str:
    return f"/api/v1/package-artifacts/{int(asset_id)}"


class PackageArtifactService:
    """Read-only access to an already published, locally materialized package.

    Package creation, upload authorization and public download links belong to
    the production cloud. The edge only resolves a signed package asset for
    the local installation transaction.
    """

    def __init__(self, *, storage: Storage, settings: Any) -> None:
        self.storage = storage
        self.settings = settings

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

    def artifact_for_api(self, asset: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(asset)
        data["storage_path"] = package_artifact_path(int(data["id"]))
        data["storage_url"] = data["storage_path"]
        return data
