# GoHome signed package contract

GoHome boxes accept only immutable Ed25519-signed application and model packages. The private key belongs to the release environment and must never be copied to a box. Each box stores only the trusted public key at `GOHOME_PACKAGE_SIGNING_PUBLIC_KEY_PATH`.

## Signed fields

Manifest version 1 signs the canonical JSON representation of these fields:

- `manifest_version`
- `package_type`: `app` or `model`
- `version`: immutable release identifier
- `family_id`
- `device_scope`: `family` or `device`
- `device_id`: required only for device-scoped releases
- `byte_size`
- `sha256`
- `signature_key_id`: first 16 hexadecimal characters of the SHA-256 of the raw Ed25519 public key
- `file_name`
- `entry_type`: `python`, `shell`, `executable`, or `data`
- `entry_path`
- `install_strategy`: `file` or `archive`

The signature is base64-encoded and stored in `signature`. App packages must use a runnable entry type. Model packages must use `data`. A file package must use its file name as `entry_path`.

## Create a manifest

Run the signing tool only in the release environment:

```bash
edge-agent/.venv/bin/python edge-agent/tools/sign-package.py \
  --private-key /secure/release/package-signing-ed25519.pem \
  --package /release/gohome-app-1.2.0.zip \
  --package-type app \
  --version 1.2.0 \
  --family-id 7 \
  --install-strategy archive \
  --entry-type python \
  --entry-path service.py \
  --output /release/gohome-app-1.2.0.manifest.json
```

Upload the package as a media asset, then create the package release using the generated manifest fields plus `asset_id`. The server verifies the signature and artifact before recording the release. The target box repeats the verification before installation.

## Box trust provisioning

Provision the matching public key as a regular PEM file owned by the service account:

```bash
install -d -m 0700 edge-agent/data/trust
install -m 0600 package-signing-ed25519-public.pem \
  edge-agent/data/trust/package-signing-ed25519.pem
```

Do not generate a replacement key automatically on the box. Key rotation requires a separately authorized trust update before packages signed by the new key can be installed.

## Installation rules

The box verifies family/device scope, byte size, SHA-256, key identity, and Ed25519 signature before extraction. ZIP and TAR members are copied individually into a private staging directory. Absolute paths, parent traversal, duplicate members, links, device nodes, encrypted ZIP files, excessive member counts, and excessive expanded sizes are rejected.

The verified release is moved atomically into an immutable version directory. The app runtime re-verifies the signed artifact, installed file index, entry location, and entry type before every start. A new app becomes current only after its startup health check succeeds. Rollback can use only a previously verified manifest.
