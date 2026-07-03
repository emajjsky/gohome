from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
import json
import shutil
import tarfile
import zipfile

from fastapi import HTTPException

from .object_storage_service import ObjectStorageService
from .schemas import V1PackageReleaseCreate
from .storage import Storage


PACKAGE_TYPES = ("app", "model")


class PackageService:
    def __init__(self, *, storage: Storage, settings: Any, object_storage: ObjectStorageService, runtime_guard: Any | None = None) -> None:
        self.storage = storage
        self.settings = settings
        self.object_storage = object_storage
        self.runtime_guard = runtime_guard

    def require_family_access(self, user: Dict[str, Any], family_id: int) -> None:
        if int(family_id) not in set(self.storage.list_user_family_ids(int(user["id"]))):
            raise HTTPException(status_code=403, detail="You do not have access to this family")

    def package_root(self, package_type: str) -> Path:
        if package_type == "app":
            return self.settings.app_releases_dir
        if package_type == "model":
            return self.settings.model_releases_dir
        raise HTTPException(status_code=400, detail="Unsupported package type")

    def current_manifest_path(self, package_type: str) -> Path:
        return self.package_root(package_type) / "current.json"

    def previous_manifest_path(self, package_type: str) -> Path:
        return self.package_root(package_type) / "previous.json"

    def read_current_manifest(self, package_type: str) -> Dict[str, Any]:
        path = self.current_manifest_path(package_type)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def read_previous_manifest(self, package_type: str) -> Dict[str, Any]:
        path = self.previous_manifest_path(package_type)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def write_current_manifest(self, package_type: str, payload: Dict[str, Any]) -> None:
        path = self.current_manifest_path(package_type)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_previous_manifest(self, package_type: str, payload: Dict[str, Any]) -> None:
        path = self.previous_manifest_path(package_type)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def clear_manifest(self, package_type: str, *, previous: bool = False) -> None:
        path = self.previous_manifest_path(package_type) if previous else self.current_manifest_path(package_type)
        if path.exists():
            path.unlink()

    def current_app_version(self, default_version: str) -> str:
        manifest = self.read_current_manifest("app")
        return str(manifest.get("version") or default_version or "")

    def current_model_version(self, default_version: str) -> str:
        manifest = self.read_current_manifest("model")
        return str(manifest.get("version") or default_version or "")

    def infer_install_strategy(self, asset: Dict[str, Any], requested: str = "") -> str:
        clean_requested = str(requested or "").strip()
        if clean_requested:
            return clean_requested
        file_name = str((asset.get("metadata") or {}).get("file_name") or asset.get("object_key") or "").lower()
        if file_name.endswith(".zip") or file_name.endswith(".tar") or file_name.endswith(".tar.gz") or file_name.endswith(".tgz"):
            return "archive"
        return "file"

    def release_file_name(self, asset: Dict[str, Any]) -> str:
        metadata = asset.get("metadata") or {}
        value = str(metadata.get("file_name") or Path(str(asset.get("object_key") or "")).name or "package.bin").strip()
        return Path(value).name or "package.bin"

    def create_release(self, payload: V1PackageReleaseCreate, *, user: Dict[str, Any]) -> Dict[str, Any]:
        self.require_family_access(user, int(payload.family_id))
        asset = self.storage.get_media_asset(int(payload.asset_id))
        if asset is None:
            raise HTTPException(status_code=404, detail="Media asset not found")
        if int(asset["family_id"]) != int(payload.family_id):
            raise HTTPException(status_code=400, detail="Asset family mismatch")
        install_strategy = self.infer_install_strategy(asset, payload.install_strategy)
        try:
            release = self.storage.create_package_release(
                family_id=int(payload.family_id),
                package_type=payload.package_type,
                version=payload.version,
                asset_id=int(payload.asset_id),
                install_strategy=install_strategy,
                entry_path=payload.entry_path,
                metadata={
                    **payload.metadata,
                    "file_name": self.release_file_name(asset),
                    "content_type": asset.get("content_type"),
                    "checksum_sha256": asset.get("checksum_sha256"),
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

    def list_releases(self, *, family_id: int, package_type: str = "", user: Dict[str, Any], limit: int = 20) -> list[Dict[str, Any]]:
        self.require_family_access(user, int(family_id))
        return [
            self.package_release_for_api(release)
            for release in self.storage.list_package_releases(family_id=int(family_id), package_type=package_type, limit=limit)
        ]

    def get_release_for_user(self, release_id: int, user: Dict[str, Any]) -> Dict[str, Any]:
        release = self.storage.get_package_release(int(release_id))
        if release is None:
            raise HTTPException(status_code=404, detail="Package release not found")
        self.require_family_access(user, int(release["family_id"]))
        return release

    def create_download_link(self, release_id: int, *, user: Dict[str, Any], expires_in_seconds: int) -> Dict[str, Any]:
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

    def list_executions(self, *, family_id: int, device_id: str = "", user: Dict[str, Any], limit: int = 20) -> list[Dict[str, Any]]:
        self.require_family_access(user, int(family_id))
        return [
            self.execution_for_api(execution)
            for execution in self.storage.list_package_executions(family_id=int(family_id), device_id=device_id, limit=limit)
        ]

    def _copy_or_extract_release(self, *, release: Dict[str, Any], asset: Dict[str, Any], package_type: str) -> tuple[Path, Path]:
        asset_file = self.object_storage.asset_file_path(asset)
        file_name = self.release_file_name(asset)
        version_dir = self.package_root(package_type) / str(release["version"])
        if version_dir.exists():
            shutil.rmtree(version_dir)
        version_dir.mkdir(parents=True, exist_ok=True)
        staged_file = version_dir / file_name
        shutil.copy2(asset_file, staged_file)
        install_strategy = str(release.get("install_strategy") or "file")
        installed_path = staged_file
        if install_strategy == "archive":
            extracted_dir = version_dir / "expanded"
            extracted_dir.mkdir(parents=True, exist_ok=True)
            lowered = file_name.lower()
            if lowered.endswith(".zip"):
                with zipfile.ZipFile(staged_file) as archive:
                    archive.extractall(extracted_dir)
            elif lowered.endswith(".tar") or lowered.endswith(".tar.gz") or lowered.endswith(".tgz"):
                with tarfile.open(staged_file) as archive:
                    archive.extractall(extracted_dir)
            else:
                raise HTTPException(status_code=400, detail="Unsupported archive format")
            entry_path = str(release.get("entry_path") or "").strip()
            installed_path = (extracted_dir / entry_path).resolve() if entry_path else extracted_dir.resolve()
        return staged_file.resolve(), installed_path.resolve()

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
            started_at=datetime.now(timezone.utc).isoformat(),
            output={"step": "prepare"},
        )
        try:
            staged_path, installed_path = self._copy_or_extract_release(
                release=release,
                asset=asset,
                package_type=package_type,
            )
            previous_manifest = self.read_current_manifest(package_type)
            manifest = {
                "package_type": package_type,
                "version": str(release["version"]),
                "release_id": int(release["id"]),
                "asset_id": int(release["asset_id"]),
                "installed_at": datetime.now(timezone.utc).isoformat(),
                "staged_path": str(staged_path),
                "installed_path": str(installed_path),
                "entry_path": str(release.get("entry_path") or ""),
                "install_strategy": str(release.get("install_strategy") or "file"),
            }
            if previous_manifest:
                self.write_previous_manifest(package_type, previous_manifest)
            else:
                self.clear_manifest(package_type, previous=True)
            self.write_current_manifest(package_type, manifest)
            runtime_output: Dict[str, Any] = {}
            status = "succeeded"
            if package_type == "app" and self.runtime_guard and self.runtime_guard.is_runnable_manifest(manifest):
                runtime_result = self.runtime_guard.apply_release(manifest, previous_manifest=previous_manifest)
                runtime_output["runtime"] = runtime_result
                if not runtime_result.get("ok"):
                    if previous_manifest:
                        self.write_current_manifest(package_type, previous_manifest)
                    else:
                        self.clear_manifest(package_type)
                    if previous_manifest:
                        self.write_previous_manifest(package_type, manifest)
                    status = "rolled_back" if runtime_result.get("rolled_back") else "failed"
                    if runtime_result.get("rolled_back") and self.runtime_guard:
                        runtime_status = self.runtime_guard.status()
                        runtime_output["runtime_status_after_rollback"] = runtime_status
                        if not runtime_status.get("running"):
                            try:
                                restarted = self.runtime_guard.restart_current()
                                runtime_output["runtime_restart_after_rollback"] = restarted
                            except Exception as restart_exc:
                                runtime_output["runtime_restart_after_rollback_error"] = str(restart_exc)
                    updated = self.storage.update_package_execution(
                        int(execution["id"]),
                        status=status,
                        staged_path=str(staged_path),
                        installed_path=str(installed_path),
                        finished_at=datetime.now(timezone.utc).isoformat(),
                        output={
                            "release_id": int(release["id"]),
                            "asset_id": int(release["asset_id"]),
                            "file_name": self.release_file_name(asset),
                            "restart_required": False,
                            **runtime_output,
                            "error": runtime_result.get("error") or "App runtime apply failed",
                        },
                    )
                    if runtime_result.get("rolled_back"):
                        return self.execution_for_api(updated)
                    raise HTTPException(status_code=500, detail=str(updated["output"].get("error") or "App runtime apply failed"))
            updated = self.storage.update_package_execution(
                int(execution["id"]),
                status=status,
                staged_path=str(staged_path),
                installed_path=str(installed_path),
                finished_at=datetime.now(timezone.utc).isoformat(),
                output={
                    "release_id": int(release["id"]),
                    "asset_id": int(release["asset_id"]),
                    "file_name": self.release_file_name(asset),
                    "restart_required": package_type == "app" and "runtime" not in runtime_output,
                    **runtime_output,
                },
            )
            return self.execution_for_api(updated)
        except HTTPException as exc:
            failed = self.storage.update_package_execution(
                int(execution["id"]),
                status="failed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                output={"error": exc.detail},
            )
            raise HTTPException(status_code=exc.status_code, detail=failed["output"].get("error")) from exc
        except Exception as exc:
            failed = self.storage.update_package_execution(
                int(execution["id"]),
                status="failed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                output={"error": str(exc)},
            )
            raise HTTPException(status_code=500, detail=failed["output"].get("error")) from exc

    def run_pending_upgrades(self, *, family_id: int, device_id: str, target: Dict[str, Any], package_types: list[str] | None = None) -> Dict[str, Any]:
        requested = [item for item in (package_types or []) if item in PACKAGE_TYPES]
        selected = requested or list(PACKAGE_TYPES)
        results: list[Dict[str, Any]] = []
        current_app = self.current_app_version(default_version="")
        current_model = self.current_model_version(default_version="")
        targets = {
            "app": str(target.get("app_version") or ""),
            "model": str(target.get("model_version") or ""),
        }
        currents = {
            "app": current_app,
            "model": current_model,
        }
        for package_type in selected:
            target_version = targets.get(package_type, "")
            if not target_version or target_version == currents.get(package_type, ""):
                continue
            results.append(
                self.execute_release(
                    family_id=family_id,
                    device_id=device_id,
                    package_type=package_type,
                    target_version=target_version,
                )
            )
        return {
            "device_id": device_id,
            "family_id": family_id,
            "executions": results,
        }
