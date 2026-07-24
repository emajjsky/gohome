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

test('native memory media uses private COS upload intents and deletes remote objects', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-native-memory-cos-'));
  const objects = new Map();
  const deletedKeys = [];
  const cosStorage = {
    enabled: true,
    signedPutUrl({ key }) {
      return `https://cos.test/upload?key=${encodeURIComponent(key)}`;
    },
    signedGetUrl({ key }) {
      return `https://cos.test/read?key=${encodeURIComponent(key)}`;
    },
    async headObject({ key }) {
      const object = objects.get(key);
      if (!object) throw new Error('not found');
      return { headers: { 'content-length': String(object.size), 'content-type': object.contentType } };
    },
    async deleteObject({ key }) {
      deletedKeys.push(key);
      objects.delete(key);
    },
  };
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'),
    dataDir,
    authMode: 'demo',
    demoOtp: '246810',
    cosStorage,
  });
  const baseURL = await listen(app.server);
  try {
    const registered = await request(baseURL, '/api/auth/register', {
      method: 'POST', body: JSON.stringify({ phone: '13800138007', code: '246810', display_name: '直传测试' }),
    });
    const authorization = { Authorization: `Bearer ${registered.body.token}` };
    const family = await request(baseURL, '/api/families', {
      method: 'POST', headers: authorization, body: JSON.stringify({ name: 'COS 图片家庭' }),
    });
    const familyID = String(family.body.id);
    const images = [
      { content_type: 'image/jpeg', size_bytes: 1200, pixel_width: 1280, pixel_height: 960 },
      { content_type: 'image/jpeg', size_bytes: 1500, pixel_width: 960, pixel_height: 1280 },
    ];

    const intents = await request(baseURL, `/api/v2/memory-media-upload-intents?family_id=${familyID}`, {
      method: 'POST', headers: authorization, body: JSON.stringify({ items: images }),
    });
    assert.equal(intents.response.status, 201);
    assert.equal(intents.body.uploads.length, 2);
    for (const [index, upload] of intents.body.uploads.entries()) {
      const key = new URL(upload.upload_url).searchParams.get('key');
      assert.match(key, new RegExp(`^memory-media/${familyID}/`));
      objects.set(key, { size: images[index].size_bytes, contentType: images[index].content_type });
    }

    const completed = await request(baseURL, `/api/v2/memory-media-upload-complete?family_id=${familyID}`, {
      method: 'POST',
      headers: authorization,
      body: JSON.stringify({
        items: intents.body.uploads.map((upload) => ({ asset_id: upload.asset_id, upload_token: upload.upload_token })),
      }),
    });
    assert.equal(completed.response.status, 201);
    assert.deepEqual(completed.body.assets.map((asset) => asset.size_bytes), [1200, 1500]);
    const persisted = completed.body.assets.map((asset) => app.store.db.assets.find((item) => item.id === asset.id));
    assert.deepEqual(persisted.map((asset) => asset.storage_provider), ['cos', 'cos']);

    const mediaResponse = await fetch(`${baseURL}${completed.body.assets[0].image_url}`, {
      headers: authorization,
      redirect: 'manual',
    });
    assert.equal(mediaResponse.status, 302);
    assert.match(mediaResponse.headers.get('location'), /^https:\/\/cos\.test\/read\?/);

    const memory = await request(baseURL, `/api/v2/memories?family_id=${familyID}`, {
      method: 'POST',
      headers: authorization,
      body: JSON.stringify({ body: 'COS 直传照片', asset_ids: completed.body.assets.map((asset) => asset.id) }),
    });
    assert.equal(memory.response.status, 201);
    const removed = await request(baseURL, `/api/v2/memories/${memory.body.memory.id}?family_id=${familyID}`, {
      method: 'DELETE', headers: authorization,
    });
    assert.equal(removed.response.status, 200);
    assert.equal(deletedKeys.length, 2);
    assert.equal(app.store.db.assets.some((asset) => completed.body.assets.some((item) => item.id === asset.id)), false);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});

test('native memory media batch persists nine-grid images in one save', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-native-memory-batch-'));
  const app = createLocalAppServer({ rootDir: path.join(__dirname, '..', '..'), dataDir, authMode: 'demo', demoOtp: '246810' });
  const baseURL = await listen(app.server);
  try {
    const registered = await request(baseURL, '/api/auth/register', {
      method: 'POST', body: JSON.stringify({ phone: '13800138008', code: '246810', display_name: '批量测试' }),
    });
    const authorization = { Authorization: `Bearer ${registered.body.token}` };
    const family = await request(baseURL, '/api/families', {
      method: 'POST', headers: authorization, body: JSON.stringify({ name: '批量图片家庭' }),
    });
    const familyID = String(family.body.id);
    const originalSave = app.store.save.bind(app.store);
    let saveCount = 0;
    app.store.save = async () => {
      saveCount += 1;
      return originalSave();
    };
    const images = [1, 2, 3, 4, 5, 6, 7, 8, 9].map((value) => ({
      content_type: 'image/jpeg',
      data: Buffer.from([0xff, 0xd8, value, 0xff, 0xd9]).toString('base64'),
      pixel_width: 1280,
      pixel_height: 960,
    }));

    const uploaded = await request(baseURL, `/api/v2/memory-media-batch?family_id=${familyID}`, {
      method: 'POST', headers: authorization, body: JSON.stringify({ images }),
    });

    assert.equal(uploaded.response.status, 201);
    assert.equal(uploaded.body.assets.length, 9);
    assert.equal(saveCount, 1);
    assert.deepEqual(
      uploaded.body.assets.map((asset) => asset.size_bytes),
      images.map((image) => Buffer.from(image.data, 'base64').length),
    );
    const persistedAssets = uploaded.body.assets.map((asset) => app.store.db.assets.find((item) => item.id === asset.id));
    assert.deepEqual(persistedAssets.map((asset) => asset.metadata.pixel_width), images.map(() => 1280));
    const tooMany = await request(baseURL, `/api/v2/memory-media-batch?family_id=${familyID}`, {
      method: 'POST', headers: authorization, body: JSON.stringify({ images: [...images, images[0]] }),
    });
    assert.equal(tooMany.response.status, 400);
    assert.equal(saveCount, 1);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});

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
