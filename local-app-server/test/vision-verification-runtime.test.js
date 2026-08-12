const assert = require('node:assert/strict');
const test = require('node:test');

const {
  providerFailure,
  verificationRetryDelaySeconds,
} = require('../vision-verification-runtime');

test('provider transport failures retain a safe cause code and remain retryable', () => {
  const cause = Object.assign(new Error('other side closed'), { code: 'UND_ERR_SOCKET' });
  const error = new TypeError('fetch failed', { cause });

  const failure = providerFailure(error);

  assert.equal(failure.retryable, true);
  assert.equal(failure.message, 'vision verification transport failed [UND_ERR_SOCKET]');
  assert.equal(failure.provider_status, null);
  assert.equal(failure.provider_code, 'UND_ERR_SOCKET');
  assert.equal(failure.message.includes('http'), false);
});

test('provider HTTP failures retry only throttling, timeout and server responses', () => {
  const badRequest = providerFailure(null, { status: 400, detail: 'invalid video input' });
  const throttled = providerFailure(null, { status: 429, detail: 'rate limit' });
  const unavailable = providerFailure(null, { status: 503, detail: 'unavailable' });

  assert.equal(badRequest.retryable, false);
  assert.equal(badRequest.message, 'vision verification failed: 400 invalid video input');
  assert.equal(throttled.retryable, true);
  assert.equal(unavailable.retryable, true);
});

test('verification transport retries remain bounded while covering a short outage', () => {
  assert.deepEqual(
    [1, 2, 3, 4].map(verificationRetryDelaySeconds),
    [5, 15, 30, 60],
  );
  assert.equal(verificationRetryDelaySeconds(99), 60);
});
