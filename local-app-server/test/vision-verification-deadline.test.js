const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { createLocalAppServer } = require('../server');

function verificationEvent(id, status, deadlineAt) {
  const startedAt = new Date(Date.parse(deadlineAt) - 90_000).toISOString();
  return {
    id,
    idempotency_key: `edge-fall-${id}`,
    family_id: 1,
    device_id: 'edge-test',
    event_type: 'fall_candidate',
    summary: '客厅摄像头检测到疑似跌倒，已进入云端复核。',
    level: 'critical',
    room: '客厅',
    camera_id: 32,
    camera_name: '冰箱摄像头',
    occurred_at: startedAt,
    acknowledged: false,
    resolution: '',
    payload: {
      verification: {
        status,
        started_at: startedAt,
        deadline_at: deadlineAt,
        updated_at: startedAt,
      },
    },
    created_at: startedAt,
    updated_at: startedAt,
  };
}

function testApp() {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-vision-deadline-'));
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'),
    dataDir,
    authMode: 'demo',
    demoOtp: '246810',
    mediaUploadCleanupEnabled: false,
    apnsProvider: { configured: false, close() {} },
  });
  return { app, dataDir };
}

test('90-second verification deadline creates exactly one suspected notification', async () => {
  const { app, dataDir } = testApp();
  const deadlineAt = '2026-08-12T14:12:00.000Z';
  const event = verificationEvent(9001, 'retrying', deadlineAt);
  const job = {
    id: 9101,
    family_id: 1,
    purpose: 'vision_event_verification',
    output_status: 'retrying',
    metadata: {
      event_id: String(event.id),
      verification_started_at: event.payload.verification.started_at,
      verification_deadline_at: deadlineAt,
      next_attempt_at: deadlineAt,
    },
    created_at: event.created_at,
    updated_at: event.updated_at,
  };
  app.store.db.events.push(event);
  app.store.db.model_generation_jobs.push(job);
  try {
    const before = app.enforceVisionVerificationDeadlines(Date.parse('2026-08-12T14:11:59.999Z'));
    assert.equal(before.timed_out, 0);
    assert.equal(app.store.db.app_messages.length, 0);

    const atDeadline = app.enforceVisionVerificationDeadlines(Date.parse(deadlineAt));
    assert.deepEqual(atDeadline, { timed_out: 1, messages_created: 1, deliveries_created: 1 });
    assert.equal(event.payload.verification.status, 'timeout_suspected');
    assert.equal(event.payload.incident.status, 'suspected');
    assert.equal(event.payload.incident.notification.reason, 'verification_timeout_suspected');
    assert.equal(job.output_status, 'timed_out');
    assert.equal(job.metadata.next_attempt_at, '');
    assert.equal(app.store.db.app_messages.length, 1);
    assert.equal(app.store.db.notification_deliveries.length, 1);

    const repeated = app.enforceVisionVerificationDeadlines(Date.parse('2026-08-12T14:15:00.000Z'));
    assert.equal(repeated.timed_out, 0);
    assert.equal(app.store.db.app_messages.length, 1);
    assert.equal(app.store.db.notification_deliveries.length, 1);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});

test('definitive result before deadline never notifies and a late result never duplicates timeout notification', async () => {
  const { app, dataDir } = testApp();
  const deadlineAt = '2026-08-12T14:12:00.000Z';
  const safe = verificationEvent(9002, 'rejected', deadlineAt);
  const delayed = verificationEvent(9003, 'verifying', deadlineAt);
  app.store.db.events.push(safe, delayed);
  try {
    app.applyIncidentVerificationOutcome(safe);
    const beforeDeadline = app.enforceVisionVerificationDeadlines(Date.parse('2026-08-12T14:11:59.999Z'));
    assert.equal(beforeDeadline.timed_out, 0);
    assert.equal(app.store.db.app_messages.length, 0);

    app.enforceVisionVerificationDeadlines(Date.parse(deadlineAt));
    assert.equal(app.store.db.app_messages.length, 1);
    assert.equal(app.store.db.notification_deliveries.length, 1);

    delayed.payload.verification = {
      ...delayed.payload.verification,
      status: 'confirmed',
      decision: 'confirm',
      result: { result_level: 'confirmed', reason: '迟到结果确认同一人物快速下降并倒在地面。' },
      verified_at: '2026-08-12T14:12:05.000Z',
    };
    const lateOutcome = app.applyIncidentVerificationOutcome(delayed);
    assert.equal(lateOutcome.status, 'confirmed');
    assert.equal(delayed.payload.incident.status, 'confirmed');
    assert.equal(app.store.db.app_messages.length, 1);
    assert.equal(app.store.db.notification_deliveries.length, 1);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});

test('late no-danger result updates the archive without changing the timeout notification or creating a second delivery', async () => {
  const { app, dataDir } = testApp();
  const deadlineAt = '2026-08-12T14:12:00.000Z';
  const event = verificationEvent(9004, 'verifying', deadlineAt);
  app.store.db.events.push(event);
  try {
    app.enforceVisionVerificationDeadlines(Date.parse(deadlineAt));
    assert.equal(app.store.db.app_messages.length, 1);
    assert.equal(app.store.db.notification_deliveries.length, 1);
    event.payload.verification = {
      ...event.payload.verification,
      status: 'rejected',
      decision: 'downgrade',
      result: { result_level: 'no_danger', event_type: 'none', reason: '四帧显示主动坐下并停留在沙发。' },
      verified_at: '2026-08-12T14:12:08.000Z',
    };
    const outcome = app.applyIncidentVerificationOutcome(event);
    assert.equal(outcome.status, 'rejected');
    assert.equal(event.payload.incident.status, 'rejected');
    assert.equal(event.payload.incident.notification.reason, 'verification_timeout_suspected');
    assert.equal(app.store.db.app_messages.length, 1);
    assert.equal(app.store.db.notification_deliveries.length, 1);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
