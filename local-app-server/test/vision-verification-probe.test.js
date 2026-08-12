const assert = require('node:assert/strict');
const test = require('node:test');

const {
  PROBE_DEVICE_ID,
  PROBE_DEVICE_TOKEN,
  registerProbeDevice,
} = require('../../scripts/verify-vision-verification-live');

test('live verification probe registers one device identity for media and events', () => {
  const app = { store: { db: { devices: {}, device_tokens: [] } } };

  registerProbeDevice(app);

  assert.equal(app.store.db.devices[PROBE_DEVICE_ID].device_id, PROBE_DEVICE_ID);
  assert.equal(app.store.db.device_tokens.length, 1);
  assert.equal(app.store.db.device_tokens[0].token, PROBE_DEVICE_TOKEN);
  assert.equal(app.store.db.device_tokens[0].device_id, PROBE_DEVICE_ID);
  assert.equal(app.store.db.device_tokens[0].status, 'active');
});
