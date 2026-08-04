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

## COS permissions

The cloud service identity has `PutObject`, `GetObject`, `HeadObject`,
`DeleteObject`, and `GetBucket` access only under `memory-media/*` and
`event-evidence/*`. The COS SDK authorizes `GetBucket` against the requested
`Prefix`, so a policy that grants it only on the bare bucket resource does not
match either inventory request.

Keep all five actions in the same prefix-scoped statement:

```json
{
  "version": "2.0",
  "statement": [
    {
      "effect": "allow",
      "action": [
        "name/cos:PutObject",
        "name/cos:GetObject",
        "name/cos:HeadObject",
        "name/cos:DeleteObject",
        "name/cos:GetBucket"
      ],
      "resource": [
        "qcs::cos:REGION:uid/OWNER_UIN:BUCKET/memory-media/*",
        "qcs::cos:REGION:uid/OWNER_UIN:BUCKET/event-evidence/*"
      ]
    }
  ]
}
```

Do not add a bare-bucket `GetBucket` statement, grant `cos:*`, enable public
bucket access, or authorize unrelated prefixes.

## Media lifecycle rollout

Keep `GOHOME_MEDIA_LIFECYCLE_DELETE_ENABLED=0` until the production inventory
has been reviewed. Retention classification and physical deletion are separate
operations. The classification phase reads current PostgreSQL references and
persists only retention metadata; expired assets and storage orphans remain
untouched:

```sh
curl -X POST \
  -H "Authorization: Bearer $GOHOME_OPS_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"classification_only":true}' \
  http://127.0.0.1:8788/api/v1/internal/media-lifecycle/run
```

Follow it with an explicit dry-run and review asset, COS orphan, and local
orphan counts. Do not enable deletion until current care-card images, published
family memories, avatars, unresolved critical evidence, and upload intents are
confirmed protected. Physical deletion must remain bounded and independently
auditable.
