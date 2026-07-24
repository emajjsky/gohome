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
      metadata: {
        duration_seconds: 42.5,
        pixel_width: 1280,
        pixel_height: 720,
        uploaded_by: 'user-1',
      },
      created_at: timestamp,
      updated_at: timestamp,
    }],
  }, { exportedAt: timestamp });

  const persisted = bundle.tables.media_assets[0];
  assert.equal(persisted.metadata.duration_seconds, 42.5);
  assert.equal(persisted.metadata.pixel_width, 1280);
  assert.equal(persisted.metadata.uploaded_by, 'user-1');

  const db = createDbFromCloudRows(bundle.tables, { created_at: timestamp });
  assert.equal(db.assets[0].metadata.duration_seconds, 42.5);
  assert.equal(db.assets[0].metadata.pixel_height, 720);
  assert.equal(db.assets[0].purpose, 'family_memory');
});
