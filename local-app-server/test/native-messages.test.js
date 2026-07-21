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

async function requestJson(baseUrl, pathname, options = {}) {
  const response = await fetch(`${baseUrl}${pathname}`, {
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  return { response, body: text ? JSON.parse(text) : null };
}

test('native return-home messages support idempotent actions without claiming WeChat delivery', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-native-messages-'));
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'),
    dataDir,
    authMode: 'demo',
    demoOtp: '246810',
  });
  const baseUrl = await listen(app.server);
  try {
    const registered = await requestJson(baseUrl, '/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ phone: '13800138002', code: '246810' }),
    });
    assert.equal(registered.response.status, 200);
    const authorization = { Authorization: `Bearer ${registered.body.token}` };
    const familyResult = await requestJson(baseUrl, '/api/families', {
      method: 'POST',
      headers: authorization,
      body: JSON.stringify({ name: 'Message family' }),
    });
    const familyId = String(familyResult.body.id);
    app.store.db.care_preferences[familyId] = {
      family_id: familyId,
      metadata: {
        care_card_schedule: {
          enabled: true,
          content_types: { visit_reminder: true },
          interest_topics: ['本地生活', '戏曲'],
          visit_reminder: { enabled: true, threshold_days: 14, last_visit_at: '2026-06-01', next_visit_at: '2026-08-01' },
          delivery_rules: {
            daily_digest: { enabled: false, mode: 'daily_digest' },
            home_status: { enabled: false, exception_push_enabled: false },
            visit_reminder: { enabled: true, mode: 'threshold', threshold_days: 14 },
          },
        },
      },
    };
    const scheduler = await requestJson(baseUrl, '/api/v1/internal/scheduler/run', {
      method: 'POST',
      body: JSON.stringify({ family_id: familyId, force: false, job_type: 'native-message-test' }),
    });
    assert.equal(scheduler.response.status, 200);
    assert.equal(scheduler.body.result.return_home_messages_created, 1);
    const messageId = `return-home-${familyId}-2026-06-01-14`;

    const list = await requestJson(baseUrl, `/api/v2/messages?family_id=${familyId}`, { headers: authorization });
    assert.equal(list.response.status, 200);
    assert.equal(list.body.messages.length, 1);
    assert.ok(list.body.messages[0].metadata.topics.length >= 2);
    assert.ok(list.body.messages[0].metadata.topics.length <= 3);
    assert.ok(list.body.messages[0].metadata.topics.every((topic) => typeof topic === 'string' && topic.trim()));
    assert.equal(list.body.messages[0].metadata.message_variants.length, 2);

    const detail = await requestJson(baseUrl, `/api/v2/messages/${messageId}?family_id=${familyId}`, { headers: authorization });
    assert.equal(detail.response.status, 200);
    assert.equal(detail.body.message.metadata.trigger_reason, 'days_since_last_visit');

    const shareOptions = {
      method: 'POST',
      headers: { ...authorization, 'Idempotency-Key': 'share-return-home-1' },
      body: JSON.stringify({ action_type: 'shared', payload: { channel: 'system-share' } }),
    };
    const firstShare = await requestJson(baseUrl, `/api/v2/messages/${messageId}/actions?family_id=${familyId}`, shareOptions);
    const repeatedShare = await requestJson(baseUrl, `/api/v2/messages/${messageId}/actions?family_id=${familyId}`, shareOptions);
    assert.equal(firstShare.response.status, 200);
    assert.equal(firstShare.body.action.id, repeatedShare.body.action.id);
    assert.equal(firstShare.body.action.payload.channel, 'system-share');
    assert.equal('wechat_delivered' in firstShare.body.action.payload, false);

    const invalidSnooze = await requestJson(baseUrl, `/api/v2/messages/${messageId}/actions?family_id=${familyId}`, {
      method: 'POST',
      headers: { ...authorization, 'Idempotency-Key': 'past-snooze' },
      body: JSON.stringify({ action_type: 'snoozed', payload: { snoozed_until: '2020-01-01T00:00:00.000Z' } }),
    });
    assert.equal(invalidSnooze.response.status, 400);

    const returnedHome = await requestJson(baseUrl, `/api/v2/messages/${messageId}/actions?family_id=${familyId}`, {
      method: 'POST',
      headers: { ...authorization, 'Idempotency-Key': 'returned-home-1' },
      body: JSON.stringify({ action_type: 'returned_home' }),
    });
    assert.equal(returnedHome.response.status, 200);
    assert.equal(returnedHome.body.message.status, 'closed');
    assert.match(
      app.store.db.care_preferences[familyId].metadata.care_card_schedule.visit_reminder.last_visit_at,
      /^\d{4}-\d{2}-\d{2}$/,
    );
    assert.equal(app.store.db.care_preferences[familyId].metadata.care_card_schedule.visit_reminder.next_visit_at, '');
    assert.equal(app.store.db.app_message_actions.length, 2);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
