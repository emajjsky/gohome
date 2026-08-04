const assert = require('node:assert/strict');
const test = require('node:test');
const {
  createDbFromCloudRows,
  persistRowDeltas,
  PostgresStore,
  TABLE_ORDER,
} = require('../postgres-store');
const { buildCloudSeedBundle } = require('../../scripts/export-local-app-db');

function emptyTables() {
  return Object.fromEntries(TABLE_ORDER.map((table) => [table, []]));
}

function recordingPool() {
  const queries = [];
  const client = {
    async query(text, values = []) {
      queries.push({ text: String(text), values });
      return { rowCount: 1, rows: [] };
    },
    release() {},
  };
  return {
    queries,
    async connect() { return client; },
    async end() {},
  };
}

test('row-delta persistence upserts only a changed camera and never wipes tables', async () => {
  const pool = recordingPool();
  const persisted = emptyTables();
  persisted.users = [{ id: 'user-1', email: 'person@example.com' }];
  persisted.families = [{ id: 'family-1', name: 'Home' }];
  persisted.cameras = [
    { id: 'camera-1', family_id: 'family-1', name: 'Old name' },
    { id: 'external-camera', family_id: 'family-1', name: 'Created outside the legacy snapshot' },
  ];
  const current = structuredClone(persisted);
  current.cameras[0].name = 'Living room';
  current.cameras = current.cameras.filter((camera) => camera.id !== 'external-camera');

  const nextSnapshot = await persistRowDeltas(pool, { tables: current }, persisted);

  const sql = pool.queries.map((query) => query.text.trim());
  assert.equal(sql.some((text) => /^delete from/i.test(text)), false);
  assert.equal(sql.some((text) => /^insert into users/i.test(text)), false);
  assert.equal(sql.some((text) => /^insert into families/i.test(text)), false);
  assert.equal(sql.filter((text) => /^insert into cameras/i.test(text)).length, 1);
  assert.equal(sql.some((text) => /pg_advisory_xact_lock/i.test(text)), true);
  assert.equal(nextSnapshot.cameras.some((camera) => camera.id === 'external-camera'), true);
});

test('explicit row deletion is parameterized and updates the persisted snapshot', async () => {
  const pool = recordingPool();
  const persisted = emptyTables();
  persisted.cameras = [{ id: 'camera-1', family_id: 'family-1', name: 'Living room' }];
  const store = new PostgresStore({ pool, db: {}, persistedTables: persisted });

  await store.deleteRow('cameras', 'camera-1');

  const deletion = pool.queries.find((query) => /^delete from cameras/i.test(query.text.trim()));
  assert.ok(deletion);
  assert.match(deletion.text, /where id = \$1/i);
  assert.deepEqual(deletion.values, ['camera-1']);
  assert.deepEqual(store.persistedTables.cameras, []);
  await assert.rejects(store.deleteRow('cameras; drop table users', 'camera-1'), /unsupported postgres table/);
});

test('event deletion mirrors PostgreSQL cascade into relation snapshots', async () => {
  const pool = recordingPool();
  const persisted = emptyTables();
  persisted.events = [{ id: 'event-1' }];
  persisted.event_media_assets = [
    { id: 'relation-1', event_id: 'event-1', asset_id: 'asset-1' },
    { id: 'relation-2', event_id: 'event-2', asset_id: 'asset-2' },
  ];
  const db = { event_media_assets: structuredClone(persisted.event_media_assets) };
  const store = new PostgresStore({ pool, db, persistedTables: persisted });

  await store.deleteRow('events', 'event-1');

  assert.deepEqual(store.persistedTables.event_media_assets.map((row) => row.id), ['relation-2']);
  assert.deepEqual(store.db.event_media_assets.map((row) => row.id), ['relation-2']);
});

test('scheduler run persistence updates one row and prunes retained history without a full save', async () => {
  const pool = recordingPool();
  const persisted = emptyTables();
  persisted.scheduler_runs = [{ id: 'run-old', created_at: '2026-07-01T00:00:00.000Z' }];
  const store = new PostgresStore({ pool, db: {}, persistedTables: persisted });
  const run = {
    id: 'run-new',
    job_type: 'background_scheduler',
    status: 'succeeded',
    result: { families_checked: 4 },
    started_at: '2026-07-30T00:00:00.000Z',
    finished_at: '2026-07-30T00:00:00.100Z',
    created_at: '2026-07-30T00:00:00.000Z',
    updated_at: '2026-07-30T00:00:00.100Z',
  };

  await store.saveSchedulerRun(run, { retention: 100 });

  const sql = pool.queries.map((query) => query.text.trim());
  assert.equal(sql.filter((text) => /^insert into scheduler_runs/i.test(text)).length, 1);
  assert.equal(sql.some((text) => /^insert into (?!scheduler_runs)/i.test(text)), false);
  const retentionDelete = pool.queries.find((query) => /^delete from scheduler_runs/i.test(query.text.trim()));
  assert.ok(retentionDelete);
  assert.deepEqual(retentionDelete.values, [100]);
  assert.equal(store.persistedTables.scheduler_runs.some((item) => item.id === 'run-new'), true);
});

test('scheduler run persistence ignores overlap placeholders without an id', async () => {
  const pool = recordingPool();
  const persisted = emptyTables();
  persisted.scheduler_runs = [{ id: 'run-existing', created_at: '2026-07-30T00:00:00.000Z' }];
  const store = new PostgresStore({ pool, db: {}, persistedTables: persisted });

  await store.saveSchedulerRun({
    id: null,
    job_type: 'background_scheduler',
    status: 'skipped',
    result: { skipped: [{ reason: 'scheduler_already_running' }] },
  });

  assert.equal(pool.queries.length, 0);
  assert.deepEqual(store.persistedTables.scheduler_runs, persisted.scheduler_runs);
});

test('media lifecycle reads fresh PostgreSQL references and persists retention rows in one batch', async () => {
  const inventoryQueries = [];
  const pool = recordingPool();
  pool.query = async (text) => {
    inventoryQueries.push(String(text));
    if (/from media_assets/i.test(text)) return { rows: [{ id: 'asset-1', size_bytes: 42, metadata: { purpose: 'family_memory' } }] };
    if (/from event_media_assets/i.test(text)) return { rows: [{ id: 'relation-1', event_id: 'event-1', asset_id: 'asset-1' }] };
    if (/from events/i.test(text)) return { rows: [{ id: 'event-1', media_asset_id: 'asset-1' }] };
    if (/from family_memory_media/i.test(text)) return { rows: [{ memory_id: 'memory-1', asset_id: 'asset-1' }] };
    if (/from care_cards/i.test(text)) return { rows: [{ id: 'card-1', image_url: 'care-cards/card.webp' }] };
    if (/from users/i.test(text)) return { rows: [{ id: 'user-1', metadata: { avatar_asset_id: 'asset-1' } }] };
    if (/from media_upload_intents/i.test(text)) return { rows: [] };
    if (/from media_orphan_cleanup/i.test(text)) return { rows: [] };
    throw new Error(`unexpected inventory query: ${text}`);
  };
  const persisted = emptyTables();
  persisted.media_assets = [{ id: 'asset-1', retention_status: 'active' }];
  const db = { assets: [{ id: 'asset-1', size: 42 }] };
  const store = new PostgresStore({ pool, db, persistedTables: persisted });

  const inventory = await store.mediaLifecycleInventory();
  assert.equal(inventory.assets[0].purpose, 'family_memory');
  assert.equal(inventory.assets[0].size, 42);
  assert.equal(inventory.event_media_assets[0].asset_id, 'asset-1');
  assert.equal(inventory.family_memory_media[0].asset_id, 'asset-1');
  assert.equal(inventoryQueries.length, 8);

  await store.saveMediaLifecycleAssets([{
    id: 'asset-1',
    retention_class: 'family_memory',
    retention_status: 'active',
    retention_reason: 'user_managed',
    retain_until: null,
    deletion_attempts: 0,
    deletion_error: '',
    next_deletion_at: null,
    deleted_at: null,
    size: 42,
    updated_at: '2026-08-04T08:00:00.000Z',
  }]);

  const update = pool.queries.find((query) => /update media_assets as target/i.test(query.text));
  assert.ok(update);
  assert.equal(pool.queries.filter((query) => /update media_assets as target/i.test(query.text)).length, 1);
  assert.equal(pool.queries.some((query) => /^insert into/i.test(query.text.trim())), false);
  assert.equal(JSON.parse(update.values[0])[0].retention_class, 'family_memory');
  assert.equal(store.db.assets[0].retention_reason, 'user_managed');

  await store.saveMediaLifecycleOrphans([{
    storage_provider: 'cos',
    storage_key: 'event-evidence/orphan.jpg',
    size_bytes: 64,
    source_modified_at: '2026-08-01T00:00:00.000Z',
    first_seen_at: '2026-08-04T08:00:00.000Z',
    last_seen_at: '2026-08-04T08:00:00.000Z',
    status: 'failed',
    deletion_attempts: 1,
    deletion_error: 'ServiceUnavailable: retry',
    next_deletion_at: '2026-08-04T08:01:00.000Z',
    created_at: '2026-08-04T08:00:00.000Z',
    updated_at: '2026-08-04T08:00:00.000Z',
  }]);

  const orphanUpsert = pool.queries.find((query) => /insert into media_orphan_cleanup/i.test(query.text));
  assert.ok(orphanUpsert);
  assert.match(orphanUpsert.text, /on conflict \(storage_provider, storage_key\)/i);
  assert.equal(JSON.parse(orphanUpsert.values[0])[0].storage_key, 'event-evidence/orphan.jpg');
  assert.equal(store.db.media_orphans[0].status, 'failed');
});

test('postgres date values retain their Shanghai calendar day after hydration', () => {
  const rows = emptyTables();
  rows.care_cards = [{
    id: '36',
    card_id: 'care-5-2026-07-22',
    family_id: '5',
    elder_id: 'elder_primary',
    card_date: new Date('2026-07-21T16:00:00.000Z'),
    card_type: 'daily',
    created_at: new Date('2026-07-22T00:00:00.000Z'),
    updated_at: new Date('2026-07-22T00:00:00.000Z'),
  }];

  const db = createDbFromCloudRows(rows, { created_at: '2026-07-22T00:00:00.000Z' });

  assert.equal(db.care_cards[0].card_date, '2026-07-22');
});

test('family metadata survives PostgreSQL hydration and serialization', () => {
  const rows = emptyTables();
  rows.families = [{
    id: 'family-1',
    name: 'Home',
    metadata: {
      member_count: 1,
      created_by_user_id: 'user-1',
      onboarding_completed_at: '2026-07-25T09:00:00.000Z',
      custom_setting: { enabled: true },
    },
  }];

  const db = createDbFromCloudRows(rows, { created_at: '2026-07-25T09:00:00.000Z' });
  assert.equal(db.families[0].metadata.onboarding_completed_at, '2026-07-25T09:00:00.000Z');
  assert.deepEqual(db.families[0].metadata.custom_setting, { enabled: true });

  const persisted = buildCloudSeedBundle(db, { exportedAt: '2026-07-25T09:00:00.000Z' }).tables.families[0];
  assert.equal(persisted.metadata.onboarding_completed_at, '2026-07-25T09:00:00.000Z');
  assert.deepEqual(persisted.metadata.custom_setting, { enabled: true });
});

test('media asset metadata survives PostgreSQL serialization and hydration', () => {
  const timestamp = '2026-07-24T02:00:00.000Z';
  const bundle = buildCloudSeedBundle({
    created_at: timestamp,
    updated_at: timestamp,
    assets: [{
      id: 'memory-video-1',
      family_id: null,
      content_type: 'video/mp4',
      storage_provider: 'cos',
      storage_key: 'memory-media/family-1/video.mp4',
      purpose: 'family_memory',
      size: 2_000_000,
      retention_class: 'family_memory',
      retention_status: 'failed',
      retention_reason: 'temporary_storage_failure',
      retain_until: '2026-08-24T02:00:00.000Z',
      deletion_attempts: 3,
      deletion_error: 'COS timeout',
      next_deletion_at: '2026-07-24T03:00:00.000Z',
      deleted_at: null,
      metadata: {
        duration_seconds: 42.5,
        pixel_width: 1280,
        pixel_height: 720,
        uploaded_by: 'user-1',
      },
      evidence_frame_role: 'current',
      created_at: timestamp,
      updated_at: timestamp,
    }],
  }, { exportedAt: timestamp });

  const persisted = bundle.tables.media_assets[0];
  assert.equal(persisted.metadata.duration_seconds, 42.5);
  assert.equal(persisted.metadata.pixel_width, 1280);
  assert.equal(persisted.metadata.uploaded_by, 'user-1');
  assert.equal(persisted.metadata.evidence_frame_role, 'current');
  assert.equal(persisted.retention_class, 'family_memory');
  assert.equal(persisted.retention_status, 'failed');
  assert.equal(persisted.retention_reason, 'temporary_storage_failure');
  assert.equal(persisted.retain_until, '2026-08-24T02:00:00.000Z');
  assert.equal(persisted.deletion_attempts, 3);
  assert.equal(persisted.deletion_error, 'COS timeout');
  assert.equal(persisted.next_deletion_at, '2026-07-24T03:00:00.000Z');
  assert.equal(persisted.deleted_at, null);

  const db = createDbFromCloudRows(bundle.tables, { created_at: timestamp });
  assert.equal(db.assets[0].metadata.duration_seconds, 42.5);
  assert.equal(db.assets[0].metadata.pixel_height, 720);
  assert.equal(db.assets[0].purpose, 'family_memory');
  assert.equal(db.assets[0].evidence_frame_role, 'current');
  assert.equal(db.assets[0].retention_class, 'family_memory');
  assert.equal(db.assets[0].retention_status, 'failed');
  assert.equal(db.assets[0].retention_reason, 'temporary_storage_failure');
  assert.equal(db.assets[0].retain_until, '2026-08-24T02:00:00.000Z');
  assert.equal(db.assets[0].deletion_attempts, 3);
  assert.equal(db.assets[0].deletion_error, 'COS timeout');
  assert.equal(db.assets[0].next_deletion_at, '2026-07-24T03:00:00.000Z');
  assert.equal(db.assets[0].deleted_at, null);
});

test('media upload intents survive PostgreSQL serialization and hydration without credentials', () => {
  const timestamp = '2026-07-24T02:00:00.000Z';
  const expiresAt = '2026-07-24T02:10:00.000Z';
  const bundle = buildCloudSeedBundle({
    created_at: timestamp,
    updated_at: timestamp,
    media_upload_intents: [{
      asset_id: 'memory-asset-pending',
      family_id: 'family-1',
      user_id: 'user-1',
      object_key: 'memory-media/family-1/2026/07/24/memory-asset-pending.mp4',
      content_type: 'video/mp4',
      size_bytes: 2_000_000,
      pixel_width: 1280,
      pixel_height: 720,
      duration_seconds: 42.5,
      expires_at: expiresAt,
      created_at: timestamp,
      updated_at: timestamp,
    }],
  }, { exportedAt: timestamp });

  const persisted = bundle.tables.media_upload_intents[0];
  assert.equal(persisted.asset_id, 'memory-asset-pending');
  assert.equal(persisted.duration_seconds, 42.5);
  assert.equal(Object.hasOwn(persisted, 'upload_url'), false);
  assert.equal(Object.hasOwn(persisted, 'upload_token'), false);

  const db = createDbFromCloudRows(bundle.tables, { created_at: timestamp });
  assert.equal(db.media_upload_intents[0].object_key, persisted.object_key);
  assert.equal(db.media_upload_intents[0].expires_at, expiresAt);
});

test('family invitations survive PostgreSQL serialization and hydration without plaintext codes', () => {
  const timestamp = '2026-07-27T08:00:00.000Z';
  const expiresAt = '2026-07-27T08:10:00.000Z';
  const codeHash = 'a'.repeat(64);
  const bundle = buildCloudSeedBundle({
    created_at: timestamp,
    updated_at: timestamp,
    family_invitations: [{
      id: 'invitation-1',
      family_id: 'family-1',
      code_hash: codeHash,
      code_hint: 'WXYZ',
      code: 'GH-THIS-MUST-NOT-PERSIST',
      created_by_user_id: 'user-1',
      status: 'active',
      expires_at: expiresAt,
      created_at: timestamp,
      updated_at: timestamp,
    }],
  }, { exportedAt: timestamp });

  const persisted = bundle.tables.family_invitations[0];
  assert.equal(persisted.code_hash, codeHash);
  assert.equal(Object.hasOwn(persisted, 'code'), false);

  const db = createDbFromCloudRows(bundle.tables, { created_at: timestamp });
  assert.equal(db.family_invitations[0].code_hash, codeHash);
  assert.equal(db.family_invitations[0].expires_at, expiresAt);
  assert.equal(Object.hasOwn(db.family_invitations[0], 'code'), false);
});
