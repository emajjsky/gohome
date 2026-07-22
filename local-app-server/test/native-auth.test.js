const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { AuthPolicyError, AuthService } = require('../native-api/auth-service');
const { createLocalAppServer } = require('../server');

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => resolve(`http://127.0.0.1:${server.address().port}`));
  });
}

test('production auth rejects fixed OTP and requires an SMS provider', async () => {
  const service = new AuthService({ mode: 'production', secret: 'server-secret' });
  await assert.rejects(
    service.requestCode('13800138000'),
    (error) => error instanceof AuthPolicyError && error.statusCode === 503,
  );
  assert.throws(
    () => service.verifyCode('13800138000', '000000'),
    (error) => error instanceof AuthPolicyError && error.statusCode === 401,
  );
});

test('demo auth returns its explicit test code and accepts only that OTP', async () => {
  const service = new AuthService({ mode: 'demo', demoOtp: '246810' });
  const challenge = await service.requestCode('13800138000');
  assert.equal(challenge.delivery, 'demo');
  assert.equal(challenge.demo_code, '246810');
  assert.equal(service.verifyCode('13800138000', '246810').mode, 'demo');
  assert.throws(() => service.verifyCode('13800138000', '000000'), /验证码不正确/);
});

test('production challenge is hashed, expires, and is consumed once', async () => {
  let now = 1000;
  let sent = null;
  const service = new AuthService({
    mode: 'production',
    secret: 'server-secret',
    clock: () => now,
    challengeTtlMs: 100,
    smsProvider: async (message) => { sent = message; },
  });
  const challenge = await service.requestCode('13800138000');
  assert.ok(challenge.challenge_id);
  assert.equal(sent.phone, '13800138000');
  assert.equal(service.challenges.get(challenge.challenge_id).code, undefined);
  assert.equal(service.verifyCode('13800138000', sent.code, challenge.challenge_id).mode, 'production');
  assert.throws(() => service.verifyCode('13800138000', sent.code, challenge.challenge_id), /已失效/);

  const second = await service.requestCode('13800138000');
  now = 1200;
  assert.throws(() => service.verifyCode('13800138000', sent.code, second.challenge_id), /已失效/);
});

test('challenge requests are rate limited', async () => {
  const service = new AuthService({
    mode: 'production',
    secret: 'server-secret',
    smsProvider: async () => {},
    maxRequestsPerWindow: 1,
  });
  await service.requestCode('13800138000');
  await assert.rejects(service.requestCode('13800138000'), /过于频繁/);
});

test('failed delivery removes its challenge and the final invalid attempt consumes it', async () => {
  const failed = new AuthService({
    mode: 'production',
    secret: 'server-secret',
    smsProvider: async () => { throw new Error('provider unavailable'); },
  });
  await assert.rejects(failed.requestCode('13800138000'), /发送失败/);
  assert.equal(failed.challenges.size, 0);

  let sent;
  const limited = new AuthService({
    mode: 'production',
    secret: 'server-secret',
    smsProvider: async (message) => { sent = message; },
    maxAttempts: 2,
  });
  const challenge = await limited.requestCode('13800138000');
  const wrongCode = sent.code === '111111' ? '222222' : '111111';
  assert.throws(() => limited.verifyCode('13800138000', wrongCode, challenge.challenge_id), /不正确/);
  assert.throws(() => limited.verifyCode('13800138000', wrongCode, challenge.challenge_id), /尝试次数过多/);
  assert.throws(() => limited.verifyCode('13800138000', sent.code, challenge.challenge_id), /已失效/);
});

test('production HTTP registration cannot bypass challenges with 000000', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-native-auth-'));
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'),
    dataDir,
    authMode: 'production',
    authSecret: 'server-secret',
  });
  const baseUrl = await listen(app.server);
  try {
    const registration = await fetch(`${baseUrl}/api/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: '13800138000', code: '000000' }),
    });
    assert.equal(registration.status, 401);

    const requestCode = await fetch(`${baseUrl}/api/auth/request-code`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: '13800138000' }),
    });
    assert.equal(requestCode.status, 503);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
