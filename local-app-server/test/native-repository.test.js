const assert = require('node:assert/strict');
const test = require('node:test');
const { JsonNativeRepository } = require('../native-api/repository');
const { PostgresNativeRepository } = require('../native-api/postgres-repository');

function fixture() {
  return {
    updated_at: '2026-07-21T08:00:00.000Z',
    users: [
      { id: 'user-a', email: 'a@example.com' },
      { id: 'user-b', email: 'b@example.com' },
    ],
    families: [
      { id: 'family-a', name: 'A' },
      { id: 'family-b', name: 'B' },
    ],
    family_members: [
      { id: 'member-a', family_id: 'family-a', user_id: 'user-a', role: 'creator', status: 'active' },
      { id: 'member-b', family_id: 'family-b', user_id: 'user-b', role: 'creator', status: 'active' },
    ],
    app_messages: [
      { id: 'message-a', message_id: 'message-a', family_id: 'family-a', title: 'A message', created_at: '2026-07-21T08:00:00.000Z' },
      { id: 'message-b', message_id: 'message-b', family_id: 'family-b', title: 'B message', created_at: '2026-07-21T08:00:00.000Z' },
    ],
    product_catalog: [
      { id: 'product-a', category: 'lighting', status: 'active', name: 'A product', verified_at: '2026-07-21T08:00:00.000Z' },
      { id: 'product-draft', category: 'lighting', status: 'draft', name: 'Draft product' },
    ],
    product_preferences: {},
    elder_profiles: {},
    devices: {},
    cameras: {},
    events: [],
    calendar_events: [],
    content_recommendations: [],
    care_cards: [{
      id: 'card-a',
      family_id: 'family-a',
      card_date: '2026-07-21',
      content_recommendations: [{
        type: 'search_result',
        module: 'local_hotspots',
        title: '社区公园本周开放夜游',
        summary: '官方发布的本周活动安排。',
        source: 'city.example.com',
        url: 'https://city.example.com/night',
        image_url: 'https://city.example.com/night.jpg',
      }],
    }],
  };
}

test('JSON repository isolates every native read and write by family membership', () => {
  const repo = new JsonNativeRepository(fixture(), {
    idFactory: () => 'action-1',
    clock: () => '2026-07-21T09:00:00.000Z',
  });

  assert.deepEqual(repo.bootstrapForUser('user-a').families.map((family) => family.id), ['family-a']);
  assert.deepEqual(repo.messagesForFamily('user-a', 'family-a').map((message) => message.family_id), ['family-a']);
  assert.deepEqual(repo.productsForFamily('user-a', 'family-a').map((product) => product.id), ['product-a']);
  assert.throws(() => repo.messagesForFamily('user-a', 'family-b'), /family access denied/);
  assert.throws(() => repo.productsForFamily('user-a', 'family-b'), /family access denied/);
  assert.throws(() => repo.productPreferences('user-a', 'family-b'), /family access denied/);
  assert.equal(repo.homeForFamily('user-a', 'family-a').articles[0].title, '社区公园本周开放夜游');
});

test('JSON family membership enforces creator boundaries and supports transfer then leave', () => {
  const data = fixture();
  data.family_members.push({
    id: 'member-a-2', family_id: 'family-a', user_id: 'user-b', role: 'member', status: 'active', joined_at: '2026-07-22T08:00:00.000Z',
  });
  data.families[0].created_by_user_id = 'user-a';
  const repo = new JsonNativeRepository(data, { clock: () => '2026-07-27T09:00:00.000Z' });

  const members = repo.familyMembers('user-a', 'family-a');
  assert.deepEqual(members.map((member) => [member.id, member.role, member.is_current_user]), [
    ['member-a', 'creator', true],
    ['member-a-2', 'member', false],
  ]);
  assert.throws(() => repo.removeFamilyMember('user-b', 'family-a', 'member-a'), /management permission/);
  assert.throws(() => repo.removeFamilyMember('user-a', 'family-a', 'member-a'), /cannot remove self/);
  assert.throws(() => repo.leaveFamily('user-a', 'family-a'), /transfer family ownership/);

  data.family_members.push({
    id: 'member-a-legacy-owner', family_id: 'family-a', user_id: 'user-c', role: 'owner', status: 'active',
  });
  const transfer = repo.transferFamilyOwnership('user-a', 'family-a', 'member-a-2', { confirmation: 'TRANSFER_OWNERSHIP' });
  assert.equal(transfer.new_owner_user_id, 'user-b');
  assert.equal(data.family_members.find((member) => member.id === 'member-a').role, 'member');
  assert.equal(data.family_members.find((member) => member.id === 'member-a-2').role, 'owner');
  assert.equal(data.family_members.filter((member) => member.family_id === 'family-a' && ['owner', 'creator'].includes(member.role)).length, 1);
  assert.equal(data.families[0].created_by_user_id, 'user-b');

  assert.deepEqual(repo.leaveFamily('user-a', 'family-a'), { left: true, family_id: 'family-a' });
  assert.equal(data.family_members.find((member) => member.id === 'member-a').status, 'left');
});

test('JSON creator can remove an ordinary member without deleting the account', () => {
  const data = fixture();
  data.family_members.push({ id: 'member-a-2', family_id: 'family-a', user_id: 'user-b', role: 'member', status: 'active' });
  const repo = new JsonNativeRepository(data);
  assert.equal(repo.removeFamilyMember('user-a', 'family-a', 'member-a-2').removed, true);
  assert.equal(data.family_members.find((member) => member.id === 'member-a-2').status, 'removed');
  assert.equal(data.users.some((user) => user.id === 'user-b'), true);
});

test('PostgreSQL ownership transfer locks the family and active memberships in one transaction', async () => {
  const calls = [];
  const client = {
    async query(text, values = []) {
      calls.push({ text, values });
      if (/select id from families/i.test(text)) return { rowCount: 1, rows: [{ id: 'family-a' }] };
      if (/select \* from family_members/i.test(text)) return { rowCount: 3, rows: [
        { id: 'member-a', family_id: 'family-a', user_id: 'user-a', role: 'owner', status: 'active' },
        { id: 'member-a-2', family_id: 'family-a', user_id: 'user-b', role: 'member', status: 'active' },
        { id: 'member-a-legacy-owner', family_id: 'family-a', user_id: 'user-c', role: 'creator', status: 'active' },
      ] };
      if (/update family_members set role = 'member'/i.test(text)) return { rowCount: 2, rows: [
        { id: 'member-a', family_id: 'family-a', user_id: 'user-a', role: 'member', status: 'active' },
        { id: 'member-a-legacy-owner', family_id: 'family-a', user_id: 'user-c', role: 'member', status: 'active' },
      ] };
      if (/update family_members set role = 'owner'/i.test(text)) return { rowCount: 1, rows: [{ id: 'member-a-2', family_id: 'family-a', user_id: 'user-b', role: 'owner', status: 'active' }] };
      return { rowCount: 1, rows: [] };
    },
    release() {},
  };
  const changes = [];
  const repo = new PostgresNativeRepository({ connect: async () => client, query: (...args) => client.query(...args) }, {
    onFamilyMembershipChange: (change) => changes.push(change),
  });
  const result = await repo.transferFamilyOwnership('user-a', 'family-a', 'member-a-2', { confirmation: 'TRANSFER_OWNERSHIP' });

  assert.equal(result.new_owner_user_id, 'user-b');
  assert.equal(calls.some((call) => /families.*for update/i.test(call.text)), true);
  assert.equal(calls.some((call) => /family_members.*order by id for update/i.test(call.text)), true);
  assert.equal(calls.some((call) => /id <> \$2.*role in \('owner', 'creator'\)/is.test(call.text)), true);
  assert.equal(calls.some((call) => /^commit$/i.test(call.text)), true);
  assert.equal(changes[0].created_by_user_id, 'user-b');
  assert.deepEqual(changes[0].memberships.map((member) => member.role), ['member', 'member', 'owner']);
});

test('JSON onboarding remains complete after the last camera is deleted', () => {
  const data = fixture();
  data.elder_profiles['profile-a'] = { id: 'profile-a', family_id: 'family-a' };
  data.devices['device-a'] = { id: 'device-a', family_id: 'family-a', status: 'online' };
  data.cameras['camera-a'] = { id: 'camera-a', family_id: 'family-a', status: 'online' };
  const repo = new JsonNativeRepository(data, { clock: () => '2026-07-25T09:00:00.000Z' });

  assert.deepEqual(repo.onboardingForFamily('user-a', 'family-a'), { next_step: 'complete', complete: true });
  assert.equal(data.families[0].metadata.onboarding_completed_at, '2026-07-25T09:00:00.000Z');

  delete data.cameras['camera-a'];
  assert.deepEqual(repo.onboardingForFamily('user-a', 'family-a'), { next_step: 'complete', complete: true });
});

test('JSON onboarding still requires a first camera for a genuinely new family', () => {
  const data = fixture();
  data.elder_profiles['profile-a'] = { id: 'profile-a', family_id: 'family-a' };
  data.devices['device-a'] = { id: 'device-a', family_id: 'family-a', status: 'online' };
  const repo = new JsonNativeRepository(data);

  assert.deepEqual(repo.onboardingForFamily('user-a', 'family-a'), { next_step: 'camera', complete: false });
  assert.equal(data.families[0].metadata, undefined);
});

test('JSON onboarding backfills completion from retained event history', () => {
  const data = fixture();
  data.elder_profiles['profile-a'] = { id: 'profile-a', family_id: 'family-a' };
  data.events.push({ id: 'event-a', family_id: 'family-a', camera_id: null });
  const repo = new JsonNativeRepository(data, { clock: () => '2026-07-25T09:00:00.000Z' });

  assert.deepEqual(repo.onboardingForFamily('user-a', 'family-a'), { next_step: 'complete', complete: true });
  assert.equal(data.families[0].metadata.onboarding_completed_at, '2026-07-25T09:00:00.000Z');
});

test('PostgreSQL onboarding backfills an established family after its box is unbound', async () => {
  let metadataChange = null;
  const pool = {
    async query(text, values) {
      if (/from family_members/i.test(text)) return { rowCount: 1, rows: [{ role: 'owner' }] };
      if (/update families/i.test(text)) return { rowCount: 1, rows: [] };
      return {
        rowCount: 1,
        rows: [{
          onboarding_completed_at: '',
          has_profile: true,
          has_device: false,
          has_camera: false,
          has_camera_history: true,
        }],
      };
    },
  };
  const repo = new PostgresNativeRepository(pool, {
    clock: () => new Date('2026-07-25T09:00:00.000Z'),
    onFamilyMetadataChange: (familyId, metadata) => { metadataChange = { familyId, metadata }; },
  });

  assert.deepEqual(await repo.onboardingForFamily('user-a', 'family-a'), { next_step: 'complete', complete: true });
  assert.deepEqual(metadataChange, {
    familyId: 'family-a',
    metadata: { onboarding_completed_at: '2026-07-25T09:00:00.000Z' },
  });
});

test('JSON repository records message actions idempotently', () => {
  const repo = new JsonNativeRepository(fixture(), { idFactory: () => 'action-1' });
  const input = { action_type: 'shared', idempotency_key: 'share-1', payload: { channel: 'system-share' } };
  const first = repo.recordMessageAction('user-a', 'family-a', 'message-a', input);
  const duplicate = repo.recordMessageAction('user-a', 'family-a', 'message-a', input);
  assert.equal(first.id, duplicate.id);
  assert.equal(repo.db.app_message_actions.length, 1);
  assert.throws(() => repo.recordMessageAction('user-a', 'family-b', 'message-b', input), /family access denied/);
});

test('JSON repository prefers actionable return-home copy over a newer daily care card', () => {
  const repo = new JsonNativeRepository(fixture());
  repo.db.app_messages.push(
    {
      message_id: 'return-home-a', family_id: 'family-a', message_type: 'return_home', status: 'open',
      created_at: '2026-07-22T08:00:00.000Z', metadata: { topics: ['周末安排'] },
    },
    {
      message_id: 'daily-care-a', family_id: 'family-a', message_type: 'care_card', status: 'open',
      created_at: '2026-07-23T08:00:00.000Z', metadata: {},
    },
  );

  assert.equal(repo.homeForFamily('user-a', 'family-a').care_message.message_id, 'return-home-a');
});

test('JSON repository keeps product preferences family-scoped and returns copies', () => {
  const repo = new JsonNativeRepository(fixture());
  const saved = repo.updateProductPreferences('user-a', 'family-a', {
    categories: ['lighting', 'lighting', ''],
    needs: ['visibility'],
  });
  assert.deepEqual(saved.categories, ['lighting']);
  assert.deepEqual(repo.productPreferences('user-a', 'family-a').needs, ['visibility']);
  saved.categories.push('mutated');
  assert.deepEqual(repo.productPreferences('user-a', 'family-a').categories, ['lighting']);
  assert.throws(() => repo.updateProductPreferences('user-a', 'family-b', {}), /family access denied/);
});

test('JSON activity deletion is creator-only and retention follows family settings', () => {
  const data = fixture();
  data.family_members.push({ id: 'member-a-2', family_id: 'family-a', user_id: 'user-b', role: 'member', status: 'active' });
  data.care_preferences = { 'family-a': { metadata: { activity_history: { retention_days: 7 } } } };
  data.activity_intervals = [
    { id: 'old', family_id: 'family-a', started_at: '2026-07-01T01:00:00.000Z', ended_at: '2026-07-01T01:10:00.000Z' },
    { id: 'fresh', family_id: 'family-a', started_at: '2026-07-24T01:00:00.000Z', ended_at: '2026-07-24T01:10:00.000Z' },
  ];
  const repo = new JsonNativeRepository(data, { clock: () => '2026-07-25T01:00:00.000Z' });
  assert.throws(() => repo.deleteActivityHistory('user-b', 'family-a'), /management permission/);
  assert.deepEqual(repo.cleanupExpiredActivityIntervals(), { deleted: 1 });
  assert.deepEqual(repo.db.activity_intervals.map((item) => item.id), ['fresh']);
  assert.deepEqual(repo.deleteActivityHistory('user-a', 'family-a'), { deleted: 1 });
});

test('JSON memory writes reject cross-family assets without leaving partial records', () => {
  const data = fixture();
  data.assets = [{ id: 10, family_id: 'family-b' }];
  const repo = new JsonNativeRepository(data, { idFactory: () => 'memory-1' });

  assert.throws(
    () => repo.createMemory('user-a', 'family-a', { body: '家庭记忆', asset_ids: ['10'] }),
    /memory asset not found/,
  );
  assert.deepEqual(repo.db.family_memories, []);
});

test('PostgreSQL repository stops a denied family read before querying messages', async () => {
  const calls = [];
  const pool = {
    async query(text, values) {
      calls.push({ text, values });
      return { rowCount: 0, rows: [] };
    },
  };
  const repo = new PostgresNativeRepository(pool);

  await assert.rejects(
    repo.messagesForFamily('user-a', 'family-b'),
    /family access denied/,
  );
  assert.equal(calls.length, 1);
  assert.match(calls[0].text, /from family_members/i);
  assert.deepEqual(calls[0].values, ['family-b', 'user-a']);
});

test('PostgreSQL preference update authorizes and writes in one parameterized statement', async () => {
  const calls = [];
  const pool = {
    async query(text, values) {
      calls.push({ text, values });
      return {
        rowCount: 1,
        rows: [{ family_id: values[0], categories: ['lighting'], needs: ['visibility'] }],
      };
    },
  };
  const repo = new PostgresNativeRepository(pool);
  const result = await repo.updateProductPreferences('user-a', 'family-a', {
    categories: ['lighting'],
    needs: ['visibility'],
  });

  assert.equal(calls.length, 1);
  assert.match(calls[0].text, /insert into product_preferences/i);
  assert.match(calls[0].text, /from family_members/i);
  assert.match(calls[0].text, /family_id = \$1 and user_id = \$4/i);
  assert.deepEqual(calls[0].values, [
    'family-a',
    '["lighting"]',
    '["visibility"]',
    'user-a',
  ]);
  assert.equal(result.family_id, 'family-a');
});

test('PostgreSQL onboarding persists completion and does not depend on current cameras afterward', async () => {
  const calls = [];
  const metadataChanges = [];
  let completedAt = '';
  let hasCamera = true;
  const pool = {
    async query(text, values) {
      calls.push({ text, values });
      if (/from family_members/i.test(text)) return { rowCount: 1, rows: [{ role: 'owner' }] };
      if (/update families/i.test(text)) {
        completedAt = values[1];
        return { rowCount: 1, rows: [] };
      }
      return {
        rowCount: 1,
        rows: [{
          onboarding_completed_at: completedAt,
          has_profile: true,
          has_device: true,
          has_camera: hasCamera,
          has_camera_history: false,
        }],
      };
    },
  };
  const repo = new PostgresNativeRepository(pool, {
    clock: () => new Date('2026-07-25T09:00:00.000Z'),
    onFamilyMetadataChange: (familyId, metadata) => metadataChanges.push({ familyId, metadata }),
  });

  assert.deepEqual(await repo.onboardingForFamily('user-a', 'family-a'), { next_step: 'complete', complete: true });
  assert.equal(completedAt, '2026-07-25T09:00:00.000Z');
  assert.deepEqual(metadataChanges, [{
    familyId: 'family-a',
    metadata: { onboarding_completed_at: '2026-07-25T09:00:00.000Z' },
  }]);
  hasCamera = false;
  assert.deepEqual(await repo.onboardingForFamily('user-a', 'family-a'), { next_step: 'complete', complete: true });
  assert.equal(calls.filter((call) => /update families/i.test(call.text)).length, 1);
});
