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

function dateKey(date) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(date);
}

function dayOffset(offset) {
  return dateKey(new Date(Date.now() + offset * 24 * 60 * 60 * 1000));
}

function interval(familyID, date, minutes, index) {
  const start = Date.parse(`${date}T09:00:00+08:00`);
  return {
    id: `activity-${index}`,
    family_id: familyID,
    device_id: 'edge-test',
    camera_id: '2',
    source_interval_id: `source-${index}`,
    room: '客厅',
    started_at: new Date(start).toISOString(),
    ended_at: new Date(start + minutes * 60000).toISOString(),
    person_count_max: 1,
    postures: ['standing'],
    confidence: 0.9,
    metadata: {},
  };
}

test('scheduler turns a conservative activity insight into one editable care message', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-activity-insight-'));
  const evaluationAt = new Date(`${dayOffset(0)}T20:30:00+08:00`);
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'),
    dataDir,
    authMode: 'demo',
    demoOtp: '246810',
    activityEvaluationNow: () => evaluationAt,
  });
  const baseURL = await listen(app.server);
  try {
    const registered = await request(baseURL, '/api/auth/register', {
      method: 'POST', body: JSON.stringify({ phone: '13800138029', code: '246810' }),
    });
    const authorization = { Authorization: `Bearer ${registered.body.token}` };
    const family = await request(baseURL, '/api/families', {
      method: 'POST', headers: authorization, body: JSON.stringify({ name: '活动洞察家庭' }),
    });
    const familyID = String(family.body.id);
    app.store.db.care_preferences[familyID] = {
      family_id: familyID,
      metadata: {
        activity_history: { tracking_enabled: true, anomaly_reminders_enabled: false, retention_days: 30 },
        care_card_schedule: {
          enabled: true,
          content_types: { visit_reminder: false },
          visit_reminder: { enabled: false },
          delivery_rules: {
            daily_digest: { enabled: false },
            home_status: { enabled: true, exception_push_enabled: true },
            visit_reminder: { enabled: false },
          },
        },
      },
    };
    app.store.db.activity_intervals.push(
      interval(familyID, dayOffset(-3), 60, 1),
      interval(familyID, dayOffset(-2), 60, 2),
      interval(familyID, dayOffset(-1), 60, 3),
      interval(familyID, dayOffset(0), 10, 4),
    );

    const disabled = await request(baseURL, '/api/v1/internal/scheduler/run', {
      method: 'POST', body: JSON.stringify({ family_id: familyID, job_type: 'activity-insight-disabled-test' }),
    });
    assert.equal(disabled.body.result.activity_insight_messages_created, 0);
    app.store.db.care_preferences[familyID].metadata.activity_history.anomaly_reminders_enabled = true;
    app.store.db.care_preferences[familyID].metadata.care_card_schedule.enabled = false;

    const first = await request(baseURL, '/api/v1/internal/scheduler/run', {
      method: 'POST', body: JSON.stringify({ family_id: familyID, job_type: 'activity-insight-test' }),
    });
    const repeated = await request(baseURL, '/api/v1/internal/scheduler/run', {
      method: 'POST', body: JSON.stringify({ family_id: familyID, job_type: 'activity-insight-test-repeat' }),
    });
    assert.equal(first.body.result.activity_insight_messages_created, 1);
    assert.equal(first.body.result.care_cards_generated, 0);
    assert.equal(repeated.body.result.activity_insight_messages_created, 0);

    const home = await request(baseURL, `/api/v2/home?family_id=${familyID}`, { headers: authorization });
    assert.equal(home.body.care_message.message_type, 'activity_insight');
    assert.equal(home.body.care_message.metadata.trigger_reason, 'activity_reduced');
    assert.equal(home.body.care_message.metadata.message_variants.length, 1);
    assert.equal(home.body.care_message.body.includes('不代表身体异常'), true);
    assert.equal(app.store.db.notification_deliveries.filter((item) => item.message_id === home.body.care_message.message_id).length, 1);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
