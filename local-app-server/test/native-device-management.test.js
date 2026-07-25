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
    const member = await register(baseURL, '13800138102', '家庭成员');
    const joined = await request(baseURL, '/api/families/join', {
      method: 'POST', headers: member.headers, body: JSON.stringify({ code: familyResult.body.join_code }),
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
