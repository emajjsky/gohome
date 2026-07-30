const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { createLocalAppServer } = require('../server');
const { isProductAllowed, productPolicyErrors } = require('../native-api/product-policy');

const NOW = Date.parse('2026-07-21T00:00:00.000Z');
const validProduct = {
  id: 'light-1',
  category: '照明与视野',
  brand: 'Panasonic',
  name: '感应小夜灯',
  summary: '夜间起身时提供柔和照明。',
  image_url: 'https://example.com/night-light.jpg',
  source_name: '品牌官方页面',
  source_url: 'https://example.com/night-light',
  suitability: ['夜间照明', '无需复杂操作'],
  disclosure: '',
  status: 'active',
  verified_at: '2026-07-01T00:00:00.000Z',
};

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

test('product policy accepts sourced household products and rejects regulated or stale entries', () => {
  assert.equal(isProductAllowed(validProduct, { now: NOW }), true);
  assert.ok(productPolicyErrors({ ...validProduct, source_url: 'http://example.com/item' }, { now: NOW }).includes('https source required'));
  assert.ok(productPolicyErrors({ ...validProduct, verified_at: '2025-01-01T00:00:00.000Z' }, { now: NOW }).includes('verification is stale'));
  assert.ok(productPolicyErrors({ ...validProduct, category: '医疗器械', summary: '监测血压并辅助诊断' }, { now: NOW }).includes('medical or regulated claim excluded'));
  assert.ok(productPolicyErrors({ ...validProduct, brand: '' }, { now: NOW }).includes('brand required'));
});

test('native product endpoints expose only policy-approved fields and family preferences', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-native-products-'));
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'),
    dataDir,
    authMode: 'demo',
    demoOtp: '246810',
  });
  const baseUrl = await listen(app.server);
  try {
    const registered = await requestJson(baseUrl, '/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ phone: '13800138003', code: '246810' }),
    });
    const authorization = { Authorization: `Bearer ${registered.body.token}` };
    const familyResult = await requestJson(baseUrl, '/api/families', {
      method: 'POST',
      headers: authorization,
      body: JSON.stringify({ name: 'Product family' }),
    });
    const familyId = String(familyResult.body.id);
    app.store.db.product_catalog = [
      validProduct,
      { ...validProduct, id: 'storage-1', category: '日常生活与收纳', name: '抽屉分隔收纳盒', suitability: ['物品归类'] },
      { ...validProduct, id: 'medicine-1', category: '医疗器械', name: '诊断设备', summary: '帮助诊断并治疗' },
      { ...validProduct, id: 'stale-1', verified_at: '2024-01-01T00:00:00.000Z' },
    ];

    const preferences = await requestJson(baseUrl, `/api/v2/product-preferences?family_id=${familyId}`, {
      method: 'PUT',
      headers: authorization,
      body: JSON.stringify({ categories: ['照明与视野'], needs: ['夜间照明'] }),
    });
    assert.equal(preferences.response.status, 200);
    assert.deepEqual(preferences.body.preferences.categories, ['照明与视野']);
    const persistedAfterPreference = JSON.parse(fs.readFileSync(path.join(dataDir, 'db.json'), 'utf8'));
    assert.deepEqual(persistedAfterPreference.product_preferences[familyId].categories, ['照明与视野']);

    const list = await requestJson(baseUrl, `/api/v2/products?family_id=${familyId}`, { headers: authorization });
    assert.equal(list.response.status, 200);
    assert.deepEqual(list.body.products.map((product) => product.id), ['light-1']);
    assert.match(list.body.products[0].recommendation_reason, /夜间照明/);
    for (const forbidden of ['price', 'inventory', 'cart', 'checkout', 'payment', 'order']) {
      assert.equal(forbidden in list.body.products[0], false);
    }

    const detail = await requestJson(baseUrl, `/api/v2/products/light-1?family_id=${familyId}`, { headers: authorization });
    assert.equal(detail.response.status, 200);
    assert.equal(detail.body.product.source_url, 'https://example.com/night-light');

    const rejectedPreferences = await requestJson(baseUrl, `/api/v2/product-preferences?family_id=${familyId}`, {
      method: 'PUT',
      headers: authorization,
      body: JSON.stringify({ categories: ['药品'], needs: [] }),
    });
    assert.equal(rejectedPreferences.response.status, 400);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
