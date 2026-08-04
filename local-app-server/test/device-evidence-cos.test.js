const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { createLocalAppServer } = require('../server');

async function readStream(stream) {
  const chunks = [];
  for await (const chunk of stream) chunks.push(Buffer.from(chunk));
  return Buffer.concat(chunks);
}

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => resolve(`http://127.0.0.1:${server.address().port}`));
  });
}

async function request(baseURL, pathname, options = {}) {
  const response = await fetch(`${baseURL}${pathname}`, options);
  const text = await response.text();
  return { response, body: text ? JSON.parse(text) : null };
}

test('device event evidence is stored in COS and served through an authorized asset URL', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-device-evidence-cos-'));
  const objects = new Map();
  const cosStorage = {
    enabled: true,
    async putObject({ key, body, contentType, contentLength }) {
      const content = await readStream(body);
      assert.equal(content.length, contentLength);
      objects.set(key, { body: content, contentType });
    },
    signedGetUrl({ key }) {
      return `https://cos.test/read?key=${encodeURIComponent(key)}`;
    },
    signedPutUrl() { throw new Error('not used'); },
    async headObject() { throw new Error('not used'); },
    async deleteObject() {},
  };
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'),
    dataDir,
    authMode: 'demo',
    demoOtp: '246810',
    cosStorage,
    mediaUploadCleanupEnabled: false,
  });
  const baseURL = await listen(app.server);
  try {
    const registration = await request(baseURL, '/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: '13800138301', code: '246810', display_name: '证据测试' }),
    });
    const appHeaders = { Authorization: `Bearer ${registration.body.token}` };
    const family = await request(baseURL, '/api/families', {
      method: 'POST',
      headers: { ...appHeaders, 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: '证据家庭' }),
    });
    const familyID = Number(family.body.id);
    const deviceID = 'event-evidence-cos';
    const deviceToken = 'event-evidence-cos-token';
    app.store.db.devices[deviceID] = { id: deviceID, device_id: deviceID, family_id: familyID, status: 'online' };
    app.store.db.device_tokens.push({
      id: 'device-evidence-token', token: deviceToken, device_id: deviceID,
      family_id: familyID, status: 'active', created_at: new Date().toISOString(),
    });

    const jpeg = Buffer.from([0xff, 0xd8, 0x12, 0x34, 0xff, 0xd9]);
    const uploaded = await request(
      baseURL,
      '/api/v1/device/media-assets/upload?file_name=fall.jpg&snapshot_path=camera-1/fall.jpg&content_type=image%2Fjpeg&edge_event_id=42&idempotency_key=evidence-job-42',
      {
        method: 'POST',
        headers: { Authorization: `Bearer ${deviceToken}`, 'Content-Type': 'image/jpeg' },
        body: jpeg,
      },
    );
    assert.equal(uploaded.response.status, 200);
    assert.equal(uploaded.body.asset.storage_provider, 'cos');
    assert.match(uploaded.body.asset.storage_key, new RegExp(`^event-evidence/${familyID}/`));
    assert.deepEqual(objects.get(uploaded.body.asset.storage_key).body, jpeg);
    assert.equal(fs.existsSync(path.join(dataDir, 'media', uploaded.body.asset.storage_key)), false);

    const duplicate = await request(
      baseURL,
      '/api/v1/device/media-assets/upload?file_name=fall.jpg&snapshot_path=camera-1/fall.jpg&content_type=image%2Fjpeg&edge_event_id=42&idempotency_key=evidence-job-42',
      {
        method: 'POST',
        headers: { Authorization: `Bearer ${deviceToken}`, 'Content-Type': 'image/jpeg' },
        body: jpeg,
      },
    );
    assert.equal(duplicate.response.status, 200);
    assert.equal(duplicate.body.duplicate, true);
    assert.equal(duplicate.body.asset.id, uploaded.body.asset.id);
    assert.equal(objects.size, 1);

    const served = await fetch(`${baseURL}${uploaded.body.asset.url}`, {
      headers: appHeaders,
      redirect: 'manual',
    });
    assert.equal(served.status, 302);
    assert.match(served.headers.get('location'), /^https:\/\/cos\.test\/read\?/);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
