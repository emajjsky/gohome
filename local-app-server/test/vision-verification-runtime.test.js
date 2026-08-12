const assert = require('node:assert/strict');
const test = require('node:test');

const {
  providerFailure,
  verificationDeadlineAt,
  verificationDeadlineReached,
  verificationNextAttemptAt,
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

test('verification deadline is measured from evidence readiness and expires at exactly 90 seconds', () => {
  const startedAt = '2026-08-12T14:10:30.000Z';
  const deadlineAt = verificationDeadlineAt(startedAt);

  assert.equal(deadlineAt, '2026-08-12T14:12:00.000Z');
  assert.equal(verificationDeadlineReached(deadlineAt, Date.parse('2026-08-12T14:11:59.999Z')), false);
  assert.equal(verificationDeadlineReached(deadlineAt, Date.parse('2026-08-12T14:12:00.000Z')), true);
});

test('provider retries are scheduled only when they can start before the verification deadline', () => {
  const deadlineAt = '2026-08-12T14:12:00.000Z';

  assert.equal(verificationNextAttemptAt({
    attempt: 1,
    deadlineAt,
    nowMs: Date.parse('2026-08-12T14:10:40.000Z'),
  }), '2026-08-12T14:10:45.000Z');
  assert.equal(verificationNextAttemptAt({
    attempt: 3,
    deadlineAt,
    nowMs: Date.parse('2026-08-12T14:11:30.000Z'),
  }), '');
});
