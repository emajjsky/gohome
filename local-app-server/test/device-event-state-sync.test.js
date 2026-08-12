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

test('app event acknowledgement is delivered to the edge exactly once', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-event-state-sync-'));
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'),
    dataDir,
    authMode: 'demo',
    demoOtp: '246810',
  });
  const baseURL = await listen(app.server);
  try {
    const registration = await request(baseURL, '/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ phone: '13800138301', code: '246810', display_name: '事件同步测试' }),
    });
    assert.equal(registration.response.status, 200);
    const appHeaders = { Authorization: `Bearer ${registration.body.token}` };
    const family = await request(baseURL, '/api/families', {
      method: 'POST', headers: appHeaders, body: JSON.stringify({ name: '事件同步家庭' }),
    });
    assert.equal(family.response.status, 200);

    const deviceID = 'edge-event-state-sync';
    const deviceToken = 'edge-event-state-sync-token';
    const familyID = String(family.body.id);
    app.store.db.devices[deviceID] = {
      id: deviceID, device_id: deviceID, family_id: familyID, name: '事件同步盒子', status: 'online', metadata: {},
    };
    app.store.db.device_tokens.push({
      id: 'token-event-state-sync', token: deviceToken, device_id: deviceID,
      family_id: Number(familyID), status: 'active', created_at: new Date().toISOString(),
    });
    app.store.db.cameras['401'] = {
      id: 401, family_id: familyID, device_id: deviceID, name: '客厅', room: '客厅', enabled: true,
    };
    const timestamp = new Date().toISOString();
    app.store.db.events.push({
      id: 900,
      family_id: familyID,
      device_id: deviceID,
      camera_id: 401,
      edge_event_id: '2177',
      idempotency_key: 'edge-event-state-sync:2177',
      event_type: 'fall_candidate',
      level: 'critical',
      summary: '跌倒测试事件',
      room: '客厅',
      acknowledged: false,
      resolution: '',
      payload: {},
      occurred_at: timestamp,
      created_at: timestamp,
      updated_at: timestamp,
    });

    const acknowledged = await request(baseURL, '/api/v1/events/900', {
      method: 'PATCH',
      headers: appHeaders,
      body: JSON.stringify({ acknowledged: true, resolution: 'handled' }),
    });
    assert.equal(acknowledged.response.status, 200);
    assert.equal(acknowledged.body.acknowledged, true);

    const deviceHeaders = { Authorization: `Bearer ${deviceToken}` };
    const pendingConfig = await request(baseURL, '/api/v1/device/config', { headers: deviceHeaders });
    assert.equal(pendingConfig.response.status, 200);
    assert.equal(pendingConfig.body.event_state_commands.length, 1);
    const command = pendingConfig.body.event_state_commands[0];
    assert.equal(command.edge_event_id, '2177');
    assert.equal(command.state, 'resolved');
    assert.equal(command.resolution, 'handled');

    const sync = await request(baseURL, '/api/v1/device/sync', {
      method: 'POST',
      headers: deviceHeaders,
      body: JSON.stringify({
        device_id: deviceID,
        config_version: pendingConfig.body.config_version,
        status: { status: 'online', sync_status: 'healthy' },
        cameras: [],
        event_state_commands: [{
          command_id: command.command_id,
          edge_event_id: command.edge_event_id,
          state: command.state,
          resolution: command.resolution,
          status: 'applied',
        }],
      }),
    });
    assert.equal(sync.response.status, 200);
    assert.deepEqual(sync.body.config.event_state_commands, []);

    const stableConfig = await request(baseURL, '/api/v1/device/config', { headers: deviceHeaders });
    assert.deepEqual(stableConfig.body.event_state_commands, []);
    const receipts = app.store.db.devices[deviceID].metadata.event_state_command_receipts;
    assert.equal(receipts.length, 1);
    assert.equal(receipts[0].command_id, command.command_id);
    assert.equal(receipts[0].status, 'applied');
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});

test('app false-positive resolution atomically closes every event in the incident', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-incident-resolution-'));
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'),
    dataDir,
    authMode: 'demo',
    demoOtp: '246810',
  });
  const baseURL = await listen(app.server);
  try {
    const registration = await request(baseURL, '/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ phone: '13800138308', code: '246810', display_name: '关联事件测试' }),
    });
    const appHeaders = { Authorization: `Bearer ${registration.body.token}` };
    const family = await request(baseURL, '/api/families', {
      method: 'POST', headers: appHeaders, body: JSON.stringify({ name: '关联事件家庭' }),
    });
    const familyID = String(family.body.id);
    const timestamp = new Date().toISOString();
    for (const [id, cameraID] of [[910, 501], [911, 502]]) {
      app.store.db.cameras[String(cameraID)] = {
        id: cameraID, family_id: familyID, device_id: 'edge-incident', name: `摄像头${cameraID}`, room: '客厅', enabled: true,
      };
      app.store.db.events.push({
        id,
        family_id: familyID,
        device_id: 'edge-incident',
        camera_id: cameraID,
        edge_event_id: String(id),
        idempotency_key: `edge-incident:${id}`,
        event_type: 'fall_candidate',
        level: 'critical',
        summary: '关联跌倒事件',
        room: '客厅',
        acknowledged: false,
        resolution: '',
        payload: { incident: {
          incident_id: 'incident-two-cameras',
          primary_event_id: 910,
          status: 'suspected',
          source_event_ids: [910, 911],
          source_camera_ids: [501, 502],
        } },
        occurred_at: timestamp,
        created_at: timestamp,
        updated_at: timestamp,
      });
    }

    const resolved = await request(baseURL, '/api/v1/events/910', {
      method: 'PATCH',
      headers: appHeaders,
      body: JSON.stringify({ acknowledged: true, resolution: 'false_positive' }),
    });

    assert.equal(resolved.response.status, 200);
    const linked = app.store.db.events.filter((event) => event.payload.incident.incident_id === 'incident-two-cameras');
    assert.equal(linked.length, 2);
    assert.ok(linked.every((event) => event.acknowledged === true));
    assert.ok(linked.every((event) => event.resolution === 'false_positive'));
    assert.ok(linked.every((event) => event.payload.incident.status === 'rejected'));
    assert.ok(linked.every((event) => event.payload.manual_feedback.source === 'app_user'));
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});

test('confirmed camera reconnection closes the offline event and archives its reminder idempotently', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-camera-recovery-sync-'));
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'),
    dataDir,
    authMode: 'demo',
    demoOtp: '246810',
  });
  const baseURL = await listen(app.server);
  try {
    const registration = await request(baseURL, '/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ phone: '13800138302', code: '246810', display_name: '摄像头恢复测试' }),
    });
    assert.equal(registration.response.status, 200);
    const family = await request(baseURL, '/api/families', {
      method: 'POST',
      headers: { Authorization: `Bearer ${registration.body.token}` },
      body: JSON.stringify({ name: '摄像头恢复家庭' }),
    });
    assert.equal(family.response.status, 200);

    const familyID = String(family.body.id);
    const deviceID = 'edge-camera-recovery-sync';
    const deviceToken = 'edge-camera-recovery-sync-token';
    app.store.db.devices[deviceID] = {
      id: deviceID, device_id: deviceID, family_id: familyID, name: '恢复测试盒子', status: 'online', metadata: {},
    };
    app.store.db.device_tokens.push({
      id: 'token-camera-recovery-sync', token: deviceToken, device_id: deviceID,
      family_id: Number(familyID), status: 'active', created_at: new Date().toISOString(),
    });
    app.store.db.cameras['402'] = {
      id: 402, family_id: familyID, device_id: deviceID, name: '冰箱上摄像头', room: '客厅', enabled: true,
    };
    const timestamp = new Date().toISOString();
    app.store.db.events.push({
      id: 901,
      family_id: familyID,
      device_id: deviceID,
      camera_id: 402,
      edge_event_id: '2197',
      idempotency_key: 'edge-camera-recovery-sync:2197',
      event_type: 'camera_offline',
      level: 'critical',
      summary: '冰箱上摄像头持续无法连接',
      room: '客厅',
      acknowledged: false,
      resolution: '',
      payload: {},
      occurred_at: timestamp,
      created_at: timestamp,
      updated_at: timestamp,
    });
    app.store.db.app_messages.push({
      id: 'camera-offline-message-901',
      message_id: 'camera-offline-message-901',
      event_id: 901,
      family_id: familyID,
      source_event_ids: [901],
      status: 'open',
      metadata: {},
      created_at: timestamp,
      updated_at: timestamp,
    });

    const deviceHeaders = { Authorization: `Bearer ${deviceToken}` };
    const unconfirmed = await request(baseURL, '/api/v1/device/events/2197/state', {
      method: 'POST',
      headers: deviceHeaders,
      body: JSON.stringify({
        state: 'resolved', resolution: 'camera_reconnected', observed_at: timestamp,
        evidence: { schema_version: 'gohome-camera-recovery-v1', confirmed: false },
      }),
    });
    assert.equal(unconfirmed.response.status, 400);
    assert.equal(app.store.db.events.find((event) => event.id === 901).resolution, '');
    assert.equal(app.store.db.app_messages[0].status, 'open');

    const recoveredAt = new Date(Date.now() + 1000).toISOString();
    const recovered = await request(baseURL, '/api/v1/device/events/2197/state', {
      method: 'POST',
      headers: deviceHeaders,
      body: JSON.stringify({
        state: 'resolved', resolution: 'camera_reconnected', observed_at: recoveredAt,
        evidence: {
          schema_version: 'gohome-camera-recovery-v1', confirmed: true,
          failure_count: 3, duration_seconds: 16.2, recovered_at: recoveredAt,
        },
      }),
    });
    assert.equal(recovered.response.status, 200);
    assert.equal(recovered.body.event.acknowledged, true);
    assert.equal(recovered.body.event.resolution, 'camera_reconnected');
    assert.equal(recovered.body.event.payload.edge_recovery.evidence.failure_count, 3);
    assert.equal(app.store.db.app_messages[0].status, 'archived');
    assert.equal(app.store.db.app_messages[0].metadata.resolution, 'camera_reconnected');

    const repeated = await request(baseURL, '/api/v1/device/events/2197/state', {
      method: 'POST',
      headers: deviceHeaders,
      body: JSON.stringify({
        state: 'resolved', resolution: 'camera_reconnected', observed_at: recoveredAt,
        evidence: { schema_version: 'gohome-camera-recovery-v1', confirmed: true },
      }),
    });
    assert.equal(repeated.response.status, 200);
    assert.equal(repeated.body.duplicate, true);
    assert.equal(app.store.db.app_messages.filter((message) => message.status === 'archived').length, 1);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
