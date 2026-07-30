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
    opsToken: 'test-ops-token',
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
  assert.equal(queued.body.message.delivery_status, 'queued');
  assert.equal(queued.body.message.delivered_at, '');
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
    assert.equal(delivery.response_payload.attempt_count, 1);
    assert.ok(delivery.response_payload.provider_latency_ms >= 0);
    assert.ok(delivery.response_payload.queued_to_sent_ms >= 0);
    const message = context.app.store.db.app_messages.find((item) => String(item.message_id) === String(delivery.message_id));
    assert.equal(message.delivered_at, '');
    assert.equal(request.environment, 'sandbox');
    assert.equal(request.tokenCiphertext, 'v1:opaque-encrypted-token');
    assert.equal(request.payload.gohome.route, 'home');
    assert.equal(request.payload.gohome.delivery_id, String(delivery.id));
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
      delivery_id: String(delivery.id),
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
    assert.equal(delivery.response_payload.failure_history.length, 1);
    const retryDeadline = delivery.response_payload.next_attempt_at;
    const message = context.app.store.db.app_messages.find((item) => String(item.message_id) === String(delivery.message_id));
    const repeated = context.app.queueNotificationDelivery(message);
    assert.equal(repeated[0], delivery);
    assert.equal(delivery.response_payload.attempt_count, 1);
    assert.equal(delivery.response_payload.next_attempt_at, retryDeadline);
  } finally {
    await closeFixture(context);
  }
});

test('authenticated native receipts mark one delivery as delivered without creating another notification', async () => {
  const context = await fixture(async () => ({ statusCode: 200, apnsId: 'accepted-for-receipt' }));
  try {
    await context.app.dispatchQueuedPushDeliveries();
    const delivery = context.app.store.db.notification_deliveries[0];
    const registration = await requestJson(context.baseUrl, '/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ phone: '13800138008', code: '246810' }),
    });
    const authorization = { Authorization: `Bearer ${registration.body.token}` };
    const receiptPayload = {
      delivery_id: String(delivery.id),
      state: 'opened',
      app_install_id: 'ios-test-install',
      app_version: '1.0.0',
    };
    const first = await requestJson(context.baseUrl, '/api/v1/notifications/receipts', {
      method: 'POST',
      headers: authorization,
      body: JSON.stringify(receiptPayload),
    });
    const repeated = await requestJson(context.baseUrl, '/api/v1/notifications/receipts', {
      method: 'POST',
      headers: authorization,
      body: JSON.stringify(receiptPayload),
    });

    assert.equal(first.response.status, 200);
    assert.equal(repeated.response.status, 200);
    assert.equal(delivery.status, 'delivered');
    assert.ok(delivery.delivered_at);
    assert.ok(delivery.clicked_at);
    const message = context.app.store.db.app_messages.find((item) => String(item.message_id) === String(delivery.message_id));
    assert.equal(message.delivered_at, delivery.delivered_at);
    context.app.upsertAppMessage({
      message_id: message.message_id,
      family_id: message.family_id,
      title: message.title,
      body: message.body,
    });
    assert.equal(message.delivered_at, delivery.delivered_at);
    assert.equal(delivery.response_payload.receipts.length, 1);
    assert.equal(context.app.store.db.notification_deliveries.length, 1);
  } finally {
    await closeFixture(context);
  }
});

test('health reports push backlog separately from device delivery', async () => {
  const context = await fixture(async () => ({ statusCode: 200, apnsId: 'accepted-health' }));
  try {
    const before = await requestJson(context.baseUrl, '/health');
    assert.equal(before.response.status, 200);
    assert.equal(before.body.push_metrics.queued, 1);
    assert.equal(before.body.push_metrics.sent, 0);
    assert.equal(before.body.push_metrics.delivered, 0);
    assert.equal(before.body.push_metrics.opened, 0);

    await context.app.dispatchQueuedPushDeliveries();
    const after = await requestJson(context.baseUrl, '/health');
    assert.equal(after.body.push_metrics.queued, 0);
    assert.equal(after.body.push_metrics.sent, 1);
    assert.equal(after.body.push_metrics.delivered, 0);
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

test('re-registering the same APNs token revokes stale installs and queues one delivery', async () => {
  const context = await fixture(async () => ({ statusCode: 200, apnsId: 'accepted-once' }));
  try {
    const registration = await requestJson(context.baseUrl, '/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ phone: '13800138008', code: '246810' }),
    });
    const authorization = { Authorization: `Bearer ${registration.body.token}` };
    const second = await requestJson(context.baseUrl, '/api/v1/app/push-tokens', {
      method: 'POST',
      headers: authorization,
      body: JSON.stringify({
        family_id: context.familyID,
        app_install_id: 'ios-reinstalled',
        platform: 'ios',
        push_token: 'ab'.repeat(32),
        environment: 'sandbox',
      }),
    });
    assert.equal(second.response.status, 200);
    const matching = context.app.store.db.app_push_tokens.filter((token) => token.push_token_hash);
    assert.equal(matching.filter((token) => token.status === 'active').length, 1);
    assert.equal(matching.filter((token) => token.status === 'revoked').length, 1);

    const queued = await requestJson(context.baseUrl, '/api/v1/app/push-test', {
      method: 'POST',
      headers: authorization,
      body: JSON.stringify({ family_id: context.familyID }),
    });
    assert.equal(queued.response.status, 200);
    assert.equal(queued.body.deliveries.length, 1);
  } finally {
    await closeFixture(context);
  }
});

test('ops notification test targets the latest production install exactly once per request', async () => {
  const sentRequests = [];
  const context = await fixture(async (request) => {
    sentRequests.push(request);
    return { statusCode: 200, apnsId: `ops-${sentRequests.length}` };
  });
  try {
    const unauthorized = await requestJson(context.baseUrl, '/api/v1/internal/notifications/test', {
      method: 'POST',
      body: JSON.stringify({ family_id: context.familyID }),
    });
    assert.equal(unauthorized.response.status, 403);

    const opsAuthorization = { Authorization: 'Bearer test-ops-token' };
    const missingProductionToken = await requestJson(context.baseUrl, '/api/v1/internal/notifications/test', {
      method: 'POST',
      headers: opsAuthorization,
      body: JSON.stringify({ family_id: context.familyID }),
    });
    assert.equal(missingProductionToken.response.status, 409);

    const login = await requestJson(context.baseUrl, '/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ phone: '13800138008', code: '246810' }),
    });
    const appAuthorization = { Authorization: `Bearer ${login.body.token}` };
    for (const installation of [
      { id: 'ios-production-old', token: 'cd'.repeat(32) },
      { id: 'ios-production-current', token: 'ef'.repeat(32) },
    ]) {
      const registered = await requestJson(context.baseUrl, '/api/v1/app/push-tokens', {
        method: 'POST',
        headers: appAuthorization,
        body: JSON.stringify({
          family_id: context.familyID,
          app_install_id: installation.id,
          platform: 'ios',
          push_token: installation.token,
          environment: 'production',
        }),
      });
      assert.equal(registered.response.status, 200);
    }
    const oldToken = context.app.store.db.app_push_tokens.find((token) => token.app_install_id === 'ios-production-old');
    const currentToken = context.app.store.db.app_push_tokens.find((token) => token.app_install_id === 'ios-production-current');
    oldToken.last_seen_at = '2026-07-29T00:00:00.000Z';
    currentToken.last_seen_at = '2026-07-30T00:00:00.000Z';
    await context.app.store.save();

    const messageCount = context.app.store.db.app_messages.length;
    const deliveryCount = context.app.store.db.notification_deliveries.length;
    const first = await requestJson(context.baseUrl, '/api/v1/internal/notifications/test', {
      method: 'POST',
      headers: opsAuthorization,
      body: JSON.stringify({ family_id: context.familyID }),
    });
    assert.equal(first.response.status, 200);
    assert.equal(first.body.target.app_install_id, 'ios-production-current');
    assert.equal(first.body.target.environment, 'production');
    assert.equal(first.body.deliveries.length, 1);
    assert.equal(first.body.deliveries[0].status, 'sent');
    assert.deepEqual(first.body.dispatch, { attempted: 1, sent: 1, failed: 0 });
    assert.equal(context.app.store.db.app_messages.length, messageCount + 1);
    assert.equal(context.app.store.db.notification_deliveries.length, deliveryCount + 1);
    assert.equal(sentRequests.length, 1);
    assert.equal(sentRequests[0].environment, 'production');
    const firstMessage = context.app.store.db.app_messages.find((message) => message.message_id === first.body.message.message_id);
    assert.equal(firstMessage.generated_by, 'ops-notification-test');
    assert.equal(firstMessage.event_id, '');
    assert.equal(firstMessage.metadata.target_install_id, 'ios-production-current');
    assert.equal(JSON.stringify(first.body).includes('v1:opaque-encrypted-token'), false);

    const second = await requestJson(context.baseUrl, '/api/v1/internal/notifications/test', {
      method: 'POST',
      headers: opsAuthorization,
      body: JSON.stringify({ family_id: context.familyID }),
    });
    assert.equal(second.response.status, 200);
    assert.notEqual(second.body.request_id, first.body.request_id);
    assert.notEqual(second.body.message.message_id, first.body.message.message_id);
    assert.equal(context.app.store.db.app_messages.length, messageCount + 2);
    assert.equal(context.app.store.db.notification_deliveries.length, deliveryCount + 2);
    assert.equal(sentRequests.length, 2);
  } finally {
    await closeFixture(context);
  }
});
