const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { JsonNativeRepository } = require('../native-api/repository');
const { PostgresNativeRepository } = require('../native-api/postgres-repository');
const { createLocalAppServer } = require('../server');

function fixture() {
  return {
    updated_at: '2026-07-27T08:00:00.000Z',
    active_user_id: 'user-a',
    users: [
      { id: 'user-a', email: 'a@example.com', phone: '13800138000', display_name: 'A', password: 'raw-password', password_hash: 'secret-hash' },
      { id: 'user-b', email: 'b@example.com', phone: '13800138001', display_name: 'B' },
    ],
    families: [{ id: 'family-a', name: 'A Home', created_by_user_id: 'user-a' }],
    family_members: [{ id: 'member-a', family_id: 'family-a', user_id: 'user-a', role: 'owner', status: 'active' }],
    elder_profiles: {},
    devices: { 'box-a': { id: 'box-a', device_id: 'box-a', family_id: 'family-a', name: 'Box', lan_url: 'http://secret-lan' } },
    device_bindings: [{ id: 'binding-a', family_id: 'family-a', device_id: 'box-a', status: 'active' }],
    binding_codes: [{ id: 'code-a', family_id: 'family-a', code: 'SECRET-CODE' }],
    device_tokens: [{ id: 'token-a', family_id: 'family-a', device_id: 'box-a', token_hash: 'device-token-secret' }],
    cameras: { 'camera-a': { id: 'camera-a', family_id: 'family-a', device_id: 'box-a', name: 'Camera', stream_url: 'rtsp://secret', username: 'admin', password: 'camera-secret' } },
    assets: [{
      id: 'asset-a', family_id: 'family-a', content_type: 'image/jpeg', storage_provider: 'cos',
      storage_key: 'private/family-a/asset-a.jpg', purpose: 'family_memory', size: 123,
    }],
    media_upload_intents: [{ asset_id: 'pending-a', family_id: 'family-a', user_id: 'user-a', object_key: 'memory-media/family-a/pending.jpg' }],
    events: [{ id: 'event-a', family_id: 'family-a', media_asset_id: 'asset-a', event_type: 'fall', summary: '跌倒提醒' }],
    app_sessions: [{ id: 'session-a', user_id: 'user-a', token: 'raw-session-token', token_hash: 'session-hash', status: 'active' }],
    app_push_tokens: [{ id: 'push-a', family_id: 'family-a', user_id: 'user-a', token_ciphertext: 'push-secret', status: 'active' }],
    family_memories: [{ id: 'memory-a', family_id: 'family-a', author_user_id: 'user-a', body: 'Memory' }],
    family_memory_media: [{ id: 'media-a', family_id: 'family-a', memory_id: 'memory-a', asset_id: 'asset-a' }],
    family_memory_comments: [],
    family_memory_favorites: [],
    activity_intervals: [],
    family_rules: {},
    care_preferences: {},
    calendar_events: [],
    home_visits: [{ id: 'visit-a', family_id: 'family-a', user_id: 'user-a', visit_date: '2026-07-27', verified_at: '2026-07-27T08:00:00Z', verification_method: 'public_network_match' }],
    home_return_plans: [{ id: 'plan-a', family_id: 'family-a', user_id: 'user-a', starts_at: '2026-08-02T10:00:00Z', note: '回家吃饭', status: 'planned' }],
    care_cards: [],
    app_messages: [],
    app_message_actions: [],
    notification_deliveries: [],
    scheduler_runs: [],
    model_generation_jobs: [],
    content_sources: [],
    content_recommendations: [],
  };
}

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => resolve(`http://127.0.0.1:${server.address().port}`));
  });
}

test('account export is family-scoped and excludes credentials and storage secrets', () => {
  const repo = new JsonNativeRepository(fixture(), { clock: () => '2026-07-27T09:00:00.000Z' });
  const exported = repo.accountExport('user-a');
  const serialized = JSON.stringify(exported);

  assert.equal(exported.account.phone, '13800138000');
  assert.equal(exported.families[0].events[0].summary, '跌倒提醒');
  assert.equal(exported.families[0].home_visits[0].visit_date, '2026-07-27');
  assert.equal(exported.families[0].home_return_plan.note, '回家吃饭');
  for (const forbidden of ['raw-password', 'secret-hash', 'SECRET-CODE', 'device-token-secret', 'rtsp://secret', 'camera-secret', 'private/family-a/asset-a.jpg', 'raw-session-token', 'push-secret']) {
    assert.equal(serialized.includes(forbidden), false, forbidden);
  }
});

test('family creator must transfer ownership before deleting an account', () => {
  const data = fixture();
  data.family_members.push({ id: 'member-b', family_id: 'family-a', user_id: 'user-b', role: 'member', status: 'active' });
  const repo = new JsonNativeRepository(data);

  const plan = repo.accountDeletionPlan('user-a');
  assert.equal(plan.can_delete, false);
  assert.equal(plan.blockers[0].code, 'ownership_transfer_required');
  assert.throws(
    () => repo.deleteAccount('user-a', { confirmation: 'DELETE_ACCOUNT' }),
    (error) => error.statusCode === 409,
  );
  assert.equal(data.users.some((user) => user.id === 'user-a'), true);
  assert.equal(data.families.length, 1);
});

test('ordinary member deletion preserves family data and removes authored restricted rows', () => {
  const data = fixture();
  data.family_members[0] = { id: 'member-b', family_id: 'family-a', user_id: 'user-b', role: 'owner', status: 'active' };
  data.family_members.push({ id: 'member-a', family_id: 'family-a', user_id: 'user-a', role: 'member', status: 'active' });
  data.families[0].created_by_user_id = 'user-b';
  data.family_memories.push({ id: 'memory-b', family_id: 'family-a', author_user_id: 'user-b', body: 'Keep' });
  data.family_memory_comments.push({ id: 'comment-a', family_id: 'family-a', memory_id: 'memory-b', author_user_id: 'user-a', body: 'Remove' });
  const repo = new JsonNativeRepository(data);

  const result = repo.deleteAccount('user-a', { confirmation: 'DELETE_ACCOUNT' });
  assert.equal(result.deleted, true);
  assert.deepEqual(result.deleted_family_ids, []);
  assert.equal(data.families.length, 1);
  assert.deepEqual(data.family_memories.map((memory) => memory.id), ['memory-b']);
  assert.equal(data.family_memory_comments.length, 0);
  assert.equal(data.users.some((user) => user.id === 'user-a'), false);
  assert.equal(data.family_members.some((member) => member.user_id === 'user-a'), false);
  assert.deepEqual(result.cleanup_all_asset_ids, ['asset-a']);
});

test('member deletion never cleans media that a retained family memory still references', () => {
  const data = fixture();
  data.family_members[0] = { id: 'member-b', family_id: 'family-a', user_id: 'user-b', role: 'owner', status: 'active' };
  data.family_members.push({ id: 'member-a', family_id: 'family-a', user_id: 'user-a', role: 'member', status: 'active' });
  data.families[0].created_by_user_id = 'user-b';
  data.family_memories.push({ id: 'memory-b', family_id: 'family-a', author_user_id: 'user-b', body: 'Keep' });
  data.family_memory_media.push({ id: 'media-b', family_id: 'family-a', memory_id: 'memory-b', asset_id: 'asset-a' });
  const repo = new JsonNativeRepository(data);

  const result = repo.deleteAccount('user-a', { confirmation: 'DELETE_ACCOUNT' });
  assert.deepEqual(result.cleanup_all_asset_ids, []);
  assert.deepEqual(data.family_memories.map((memory) => memory.id), ['memory-b']);
  assert.deepEqual(data.family_memory_media.map((media) => media.id), ['media-b']);
});

test('sole creator deletion removes the family and returns the physical box to unbound state', () => {
  const data = fixture();
  const repo = new JsonNativeRepository(data);
  const result = repo.deleteAccount('user-a', { confirmation: 'DELETE_ACCOUNT' });

  assert.equal(result.deleted, true);
  assert.deepEqual(result.deleted_family_ids, ['family-a']);
  assert.equal(data.families.length, 0);
  assert.equal(data.cameras['camera-a'], undefined);
  assert.equal(data.events.length, 0);
  assert.equal(data.devices['box-a'].family_id, null);
  assert.deepEqual(result.cleanup_all_asset_ids, ['asset-a']);
  assert.deepEqual(result.cleanup_storage_objects, [{ storage_provider: 'cos', storage_key: 'memory-media/family-a/pending.jpg' }]);
});

test('PostgreSQL deletion plan blocks an owner while another member remains', async () => {
  const pool = {
    async query(text) {
      if (/select id from users/i.test(text)) return { rowCount: 1, rows: [{ id: 'user-a' }] };
      if (/from family_members fm join families/i.test(text)) {
        return { rowCount: 1, rows: [{ family_id: 'family-a', role: 'owner', name: 'A Home', active_member_count: 2 }] };
      }
      if (/count\(\*\).*from family_memories/i.test(text)) return { rowCount: 1, rows: [{ count: 1 }] };
      throw new Error(`unexpected query: ${text}`);
    },
  };
  const repo = new PostgresNativeRepository(pool);
  const plan = await repo.accountDeletionPlan('user-a');
  assert.equal(plan.can_delete, false);
  assert.equal(plan.blockers[0].family_id, 'family-a');
});

test('PostgreSQL account deletion runs in one transaction and returns storage cleanup work', async () => {
  const calls = [];
  const client = {
    async query(text, values = []) {
      calls.push({ text, values });
      if (/select id from users/i.test(text)) return { rowCount: 1, rows: [{ id: 'user-a' }] };
      if (/select id, family_id from family_members/i.test(text)) return { rowCount: 1, rows: [{ id: 'member-a', family_id: 'family-a' }] };
      if (/select id from families/i.test(text)) return { rowCount: 1, rows: [{ id: 'family-a' }] };
      if (/from family_members fm join families/i.test(text)) {
        return { rowCount: 1, rows: [{ family_id: 'family-a', role: 'owner', name: 'A Home', active_member_count: 1 }] };
      }
      if (/count\(\*\).*from family_memories/i.test(text)) return { rowCount: 1, rows: [{ count: 1 }] };
      if (/select device_id from devices/i.test(text)) return { rowCount: 1, rows: [{ device_id: 'box-a' }] };
      if (/select distinct a.id/i.test(text)) return { rowCount: 1, rows: [{ id: 'asset-a' }] };
      if (/select distinct object_key/i.test(text)) return { rowCount: 1, rows: [{ object_key: 'memory-media/pending.jpg' }] };
      return { rowCount: 1, rows: [] };
    },
    release() {},
  };
  const pool = {
    async query(text, values) { return client.query(text, values); },
    async connect() { return client; },
  };
  const repo = new PostgresNativeRepository(pool);
  const result = await repo.deleteAccount('user-a', { confirmation: 'DELETE_ACCOUNT' });

  assert.equal(result.deleted, true);
  assert.deepEqual(result.deleted_family_ids, ['family-a']);
  assert.deepEqual(result.cleanup_all_asset_ids, ['asset-a']);
  assert.deepEqual(result.cleanup_storage_objects, [{ storage_provider: 'cos', storage_key: 'memory-media/pending.jpg' }]);
  assert.equal(calls.some((call) => /^commit$/i.test(call.text)), true);
  assert.equal(calls.some((call) => /delete from users where id = \$1/i.test(call.text)), true);
  assert.equal(calls.some((call) => /delete from device_heartbeats/i.test(call.text)), true);
});

test('HTTP account deletion cleans COS objects and immediately revokes the bearer token', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-account-delete-'));
  const deletedKeys = [];
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'),
    dataDir,
    authMode: 'demo',
    demoOtp: '246810',
    cosStorage: {
      enabled: true,
      async deleteObject({ key }) { deletedKeys.push(key); },
    },
  });
  const baseURL = await listen(app.server);
  try {
    const registrationResponse = await fetch(`${baseURL}/api/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: '13800138999', code: '246810' }),
    });
    const registration = await registrationResponse.json();
    assert.equal(registrationResponse.ok, true, JSON.stringify(registration));
    const userID = String(registration.user.id);
    const authorization = { Authorization: `Bearer ${registration.token}` };
    const familyResponse = await fetch(`${baseURL}/api/families`, {
      method: 'POST',
      headers: { ...authorization, 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Delete Test Home' }),
    });
    const family = await familyResponse.json();
    assert.equal(familyResponse.ok, true, JSON.stringify(family));
    const familyID = String(family.id);

    app.store.db.assets.push({
      id: 'delete-asset', family_id: familyID, storage_provider: 'cos', storage_key: 'memory-media/delete-asset.jpg',
      purpose: 'family_memory', metadata: { purpose: 'family_memory' },
    });
    app.store.db.media_upload_intents.push({
      asset_id: 'pending-delete', family_id: familyID, user_id: userID, object_key: 'memory-media/pending-delete.jpg',
    });
    await app.store.save();

    const planResponse = await fetch(`${baseURL}/api/v2/account/deletion-plan`, { headers: authorization });
    const plan = await planResponse.json();
    assert.equal(plan.can_delete, true);

    const deletionResponse = await fetch(`${baseURL}/api/v2/account`, {
      method: 'DELETE',
      headers: { ...authorization, 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmation: 'DELETE_ACCOUNT' }),
    });
    assert.deepEqual(await deletionResponse.json(), { deleted: true });
    assert.equal(app.store.db.users.some((user) => String(user.id) === userID), false);
    assert.equal(app.store.db.families.some((family) => String(family.id) === familyID), false);
    assert.equal(app.store.db.assets.some((asset) => String(asset.id) === 'delete-asset'), false);
    assert.deepEqual(new Set(deletedKeys), new Set(['memory-media/delete-asset.jpg', 'memory-media/pending-delete.jpg']));

    const revoked = await fetch(`${baseURL}/api/v2/app/bootstrap`, { headers: authorization });
    assert.equal(revoked.status, 401);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
