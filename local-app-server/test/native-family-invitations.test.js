const assert = require('node:assert/strict');
const crypto = require('node:crypto');
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

async function request(baseURL, pathname, { method = 'GET', token = '', body } = {}) {
  const response = await fetch(`${baseURL}${pathname}`, {
    method,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const text = await response.text();
  return { response, body: text ? JSON.parse(text) : null };
}

async function register(baseURL, suffix, name) {
  const result = await request(baseURL, '/api/auth/register', {
    method: 'POST',
    body: { phone: `13800139${String(suffix).padStart(3, '0')}`, code: '246810', display_name: name },
  });
  assert.equal(result.response.status, 200, JSON.stringify(result.body));
  return result.body;
}

async function createFamily(baseURL, token, name) {
  const result = await request(baseURL, '/api/families', { method: 'POST', token, body: { name } });
  assert.equal(result.response.status, 200, JSON.stringify(result.body));
  assert.equal(result.body.join_code, undefined);
  return result.body;
}

async function createInvitation(baseURL, token, familyID) {
  return request(baseURL, `/api/v2/families/${familyID}/invitations`, {
    method: 'POST', token, body: { expires_in_minutes: 10 },
  });
}

test('family invitations are short-lived, hash-only, revocable, one-time, and atomic', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-family-invitations-'));
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'), dataDir, authMode: 'demo', demoOtp: '246810',
  });
  const baseURL = await listen(app.server);
  try {
    const owner = await register(baseURL, 1, '创建者');
    const member = await register(baseURL, 2, '成员');
    const candidateA = await register(baseURL, 3, '候选甲');
    const candidateB = await register(baseURL, 4, '候选乙');
    const family = await createFamily(baseURL, owner.token, '安全邀请验收');
    const familyID = String(family.id);

    const first = await createInvitation(baseURL, owner.token, familyID);
    assert.equal(first.response.status, 201, JSON.stringify(first.body));
    assert.match(first.body.code, /^GH-[23456789ABCDEFGHJKMNPQRSTVWXYZ]{4}(?:-[23456789ABCDEFGHJKMNPQRSTVWXYZ]{4}){2}$/);
    assert.equal(JSON.stringify(app.store.db).includes(first.body.code), false);
    const stored = app.store.db.family_invitations.find((item) => item.id === first.body.id);
    assert.equal(stored.code_hash, crypto.createHash('sha256').update(first.body.code).digest('hex'));
    assert.equal(stored.code, undefined);

    const listed = await request(baseURL, `/api/v2/families/${familyID}/invitations`, { token: owner.token });
    assert.equal(listed.response.status, 200);
    assert.equal(listed.body.invitations[0].code, undefined);
    assert.equal(listed.body.invitations[0].code_hash, undefined);

    const joined = await request(baseURL, '/api/v2/family-invitations/consume', {
      method: 'POST', token: member.token, body: { code: first.body.code },
    });
    assert.equal(joined.response.status, 200, JSON.stringify(joined.body));
    assert.equal(joined.body.joined, true);
    assert.equal(String(joined.body.family.id), familyID);

    const reused = await request(baseURL, '/api/v2/family-invitations/consume', {
      method: 'POST', token: candidateA.token, body: { code: first.body.code },
    });
    assert.equal(reused.response.status, 404);

    const denied = await createInvitation(baseURL, member.token, familyID);
    assert.equal(denied.response.status, 403);

    const activeForExistingMember = await createInvitation(baseURL, owner.token, familyID);
    const existingMember = await request(baseURL, '/api/v2/family-invitations/consume', {
      method: 'POST', token: member.token, body: { code: activeForExistingMember.body.code },
    });
    assert.equal(existingMember.response.status, 409);
    assert.equal(app.store.db.family_invitations.find((item) => item.id === activeForExistingMember.body.id).status, 'active');

    const replacement = await createInvitation(baseURL, owner.token, familyID);
    assert.equal(replacement.response.status, 201);
    assert.equal(app.store.db.family_invitations.find((item) => item.id === activeForExistingMember.body.id).status, 'revoked');
    const superseded = await request(baseURL, '/api/v2/family-invitations/consume', {
      method: 'POST', token: candidateA.token, body: { code: activeForExistingMember.body.code },
    });
    assert.equal(superseded.response.status, 404);

    const revoked = await request(baseURL, `/api/v2/families/${familyID}/invitations/${replacement.body.id}`, {
      method: 'DELETE', token: owner.token,
    });
    assert.equal(revoked.response.status, 200);
    assert.equal(revoked.body.status, 'revoked');
    const revokedUse = await request(baseURL, '/api/v2/family-invitations/consume', {
      method: 'POST', token: candidateA.token, body: { code: replacement.body.code },
    });
    assert.equal(revokedUse.response.status, 404);

    const expired = await createInvitation(baseURL, owner.token, familyID);
    app.store.db.family_invitations.find((item) => item.id === expired.body.id).expires_at = '2020-01-01T00:00:00.000Z';
    const expiredUse = await request(baseURL, '/api/v2/family-invitations/consume', {
      method: 'POST', token: candidateA.token, body: { code: expired.body.code },
    });
    assert.equal(expiredUse.response.status, 404);
    assert.equal(app.store.db.family_invitations.find((item) => item.id === expired.body.id).status, 'expired');

    const legacyDigest = crypto.createHash('sha256')
      .update(`${family.id}:${family.created_at || ''}:${family.name || ''}`)
      .digest('hex').slice(0, 6).toUpperCase();
    const legacy = await request(baseURL, '/api/families/join', {
      method: 'POST', token: candidateA.token, body: { code: `GH-${familyID}-${legacyDigest}` },
    });
    assert.equal(legacy.response.status, 404);

    const concurrentFamily = await createFamily(baseURL, owner.token, '并发邀请验收');
    const concurrentInvitation = await createInvitation(baseURL, owner.token, String(concurrentFamily.id));
    const results = await Promise.all([candidateA, candidateB].map((candidate) => request(
      baseURL,
      '/api/v2/family-invitations/consume',
      { method: 'POST', token: candidate.token, body: { code: concurrentInvitation.body.code } },
    )));
    assert.deepEqual(results.map((result) => result.response.status).sort(), [200, 404]);
    const winners = app.store.db.family_members.filter((item) => (
      String(item.family_id) === String(concurrentFamily.id)
      && [String(candidateA.user.id), String(candidateB.user.id)].includes(String(item.user_id))
      && item.status === 'active'
    ));
    assert.equal(winners.length, 1);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
