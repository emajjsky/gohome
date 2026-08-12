const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { createLocalAppServer, createLocalAppServerAsync } = require('../server');

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => resolve(`http://127.0.0.1:${server.address().port}`));
  });
}

async function requestJson(baseURL, pathname, options = {}) {
  const response = await fetch(`${baseURL}${pathname}`, {
    ...options,
    headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) },
  });
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  assert.equal(response.ok, true, JSON.stringify(body));
  return body;
}

test('server-observed public network verifies visits idempotently and keeps return plans explicit', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-home-return-'));
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'),
    dataDir,
    authMode: 'demo',
    demoOtp: '246810',
    homeNetworkSecret: 'home-network-secret-at-least-thirty-two-bytes',
  });
  const baseURL = await listen(app.server);
  try {
    const registration = await requestJson(baseURL, '/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ phone: '13800138008', code: '246810' }),
    });
    const authorization = { Authorization: `Bearer ${registration.token}` };
    const family = await requestJson(baseURL, '/api/families', {
      method: 'POST', headers: authorization, body: JSON.stringify({ name: 'Home return family' }),
    });
    const familyID = String(family.id);
    app.store.db.devices['box-home'] = { device_id: 'box-home', family_id: familyID, status: 'online', runtime: {} };

    await requestJson(baseURL, '/api/v1/device/heartbeat', {
      method: 'POST',
      headers: { Authorization: 'Bearer gohome-local-device-token', 'X-Real-IP': '203.0.113.10' },
      body: JSON.stringify({ device_id: 'box-home', runtime: { lan_url: 'http://192.168.1.12:8711' } }),
    });

    const sameNetworkHeaders = { ...authorization, 'X-Real-IP': '203.0.113.10' };
    const first = await requestJson(baseURL, `/api/v2/home/visit-verification?family_id=${familyID}`, {
      method: 'POST',
      headers: sameNetworkHeaders,
      body: JSON.stringify({ meters: 0, network_identity: 'client-controlled-value' }),
    });
    const duplicate = await requestJson(baseURL, `/api/v2/home/visit-verification?family_id=${familyID}`, {
      method: 'POST', headers: sameNetworkHeaders, body: '{}',
    });
    assert.deepEqual([first.matched, first.recorded], [true, true]);
    assert.deepEqual([duplicate.matched, duplicate.recorded], [true, false]);
    assert.equal(app.store.db.home_visits.length, 1);

    const away = await requestJson(baseURL, `/api/v2/home/visit-verification?family_id=${familyID}`, {
      method: 'POST',
      headers: { ...authorization, 'X-Real-IP': '198.51.100.20' },
      body: JSON.stringify({ meters: 1 }),
    });
    assert.deepEqual([away.matched, away.recorded], [false, false]);
    assert.equal(app.store.db.home_visits.length, 1);

    await requestJson(baseURL, `/api/v2/home/return-plan?family_id=${familyID}`, {
      method: 'PUT',
      headers: authorization,
      body: JSON.stringify({ starts_at: '2026-08-19T10:00:00.000Z', note: '周末回家吃饭' }),
    });
    const home = await requestJson(baseURL, `/api/v2/home?family_id=${familyID}`, { headers: sameNetworkHeaders });
    assert.equal(home.return_home.is_at_home, true);
    assert.equal(home.return_home.days_since_last_visit, 0);
    assert.equal(home.return_plan.note, '周末回家吃饭');

    await requestJson(baseURL, `/api/v2/home/return-plan?family_id=${familyID}`, {
      method: 'DELETE', headers: authorization,
    });
    const afterCancellation = await requestJson(baseURL, `/api/v2/home?family_id=${familyID}`, { headers: authorization });
    assert.equal(afterCancellation.return_plan, null);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});

test('IPv6 privacy addresses on the same home /64 verify as one network', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-home-return-ipv6-'));
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'),
    dataDir,
    authMode: 'demo',
    demoOtp: '246810',
    homeNetworkSecret: 'home-network-secret-at-least-thirty-two-bytes',
  });
  const baseURL = await listen(app.server);
  try {
    const registration = await requestJson(baseURL, '/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ phone: '13800138018', code: '246810' }),
    });
    const authorization = { Authorization: `Bearer ${registration.token}` };
    const family = await requestJson(baseURL, '/api/families', {
      method: 'POST', headers: authorization, body: JSON.stringify({ name: 'IPv6 home' }),
    });
    app.store.db.devices['box-ipv6'] = { device_id: 'box-ipv6', family_id: family.id, status: 'online', runtime: {} };

    await requestJson(baseURL, '/api/v1/device/heartbeat', {
      method: 'POST',
      headers: { Authorization: 'Bearer gohome-local-device-token', 'X-Real-IP': '2001:db8:1234:5678:1111:2222:3333:4444' },
      body: JSON.stringify({ device_id: 'box-ipv6' }),
    });
    const verified = await requestJson(baseURL, `/api/v2/home/visit-verification?family_id=${family.id}`, {
      method: 'POST',
      headers: { ...authorization, 'X-Real-IP': '2001:db8:1234:5678:aaaa:bbbb:cccc:dddd' },
      body: '{}',
    });
    assert.deepEqual([verified.matched, verified.recorded], [true, true]);

    const differentNetwork = await requestJson(baseURL, `/api/v2/home/visit-verification?family_id=${family.id}`, {
      method: 'POST',
      headers: { ...authorization, 'X-Real-IP': '2001:db8:1234:9999:aaaa:bbbb:cccc:dddd' },
      body: '{}',
    });
    assert.deepEqual([differentNetwork.matched, differentNetwork.recorded], [false, false]);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});

test('production startup rejects a missing-strength home network secret', async () => {
  await assert.rejects(
    createLocalAppServerAsync({ authMode: 'production', homeNetworkSecret: 'too-short' }),
    /GOHOME_HOME_NETWORK_SECRET must contain at least 32 characters in production/,
  );
});
