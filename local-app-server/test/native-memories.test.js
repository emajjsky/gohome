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

test('native memories form a private family timeline with editable durable records', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-native-memories-'));
  const app = createLocalAppServer({ rootDir: path.join(__dirname, '..', '..'), dataDir, authMode: 'demo', demoOtp: '246810' });
  const baseURL = await listen(app.server);
  try {
    const registered = await request(baseURL, '/api/auth/register', {
      method: 'POST', body: JSON.stringify({ phone: '13800138009', code: '246810', display_name: '小林' }),
    });
    const authorization = { Authorization: `Bearer ${registered.body.token}` };
    const family = await request(baseURL, '/api/families', {
      method: 'POST', headers: authorization, body: JSON.stringify({ name: '记忆测试家庭' }),
    });
    const familyID = String(family.body.id);

    const empty = await request(baseURL, `/api/v2/memories?family_id=${familyID}`, { headers: authorization });
    assert.equal(empty.response.status, 200);
    assert.deepEqual(empty.body.memories, []);

    const uploaded = await request(baseURL, `/api/v2/memory-media?family_id=${familyID}`, {
      method: 'POST',
      headers: { ...authorization, 'Content-Type': 'image/jpeg' },
      body: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
    });
    assert.equal(uploaded.response.status, 201);
    const assetID = uploaded.body.asset.id;
    assert.match(assetID, /^memory-asset-/);

    const created = await request(baseURL, `/api/v2/memories?family_id=${familyID}`, {
      method: 'POST',
      headers: authorization,
      body: JSON.stringify({
        body: '第一次一起去江边散步。',
        happened_at: '2026-07-20T10:00:00+08:00',
        location_name: '滨江步道',
        people: ['爸爸', '小林'],
        asset_ids: [assetID],
      }),
    });
    assert.equal(created.response.status, 201);
    assert.equal(created.body.memory.author.display_name, '小林');
    assert.deepEqual(created.body.memory.people, ['爸爸', '小林']);
    assert.equal(created.body.memory.media[0].asset_id, assetID);
    const memoryID = created.body.memory.id;

    const replacementUpload = await request(baseURL, `/api/v2/memory-media?family_id=${familyID}`, {
      method: 'POST',
      headers: { ...authorization, 'Content-Type': 'image/jpeg' },
      body: Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0xff, 0xd9]),
    });
    assert.equal(replacementUpload.response.status, 201);
    const replacementAssetID = replacementUpload.body.asset.id;

    const updated = await request(baseURL, `/api/v2/memories/${memoryID}?family_id=${familyID}`, {
      method: 'PATCH', headers: authorization, body: JSON.stringify({
        body: '傍晚一起去江边散步，看到了晚霞。',
        asset_ids: [replacementAssetID],
      }),
    });
    assert.equal(updated.response.status, 200);
    assert.match(updated.body.memory.body, /晚霞/);
    assert.equal(updated.body.memory.media[0].asset_id, replacementAssetID);
    assert.equal(app.store.db.assets.some((asset) => String(asset.id) === assetID), false);

    const timeline = await request(baseURL, `/api/v2/memories?family_id=${familyID}`, { headers: authorization });
    assert.equal(timeline.body.memories.length, 1);
    assert.equal(timeline.body.memories[0].id, memoryID);
    assert.ok(timeline.response.headers.get('etag'));

    const commented = await request(baseURL, `/api/v2/memories/${memoryID}/comments?family_id=${familyID}`, {
      method: 'POST', headers: authorization, body: JSON.stringify({ body: '这张晚霞很好看。' }),
    });
    assert.equal(commented.response.status, 201);
    assert.equal(commented.body.memory.comments.length, 1);
    const commentID = commented.body.memory.comments[0].id;

    const favorited = await request(baseURL, `/api/v2/memories/${memoryID}/favorite?family_id=${familyID}`, {
      method: 'PUT', headers: authorization,
    });
    assert.equal(favorited.response.status, 200);
    assert.equal(favorited.body.memory.is_favorite, true);
    assert.equal(favorited.body.memory.favorite_count, 1);

    const uncommented = await request(baseURL, `/api/v2/memories/${memoryID}/comments/${commentID}?family_id=${familyID}`, {
      method: 'DELETE', headers: authorization,
    });
    assert.equal(uncommented.body.memory.comments.length, 0);

    const unfavorited = await request(baseURL, `/api/v2/memories/${memoryID}/favorite?family_id=${familyID}`, {
      method: 'DELETE', headers: authorization,
    });
    assert.equal(unfavorited.body.memory.favorite_count, 0);

    const deleted = await request(baseURL, `/api/v2/memories/${memoryID}?family_id=${familyID}`, {
      method: 'DELETE', headers: authorization,
    });
    assert.equal(deleted.response.status, 200);
    assert.equal(deleted.body.deleted, true);
    assert.equal(app.store.db.family_memories.length, 0);
    assert.equal(app.store.db.assets.some((asset) => String(asset.id) === replacementAssetID), false);

    const removedMedia = await fetch(`${baseURL}/api/v1/video/assets/${replacementAssetID}`, { headers: authorization });
    assert.equal(removedMedia.status, 404);

    const persisted = JSON.parse(fs.readFileSync(path.join(dataDir, 'db.json'), 'utf8'));
    assert.deepEqual(persisted.family_memories, []);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
