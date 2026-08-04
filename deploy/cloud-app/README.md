# GoHome cloud API deployment

The production API uses immutable versioned releases. `/opt/gohome/current` is
the only runtime pointer; deployments never copy files into a mutable source
tree.

## Build

Run from a clean tracked worktree:

```sh
deploy/cloud-app/build-release.sh
```

The archive contains only the cloud runtime, PostgreSQL migrations, the retained
Web interface and their assets. Tests, iOS, edge code, research files,
AppleDouble files and backups are rejected.

## Install

Upload the archive, its SHA-256 value, `install-release.sh`, and
`gohome-app.service`, then run:

```sh
sudo install-release.sh ARCHIVE EXPECTED_SHA256 RELEASE_ID gohome-app.service
```

The installer verifies archive paths and checksum, runs `npm ci --omit=dev`,
atomically switches `/opt/gohome/current`, restarts the service, and checks
`/health`. A failed health check restores the previous target. At most three
managed releases are retained.

The first migration can roll back to the existing `/opt/gohome/app` tree. Remove
that legacy mutable tree only after the WebRTC TestFlight and box cutover pass.
