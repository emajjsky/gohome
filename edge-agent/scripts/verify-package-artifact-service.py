from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sys

from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.package_artifact_service import PackageArtifactService
from app.storage import Storage


def main() -> None:
    with TemporaryDirectory(prefix="gohome-package-artifact-") as temporary:
        root = Path(temporary)
        settings = SimpleNamespace(object_storage_dir=root / "objects")
        settings.object_storage_dir.mkdir(parents=True)
        storage = Storage(root / "agent.db")
        storage.init_schema()
        service = PackageArtifactService(storage=storage, settings=settings)
        object_key = "package-artifacts/family_1/release.zip"
        target = service.object_path_from_key(object_key)
        target.parent.mkdir(parents=True)
        target.write_bytes(b"signed-package-content")
        asset = {
            "id": 1,
            "object_key": object_key,
            "retention_class": "package_artifact",
            "retention_status": "active",
            "status": "uploaded",
        }
        if service.asset_file_path(asset).read_bytes() != b"signed-package-content":
            raise SystemExit("read-only package artifact bytes do not match")
        if service.artifact_for_api(asset)["storage_path"] != "/api/v1/package-artifacts/1":
            raise SystemExit("package artifact metadata path is wrong")
        try:
            service.object_path_from_key("../outside/release.zip")
        except HTTPException as exc:
            if exc.status_code != 400:
                raise
        else:
            raise SystemExit("package artifact path escaped object storage root")
        try:
            service.asset_file_path({**asset, "retention_status": "deleted"})
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
        else:
            raise SystemExit("deleted package artifact remained readable")
        print("read-only package artifact store verified")


if __name__ == "__main__":
    main()
