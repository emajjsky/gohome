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

async function register(baseURL, phone, displayName) {
  const result = await request(baseURL, '/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ phone, code: '246810', display_name: displayName }),
  });
  assert.equal(result.response.status, 200);
  return { token: result.body.token, headers: { Authorization: `Bearer ${result.body.token}` } };
}

test('native device and camera mutations are creator-only and stay bound to one family device', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-native-devices-'));
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'),
    dataDir,
    authMode: 'demo',
    demoOtp: '246810',
  });
  const baseURL = await listen(app.server);
  try {
    const owner = await register(baseURL, '13800138101', '创建者');
    const familyResult = await request(baseURL, '/api/families', {
      method: 'POST', headers: owner.headers, body: JSON.stringify({ name: '设备权限家庭' }),
    });
    const familyID = String(familyResult.body.id);
    const invitation = await request(baseURL, `/api/v2/families/${familyID}/invitations`, {
      method: 'POST', headers: owner.headers, body: JSON.stringify({ expires_in_minutes: 10 }),
    });
    assert.equal(invitation.response.status, 201);
    const member = await register(baseURL, '13800138102', '家庭成员');
    const joined = await request(baseURL, '/api/families/join', {
      method: 'POST', headers: member.headers, body: JSON.stringify({ code: invitation.body.code }),
    });
    assert.equal(String(joined.body.id), familyID);

    app.store.db.devices['edge-device-test'] = {
      id: 'edge-device-test', device_id: 'edge-device-test', family_id: familyID, name: '测试盒子', status: 'online',
    };
    app.store.db.device_bindings.push({
      id: 'binding-device-test', family_id: Number(familyID), device_id: 'edge-device-test',
      device_name: '测试盒子', status: 'active', bound_at: new Date().toISOString(),
    });

    const memberCreate = await request(baseURL, '/api/cameras', {
      method: 'POST', headers: member.headers,
      body: JSON.stringify({ family_id: familyID, name: '越权画面', room: '客厅', stream_url: 'rtsp://192.168.1.8:554/1/2' }),
    });
    assert.equal(memberCreate.response.status, 403);

    const created = await request(baseURL, '/api/cameras', {
      method: 'POST', headers: owner.headers,
      body: JSON.stringify({
        family_id: familyID,
        device_id: 'edge-device-test',
        name: '客厅主视',
        room: '客厅',
        stream_url: 'rtsp://192.168.1.8:554/1/2',
        username: 'admin',
        password: 'camera-secret',
      }),
    });
    assert.equal(created.response.status, 200);
    assert.equal(created.body.device_id, 'edge-device-test');
    assert.equal(created.body.password_set, true);
    assert.equal(created.body.password, undefined);
    assert.equal(created.body.stream_url, undefined);
    assert.deepEqual(created.body.connection, {
      scheme: 'rtsp', host: '192.168.1.8', port: 554, path: '/1/2', username_set: true,
    });

    for (const method of ['PATCH', 'DELETE']) {
      const denied = await request(baseURL, `/api/cameras/${created.body.id}`, {
        method, headers: member.headers,
        ...(method === 'PATCH' ? { body: JSON.stringify({ name: '成员修改' }) } : {}),
      });
      assert.equal(denied.response.status, 403);
    }
    const deniedTest = await request(baseURL, `/api/cameras/${created.body.id}/test`, {
      method: 'POST', headers: member.headers,
    });
    assert.equal(deniedTest.response.status, 403);

    const migrationPatch = await request(baseURL, `/api/cameras/${created.body.id}`, {
      method: 'PATCH', headers: owner.headers, body: JSON.stringify({ device_id: 'other-device' }),
    });
    assert.equal(migrationPatch.response.status, 400);

    const updated = await request(baseURL, `/api/cameras/${created.body.id}`, {
      method: 'PATCH', headers: owner.headers, body: JSON.stringify({ name: '客厅全景', room: '客厅', enabled: false }),
    });
    assert.equal(updated.response.status, 200);
    assert.equal(updated.body.name, '客厅全景');
    assert.equal(updated.body.enabled, false);

    const connectionUpdated = await request(baseURL, `/api/cameras/${created.body.id}`, {
      method: 'PATCH', headers: owner.headers,
      body: JSON.stringify({ stream_url: 'rtsp://192.168.1.7:554/1/2' }),
    });
    assert.equal(connectionUpdated.response.status, 200);
    assert.equal(connectionUpdated.body.connection.host, '192.168.1.7');
    assert.equal(connectionUpdated.body.status, 'pending_edge_sync');
    assert.equal(connectionUpdated.body.sync_status, 'pending_edge_sync');
    assert.equal(app.store.db.cameras[String(created.body.id)].password, 'camera-secret');

    const invalidConnection = await request(baseURL, `/api/cameras/${created.body.id}`, {
      method: 'PATCH', headers: owner.headers, body: JSON.stringify({ stream_url: 'http://192.168.1.7/live' }),
    });
    assert.equal(invalidConnection.response.status, 400);
    assert.equal(app.store.db.cameras[String(created.body.id)].stream_url, 'rtsp://192.168.1.7:554/1/2');

    const unbound = await request(baseURL, '/api/device-bindings/binding-device-test', {
      method: 'DELETE', headers: owner.headers,
    });
    assert.equal(unbound.response.status, 200);
    assert.equal(unbound.body.removed_camera_count, 1);
    assert.equal(app.store.db.cameras[String(created.body.id)], undefined);

    const activeBindings = await request(baseURL, `/api/device-bindings?family_id=${familyID}`, {
      headers: owner.headers,
    });
    assert.equal(activeBindings.response.status, 200);
    assert.deepEqual(activeBindings.body, []);

    const withoutBox = await request(baseURL, '/api/cameras', {
      method: 'POST', headers: owner.headers,
      body: JSON.stringify({ family_id: familyID, name: '无盒子画面', room: '卧室', stream_url: 'rtsp://192.168.1.9:554/1/2' }),
    });
    assert.equal(withoutBox.response.status, 409);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});

test('LAN pairing returns only a sanitized ownership summary and revoked devices lose cloud access', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-native-pairing-'));
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'),
    dataDir,
    authMode: 'demo',
    demoOtp: '246810',
  });
  const baseURL = await listen(app.server);
  try {
    const owner = await register(baseURL, '13818462550', '家庭创建者');
    const familyResult = await request(baseURL, '/api/families', {
      method: 'POST', headers: owner.headers, body: JSON.stringify({ name: '安全配对家庭' }),
    });
    const familyID = String(familyResult.body.id);
    const codeResult = await request(baseURL, '/api/device/binding-codes', {
      method: 'POST', headers: owner.headers,
      body: JSON.stringify({ family_id: familyID, expires_in_minutes: 10 }),
    });
    assert.equal(codeResult.response.status, 200);

    const paired = await request(baseURL, '/api/device/token/exchange', {
      method: 'POST',
      body: JSON.stringify({
        code: codeResult.body.code,
        device_id: 'edge-secure-pairing',
        device_name: '安全配对盒子',
      }),
    });
    assert.equal(paired.response.status, 200);
    assert.deepEqual(paired.body.binding_summary, {
      status: 'bound',
      family_name: '安全配对家庭',
      owner_account: '138****2550',
      owner_display_name: '家庭创建者',
      bound_at: paired.body.binding.bound_at,
    });
    assert.equal(JSON.stringify(paired.body.binding_summary).includes('13818462550'), false);

    const config = await request(baseURL, '/api/v1/device/config', {
      headers: { Authorization: `Bearer ${paired.body.device_token}` },
    });
    assert.equal(config.response.status, 200);
    assert.deepEqual(config.body.binding_summary, paired.body.binding_summary);

    const unbound = await request(baseURL, `/api/device-bindings/${paired.body.binding.id}`, {
      method: 'DELETE', headers: owner.headers,
    });
    assert.equal(unbound.response.status, 200);

    const revokedConfig = await request(baseURL, '/api/v1/device/config', {
      headers: { Authorization: `Bearer ${paired.body.device_token}` },
    });
    assert.equal(revokedConfig.response.status, 401);

    const historicalBinding = app.store.db.device_bindings.find((item) => String(item.id) === String(paired.body.binding.id));
    historicalBinding.bound_at = '2020-01-01T00:00:00.000Z';
    historicalBinding.updated_at = '2020-01-01T00:00:00.000Z';
    const nextCode = await request(baseURL, '/api/device/binding-codes', {
      method: 'POST', headers: owner.headers,
      body: JSON.stringify({ family_id: familyID, expires_in_minutes: 10 }),
    });
    const rebound = await request(baseURL, '/api/device/token/exchange', {
      method: 'POST',
      body: JSON.stringify({
        code: nextCode.body.code,
        device_id: 'edge-secure-pairing',
        device_name: '安全配对盒子',
      }),
    });
    assert.equal(rebound.response.status, 200);
    assert.notEqual(rebound.body.binding.bound_at, '2020-01-01T00:00:00.000Z');
    assert.equal(rebound.body.binding_summary.bound_at, rebound.body.binding.bound_at);

    const reboundAt = rebound.body.binding.bound_at;
    historicalBinding.updated_at = '2030-01-01T00:00:00.000Z';
    const bindingsAfterSync = await request(baseURL, `/api/device-bindings?family_id=${familyID}`, {
      headers: owner.headers,
    });
    assert.equal(bindingsAfterSync.response.status, 200);
    assert.equal(bindingsAfterSync.body[0].bound_at, reboundAt);
    assert.equal(historicalBinding.bound_at, reboundAt);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
