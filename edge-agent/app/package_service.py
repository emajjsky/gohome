from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
import fcntl
import os

from fastapi import HTTPException

from .object_storage_service import ObjectStorageService
from .package_trust import (
    PackageTrustError,
    PackageTrustStore,
    atomic_write_json,
    read_json_object,
)
from .schemas import V1PackageReleaseCreate
from .storage import Storage


PACKAGE_TYPES = ("app", "model")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PackageService:
    def __init__(
        self,
        *,
        storage: Storage,
        settings: Any,
        object_storage: ObjectStorageService,
        runtime_guard: Any | None = None,
    ) -> None:
        self.storage = storage
        self.settings = settings
        self.object_storage = object_storage
        self.runtime_guard = runtime_guard
        self.trust_store = PackageTrustStore(settings)

    def require_family_access(self, user: Dict[str, Any], family_id: int) -> None:
        if int(family_id) not in set(self.storage.list_user_family_ids(int(user["id"]))):
            raise HTTPException(status_code=403, detail="You do not have access to this family")

    def package_root(self, package_type: str) -> Path:
        try:
            return self.trust_store.package_root(package_type)
        except PackageTrustError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def current_manifest_path(self, package_type: str) -> Path:
        return self.package_root(package_type) / "current.json"

    def previous_manifest_path(self, package_type: str) -> Path:
        return self.package_root(package_type) / "previous.json"

    def read_current_manifest(self, package_type: str) -> Dict[str, Any]:
        return read_json_object(self.current_manifest_path(package_type))

    def read_previous_manifest(self, package_type: str) -> Dict[str, Any]:
        return read_json_object(self.previous_manifest_path(package_type))

    def write_current_manifest(self, package_type: str, payload: Dict[str, Any]) -> None:
        atomic_write_json(self.current_manifest_path(package_type), payload)

    def write_previous_manifest(self, package_type: str, payload: Dict[str, Any]) -> None:
        atomic_write_json(self.previous_manifest_path(package_type), payload)

    def clear_manifest(self, package_type: str, *, previous: bool = False) -> None:
        path = self.previous_manifest_path(package_type) if previous else self.current_manifest_path(package_type)
        if not path.exists():
            return
        path.unlink()
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def verified_manifest(self, package_type: str, *, previous: bool = False) -> Dict[str, Any]:
        manifest = self.read_previous_manifest(package_type) if previous else self.read_current_manifest(package_type)
        if not manifest:
            return {}
        return self.trust_store.validate_installed_manifest(manifest)

    def current_app_version(self, default_version: str) -> str:
        try:
            manifest = self.verified_manifest("app")
        except PackageTrustError:
            return str(default_version or "")
        signed = dict(manifest.get("signed_manifest") or {})
        return str(signed.get("version") or default_version or "")

    def current_model_version(self, default_version: str) -> str:
        try:
            manifest = self.verified_manifest("model")
        except PackageTrustError:
            return str(default_version or "")
        signed = dict(manifest.get("signed_manifest") or {})
        return str(signed.get("version") or default_version or "")

    def release_file_name(self, asset: Dict[str, Any]) -> str:
        metadata = asset.get("metadata") or {}
        value = str(metadata.get("file_name") or Path(str(asset.get("object_key") or "")).name or "").strip()
        return Path(value).name

    def signed_manifest_from_payload(self, payload: V1PackageReleaseCreate, *, file_name: str) -> Dict[str, Any]:
        return {
            "manifest_version": int(payload.manifest_version),
            "package_type": payload.package_type,
            "version": payload.version,
            "family_id": int(payload.family_id),
            "device_scope": payload.device_scope,
            "device_id": payload.device_id,
            "byte_size": int(payload.byte_size),
            "sha256": payload.sha256,
            "signature_key_id": payload.signature_key_id,
            "file_name": file_name,
            "entry_type": payload.entry_type,
            "entry_path": payload.entry_path,
            "install_strategy": payload.install_strategy,
            "signature": payload.signature,
        }

    def create_release(self, payload: V1PackageReleaseCreate, *, user: Dict[str, Any]) -> Dict[str, Any]:
        self.require_family_access(user, int(payload.family_id))
        asset = self.storage.get_media_asset(int(payload.asset_id))
        if asset is None:
            raise HTTPException(status_code=404, detail="Media asset not found")
        if int(asset["family_id"]) != int(payload.family_id):
            raise HTTPException(status_code=400, detail="Asset family mismatch")
        file_name = self.release_file_name(asset)
        signed_manifest = self.signed_manifest_from_payload(payload, file_name=file_name)
        try:
            normalized = self.trust_store.verify_signature(signed_manifest)
            self.trust_store.verify_artifact(self.object_storage.asset_file_path(asset), normalized)
        except PackageTrustError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            release = self.storage.create_package_release(
                family_id=int(payload.family_id),
                package_type=payload.package_type,
                version=payload.version,
                asset_id=int(payload.asset_id),
                install_strategy=payload.install_strategy,
                entry_path=payload.entry_path,
                metadata={
                    **payload.metadata,
                    "content_type": asset.get("content_type"),
                    "signed_manifest": normalized,
                },
                created_by_user_id=int(user["id"]),
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return self.package_release_for_api(release)

    def package_release_for_api(self, release: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(release)
        asset = self.storage.get_media_asset(int(release["asset_id"]))
        if asset:
            data["asset"] = self.object_storage.media_asset_for_api(asset)
        return data

    def list_releases(
        self,
        *,
        family_id: int,
        package_type: str = "",
        user: Dict[str, Any],
        limit: int = 20,
    ) -> list[Dict[str, Any]]:
        self.require_family_access(user, int(family_id))
        return [
            self.package_release_for_api(release)
            for release in self.storage.list_package_releases(
                family_id=int(family_id), package_type=package_type, limit=limit
            )
        ]

    def get_release_for_user(self, release_id: int, user: Dict[str, Any]) -> Dict[str, Any]:
        release = self.storage.get_package_release(int(release_id))
        if release is None:
            raise HTTPException(status_code=404, detail="Package release not found")
        self.require_family_access(user, int(release["family_id"]))
        return release

    def create_download_link(
        self,
        release_id: int,
        *,
        user: Dict[str, Any],
        expires_in_seconds: int,
    ) -> Dict[str, Any]:
        release = self.get_release_for_user(release_id, user)
        link = self.object_storage.create_public_link(
            int(release["asset_id"]),
            user=user,
            expires_in_seconds=expires_in_seconds,
        )
        return {
            "release_id": int(release["id"]),
            "package_type": release["package_type"],
            "version": release["version"],
            **link,
        }

    def execution_for_api(self, execution: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(execution)
        if execution.get("release_id"):
            release = self.storage.get_package_release(int(execution["release_id"]))
            if release is not None:
                data["release"] = self.package_release_for_api(release)
        return data

    def list_executions(
        self,
        *,
        family_id: int,
        device_id: str = "",
        user: Dict[str, Any],
        limit: int = 20,
    ) -> list[Dict[str, Any]]:
        self.require_family_access(user, int(family_id))
        return [
            self.execution_for_api(execution)
            for execution in self.storage.list_package_executions(
                family_id=int(family_id), device_id=device_id, limit=limit
            )
        ]

    def _record_failure(self, execution_id: int, exc: Exception) -> None:
        self.storage.update_package_execution(
            execution_id,
            status="failed",
            finished_at=now_iso(),
            output={"error": str(exc)},
        )

    def acquire_upgrade_lock(self, package_type: str) -> int:
        lock_path = self.package_root(package_type) / ".upgrade.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        return descriptor

    @staticmethod
    def release_upgrade_lock(descriptor: int | None) -> None:
        if descriptor is None:
            return
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    def execute_release(
        self,
        *,
        family_id: int,
        device_id: str,
        package_type: str,
        target_version: str,
    ) -> Dict[str, Any]:
        release = self.storage.get_package_release_by_version(family_id, package_type, target_version)
        if release is None:
            raise HTTPException(status_code=404, detail=f"{package_type} package release not found")
        asset = self.storage.get_media_asset(int(release["asset_id"]))
        if asset is None:
            raise HTTPException(status_code=404, detail="Package asset not found")
        execution = self.storage.create_package_execution(
            family_id=family_id,
            device_id=device_id,
            package_type=package_type,
            target_version=target_version,
            release_id=int(release["id"]),
            status="running",
            started_at=now_iso(),
            output={"step": "verify"},
        )
        execution_id = int(execution["id"])
        lock_descriptor: int | None = None
        execution_finalized = False
        try:
            lock_descriptor = self.acquire_upgrade_lock(package_type)
            signed_manifest = dict((release.get("metadata") or {}).get("signed_manifest") or {})
            candidate = self.trust_store.install(
                self.object_storage.asset_file_path(asset),
                signed_manifest,
                family_id=family_id,
                device_id=device_id,
            )
            previous = self.verified_manifest(package_type)
            if previous:
                self.write_previous_manifest(package_type, previous)
            else:
                self.clear_manifest(package_type, previous=True)
            runtime_output: Dict[str, Any] = {}
            if package_type == "app":
                if self.runtime_guard is None:
                    raise PackageTrustError("App runtime guard is not configured")
                self.runtime_guard.validate_manifest(candidate)
                runtime_result = self.runtime_guard.apply_release(
                    candidate,
                    previous_manifest=previous,
                    activate=lambda: self.write_current_manifest(package_type, candidate),
                )
                runtime_output["runtime"] = runtime_result
                if not runtime_result.get("ok"):
                    status = "rolled_back" if runtime_result.get("rolled_back") else "failed"
                    updated = self.storage.update_package_execution(
                        execution_id,
                        status=status,
                        staged_path=str(candidate["artifact_path"]),
                        installed_path=str(candidate["installed_path"]),
                        finished_at=now_iso(),
                        output={
                            "release_id": int(release["id"]),
                            "asset_id": int(release["asset_id"]),
                            **runtime_output,
                            "error": runtime_result.get("error") or "App runtime apply failed",
                        },
                    )
                    execution_finalized = True
                    if status == "rolled_back":
                        return self.execution_for_api(updated)
                    raise HTTPException(status_code=500, detail=str(updated["output"]["error"]))
            else:
                self.write_current_manifest(package_type, candidate)
            updated = self.storage.update_package_execution(
                execution_id,
                status="succeeded",
                staged_path=str(candidate["artifact_path"]),
                installed_path=str(candidate["installed_path"]),
                finished_at=now_iso(),
                output={
                    "release_id": int(release["id"]),
                    "asset_id": int(release["asset_id"]),
                    "verified_manifest_version": int(candidate["manifest_version"]),
                    **runtime_output,
                },
            )
            execution_finalized = True
            return self.execution_for_api(updated)
        except HTTPException as exc:
            if not execution_finalized:
                self._record_failure(execution_id, exc)
            raise
        except Exception as exc:
            if not execution_finalized:
                self._record_failure(execution_id, exc)
            status_code = 400 if isinstance(exc, PackageTrustError) else 500
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        finally:
            self.release_upgrade_lock(lock_descriptor)

    def run_pending_upgrades(
        self,
        *,
        family_id: int,
        device_id: str,
        target: Dict[str, Any],
        package_types: list[str] | None = None,
    ) -> Dict[str, Any]:
        requested = [item for item in (package_types or []) if item in PACKAGE_TYPES]
        selected = requested or list(PACKAGE_TYPES)
        currents = {
            "app": self.current_app_version(default_version=""),
            "model": self.current_model_version(default_version=""),
        }
        targets = {
            "app": str(target.get("app_version") or ""),
            "model": str(target.get("model_version") or ""),
        }
        results: list[Dict[str, Any]] = []
        for package_type in selected:
            target_version = targets[package_type]
            if not target_version or target_version == currents[package_type]:
                continue
            results.append(
                self.execute_release(
                    family_id=family_id,
                    device_id=device_id,
                    package_type=package_type,
                    target_version=target_version,
                )
            )
        return {"device_id": device_id, "family_id": family_id, "executions": results}
