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

test('JSON repository records message actions idempotently', () => {
  const repo = new JsonNativeRepository(fixture(), { idFactory: () => 'action-1' });
  const input = { action_type: 'shared', idempotency_key: 'share-1', payload: { channel: 'system-share' } };
  const first = repo.recordMessageAction('user-a', 'family-a', 'message-a', input);
  const duplicate = repo.recordMessageAction('user-a', 'family-a', 'message-a', input);
  assert.equal(first.id, duplicate.id);
  assert.equal(repo.db.app_message_actions.length, 1);
  assert.throws(() => repo.recordMessageAction('user-a', 'family-b', 'message-b', input), /family access denied/);
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
