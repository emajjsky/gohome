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

async function requestJson(baseUrl, pathname, options = {}) {
  const response = await fetch(`${baseUrl}${pathname}`, {
    ...options,
    headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) },
  });
  const text = await response.text();
  return { response, body: text ? JSON.parse(text) : null };
}

test('account profile persists identity fields and validates avatar ownership', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-account-profile-'));
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'),
    dataDir,
    authMode: 'demo',
    demoOtp: '246810',
  });
  const baseUrl = await listen(app.server);
  try {
    const registration = await requestJson(baseUrl, '/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ phone: '13800138019', code: '246810', display_name: '初始昵称' }),
    });
    const authorization = { Authorization: `Bearer ${registration.body.token}` };
    const family = await requestJson(baseUrl, '/api/families', {
      method: 'POST', headers: authorization, body: JSON.stringify({ name: '账户测试家庭' }),
    });
    app.store.db.assets.push({ id: 'avatar-owned', family_id: family.body.id, content_type: 'image/jpeg' });
    app.store.db.assets.push({ id: 'avatar-foreign', family_id: 'another-family', content_type: 'image/jpeg' });

    const updated = await requestJson(baseUrl, '/api/v2/account/profile', {
      method: 'PATCH',
      headers: authorization,
      body: JSON.stringify({ display_name: '小宜', city: '上海市', district: '徐汇区', avatar_asset_id: 'avatar-owned' }),
    });
    assert.equal(updated.response.status, 200);
    assert.deepEqual(updated.body.profile, {
      id: String(registration.body.user.id),
      phone: '13800138019',
      display_name: '小宜',
      city: '上海市',
      district: '徐汇区',
      avatar_asset_id: 'avatar-owned',
      avatar_url: '/api/v1/video/assets/avatar-owned?variant=grid',
      updated_at: updated.body.profile.updated_at,
    });

    const loaded = await requestJson(baseUrl, '/api/v2/account/profile', { headers: authorization });
    assert.equal(loaded.body.profile.display_name, '小宜');
    assert.equal(loaded.body.profile.city, '上海市');

    const rejected = await requestJson(baseUrl, '/api/v2/account/profile', {
      method: 'PATCH', headers: authorization, body: JSON.stringify({ avatar_asset_id: 'avatar-foreign' }),
    });
    assert.equal(rejected.response.status, 400);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
