from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
import fcntl
import os

from fastapi import HTTPException

from .package_artifact_service import PackageArtifactService
from .package_trust import (
    PackageTrustError,
    PackageTrustStore,
    atomic_write_json,
    read_json_object,
)
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
        artifact_store: PackageArtifactService,
        runtime_guard: Any | None = None,
    ) -> None:
        self.storage = storage
        self.settings = settings
        self.artifact_store = artifact_store
        self.runtime_guard = runtime_guard
        self.trust_store = PackageTrustStore(settings)

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

    def package_release_for_api(self, release: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(release)
        asset = self.storage.get_media_asset(int(release["asset_id"]))
        if asset:
            data["asset"] = self.artifact_store.artifact_for_api(asset)
        return data

    def execution_for_api(self, execution: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(execution)
        if execution.get("release_id"):
            release = self.storage.get_package_release(int(execution["release_id"]))
            if release is not None:
                data["release"] = self.package_release_for_api(release)
        return data

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
                self.artifact_store.asset_file_path(asset),
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
