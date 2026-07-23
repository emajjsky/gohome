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

test('device activity intervals are idempotent, family scoped, and factual', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-native-activity-'));
  const clock = () => '2026-07-23T10:30:00.000Z';
  const app = createLocalAppServer({ rootDir: path.join(__dirname, '..', '..'), dataDir, authMode: 'demo', demoOtp: '246810' });
  app.nativeRepository.clock = clock;
  const baseURL = await listen(app.server);
  try {
    const registered = await request(baseURL, '/api/auth/register', {
      method: 'POST', body: JSON.stringify({ phone: '13800138019', code: '246810', display_name: '轨迹测试' }),
    });
    const authorization = { Authorization: `Bearer ${registered.body.token}` };
    const family = await request(baseURL, '/api/families', {
      method: 'POST', headers: authorization, body: JSON.stringify({ name: '轨迹家庭' }),
    });
    const familyID = String(family.body.id);
    app.store.db.devices['edge-activity-test'] = { id: 'edge-activity-test', device_id: 'edge-activity-test', family_id: familyID };

    const interval = {
      source_interval_id: 'camera-2-presence-20260723-001',
      camera_id: '2',
      room: '客厅',
      started_at: '2026-07-23T09:00:00+08:00',
      ended_at: '2026-07-23T09:08:00+08:00',
      person_count_max: 1,
      postures: ['standing', 'sitting'],
      confidence: 0.88,
    };
    const uploaded = await request(baseURL, '/api/v1/device/activity-intervals', {
      method: 'POST', headers: { Authorization: `Bearer ${app.deviceToken}` },
      body: JSON.stringify({ device_id: 'edge-activity-test', intervals: [interval] }),
    });
    assert.equal(uploaded.response.status, 200);
    assert.deepEqual({ accepted: uploaded.body.accepted, inserted: uploaded.body.inserted }, { accepted: 1, inserted: 1 });

    const repeated = await request(baseURL, '/api/v1/device/activity-intervals', {
      method: 'POST', headers: { Authorization: `Bearer ${app.deviceToken}` },
      body: JSON.stringify({ device_id: 'edge-activity-test', intervals: [interval] }),
    });
    assert.equal(repeated.body.inserted, 0);

    const timeline = await request(baseURL, `/api/v2/activity-timeline?family_id=${familyID}&date=2026-07-23`, { headers: authorization });
    assert.equal(timeline.response.status, 200);
    assert.equal(timeline.body.intervals.length, 1);
    assert.deepEqual(timeline.body.intervals[0].postures, ['standing', 'sitting']);
    assert.equal(JSON.stringify(timeline.body).includes('吃饭'), false);
    assert.ok(timeline.response.headers.get('etag'));

    const invalid = await request(baseURL, '/api/v1/device/activity-intervals', {
      method: 'POST', headers: { Authorization: `Bearer ${app.deviceToken}` },
      body: JSON.stringify({ device_id: 'edge-activity-test', intervals: [{ ...interval, source_interval_id: 'bad', ended_at: interval.started_at }] }),
    });
    assert.equal(invalid.response.status, 400);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
