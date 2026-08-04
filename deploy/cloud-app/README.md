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
and applies checksum-protected PostgreSQL migrations as the `gohome` service
account before switching traffic. Migrations must remain backward compatible
with the previous application release because database changes are not rolled
back with application files. The installer resolves every deployment input
before entering the release directory, installs the systemd unit before the
atomic `/opt/gohome/current` switch, restarts the service, and checks `/health`.
Any failure after the switch restores and restarts the previous target. At most
three managed releases are retained.

The first migration can roll back to the existing `/opt/gohome/app` tree. Remove
that legacy mutable tree only after the WebRTC TestFlight and box cutover pass.
