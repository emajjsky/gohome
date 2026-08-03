from __future__ import annotations

from base64 import b64decode
from binascii import Error as Base64Error
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path, PurePosixPath
from stat import S_IFMT, S_IFREG, S_IXGRP, S_IXOTH, S_IXUSR
from typing import Any, Dict, Iterable
import json
import os
import re
import shutil
import tarfile
import tempfile
import zipfile

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


SIGNED_MANIFEST_VERSION = 1
SIGNED_FIELDS = (
    "manifest_version",
    "package_type",
    "version",
    "family_id",
    "device_scope",
    "device_id",
    "byte_size",
    "sha256",
    "signature_key_id",
    "file_name",
    "entry_type",
    "entry_path",
    "install_strategy",
)
PACKAGE_TYPES = {"app", "model"}
INSTALL_STRATEGIES = {"file", "archive"}
VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class PackageTrustError(RuntimeError):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_signed_payload(manifest: Dict[str, Any]) -> bytes:
    payload = {field: manifest.get(field) for field in SIGNED_FIELDS}
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def read_json_object(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_relative_path(value: str, *, field: str) -> PurePosixPath:
    if not value or len(value) > 512 or "\\" in value or "\x00" in value:
        raise PackageTrustError(f"Invalid {field}")
    candidate = PurePosixPath(value)
    if (
        candidate.is_absolute()
        or len(candidate.parts) > 32
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise PackageTrustError(f"Invalid {field}")
    return candidate


def _sha256_file(path: Path) -> tuple[int, str]:
    digest = sha256()
    byte_size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            byte_size += len(chunk)
            digest.update(chunk)
    return byte_size, digest.hexdigest()


def _copy_exact(source: Any, output: Any, expected_bytes: int) -> None:
    copied = 0
    while True:
        chunk = source.read(min(1024 * 1024, expected_bytes - copied + 1))
        if not chunk:
            break
        copied += len(chunk)
        if copied > expected_bytes:
            raise PackageTrustError("Package content exceeds declared byte size")
        output.write(chunk)
    if copied != expected_bytes:
        raise PackageTrustError("Package content does not match declared byte size")


def _tree_index(root: Path) -> tuple[list[Dict[str, Any]], str]:
    files: list[Dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise PackageTrustError(f"Installed tree contains a symbolic link: {path.name}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise PackageTrustError(f"Installed tree contains a non-regular file: {path.name}")
        byte_size, digest = _sha256_file(path)
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "byte_size": byte_size,
                "sha256": digest,
            }
        )
    encoded = json.dumps(files, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return files, sha256(encoded).hexdigest()


def _remove_tree(path: Path) -> None:
    if not path.exists():
        return
    for directory in sorted((item for item in path.rglob("*") if item.is_dir()), reverse=True):
        os.chmod(directory, 0o700)
    os.chmod(path, 0o700)
    shutil.rmtree(path)


class PackageTrustStore:
    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self.max_artifact_bytes = max(1, int(getattr(settings, "package_max_artifact_bytes", 50 * 1024 * 1024)))
        self.max_archive_members = max(1, int(getattr(settings, "package_max_archive_members", 4096)))
        self.max_expanded_bytes = max(1, int(getattr(settings, "package_max_expanded_bytes", 1024 * 1024 * 1024)))

    @property
    def public_key_path(self) -> Path:
        configured = getattr(self.settings, "package_signing_public_key_path", "")
        if configured:
            return Path(configured)
        return Path(self.settings.data_dir) / "trust" / "package-signing-ed25519.pem"

    def package_root(self, package_type: str) -> Path:
        if package_type == "app":
            return Path(self.settings.app_releases_dir)
        if package_type == "model":
            return Path(self.settings.model_releases_dir)
        raise PackageTrustError("Unsupported package type")

    def load_public_key(self) -> tuple[Ed25519PublicKey, str]:
        path = self.public_key_path
        if path.is_symlink() or not path.is_file():
            raise PackageTrustError(f"Trusted package signing key is not configured: {path}")
        try:
            key = serialization.load_pem_public_key(path.read_bytes())
        except (OSError, ValueError, TypeError) as exc:
            raise PackageTrustError("Trusted package signing key is invalid") from exc
        if not isinstance(key, Ed25519PublicKey):
            raise PackageTrustError("Trusted package signing key must be Ed25519")
        raw_key = key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return key, sha256(raw_key).hexdigest()[:16]

    def validate_signed_manifest(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(manifest, dict):
            raise PackageTrustError("Signed package manifest must be an object")
        normalized = {field: manifest.get(field) for field in SIGNED_FIELDS}
        normalized["signature"] = str(manifest.get("signature") or "").strip()
        if int(normalized.get("manifest_version") or 0) != SIGNED_MANIFEST_VERSION:
            raise PackageTrustError("Unsupported signed package manifest version")
        normalized["manifest_version"] = SIGNED_MANIFEST_VERSION
        normalized["package_type"] = str(normalized.get("package_type") or "").strip()
        if normalized["package_type"] not in PACKAGE_TYPES:
            raise PackageTrustError("Unsupported package type")
        normalized["version"] = str(normalized.get("version") or "").strip()
        if not VERSION_PATTERN.fullmatch(normalized["version"]):
            raise PackageTrustError("Invalid package version")
        try:
            normalized["family_id"] = int(normalized.get("family_id") or 0)
            normalized["byte_size"] = int(normalized.get("byte_size") or 0)
        except (TypeError, ValueError) as exc:
            raise PackageTrustError("Invalid signed package numeric field") from exc
        if normalized["family_id"] < 1 or normalized["byte_size"] < 1:
            raise PackageTrustError("Signed package family and byte size must be positive")
        if normalized["byte_size"] > self.max_artifact_bytes:
            raise PackageTrustError("Signed package exceeds artifact byte limit")
        normalized["device_scope"] = str(normalized.get("device_scope") or "").strip()
        normalized["device_id"] = str(normalized.get("device_id") or "").strip()
        if normalized["device_scope"] not in {"family", "device"}:
            raise PackageTrustError("Invalid package device scope")
        if normalized["device_scope"] == "device" and not normalized["device_id"]:
            raise PackageTrustError("Device-scoped package requires device_id")
        if normalized["device_scope"] == "family" and normalized["device_id"]:
            raise PackageTrustError("Family-scoped package must not include device_id")
        normalized["sha256"] = str(normalized.get("sha256") or "").strip().lower()
        if not SHA256_PATTERN.fullmatch(normalized["sha256"]):
            raise PackageTrustError("Invalid package SHA-256")
        normalized["signature_key_id"] = str(normalized.get("signature_key_id") or "").strip().lower()
        normalized["file_name"] = _safe_relative_path(
            str(normalized.get("file_name") or "").strip(), field="package file name"
        ).as_posix()
        if "/" in normalized["file_name"]:
            raise PackageTrustError("Package file name must not contain a directory")
        normalized["entry_path"] = _safe_relative_path(
            str(normalized.get("entry_path") or "").strip(), field="package entry path"
        ).as_posix()
        normalized["entry_type"] = str(normalized.get("entry_type") or "").strip()
        if normalized["entry_type"] not in {"python", "shell", "executable", "data"}:
            raise PackageTrustError("Invalid package entry type")
        if normalized["package_type"] == "app" and normalized["entry_type"] == "data":
            raise PackageTrustError("App package entry type must be runnable")
        if normalized["package_type"] == "model" and normalized["entry_type"] != "data":
            raise PackageTrustError("Model package entry type must be data")
        if normalized["entry_type"] == "python" and not normalized["entry_path"].lower().endswith(".py"):
            raise PackageTrustError("Python package entry must use .py")
        if normalized["entry_type"] == "shell" and not normalized["entry_path"].lower().endswith(".sh"):
            raise PackageTrustError("Shell package entry must use .sh")
        normalized["install_strategy"] = str(normalized.get("install_strategy") or "").strip()
        if normalized["install_strategy"] not in INSTALL_STRATEGIES:
            raise PackageTrustError("Invalid package install strategy")
        if normalized["install_strategy"] == "file" and normalized["entry_path"] != normalized["file_name"]:
            raise PackageTrustError("File package entry_path must equal file_name")
        if not normalized["signature"]:
            raise PackageTrustError("Package signature is required")
        return normalized

    def verify_signature(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self.validate_signed_manifest(manifest)
        key, key_id = self.load_public_key()
        if normalized["signature_key_id"] != key_id:
            raise PackageTrustError("Package signature key does not match trusted key")
        try:
            signature = b64decode(normalized["signature"], validate=True)
        except (ValueError, Base64Error) as exc:
            raise PackageTrustError("Package signature is not valid base64") from exc
        try:
            key.verify(signature, canonical_signed_payload(normalized))
        except InvalidSignature as exc:
            raise PackageTrustError("Package signature verification failed") from exc
        return normalized

    def verify_scope(self, manifest: Dict[str, Any], *, family_id: int, device_id: str) -> None:
        if int(manifest["family_id"]) != int(family_id):
            raise PackageTrustError("Signed package family scope mismatch")
        if manifest["device_scope"] == "device" and manifest["device_id"] != str(device_id):
            raise PackageTrustError("Signed package device scope mismatch")

    def verify_artifact(self, artifact: Path, manifest: Dict[str, Any]) -> None:
        if artifact.is_symlink() or not artifact.is_file():
            raise PackageTrustError("Package artifact must be a regular file")
        byte_size, digest = _sha256_file(artifact)
        if byte_size != int(manifest["byte_size"]):
            raise PackageTrustError("Package byte size verification failed")
        if digest != manifest["sha256"]:
            raise PackageTrustError("Package SHA-256 verification failed")

    def _checked_members(self, members: Iterable[tuple[str, int]]) -> list[PurePosixPath]:
        checked: list[PurePosixPath] = []
        seen: set[str] = set()
        expanded_bytes = 0
        for name, byte_size in members:
            if int(byte_size) < 0:
                raise PackageTrustError("Archive member has an invalid byte size")
            relative = _safe_relative_path(name.rstrip("/"), field="archive member path")
            key = relative.as_posix()
            if key in seen:
                raise PackageTrustError(f"Archive contains duplicate member: {key}")
            seen.add(key)
            checked.append(relative)
            expanded_bytes += max(0, int(byte_size))
            if len(checked) > self.max_archive_members:
                raise PackageTrustError("Archive member limit exceeded")
            if expanded_bytes > self.max_expanded_bytes:
                raise PackageTrustError("Archive expanded byte limit exceeded")
        return checked

    def _extract_zip(self, artifact: Path, destination: Path) -> None:
        with zipfile.ZipFile(artifact) as archive:
            infos = archive.infolist()
            paths = self._checked_members((info.filename, info.file_size) for info in infos)
            for info, relative in zip(infos, paths):
                mode = (info.external_attr >> 16) & 0xFFFF
                file_type = S_IFMT(mode)
                if file_type and file_type not in {S_IFREG} and not info.is_dir():
                    raise PackageTrustError(f"Archive member is not a regular file: {relative}")
                target = destination.joinpath(*relative.parts)
                if not _inside(target.resolve(), destination.resolve()):
                    raise PackageTrustError("Archive member escapes extraction root")
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if info.flag_bits & 0x1:
                    raise PackageTrustError("Encrypted ZIP packages are not supported")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as source, target.open("xb") as output:
                    _copy_exact(source, output, info.file_size)
                os.chmod(target, 0o555 if mode & (S_IXUSR | S_IXGRP | S_IXOTH) else 0o444)

    def _extract_tar(self, artifact: Path, destination: Path) -> None:
        with tarfile.open(artifact, mode="r:*") as archive:
            members = archive.getmembers()
            paths = self._checked_members((member.name, member.size) for member in members)
            for member, relative in zip(members, paths):
                if not (member.isdir() or member.isreg()):
                    raise PackageTrustError(f"Archive member is not a regular file: {relative}")
                target = destination.joinpath(*relative.parts)
                if not _inside(target.resolve(), destination.resolve()):
                    raise PackageTrustError("Archive member escapes extraction root")
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                source = archive.extractfile(member)
                if source is None:
                    raise PackageTrustError(f"Archive member cannot be read: {relative}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with source, target.open("xb") as output:
                    _copy_exact(source, output, member.size)
                os.chmod(target, 0o555 if member.mode & (S_IXUSR | S_IXGRP | S_IXOTH) else 0o444)

    def _extract_archive(self, artifact: Path, destination: Path, file_name: str) -> None:
        lowered = file_name.lower()
        if lowered.endswith(".zip"):
            self._extract_zip(artifact, destination)
            return
        if lowered.endswith((".tar", ".tar.gz", ".tgz")):
            self._extract_tar(artifact, destination)
            return
        raise PackageTrustError("Unsupported signed archive format")

    def _payload_root(self, release_root: Path, manifest: Dict[str, Any]) -> Path:
        return release_root / ("expanded" if manifest["install_strategy"] == "archive" else "artifact")

    def _entry_path(self, release_root: Path, manifest: Dict[str, Any]) -> Path:
        return self._payload_root(release_root, manifest).joinpath(*PurePosixPath(manifest["entry_path"]).parts)

    def install(
        self,
        source_artifact: Path,
        signed_manifest: Dict[str, Any],
        *,
        family_id: int,
        device_id: str,
    ) -> Dict[str, Any]:
        manifest = self.verify_signature(signed_manifest)
        self.verify_scope(manifest, family_id=family_id, device_id=device_id)
        self.verify_artifact(source_artifact, manifest)
        package_root = self.package_root(manifest["package_type"]).resolve()
        versions_root = package_root / "versions"
        staging_root = package_root / ".staging"
        versions_root.mkdir(parents=True, exist_ok=True)
        staging_root.mkdir(parents=True, exist_ok=True)
        final_root = versions_root / manifest["version"]
        if final_root.exists():
            existing = read_json_object(final_root / "install.json")
            if existing.get("signed_manifest") != manifest:
                raise PackageTrustError("Package version is immutable and already contains different content")
            return self.validate_installed_manifest(existing, family_id=family_id, device_id=device_id)

        temporary_root = Path(tempfile.mkdtemp(prefix=f"{manifest['version']}.", dir=str(staging_root)))
        try:
            artifact_dir = temporary_root / "artifact"
            artifact_dir.mkdir(mode=0o700)
            artifact = artifact_dir / manifest["file_name"]
            with source_artifact.open("rb") as source, artifact.open("xb") as output:
                _copy_exact(source, output, int(manifest["byte_size"]))
                output.flush()
                os.fsync(output.fileno())
            self.verify_artifact(artifact, manifest)
            if manifest["install_strategy"] == "archive":
                expanded = temporary_root / "expanded"
                expanded.mkdir(mode=0o700)
                self._extract_archive(artifact, expanded, manifest["file_name"])
            entry = self._entry_path(temporary_root, manifest)
            payload_root = self._payload_root(temporary_root, manifest).resolve()
            resolved_entry = entry.resolve()
            if not _inside(resolved_entry, payload_root) or resolved_entry.is_symlink() or not resolved_entry.is_file():
                raise PackageTrustError("Package entry is not a regular file inside the verified release")
            if manifest["entry_type"] == "executable":
                os.chmod(resolved_entry, 0o555)
            else:
                os.chmod(resolved_entry, 0o444)
            files, tree_digest = _tree_index(payload_root)
            install_manifest = {
                "manifest_version": SIGNED_MANIFEST_VERSION,
                "signed_manifest": manifest,
                "release_root": str(final_root),
                "artifact_path": str(final_root / "artifact" / manifest["file_name"]),
                "installed_path": str(self._entry_path(final_root, manifest)),
                "tree_sha256": tree_digest,
                "tree_files": files,
                "verified_at": utc_now_iso(),
            }
            atomic_write_json(temporary_root / "install.json", install_manifest)
            os.replace(temporary_root, final_root)
            os.chmod(final_root / "install.json", 0o444)
            for directory in sorted((path for path in final_root.rglob("*") if path.is_dir()), reverse=True):
                os.chmod(directory, 0o555)
            os.chmod(final_root, 0o555)
            try:
                return self.validate_installed_manifest(install_manifest, family_id=family_id, device_id=device_id)
            except Exception:
                _remove_tree(final_root)
                raise
        finally:
            if temporary_root.exists():
                _remove_tree(temporary_root)

    def validate_installed_manifest(
        self,
        install_manifest: Dict[str, Any],
        *,
        family_id: int | None = None,
        device_id: str = "",
    ) -> Dict[str, Any]:
        signed = self.verify_signature(dict(install_manifest.get("signed_manifest") or {}))
        if family_id is not None:
            self.verify_scope(signed, family_id=family_id, device_id=device_id)
        expected_root = (self.package_root(signed["package_type"]) / "versions" / signed["version"]).resolve()
        release_root = Path(str(install_manifest.get("release_root") or "")).resolve()
        if release_root != expected_root or not release_root.is_dir():
            raise PackageTrustError("Installed package release root is invalid")
        on_disk_manifest = read_json_object(release_root / "install.json")
        if on_disk_manifest != install_manifest:
            raise PackageTrustError("Installed package manifest does not match active manifest")
        artifact = Path(str(install_manifest.get("artifact_path") or "")).resolve()
        expected_artifact = (release_root / "artifact" / signed["file_name"]).resolve()
        if artifact != expected_artifact or not _inside(artifact, release_root):
            raise PackageTrustError("Installed package artifact path is invalid")
        self.verify_artifact(artifact, signed)
        entry = Path(str(install_manifest.get("installed_path") or "")).resolve()
        expected_entry = self._entry_path(release_root, signed).resolve()
        payload_root = self._payload_root(release_root, signed).resolve()
        if entry != expected_entry or not _inside(entry, payload_root) or entry.is_symlink() or not entry.is_file():
            raise PackageTrustError("Installed package entry is invalid")
        files, tree_digest = _tree_index(payload_root)
        if tree_digest != str(install_manifest.get("tree_sha256") or ""):
            raise PackageTrustError("Installed package content verification failed")
        if files != list(install_manifest.get("tree_files") or []):
            raise PackageTrustError("Installed package file index verification failed")
        return dict(install_manifest)
