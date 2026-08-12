const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { createLocalAppServer } = require('../server');

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => resolve(`http://127.0.0.1:${server.address().port}`));
  });
}

async function request(baseURL, pathname, options = {}) {
  const response = await fetch(`${baseURL}${pathname}`, {
    ...options,
    headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) },
  });
  const text = await response.text();
  return { response, body: text ? JSON.parse(text) : null };
}

test('daily care uses one factual message without suppressing its scheduled delivery', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-care-flow-'));
  const previousModelCalls = process.env.GOHOME_CARE_MODEL_CALLS;
  process.env.GOHOME_CARE_MODEL_CALLS = '0';
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'), dataDir, authMode: 'demo', demoOtp: '246810',
  });
  const baseURL = await listen(app.server);
  try {
    const registered = await request(baseURL, '/api/auth/register', {
      method: 'POST', body: JSON.stringify({ phone: '13800138039', code: '246810' }),
    });
    const headers = { Authorization: `Bearer ${registered.body.token}` };
    const family = await request(baseURL, '/api/families', {
      method: 'POST', headers, body: JSON.stringify({ name: '关怀事实家庭' }),
    });
    const familyID = String(family.body.id);
    const preferences = await request(baseURL, `/api/v1/families/${familyID}/care-preferences`, { headers });
    app.store.db.care_preferences[familyID] = preferences.body;
    app.store.db.care_preferences[familyID].metadata.care_card_schedule.content_types = {
      home_status: false, elder_interest_topics: false, local_hotspots: false, health_tips: false,
      anti_fraud: false, culture_entertainment: false, weather: false, holidays: false,
      anniversaries: false, visit_reminder: true,
    };
    app.store.db.care_preferences[familyID].metadata.care_card_schedule.delivery_rules.weather.enabled = false;

    const noSignal = await request(baseURL, '/api/v1/internal/care-cards/generate', {
      method: 'POST', headers, body: JSON.stringify({ family_id: familyID, force: true }),
    });
    assert.equal(noSignal.body.card.status, 'pending');
    assert.equal(app.store.db.app_messages.some((item) => item.message_type === 'care_card'), false);
    app.store.db.care_cards.push({
      id: 'old-care-card', card_id: 'old-care-card', family_id: Number(familyID), elder_id: 'elder_primary',
      card_date: '2026-08-11', card_type: 'daily', title: '昨天的天气', body: '昨天的具体内容', facts: [],
      status: 'open', created_at: '2026-08-11T00:00:00.000Z', updated_at: '2026-08-11T00:00:00.000Z',
    });
    const stillPending = await request(baseURL, `/api/v1/app/care-cards/today?family_id=${familyID}`, { headers });
    assert.equal(stillPending.body.status, 'pending');
    assert.equal(stillPending.body.title, '');

    app.store.db.home_return_plans.push({
      id: 'plan-care-flow', family_id: Number(familyID), user_id: registered.body.user.id,
      starts_at: '2026-08-20T10:00:00.000Z', note: '', status: 'planned',
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
    });

    const pending = await request(baseURL, `/api/v1/app/care-cards/today?family_id=${familyID}`, { headers });
    assert.equal(pending.body.status, 'pending');
    assert.equal(pending.body.title, '');
    assert.equal(pending.body.body, '');

    const generated = await request(baseURL, '/api/v1/internal/care-cards/generate', {
      method: 'POST', headers, body: JSON.stringify({ family_id: familyID, force: true }),
    });
    const card = generated.body.card;
    assert.equal(card.title, '回家计划已经定下来了');
    const message = app.store.db.app_messages.find((item) => item.care_card_id === card.card_id);
    assert.ok(message);
    assert.equal(app.store.db.notification_deliveries.some((item) => item.message_id === message.message_id), false);

    const scheduler = await request(baseURL, '/api/v1/internal/scheduler/run', {
      method: 'POST', body: JSON.stringify({ family_id: familyID }),
    });
    assert.equal(scheduler.response.status, 200);
    assert.equal(app.store.db.notification_deliveries.some((item) => item.message_id === message.message_id), true);

    const home = await request(baseURL, `/api/v2/home?family_id=${familyID}`, { headers });
    assert.equal(home.body.care_message.care_card_id, card.card_id);
    assert.equal(home.body.care_message.title, card.title);
    assert.equal(home.body.care_message.body, card.body);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    if (previousModelCalls === undefined) delete process.env.GOHOME_CARE_MODEL_CALLS;
    else process.env.GOHOME_CARE_MODEL_CALLS = previousModelCalls;
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});

test('daily care uses interests only after the user explicitly saves them', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-care-interests-'));
  const previousModelCalls = process.env.GOHOME_CARE_MODEL_CALLS;
  process.env.GOHOME_CARE_MODEL_CALLS = '0';
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'), dataDir, authMode: 'demo', demoOtp: '246810',
  });
  const baseURL = await listen(app.server);
  try {
    const registered = await request(baseURL, '/api/auth/register', {
      method: 'POST', body: JSON.stringify({ phone: '13800138040', code: '246810' }),
    });
    const headers = { Authorization: `Bearer ${registered.body.token}` };
    const family = await request(baseURL, '/api/families', {
      method: 'POST', headers, body: JSON.stringify({ name: '明确兴趣家庭' }),
    });
    const familyID = String(family.body.id);
    const initial = await request(baseURL, `/api/v1/families/${familyID}/care-preferences`, { headers });
    assert.deepEqual(initial.body.interests, []);
    assert.equal(Boolean(initial.body.metadata.interests_configured), false);

    app.store.db.care_preferences[familyID] = initial.body;
    app.store.db.care_preferences[familyID].interests = ['天气', '养生', '家常', '戏曲'];
    app.store.db.care_preferences[familyID].content_sources_enabled = false;
    app.store.db.care_preferences[familyID].content_recommendations_enabled = false;
    app.store.db.care_preferences[familyID].metadata.care_card_schedule.content_types = {
      home_status: false, elder_interest_topics: true, local_hotspots: false, health_tips: false,
      anti_fraud: false, culture_entertainment: false, weather: false, holidays: false,
      anniversaries: false, visit_reminder: false,
    };

    const legacy = await request(baseURL, '/api/v1/internal/care-cards/generate', {
      method: 'POST', headers, body: JSON.stringify({ family_id: familyID, force: true }),
    });
    assert.equal(legacy.body.card.status, 'pending', JSON.stringify(legacy.body.card));
    assert.equal(app.store.db.app_messages.some((item) => item.message_type === 'care_card'), false);

    const saved = await request(baseURL, `/api/v1/families/${familyID}/care-preferences`, {
      method: 'PUT', headers, body: JSON.stringify({ interests: ['戏曲', '家常'] }),
    });
    assert.deepEqual(saved.body.interests, ['戏曲', '家常']);
    assert.equal(saved.body.metadata.interests_configured, true);

    const configured = await request(baseURL, '/api/v1/internal/care-cards/generate', {
      method: 'POST', headers, body: JSON.stringify({ family_id: familyID, force: true }),
    });
    assert.equal(configured.body.card.title, '戏曲，刚好可以当开场');
    assert.equal(configured.body.card.metadata.primary_signal.type, 'interest_topic');

    const persisted = await request(baseURL, `/api/v1/families/${familyID}/care-preferences`, { headers });
    assert.equal(persisted.body.metadata.interests_configured, true);
    const persistedDb = JSON.parse(fs.readFileSync(path.join(dataDir, 'db.json'), 'utf8'));
    assert.equal(persistedDb.care_preferences[familyID].metadata.interests_configured, true);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    if (previousModelCalls === undefined) delete process.env.GOHOME_CARE_MODEL_CALLS;
    else process.env.GOHOME_CARE_MODEL_CALLS = previousModelCalls;
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
