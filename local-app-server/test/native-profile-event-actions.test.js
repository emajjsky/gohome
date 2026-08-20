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

test('native profile writes home coordinates without the legacy snapshot save path', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-native-profile-'));
  const app = createLocalAppServer({ rootDir: path.join(__dirname, '..', '..'), dataDir, authMode: 'demo', demoOtp: '246810' });
  const baseURL = await listen(app.server);
  try {
    const registration = await request(baseURL, '/api/auth/register', {
      method: 'POST', body: JSON.stringify({ phone: '13800138051', code: '246810' }),
    });
    const headers = { Authorization: `Bearer ${registration.body.token}` };
    const family = await request(baseURL, '/api/families', {
      method: 'POST', headers, body: JSON.stringify({ name: 'Native profile' }),
    });
    const familyID = String(family.body.id);
    const saved = await request(baseURL, `/api/v2/families/${familyID}/elders/elder_primary/profile`, {
      method: 'PUT', headers,
      body: JSON.stringify({
        display_name: '妈妈', relationship: '母亲', city: '上海市', district: '徐汇区',
        home_latitude: 31.1883, home_longitude: 121.4365, home_location_label: '家',
      }),
    });
    assert.equal(saved.response.status, 200);
    assert.equal(saved.body.home_latitude, 31.1883);
    const loaded = await request(baseURL, `/api/v2/families/${familyID}/elders/elder_primary/profile`, { headers });
    assert.equal(loaded.response.status, 200);
    assert.equal(loaded.body.home_location_label, '家');
    const home = await request(baseURL, `/api/v2/home?family_id=${familyID}`, { headers });
    assert.equal(home.body.home_location.latitude, 31.1883);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});

test('native event resolution closes the incident and archives its messages', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-native-event-'));
  const app = createLocalAppServer({ rootDir: path.join(__dirname, '..', '..'), dataDir, authMode: 'demo', demoOtp: '246810' });
  const baseURL = await listen(app.server);
  try {
    const registration = await request(baseURL, '/api/auth/register', {
      method: 'POST', body: JSON.stringify({ phone: '13800138052', code: '246810' }),
    });
    const headers = { Authorization: `Bearer ${registration.body.token}` };
    const family = await request(baseURL, '/api/families', {
      method: 'POST', headers, body: JSON.stringify({ name: 'Native events' }),
    });
    const familyID = String(family.body.id);
    app.store.db.events.push(
      {
        id: 'event-primary', family_id: familyID, event_type: 'fall_candidate', level: 'critical',
        summary: '疑似跌倒', acknowledged: false, resolution: '', occurred_at: new Date().toISOString(),
        created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
        payload: { incident: { incident_id: 'incident-1', primary_event_id: 'event-primary', status: 'verifying' } },
      },
      {
        id: 'event-linked', family_id: familyID, event_type: 'fall_candidate', level: 'critical',
        summary: '另一视角', acknowledged: false, resolution: '', occurred_at: new Date().toISOString(),
        created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
        payload: { incident: { incident_id: 'incident-1', primary_event_id: 'event-primary', status: 'verifying' } },
      },
    );
    app.store.db.app_messages.push({
      message_id: 'incident-message', event_id: 'event-primary', family_id: familyID,
      source_event_ids: ['event-primary', 'event-linked'], source: [{ type: 'safety_incident', id: 'incident-1' }], status: 'open',
    });
    const resolved = await request(baseURL, '/api/v2/events/event-primary', {
      method: 'PATCH', headers, body: JSON.stringify({ acknowledged: true, resolution: 'false_positive' }),
    });
    assert.equal(resolved.response.status, 200, JSON.stringify(resolved.body));
    assert.equal(resolved.body.acknowledged, true);
    assert.equal(resolved.body.resolution, 'false_positive');
    assert.equal(app.store.db.events.every((event) => event.acknowledged && event.resolution === 'false_positive'), true);
    assert.equal(app.store.db.app_messages[0].status, 'archived');
    assert.equal(app.store.db.events[0].payload.incident.status, 'rejected');
    const listed = await request(baseURL, `/api/v2/events?family_id=${familyID}`, { headers });
    assert.equal(listed.response.status, 200);
    assert.equal(listed.body.find((event) => event.id === 'event-primary').resolution, 'false_positive');
    const detail = await request(baseURL, '/api/v2/events/event-primary', { headers });
    assert.equal(detail.response.status, 200);
    assert.equal(detail.body.acknowledged, true);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
