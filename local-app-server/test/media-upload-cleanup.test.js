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

function close(server) {
  return new Promise((resolve) => server.close(resolve));
}

async function request(baseURL, pathname, options = {}) {
  const response = await fetch(`${baseURL}${pathname}`, {
    ...options,
    headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) },
  });
  const text = await response.text();
  return { response, body: text ? JSON.parse(text) : null };
}

test('expired COS upload intent survives server restart and is reclaimed', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-media-upload-restart-'));
  const objects = new Set();
  const deletedKeys = [];
  const cosStorage = {
    enabled: true,
    signedPutUrl({ key }) { return `https://cos.test/upload?key=${encodeURIComponent(key)}`; },
    signedGetUrl({ key }) { return `https://cos.test/read?key=${encodeURIComponent(key)}`; },
    async headObject() { throw new Error('not uploaded'); },
    async deleteObject({ key }) {
      deletedKeys.push(key);
      objects.delete(key);
    },
  };
  const createApp = () => createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'),
    dataDir,
    authMode: 'demo',
    demoOtp: '246810',
    mediaUploadSecret: 'restart-test-media-secret',
    mediaUploadCleanupEnabled: false,
    cosStorage,
  });
  let app = createApp();
  try {
    const baseURL = await listen(app.server);
    const registered = await request(baseURL, '/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ phone: '13800138017', code: '246810', display_name: '回收测试' }),
    });
    const authorization = { Authorization: `Bearer ${registered.body.token}` };
    const family = await request(baseURL, '/api/families', {
      method: 'POST', headers: authorization, body: JSON.stringify({ name: '回收测试家庭' }),
    });
    const intentResponse = await request(
      baseURL,
      `/api/v2/memory-media-upload-intents?family_id=${family.body.id}`,
      {
        method: 'POST',
        headers: authorization,
        body: JSON.stringify({ items: [{
          content_type: 'image/jpeg', size_bytes: 1200, pixel_width: 1280, pixel_height: 960,
        }] }),
      },
    );
    assert.equal(intentResponse.response.status, 201);
    const upload = intentResponse.body.uploads[0];
    const objectKey = new URL(upload.upload_url).searchParams.get('key');
    objects.add(objectKey);
    app.store.db.media_upload_intents[0].expires_at = new Date(Date.now() - 1000).toISOString();
    await app.store.save();
    await close(app.server);

    app = createApp();
    assert.equal(app.store.db.media_upload_intents.length, 1);
    const cleanup = await app.cleanupExpiredMemoryUploads();

    assert.deepEqual(cleanup, { scanned: 1, deleted: 1, released: 1, failed: 0, running: false });
    assert.deepEqual(deletedKeys, [objectKey]);
    assert.equal(objects.has(objectKey), false);
    assert.equal(app.store.db.media_upload_intents.length, 0);
  } finally {
    if (app.server.listening) await close(app.server);
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
