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

    const overview = await request(baseURL, `/api/v2/activity-overview?family_id=${familyID}&date=2026-07-23`, { headers: authorization });
    assert.equal(overview.response.status, 200);
    assert.equal(overview.body.today.active_minutes, 8);
    assert.equal(overview.body.today.rooms[0].room, '客厅');
    assert.equal(overview.body.seven_day_trend.length, 7);
    assert.equal(JSON.stringify(overview.body).includes('吃饭'), false);

    const crossingMidnight = {
      ...interval,
      source_interval_id: 'camera-2-presence-20260721-crossing-midnight',
      started_at: '2026-07-21T23:50:00+08:00',
      ended_at: '2026-07-22T00:20:00+08:00',
    };
    const crossingUpload = await request(baseURL, '/api/v1/device/activity-intervals', {
      method: 'POST', headers: { Authorization: `Bearer ${app.deviceToken}` },
      body: JSON.stringify({ device_id: 'edge-activity-test', intervals: [crossingMidnight] }),
    });
    assert.equal(crossingUpload.response.status, 200, JSON.stringify(crossingUpload.body));
    assert.equal(crossingUpload.body.inserted, 1);

    const previousDay = await request(baseURL, `/api/v2/activity-timeline?family_id=${familyID}&date=2026-07-21`, { headers: authorization });
    const nextDay = await request(baseURL, `/api/v2/activity-timeline?family_id=${familyID}&date=2026-07-22`, { headers: authorization });
    assert.equal(Date.parse(previousDay.body.intervals[0].ended_at) - Date.parse(previousDay.body.intervals[0].started_at), 10 * 60 * 1000);
    assert.equal(Date.parse(nextDay.body.intervals[0].ended_at) - Date.parse(nextDay.body.intervals[0].started_at), 20 * 60 * 1000);

    const nextDayOverview = await request(baseURL, `/api/v2/activity-overview?family_id=${familyID}&date=2026-07-22`, { headers: authorization });
    assert.equal(nextDayOverview.body.today.active_minutes, 20);

    const preferences = await request(baseURL, `/api/v1/families/${familyID}/care-preferences`, {
      method: 'PUT', headers: authorization,
      body: JSON.stringify({ metadata: { activity_history: { tracking_enabled: false, retention_days: 14 } } }),
    });
    assert.equal(preferences.response.status, 200);
    assert.equal(preferences.body.metadata.activity_history.tracking_enabled, false);
    assert.equal(preferences.body.metadata.activity_history.retention_days, 14);

    const skipped = await request(baseURL, '/api/v1/device/activity-intervals', {
      method: 'POST', headers: { Authorization: `Bearer ${app.deviceToken}` },
      body: JSON.stringify({ device_id: 'edge-activity-test', intervals: [{ ...interval, source_interval_id: 'disabled-interval' }] }),
    });
    assert.deepEqual(
      { accepted: skipped.body.accepted, inserted: skipped.body.inserted, reason: skipped.body.reason },
      { accepted: 0, inserted: 0, reason: 'activity_tracking_disabled' },
    );

    const invalid = await request(baseURL, '/api/v1/device/activity-intervals', {
      method: 'POST', headers: { Authorization: `Bearer ${app.deviceToken}` },
      body: JSON.stringify({ device_id: 'edge-activity-test', intervals: [{ ...interval, source_interval_id: 'bad', ended_at: interval.started_at }] }),
    });
    assert.equal(invalid.response.status, 400);

    const deleted = await request(baseURL, `/api/v2/activity-history?family_id=${familyID}`, {
      method: 'DELETE', headers: authorization,
    });
    assert.equal(deleted.response.status, 200);
    assert.equal(deleted.body.deleted, 2);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
