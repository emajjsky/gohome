const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const { createApnsProvider } = require('../apns-provider');

function providerWith(request) {
  const { privateKey } = crypto.generateKeyPairSync('ec', { namedCurve: 'P-256' });
  return createApnsProvider({
    provider: 'apns', teamId: 'TEAM123456', keyId: 'KEY123456', topic: 'com.gohome.family',
    authKey: privateKey.export({ type: 'pkcs8', format: 'pem' }),
    tokenEncryptionKey: crypto.randomBytes(32).toString('base64'),
    request,
  });
}

test('APNs token encryption is reversible without storing plaintext', () => {
  const provider = providerWith(async () => ({ headers: { ':status': 200 }, body: '' }));
  const token = 'ab'.repeat(32);
  const encrypted = provider.encryptToken(token);
  assert.equal(encrypted.includes(token), false);
  assert.equal(provider.decryptToken(encrypted), token);
});

test('APNs provider sends an ES256 bearer request to the selected environment', async () => {
  const captured = [];
  const provider = providerWith(async (request) => {
    captured.push(request);
    return { headers: { ':status': 200, 'apns-id': 'accepted-id' }, body: '' };
  });
  const token = 'cd'.repeat(32);
  const result = await provider.send({
    tokenCiphertext: provider.encryptToken(token), environment: 'sandbox',
    payload: { aps: { alert: { title: '测试', body: '消息' } } }, apnsId: 'request-id',
  });
  await provider.send({
    tokenCiphertext: provider.encryptToken(token), environment: 'production',
    payload: { aps: { alert: { title: '测试', body: '消息' } } }, apnsId: 'production-request-id',
  });
  assert.equal(captured[0].authority, 'https://api.sandbox.push.apple.com');
  assert.equal(captured[1].authority, 'https://api.push.apple.com');
  assert.equal(captured[0].headers[':path'], `/3/device/${token}`);
  assert.match(captured[0].headers.authorization, /^bearer [^.]+\.[^.]+\.[^.]+$/);
  assert.equal(captured[0].headers['apns-topic'], 'com.gohome.family');
  assert.equal(result.apnsId, 'accepted-id');
});

test('APNs migration persists only encrypted delivery material', () => {
  const sql = fs.readFileSync(path.join(__dirname, '..', 'migrations', '010_apns_delivery.sql'), 'utf8').toLowerCase();
  assert.match(sql, /token_ciphertext text not null/);
  assert.match(sql, /environment in \('sandbox', 'production'\)/);
  assert.doesNotMatch(sql, /push_token_plaintext/);
});
