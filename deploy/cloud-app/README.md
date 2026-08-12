# GoHome cloud API deployment

The production API uses immutable versioned releases. `/opt/gohome/current` is
the only runtime pointer; deployments never copy files into a mutable source
tree.

## Build

Build the immutable release from a committed revision. The default is `HEAD`;
an explicit revision can be supplied as the second argument:

```sh
deploy/cloud-app/build-release.sh
deploy/cloud-app/build-release.sh dist/cloud-app COMMIT_SHA
```

The archive contains only the cloud runtime, PostgreSQL migrations, the retained
Web interface and their assets. Tests, iOS, edge code, research files,
AppleDouble files and backups are rejected.

The manifest, existence checks, archive, and per-file hashes are all read from
the resolved commit object. Uncommitted worktree files are never inspected or
included, so an unrelated in-progress App change cannot block or contaminate a
backend release.

The build also emits `<archive>.files.sha256`. It is the exact committed-file
manifest used to create the archive; review it together with the archive
checksum before uploading. The manifest is an audit artifact, not a runtime
dependency.

Run `deploy/cloud-app/verify-build-release.sh` after changing the builder. It
proves that a dirty worktree cannot enter the archive and that an explicitly
selected parent commit does not receive files from the current commit.

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

## Home network verification

Production startup requires `GOHOME_HOME_NETWORK_SECRET` in
`/etc/gohome/gohome.env`. Generate an independent random value with at least 32
characters; do not reuse an API, device, auth, media, database or COS secret.
The service HMACs server-observed network addresses and never writes plaintext
phone or box addresses to business tables. A missing or short secret is a
startup error, not a disabled feature.

After migration `018_home_visits_and_return_plans.sql` is applied, verify only
the setting's presence and service health. Do not print the secret or device
runtime fingerprints into deployment logs.

## Vision verification recovery

Visual event verification starts its default 90-second product deadline only
after all four evidence roles are ready and the model job is created. Transport
failures, request timeouts, throttling and provider 5xx responses use bounded
retries only while another attempt can start before that deadline; permanent
provider 4xx responses stop immediately. At the deadline, an event without a
definitive result becomes `timeout_suspected` and creates the incident's single
notification. A late definitive result may update the archived incident but
must not create a second notification. The persisted job error contains only
the failure stage, HTTP status or safe network error code. It must not contain
credentials, provider URLs or signed evidence URLs. Use
`scripts/verify-vision-verification-live.js` from an operations worktree for an
isolated four-frame provider check; the script uses a temporary database, does
not send APNs, and deletes its temporary COS objects.

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

Each deletion cycle is oldest-first and bounded by both count and bytes. The
defaults are deliberately conservative:

```sh
GOHOME_MEDIA_LIFECYCLE_MAX_ASSETS_PER_RUN=10
GOHOME_MEDIA_LIFECYCLE_MAX_ASSET_BYTES_PER_RUN=67108864
GOHOME_MEDIA_LIFECYCLE_MAX_ORPHANS_PER_RUN=25
GOHOME_MEDIA_LIFECYCLE_MAX_ORPHAN_BYTES_PER_RUN=67108864
```

Review `selected_deletions`, `selected_deletion_bytes`, `limited_deletions`,
and the corresponding COS/local orphan fields before changing these limits.

Asset and orphan deletion state is committed before physical bytes are
removed. `media_orphan_cleanup` stores only the provider, relative object key,
size, observation times, status, attempt count, sanitized error, retry time and
completion timestamps. It must never contain COS credentials, signed URLs or
absolute host paths. Failed deletions retry with deterministic exponential
backoff from one minute up to six hours. Objects that disappear or become
tracked before retry are marked `resolved`.

Every lifecycle invocation also writes a bounded `scheduler_runs` row with
`job_type=media_lifecycle`. This is the durable run history used after process
restart; `last_run` is not sourced only from process memory. A dry-run or
`classification_only` invocation records its count summary but does not change
orphan retry rows and never removes storage bytes.

After deploying a new migration, verify the durable structures before enabling
deletion:

```sql
select version, applied_at
from schema_migrations
order by applied_at desc
limit 3;

select status, storage_provider, count(*)
from media_orphan_cleanup
group by status, storage_provider
order by storage_provider, status;

select status, started_at, result
from scheduler_runs
where job_type = 'media_lifecycle'
order by started_at desc
limit 5;
```
