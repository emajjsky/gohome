from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import asyncio
import sys

from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.package_artifact_service import PackageArtifactService
from app.schemas import V1PackageArtifactUploadComplete, V1PackageArtifactUploadCreate
from app.storage import Storage


class StreamingRequest:
    def __init__(self, chunks: list[bytes], content_type: str = "application/zip") -> None:
        self._chunks = chunks
        self.headers = {"content-type": content_type}

    async def stream(self):
        for chunk in self._chunks:
            yield chunk


def main() -> None:
    with TemporaryDirectory(prefix="gohome-package-artifact-") as temporary:
        root = Path(temporary)
        settings = SimpleNamespace(
            data_dir=root / "data",
            object_storage_dir=root / "objects",
            object_storage_provider="signed-localfs",
            object_storage_bucket="package-artifacts",
            media_public_base_url="https://box.example",
        )
        settings.data_dir.mkdir(parents=True)
        settings.object_storage_dir.mkdir(parents=True)
        storage = Storage(root / "agent.db")
        storage.init_schema()
        user = storage.create_user("owner@example.com", "secret", "Owner")
        family = storage.create_family("Test family", int(user["id"]))
        service = PackageArtifactService(storage=storage, settings=settings)

        content = b"signed-package-content"
        upload = service.create_upload(
            V1PackageArtifactUploadCreate(
                family_id=int(family["id"]),
                file_name="release.zip",
                content_type="application/zip",
                byte_size=len(content),
            ),
            user=user,
        )
        asyncio.run(service.put_upload_content(
            int(upload["id"]),
            upload_token=str(upload["upload_token"]),
            request=StreamingRequest([content[:7], content[7:]]),
        ))
        completed = service.complete_upload(
            int(upload["id"]),
            upload_token=str(upload["upload_token"]),
            payload=V1PackageArtifactUploadComplete(),
        )
        asset = completed["asset"]
        if asset.get("retention_class") != "package_artifact":
            raise SystemExit(f"package artifact retention class is wrong: {asset}")
        if service.asset_file_path(asset).read_bytes() != content:
            raise SystemExit("streamed package artifact bytes do not match")
        link = service.create_public_link(int(asset["id"]), user=user, expires_in_seconds=120)
        if "/api/public/package-artifacts/" not in str(link.get("public_url") or ""):
            raise SystemExit(f"package artifact public URL is wrong: {link}")

        rejected = service.create_upload(
            V1PackageArtifactUploadCreate(
                family_id=int(family["id"]),
                file_name="oversized.zip",
                byte_size=3,
            ),
            user=user,
        )
        try:
            asyncio.run(service.put_upload_content(
                int(rejected["id"]),
                upload_token=str(rejected["upload_token"]),
                request=StreamingRequest([b"four"]),
            ))
        except HTTPException as exc:
            if exc.status_code != 413:
                raise
        else:
            raise SystemExit("oversized package artifact was accepted")
        rejected_session = storage.get_media_upload_session(int(rejected["id"]))
        rejected_path = service.object_path_from_key(str(rejected_session["object_key"]))
        if rejected_path.exists() or list(rejected_path.parent.glob(f".{rejected_path.name}.*.upload")):
            raise SystemExit("failed package artifact upload left temporary bytes")

        print("package artifact service verified")


if __name__ == "__main__":
    main()
