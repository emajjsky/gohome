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

async function request(baseURL, pathname, { method = 'GET', token = '', body } = {}) {
  const response = await fetch(`${baseURL}${pathname}`, {
    method,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  return { response, body: await response.json() };
}

async function register(baseURL, phone, name) {
  const result = await request(baseURL, '/api/auth/register', {
    method: 'POST', body: { phone, code: '246810', display_name: name },
  });
  assert.equal(result.response.status, 200, JSON.stringify(result.body));
  return result.body;
}

test('family management HTTP flow lists, protects, transfers, and leaves without deleting shared data', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-family-management-'));
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'), dataDir, authMode: 'demo', demoOtp: '246810',
  });
  const baseURL = await listen(app.server);
  try {
    const creator = await register(baseURL, '13800138701', '创建者');
    const member = await register(baseURL, '13800138702', '成员');
    const familyResult = await request(baseURL, '/api/families', {
      method: 'POST', token: creator.token, body: { name: '家庭管理验收' },
    });
    assert.equal(familyResult.response.status, 200, JSON.stringify(familyResult.body));
    const familyID = String(familyResult.body.id);
    assert.equal(familyResult.body.join_code, undefined);
    const invitation = await request(baseURL, `/api/v2/families/${familyID}/invitations`, {
      method: 'POST', token: creator.token, body: { expires_in_minutes: 10 },
    });
    assert.equal(invitation.response.status, 201, JSON.stringify(invitation.body));

    const joined = await request(baseURL, '/api/families/join', {
      method: 'POST', token: member.token, body: { code: invitation.body.code },
    });
    assert.equal(joined.response.status, 200, JSON.stringify(joined.body));

    const listed = await request(baseURL, `/api/v2/families/${familyID}/members`, { token: creator.token });
    assert.equal(listed.response.status, 200, JSON.stringify(listed.body));
    assert.equal(listed.body.members.length, 2);
    assert.equal(listed.body.members.some((item) => item.account_hint === '138****8702'), true);
    const target = listed.body.members.find((item) => !item.is_current_user);

    const denied = await request(baseURL, `/api/v2/families/${familyID}/members/${listed.body.members.find((item) => item.is_current_user).id}`, {
      method: 'DELETE', token: member.token,
    });
    assert.equal(denied.response.status, 403);

    const transferred = await request(baseURL, `/api/v2/families/${familyID}/ownership-transfer`, {
      method: 'POST', token: creator.token,
      body: { target_member_id: target.id, confirmation: 'TRANSFER_OWNERSHIP' },
    });
    assert.equal(transferred.response.status, 200, JSON.stringify(transferred.body));

    const after = await request(baseURL, `/api/v2/families/${familyID}/members`, { token: member.token });
    assert.equal(after.body.members.filter((item) => ['owner', 'creator'].includes(item.role)).length, 1);
    assert.equal(after.body.members.find((item) => item.user_id === String(member.user.id)).role, 'owner');

    const left = await request(baseURL, `/api/v2/families/${familyID}/leave`, { method: 'POST', token: creator.token });
    assert.deepEqual(left.body, { left: true, family_id: familyID });
    assert.equal(app.store.db.families.some((family) => String(family.id) === familyID), true);
    assert.equal(app.store.db.users.some((user) => String(user.id) === String(creator.user.id)), true);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
