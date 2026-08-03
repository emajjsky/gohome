#!/usr/bin/env python3
from __future__ import annotations

from argparse import ArgumentParser
from base64 import b64encode
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict
import json
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.package_trust import PackageTrustStore, atomic_write_json, canonical_signed_payload


def file_digest(path: Path) -> tuple[int, str]:
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


def load_private_key(path: Path) -> Ed25519PrivateKey:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Ed25519 private key must be a regular file")
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise RuntimeError("Package signing key must be Ed25519")
    return key


def key_id(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return sha256(raw).hexdigest()[:16]


def build_manifest(arguments: Any) -> Dict[str, Any]:
    package = arguments.package.resolve()
    if package.is_symlink() or not package.is_file():
        raise RuntimeError("Package must be a regular file")
    private_key = load_private_key(arguments.private_key.resolve())
    byte_size, digest = file_digest(package)
    manifest = {
        "manifest_version": 1,
        "package_type": arguments.package_type,
        "version": arguments.version,
        "family_id": arguments.family_id,
        "device_scope": "device" if arguments.device_id else "family",
        "device_id": arguments.device_id,
        "byte_size": byte_size,
        "sha256": digest,
        "signature_key_id": key_id(private_key),
        "file_name": package.name,
        "entry_type": arguments.entry_type,
        "entry_path": arguments.entry_path,
        "install_strategy": arguments.install_strategy,
    }
    manifest["signature"] = b64encode(private_key.sign(canonical_signed_payload(manifest))).decode("ascii")
    return manifest


def parse_arguments() -> Any:
    parser = ArgumentParser(description="Create a GoHome Ed25519 signed package manifest")
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--package-type", choices=("app", "model"), required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--family-id", type=int, required=True)
    parser.add_argument("--device-id", default="")
    parser.add_argument("--install-strategy", choices=("file", "archive"), required=True)
    parser.add_argument("--entry-type", choices=("python", "shell", "executable", "data"), required=True)
    parser.add_argument("--entry-path", required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    manifest = build_manifest(arguments)

    class ValidationSettings:
        data_dir = Path(".")
        package_signing_public_key_path = ""
        package_max_artifact_bytes = 50 * 1024 * 1024

    PackageTrustStore(ValidationSettings()).validate_signed_manifest(manifest)
    if arguments.output:
        atomic_write_json(arguments.output, manifest)
    else:
        sys.stdout.write(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
