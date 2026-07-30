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

async function register(baseURL, phone, displayName) {
  const result = await request(baseURL, '/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ phone, code: '246810', display_name: displayName }),
  });
  assert.equal(result.response.status, 200);
  return { token: result.body.token, headers: { Authorization: `Bearer ${result.body.token}` } };
}

test('video privacy is one family state shared by app playback and the edge device', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-video-privacy-'));
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'),
    dataDir,
    authMode: 'demo',
    demoOtp: '246810',
  });
  const baseURL = await listen(app.server);
  try {
    const owner = await register(baseURL, '13800138201', '创建者');
    const familyResult = await request(baseURL, '/api/families', {
      method: 'POST', headers: owner.headers, body: JSON.stringify({ name: '隐私同步家庭' }),
    });
    const familyID = String(familyResult.body.id);
    const invitation = await request(baseURL, `/api/v2/families/${familyID}/invitations`, {
      method: 'POST', headers: owner.headers, body: JSON.stringify({ expires_in_minutes: 10 }),
    });
    assert.equal(invitation.response.status, 201);
    const member = await register(baseURL, '13800138202', '家庭成员');
    await request(baseURL, '/api/families/join', {
      method: 'POST', headers: member.headers, body: JSON.stringify({ code: invitation.body.code }),
    });

    const deviceID = 'edge-video-privacy';
    const deviceToken = 'edge-video-privacy-token';
    app.store.db.devices[deviceID] = {
      id: deviceID, device_id: deviceID, family_id: familyID, name: '隐私盒子', status: 'online',
    };
    app.store.db.device_bindings.push({
      id: 'binding-video-privacy', family_id: Number(familyID), device_id: deviceID,
      device_name: '隐私盒子', status: 'active', bound_at: new Date().toISOString(),
    });
    app.store.db.device_tokens.push({
      id: 'token-video-privacy', token: deviceToken, device_id: deviceID,
      family_id: Number(familyID), status: 'active', created_at: new Date().toISOString(),
    });

    const camera = await request(baseURL, '/api/cameras', {
      method: 'POST', headers: owner.headers,
      body: JSON.stringify({
        family_id: familyID,
        device_id: deviceID,
        name: '客厅主视',
        room: '客厅',
        stream_url: 'rtsp://192.168.1.8:554/1/2',
      }),
    });
    assert.equal(camera.response.status, 200);

    const initial = await request(baseURL, `/api/v1/families/${familyID}/video-privacy`, {
      headers: owner.headers,
    });
    assert.equal(initial.response.status, 200);
    assert.equal(initial.body.minimum_mode, 'original');
    assert.equal(initial.body.can_manage, true);

    const denied = await request(baseURL, `/api/v1/families/${familyID}/video-privacy`, {
      method: 'PUT', headers: member.headers, body: JSON.stringify({ minimum_mode: 'skeleton' }),
    });
    assert.equal(denied.response.status, 403);

    const updated = await request(baseURL, `/api/v1/families/${familyID}/video-privacy`, {
      method: 'PUT', headers: owner.headers, body: JSON.stringify({ minimum_mode: 'skeleton' }),
    });
    assert.equal(updated.response.status, 200);
    assert.equal(updated.body.minimum_mode, 'skeleton');

    const deviceConfig = await request(baseURL, '/api/v1/device/config', {
      headers: { Authorization: `Bearer ${deviceToken}` },
    });
    assert.equal(deviceConfig.response.status, 200);
    assert.equal(deviceConfig.body.video_privacy.minimum_mode, 'skeleton');

    const devicePrivacy = await request(baseURL, '/api/v1/device/video-privacy', {
      headers: { Authorization: `Bearer ${deviceToken}` },
    });
    assert.equal(devicePrivacy.response.status, 200);
    assert.equal(devicePrivacy.body.minimum_mode, 'skeleton');

    const playback = await request(baseURL, '/api/v1/video/sessions', {
      method: 'POST', headers: owner.headers,
      body: JSON.stringify({
        resource_type: 'stream',
        camera_id: String(camera.body.id),
        profile: 'mobile',
        privacy_mode: 'original',
      }),
    });
    assert.equal(playback.response.status, 200);
    assert.equal(playback.body.privacy_mode, 'skeleton');
    assert.equal(playback.body.minimum_privacy_mode, 'skeleton');
    assert.equal(playback.body.display_transport, 'safe-scene-pose-v1');
    assert.equal(playback.body.pose_stream_path, `/api/v1/video/cameras/${camera.body.id}/pose-stream`);
    assert.equal(playback.body.scene_stream_path, `/api/v1/video/cameras/${camera.body.id}/scene.mjpg`);

    const posePacket = {
      schema_version: 'eacp-pose-relay-v1',
      camera_id: 24,
      frame_id: 'frame-100',
      captured_at: new Date().toISOString(),
      state: 'observed',
      source: 'observed',
      image_width: 640,
      image_height: 360,
      poses: [{
        track_id: 'person-1',
        confidence: 0.91,
        bbox: [120, 20, 400, 350],
        keypoints: [{ name: 'nose', x: 220, y: 60, confidence: 0.95, visible: true }],
      }],
      display_only: true,
      formal_evidence_eligible: false,
    };
    const poseUpload = await request(
      baseURL,
      `/api/v1/device/live-poses/upload?camera_id=${camera.body.id}&local_camera_id=24`,
      {
        method: 'POST',
        headers: { Authorization: `Bearer ${deviceToken}` },
        body: JSON.stringify(posePacket),
      },
    );
    assert.equal(poseUpload.response.status, 200);
    assert.equal(poseUpload.body.frame_id, 'frame-100');

    const unsafePose = await request(
      baseURL,
      `/api/v1/device/live-poses/upload?camera_id=${camera.body.id}&local_camera_id=24`,
      {
        method: 'POST',
        headers: { Authorization: `Bearer ${deviceToken}` },
        body: JSON.stringify({ ...posePacket, formal_evidence_eligible: true }),
      },
    );
    assert.equal(unsafePose.response.status, 400);

    const jpeg = Buffer.from([0xff, 0xd8, 0x12, 0x34, 0xff, 0xd9]);
    const sceneUpload = await fetch(
      `${baseURL}/api/v1/device/live-scenes/upload?camera_id=${camera.body.id}&local_camera_id=24`,
      {
        method: 'POST',
        headers: { Authorization: `Bearer ${deviceToken}`, 'Content-Type': 'image/jpeg' },
        body: jpeg,
      },
    );
    assert.equal(sceneUpload.status, 200);

    const playbackQuery = `playback_ticket=${encodeURIComponent(playback.body.ticket)}&privacy_mode=skeleton`;
    const poseStream = await fetch(`${baseURL}${playback.body.pose_stream_path}?${playbackQuery}`);
    assert.equal(poseStream.status, 200);
    assert.match(poseStream.headers.get('content-type') || '', /^text\/event-stream/);
    const poseReader = poseStream.body.getReader();
    const poseChunk = await poseReader.read();
    assert.match(Buffer.from(poseChunk.value).toString('utf8'), /"frame_id":"frame-100"/);
    await poseReader.cancel();

    const sceneStream = await fetch(`${baseURL}${playback.body.scene_stream_path}?${playbackQuery}`);
    assert.equal(sceneStream.status, 200);
    assert.equal(sceneStream.headers.get('x-gohome-stream-state'), 'safe_scene_relay');
    const sceneReader = sceneStream.body.getReader();
    const sceneChunk = await sceneReader.read();
    const sceneBytes = Buffer.from(sceneChunk.value);
    assert.ok(sceneBytes.includes(jpeg));
    await sceneReader.cancel();

    const upload = await fetch(
      `${baseURL}/api/v1/device/live-frames/upload?camera_id=${camera.body.id}&local_camera_id=24&privacy_mode=original&stream_epoch_ms=1000&sequence=2`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${deviceToken}`,
          'Content-Type': 'image/jpeg',
        },
        body: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
      },
    );
    assert.equal(upload.status, 200);
    const uploadBody = await upload.json();
    assert.equal(uploadBody.received_privacy_mode, 'original');
    assert.equal(uploadBody.requested_privacy_mode, 'skeleton');
    assert.equal(uploadBody.accepted, true);
    assert.equal(uploadBody.source_sequence, 2);

    const staleUpload = await fetch(
      `${baseURL}/api/v1/device/live-frames/upload?camera_id=${camera.body.id}&local_camera_id=24&privacy_mode=original&stream_epoch_ms=1000&sequence=1`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${deviceToken}`,
          'Content-Type': 'image/jpeg',
        },
        body: Buffer.from([0xff, 0xd8, 0x01, 0xff, 0xd9]),
      },
    );
    assert.equal(staleUpload.status, 200);
    const staleUploadBody = await staleUpload.json();
    assert.equal(staleUploadBody.accepted, false);
    assert.equal(staleUploadBody.stale_ignored, true);
    assert.equal(staleUploadBody.source_sequence, 2);

    const nextSessionUpload = await fetch(
      `${baseURL}/api/v1/device/live-frames/upload?camera_id=${camera.body.id}&local_camera_id=24&privacy_mode=original&stream_epoch_ms=1001&sequence=1`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${deviceToken}`,
          'Content-Type': 'image/jpeg',
        },
        body: Buffer.from([0xff, 0xd8, 0x02, 0xff, 0xd9]),
      },
    );
    assert.equal(nextSessionUpload.status, 200);
    const nextSessionUploadBody = await nextSessionUpload.json();
    assert.equal(nextSessionUploadBody.accepted, true);
    assert.equal(nextSessionUploadBody.stream_epoch_ms, 1001);
    assert.equal(nextSessionUploadBody.source_sequence, 1);

    const health = await request(baseURL, '/health');
    assert.equal(health.response.status, 200);
    const streamMetric = health.body.stream_metrics.cameras[String(camera.body.id)];
    assert.ok(streamMetric.accepted_fps_10s > 0);
    assert.equal(streamMetric.stale_rejections, 1);
    assert.ok(streamMetric.transport_latency_ms_max >= streamMetric.transport_latency_ms_p95);
    assert.deepEqual(health.body.stream_metrics.active_clients, { video: 0, pose: 0, scene: 0 });

    const boxUpdated = await request(baseURL, '/api/v1/device/video-privacy', {
      method: 'PUT',
      headers: { Authorization: `Bearer ${deviceToken}` },
      body: JSON.stringify({ minimum_mode: 'person_blur' }),
    });
    assert.equal(boxUpdated.response.status, 200);
    assert.equal(boxUpdated.body.minimum_mode, 'person_blur');

    const appAfterBox = await request(baseURL, `/api/v1/families/${familyID}/video-privacy`, {
      headers: owner.headers,
    });
    assert.equal(appAfterBox.response.status, 200);
    assert.equal(appAfterBox.body.minimum_mode, 'person_blur');
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
