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

test('home coordinates are explicit family data and the home endpoint never invents them', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-home-location-'));
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'),
    dataDir,
    authMode: 'demo',
    demoOtp: '246810',
  });
  const baseURL = await listen(app.server);
  try {
    const registration = await request(baseURL, '/api/auth/register', {
      method: 'POST', body: JSON.stringify({ phone: '13800138302', code: '246810' }),
    });
    const headers = { Authorization: `Bearer ${registration.body.token}` };
    const family = await request(baseURL, '/api/families', {
      method: 'POST', headers, body: JSON.stringify({ name: '位置家庭' }),
    });
    const familyID = String(family.body.id);

    const before = await request(baseURL, `/api/v2/home?family_id=${familyID}`, { headers });
    assert.equal(before.response.status, 200);
    assert.equal(before.body.home_location, null);
    assert.equal(before.body.weather, null);

    const saved = await request(baseURL, `/api/v1/families/${familyID}/elders/elder_primary/profile`, {
      method: 'PUT',
      headers,
      body: JSON.stringify({
        display_name: '妈妈', relationship: '母亲', city: '上海市', district: '徐汇区',
        phone: '13800138302', mobile_phone: '13800138302', home_phone: '',
        home_latitude: 31.1883, home_longitude: 121.4365, home_location_label: '徐汇区 · 上海市',
      }),
    });
    assert.equal(saved.response.status, 200);
    assert.equal(saved.body.home_latitude, 31.1883);

    const home = await request(baseURL, `/api/v2/home?family_id=${familyID}`, { headers });
    assert.equal(home.response.status, 200);
    assert.deepEqual(home.body.home_location, {
      latitude: 31.1883,
      longitude: 121.4365,
      label: '徐汇区 · 上海市',
      city: '上海市',
      district: '徐汇区',
      source: 'family_setup_phone',
      updated_at: home.body.home_location.updated_at,
    });
    assert.ok(home.body.home_location.updated_at);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
