const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { ApnsError } = require('../apns-provider');
const { createLocalAppServer } = require('../server');
const { buildCloudSeedBundle } = require('../../scripts/export-local-app-db');

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => resolve(`http://127.0.0.1:${server.address().port}`));
  });
}

async function requestJson(baseUrl, pathname, options = {}) {
  const response = await fetch(`${baseUrl}${pathname}`, {
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  return { response, body: text ? JSON.parse(text) : null };
}

async function fixture(send) {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-apns-delivery-'));
  const provider = {
    configured: true,
    encryptToken: () => 'v1:opaque-encrypted-token',
    send,
  };
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'),
    dataDir,
    authMode: 'demo',
    demoOtp: '246810',
    apnsProvider: provider,
  });
  const baseUrl = await listen(app.server);
  const registration = await requestJson(baseUrl, '/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ phone: '13800138008', code: '246810' }),
  });
  const authorization = { Authorization: `Bearer ${registration.body.token}` };
  const family = await requestJson(baseUrl, '/api/families', {
    method: 'POST',
    headers: authorization,
    body: JSON.stringify({ name: 'APNs family' }),
  });
  const familyID = String(family.body.id);
  const rawToken = 'ab'.repeat(32);
  const registeredToken = await requestJson(baseUrl, '/api/v1/app/push-tokens', {
    method: 'POST',
    headers: authorization,
    body: JSON.stringify({
      family_id: familyID,
      app_install_id: 'ios-test-install',
      platform: 'ios',
      push_token: rawToken,
      environment: 'sandbox',
    }),
  });
  assert.equal(registeredToken.response.status, 200);
  assert.equal(JSON.stringify(registeredToken.body).includes(rawToken), false);
  assert.equal(JSON.stringify(app.store.db).includes(rawToken), false);
  const queued = await requestJson(baseUrl, '/api/v1/app/push-test', {
    method: 'POST',
    headers: authorization,
    body: JSON.stringify({ family_id: familyID }),
  });
  assert.equal(queued.response.status, 200);
  assert.equal(queued.body.deliveries[0].status, 'queued');
  return { app, baseUrl, dataDir, familyID };
}

async function closeFixture({ app, dataDir }) {
  await new Promise((resolve) => app.server.close(resolve));
  fs.rmSync(dataDir, { recursive: true, force: true });
}

test('APNs acceptance records sent but never claims device delivery', async () => {
  let request;
  const context = await fixture(async (value) => {
    request = value;
    return { statusCode: 200, apnsId: 'accepted-by-apns' };
  });
  try {
    const result = await context.app.dispatchQueuedPushDeliveries();
    assert.deepEqual(result, { attempted: 1, sent: 1, failed: 0 });
    const delivery = context.app.store.db.notification_deliveries[0];
    assert.equal(delivery.status, 'sent');
    assert.ok(delivery.sent_at);
    assert.equal(delivery.delivered_at, '');
    assert.equal(delivery.response_payload.apns_id, 'accepted-by-apns');
    assert.equal(request.environment, 'sandbox');
    assert.equal(request.tokenCiphertext, 'v1:opaque-encrypted-token');
    assert.equal(request.payload.gohome.route, 'home');
    const exported = JSON.stringify(buildCloudSeedBundle(context.app.store.db));
    assert.equal(exported.includes('ab'.repeat(32)), false);
    assert.equal(exported.includes('v1:opaque-encrypted-token'), true);
  } finally {
    await closeFixture(context);
  }
});

test('event delivery includes the exact native event route and camera context', async () => {
  let request;
  const context = await fixture(async (value) => {
    request = value;
    return { statusCode: 200, apnsId: 'accepted-event-id' };
  });
  try {
    const delivery = context.app.store.db.notification_deliveries[0];
    const message = context.app.store.db.app_messages.find((item) => (
      String(item.message_id || item.id) === String(delivery.message_id)
    ));
    message.event_id = 208;
    context.app.store.db.events.push({ id: 208, family_id: context.familyID, camera_id: 2 });

    const result = await context.app.dispatchQueuedPushDeliveries();

    assert.deepEqual(result, { attempted: 1, sent: 1, failed: 0 });
    assert.deepEqual(request.payload.gohome, {
      route: 'event',
      message_id: String(message.message_id),
      event_id: '208',
      camera_id: '2',
      open_deep_link: 'gohome://open?next=event_detail.html%3FeventId%3D208',
    });
  } finally {
    await closeFixture(context);
  }
});

test('transient APNs errors remain queued with bounded retry metadata', async () => {
  const context = await fixture(async () => {
    throw new ApnsError('APNs unavailable', { statusCode: 503, reason: 'ServiceUnavailable', retryable: true });
  });
  try {
    const result = await context.app.dispatchQueuedPushDeliveries();
    assert.deepEqual(result, { attempted: 1, sent: 0, failed: 0 });
    const delivery = context.app.store.db.notification_deliveries[0];
    assert.equal(delivery.status, 'queued');
    assert.equal(delivery.response_payload.attempt_count, 1);
    assert.ok(Date.parse(delivery.response_payload.next_attempt_at) > Date.now());
  } finally {
    await closeFixture(context);
  }
});

test('invalid APNs tokens are revoked and future scheduled deliveries are not sent early', async () => {
  let calls = 0;
  const context = await fixture(async () => {
    calls += 1;
    throw new ApnsError('APNs rejected token', { statusCode: 410, reason: 'Unregistered' });
  });
  try {
    const delivery = context.app.store.db.notification_deliveries[0];
    delivery.scheduled_for = new Date(Date.now() + 60_000).toISOString();
    assert.deepEqual(
      await context.app.dispatchQueuedPushDeliveries(),
      { attempted: 0, sent: 0, failed: 0 },
    );
    assert.equal(calls, 0);
    delivery.scheduled_for = '';
    assert.deepEqual(
      await context.app.dispatchQueuedPushDeliveries(),
      { attempted: 1, sent: 0, failed: 1 },
    );
    assert.equal(context.app.store.db.app_push_tokens[0].status, 'revoked');
    assert.equal(delivery.status, 'failed');
    assert.equal(delivery.error_message, 'Unregistered');
  } finally {
    await closeFixture(context);
  }
});
