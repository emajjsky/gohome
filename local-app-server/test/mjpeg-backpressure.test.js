const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const test = require('node:test');
const { createLatestFrameMjpegWriter } = require('../server');

class SlowResponse extends EventEmitter {
  constructor(writeResults) {
    super();
    this.writeResults = [...writeResults];
    this.writes = [];
    this.destroyed = false;
    this.writableEnded = false;
  }

  write(data) {
    this.writes.push(Buffer.from(data));
    return this.writeResults.shift() ?? true;
  }
}

function relayFrame(key, marker) {
  return {
    key,
    frame: Buffer.from([0xff, 0xd8, marker, 0xff, 0xd9]),
    contentType: 'image/jpeg',
    capturedAt: `2026-07-22T22:00:0${marker}.000Z`,
    source: 'live',
    assetId: '',
  };
}

test('MJPEG relay drops stale frames while a slow client applies backpressure', () => {
  const response = new SlowResponse([false, true]);
  let latest = relayFrame('frame-1', 1);
  const writer = createLatestFrameMjpegWriter(response, {
    boundary: 'test-boundary',
    getLatestFrame: () => latest,
  });

  assert.equal(writer.writeLatest({ force: true }), true);
  latest = relayFrame('frame-2', 2);
  assert.equal(writer.writeLatest(), false);
  latest = relayFrame('frame-3', 3);
  assert.equal(writer.writeLatest(), false);
  assert.equal(response.writes.length, 1);

  response.emit('drain');

  assert.equal(response.writes.length, 2);
  assert.match(response.writes[0].toString('latin1'), /Content-Length: 5/);
  assert.deepEqual(response.writes[0].subarray(-7), Buffer.from([0xff, 0xd8, 1, 0xff, 0xd9, 0x0d, 0x0a]));
  assert.deepEqual(response.writes[1].subarray(-7), Buffer.from([0xff, 0xd8, 3, 0xff, 0xd9, 0x0d, 0x0a]));

  writer.close();
  latest = relayFrame('frame-4', 4);
  assert.equal(writer.writeLatest(), false);
  assert.equal(response.writes.length, 2);
});
