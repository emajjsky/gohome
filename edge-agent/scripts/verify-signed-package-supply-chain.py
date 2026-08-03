#!/usr/bin/env python3
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import os
import sys
import tarfile
import time
import zipfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.app_runtime_guard_service import AppRuntimeGuardService
from app.package_trust import (
    PackageTrustError,
    PackageTrustStore,
    canonical_signed_payload,
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_rejected(action, message: str) -> None:
    try:
        action()
    except PackageTrustError:
        return
    raise AssertionError(message)


def make_settings(root: Path, public_key_path: Path) -> SimpleNamespace:
    data_dir = root / "data"
    app_releases = data_dir / "releases" / "app"
    model_releases = data_dir / "releases" / "model"
    runtime = data_dir / "runtime" / "app"
    logs = runtime / "logs"
    for path in (app_releases, model_releases, runtime, logs):
        path.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(
        data_dir=data_dir,
        app_releases_dir=app_releases,
        model_releases_dir=model_releases,
        app_runtime_dir=runtime,
        runtime_logs_dir=logs,
        package_signing_public_key_path=public_key_path,
        package_max_archive_members=32,
        package_max_artifact_bytes=2 * 1024 * 1024,
        package_max_expanded_bytes=1024 * 1024,
        app_runtime_startup_grace_seconds=0.2,
        app_runtime_watchdog_interval_seconds=0.1,
    )


def write_public_key(private_key: Ed25519PrivateKey, path: Path) -> str:
    public_key = private_key.public_key()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    os.chmod(path, 0o600)
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return sha256(raw).hexdigest()[:16]


def signed_manifest(
    private_key: Ed25519PrivateKey,
    key_id: str,
    artifact: Path,
    *,
    version: str,
    file_name: str,
    entry_path: str,
    entry_type: str = "python",
    install_strategy: str = "archive",
    family_id: int = 7,
    device_scope: str = "family",
    device_id: str = "",
) -> dict:
    data = artifact.read_bytes()
    manifest = {
        "manifest_version": 1,
        "package_type": "app",
        "version": version,
        "family_id": family_id,
        "device_scope": device_scope,
        "device_id": device_id,
        "byte_size": len(data),
        "sha256": sha256(data).hexdigest(),
        "signature_key_id": key_id,
        "file_name": file_name,
        "entry_type": entry_type,
        "entry_path": entry_path,
        "install_strategy": install_strategy,
    }
    manifest["signature"] = b64encode(private_key.sign(canonical_signed_payload(manifest))).decode("ascii")
    return manifest


def make_zip(path: Path, members: list[tuple[str, bytes]], *, executable: set[str] | None = None) -> None:
    executable = executable or set()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in members:
            info = zipfile.ZipInfo(name)
            info.external_attr = ((0o100755 if name in executable else 0o100644) << 16)
            archive.writestr(info, content)


def make_tar(path: Path, members: list[tarfile.TarInfo], contents: list[bytes | None]) -> None:
    with tarfile.open(path, "w") as archive:
        for member, content in zip(members, contents):
            archive.addfile(member, BytesIO(content) if content is not None else None)


def install(
    trust: PackageTrustStore,
    artifact: Path,
    manifest: dict,
    *,
    family_id: int = 7,
    device_id: str = "box-1",
) -> dict:
    return trust.install(artifact, manifest, family_id=family_id, device_id=device_id)


def main() -> None:
    with TemporaryDirectory(prefix="gohome-package-trust-") as temporary:
        root = Path(temporary)
        private_key = Ed25519PrivateKey.generate()
        public_key_path = root / "trust" / "package-signing-ed25519.pem"
        key_id = write_public_key(private_key, public_key_path)
        settings = make_settings(root, public_key_path)
        trust = PackageTrustStore(settings)

        valid_zip = root / "valid.zip"
        make_zip(
            valid_zip,
            [("service.py", b"import time\nwhile True:\n    time.sleep(1)\n")],
        )
        valid_manifest = signed_manifest(
            private_key,
            key_id,
            valid_zip,
            version="1.0.0",
            file_name="valid.zip",
            entry_path="service.py",
        )
        installed = install(trust, valid_zip, valid_manifest)
        check(Path(installed["installed_path"]).is_file(), "valid signed package was not installed")
        check(trust.validate_installed_manifest(installed) == installed, "valid installed package did not re-verify")
        check(install(trust, valid_zip, valid_manifest) == installed, "identical immutable package was not idempotent")

        conflicting_zip = root / "conflicting.zip"
        make_zip(conflicting_zip, [("service.py", b"raise SystemExit(3)\n")])
        conflicting_manifest = signed_manifest(
            private_key,
            key_id,
            conflicting_zip,
            version="1.0.0",
            file_name=conflicting_zip.name,
            entry_path="service.py",
        )
        expect_rejected(
            lambda: install(trust, conflicting_zip, conflicting_manifest),
            "immutable version accepted different signed content",
        )

        modified = root / "modified.zip"
        modified.write_bytes(valid_zip.read_bytes() + b"tampered")
        expect_rejected(
            lambda: install(trust, modified, valid_manifest),
            "modified package bytes were accepted",
        )

        wrong_signature = dict(valid_manifest)
        wrong_signature["signature"] = b64encode(Ed25519PrivateKey.generate().sign(canonical_signed_payload(wrong_signature))).decode("ascii")
        expect_rejected(
            lambda: install(trust, valid_zip, wrong_signature),
            "package signed by an untrusted key was accepted",
        )

        wrong_size = dict(valid_manifest)
        wrong_size["byte_size"] += 1
        wrong_size["signature"] = b64encode(private_key.sign(canonical_signed_payload(wrong_size))).decode("ascii")
        expect_rejected(lambda: install(trust, valid_zip, wrong_size), "wrong package size was accepted")

        wrong_hash = dict(valid_manifest)
        wrong_hash["sha256"] = "0" * 64
        wrong_hash["signature"] = b64encode(private_key.sign(canonical_signed_payload(wrong_hash))).decode("ascii")
        expect_rejected(lambda: install(trust, valid_zip, wrong_hash), "wrong package hash was accepted")

        zip_slip = root / "zip-slip.zip"
        make_zip(zip_slip, [("../escape.py", b"pass\n")])
        zip_slip_manifest = signed_manifest(
            private_key, key_id, zip_slip, version="1.0.1", file_name=zip_slip.name, entry_path="escape.py"
        )
        expect_rejected(lambda: install(trust, zip_slip, zip_slip_manifest), "ZIP path traversal was accepted")

        zip_absolute = root / "zip-absolute.zip"
        make_zip(zip_absolute, [("/escape.py", b"pass\n")])
        zip_absolute_manifest = signed_manifest(
            private_key,
            key_id,
            zip_absolute,
            version="1.0.2",
            file_name=zip_absolute.name,
            entry_path="escape.py",
        )
        expect_rejected(lambda: install(trust, zip_absolute, zip_absolute_manifest), "absolute ZIP path was accepted")

        zip_symlink = root / "zip-symlink.zip"
        with zipfile.ZipFile(zip_symlink, "w") as archive:
            info = zipfile.ZipInfo("service.py")
            info.create_system = 3
            info.external_attr = (0o120777 << 16)
            archive.writestr(info, "/tmp/escape")
        zip_symlink_manifest = signed_manifest(
            private_key,
            key_id,
            zip_symlink,
            version="1.0.3",
            file_name=zip_symlink.name,
            entry_path="service.py",
        )
        expect_rejected(lambda: install(trust, zip_symlink, zip_symlink_manifest), "ZIP symbolic link was accepted")

        tar_slip = root / "tar-slip.tar"
        tar_slip_member = tarfile.TarInfo("../escape.py")
        tar_slip_member.size = 5
        make_tar(tar_slip, [tar_slip_member], [b"pass\n"])
        tar_slip_manifest = signed_manifest(
            private_key, key_id, tar_slip, version="1.0.4", file_name=tar_slip.name, entry_path="escape.py"
        )
        expect_rejected(lambda: install(trust, tar_slip, tar_slip_manifest), "TAR path traversal was accepted")

        tar_link = root / "tar-link.tar"
        regular = tarfile.TarInfo("service.py")
        regular.size = 5
        hardlink = tarfile.TarInfo("linked.py")
        hardlink.type = tarfile.LNKTYPE
        hardlink.linkname = "service.py"
        make_tar(tar_link, [regular, hardlink], [b"pass\n", None])
        tar_link_manifest = signed_manifest(
            private_key, key_id, tar_link, version="1.0.5", file_name=tar_link.name, entry_path="service.py"
        )
        expect_rejected(lambda: install(trust, tar_link, tar_link_manifest), "TAR hard link was accepted")

        tar_symlink = root / "tar-symlink.tar"
        symlink = tarfile.TarInfo("service.py")
        symlink.type = tarfile.SYMTYPE
        symlink.linkname = "/tmp/escape"
        make_tar(tar_symlink, [symlink], [None])
        tar_symlink_manifest = signed_manifest(
            private_key,
            key_id,
            tar_symlink,
            version="1.0.8",
            file_name=tar_symlink.name,
            entry_path="service.py",
        )
        expect_rejected(lambda: install(trust, tar_symlink, tar_symlink_manifest), "TAR symbolic link was accepted")

        too_many = root / "too-many.zip"
        make_zip(too_many, [(f"files/{index}.txt", b"") for index in range(33)])
        too_many_manifest = signed_manifest(
            private_key,
            key_id,
            too_many,
            version="1.0.9",
            file_name=too_many.name,
            entry_path="files/0.txt",
        )
        expect_rejected(lambda: install(trust, too_many, too_many_manifest), "archive member limit was ignored")

        too_large = root / "too-large.zip"
        make_zip(too_large, [("service.py", b"x" * (1024 * 1024 + 1))])
        too_large_manifest = signed_manifest(
            private_key,
            key_id,
            too_large,
            version="1.0.10",
            file_name=too_large.name,
            entry_path="service.py",
        )
        expect_rejected(lambda: install(trust, too_large, too_large_manifest), "expanded byte limit was ignored")

        direct_file = root / "direct.py"
        direct_file.write_text("raise SystemExit(0)\n", encoding="utf-8")
        direct_manifest = signed_manifest(
            private_key,
            key_id,
            direct_file,
            version="1.0.11",
            file_name=direct_file.name,
            entry_path=direct_file.name,
            install_strategy="file",
        )
        direct_install = install(trust, direct_file, direct_manifest)
        check(Path(direct_install["installed_path"]).is_file(), "valid signed file package was not installed")

        escaped_entry_manifest = signed_manifest(
            private_key,
            key_id,
            valid_zip,
            version="1.0.6",
            file_name=valid_zip.name,
            entry_path="../service.py",
        )
        expect_rejected(
            lambda: install(trust, valid_zip, escaped_entry_manifest),
            "entry path escape was accepted",
        )

        scoped_manifest = signed_manifest(
            private_key,
            key_id,
            valid_zip,
            version="1.0.7",
            file_name=valid_zip.name,
            entry_path="service.py",
            device_scope="device",
            device_id="box-2",
        )
        expect_rejected(
            lambda: install(trust, valid_zip, scoped_manifest, device_id="box-1"),
            "package for another device was accepted",
        )

        entry = Path(installed["installed_path"])
        os.chmod(entry, 0o644)
        entry.write_text("raise SystemExit(0)\n", encoding="utf-8")
        expect_rejected(
            lambda: trust.validate_installed_manifest(installed),
            "modified installed content was accepted",
        )

        runtime_root = root / "runtime-case"
        runtime_key_path = runtime_root / "trust" / "package-signing-ed25519.pem"
        runtime_key_id = write_public_key(private_key, runtime_key_path)
        runtime_settings = make_settings(runtime_root, runtime_key_path)
        runtime_trust = PackageTrustStore(runtime_settings)
        current_holder: dict = {}
        guard = AppRuntimeGuardService(
            settings=runtime_settings,
            current_manifest_loader=lambda: dict(current_holder),
        )
        stable_zip = runtime_root / "stable.zip"
        make_zip(stable_zip, [("service.py", b"import time\nwhile True:\n    time.sleep(1)\n")])
        stable_signed = signed_manifest(
            private_key,
            runtime_key_id,
            stable_zip,
            version="2.0.0",
            file_name=stable_zip.name,
            entry_path="service.py",
        )
        stable = install(runtime_trust, stable_zip, stable_signed)
        stable_result = guard.apply_release(
            stable,
            activate=lambda: (current_holder.clear(), current_holder.update(stable)),
        )
        check(stable_result.get("ok") is True, "valid signed runtime did not start")
        check(current_holder == stable, "healthy runtime was not atomically activated")

        failing_zip = runtime_root / "failing.zip"
        make_zip(failing_zip, [("service.py", b"raise SystemExit(9)\n")])
        failing_signed = signed_manifest(
            private_key,
            runtime_key_id,
            failing_zip,
            version="2.0.1",
            file_name=failing_zip.name,
            entry_path="service.py",
        )
        failing = install(runtime_trust, failing_zip, failing_signed)
        rollback = guard.apply_release(failing, previous_manifest=stable)
        check(rollback.get("ok") is False, "failing runtime was reported healthy")
        check(rollback.get("rolled_back") is True, "runtime did not roll back to verified release")
        check(guard.status().get("running") is True, "verified rollback runtime is not running")

        activation_zip = runtime_root / "activation.zip"
        make_zip(activation_zip, [("service.py", b"import time\nwhile True:\n    time.sleep(1)\n")])
        activation_signed = signed_manifest(
            private_key,
            runtime_key_id,
            activation_zip,
            version="2.0.2",
            file_name=activation_zip.name,
            entry_path="service.py",
        )
        activation_candidate = install(runtime_trust, activation_zip, activation_signed)

        def fail_activation() -> None:
            raise OSError("simulated atomic manifest failure")

        activation_result = guard.apply_release(
            activation_candidate,
            previous_manifest=stable,
            activate=fail_activation,
        )
        check(activation_result.get("ok") is False, "failed activation was reported healthy")
        check(activation_result.get("rolled_back") is True, "activation failure did not restore verified runtime")
        check(current_holder == stable, "activation failure changed the active manifest")
        guard.stop_runtime(clear_should_run=True)
        time.sleep(0.05)

    print("signed package supply-chain verification passed")


if __name__ == "__main__":
    main()
