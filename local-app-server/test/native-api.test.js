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

async function json(response) {
  const body = await response.json();
  assert.equal(response.ok, true, JSON.stringify(body));
  return body;
}

test('native bootstrap and home are session-scoped, modular, sourced, and cacheable', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gohome-native-api-'));
  let repositoryUserId = null;
  const nativeRepository = {
    async bootstrapForUser(userId) {
      repositoryUserId = String(userId);
      return {
        user: { id: String(userId), phone: '13800138001' },
        families: [{ id: 'family-native', name: 'Home' }],
        active_family_id: 'family-native',
        onboarding: { next_step: 'complete', complete: true },
        unread_count: 2,
      };
    },
    async homeForFamily(userId, familyId) {
      assert.equal(String(userId), repositoryUserId);
      assert.equal(familyId, 'family-native');
      return {
        family: { id: familyId, name: 'Home' },
        weather: { city: '上海', temperature: 28, condition: '晴' },
        calendar: [{ id: 'calendar-1', title: '周末', starts_at: '2026-07-25T00:00:00.000Z' }],
        distance: { meters: 12800, travel_minutes: 35 },
        critical_alert: {
          id: 'alert-1',
          summary: '客厅出现需要确认的情况',
          level: 'critical',
          acknowledged: false,
          payload: { raw_pose_evidence: 'must-not-leak-to-home' },
        },
        care_message: {
          message_id: 'return-home-family-native-1',
          message_type: 'return_home',
          title: '找个轻松的话题聊聊',
          subtitle: '根据最近的联系节奏整理',
          body: '今天可以从公园夜游聊起。',
          facts: ['距离上次联系已有一段时间'],
          actions: [{ key: 'shared', label: '分享' }],
          status: 'open',
          metadata: {
            trigger_reason: 'days_since_last_visit',
            topics: ['公园夜游', '周末安排'],
            message_variants: ['最近公园开放夜游了，周末想不想一起去看看？'],
          },
          created_at: '2026-07-23T08:00:00.000Z',
        },
        cameras: [{ id: 'camera-1', name: '客厅' }],
        articles: [
          { id: 'article-1', title: '城市公园本周开放夜游', url: 'https://news.example.com/a', source_name: '城市发布' },
          { id: 'article-2', title: 'No trusted source', url: 'http://unsafe.example.com/a', source_name: 'Unknown' },
        ],
      };
    },
  };
  const app = createLocalAppServer({
    rootDir: path.join(__dirname, '..', '..'),
    dataDir,
    authMode: 'demo',
    demoOtp: '246810',
    nativeRepository,
  });
  const baseUrl = await listen(app.server);
  try {
    const registration = await json(await fetch(`${baseUrl}/api/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: '13800138001', code: '246810' }),
    }));
    const authorization = { Authorization: `Bearer ${registration.token}` };

    const bootstrapResponse = await fetch(`${baseUrl}/api/v2/app/bootstrap`, { headers: authorization });
    const bootstrap = await json(bootstrapResponse);
    assert.deepEqual(Object.keys(bootstrap).sort(), [
      'active_family_id', 'families', 'onboarding', 'revision', 'unread_count', 'user',
    ]);
    assert.equal(bootstrap.onboarding.next_step, 'complete');
    assert.equal(bootstrap.unread_count, 2);
    const etag = bootstrapResponse.headers.get('etag');
    assert.ok(etag);

    const unchanged = await fetch(`${baseUrl}/api/v2/app/bootstrap`, {
      headers: { ...authorization, 'If-None-Match': etag },
    });
    assert.equal(unchanged.status, 304);

    const home = await json(await fetch(`${baseUrl}/api/v2/home?family_id=family-native`, { headers: authorization }));
    assert.deepEqual(home.weather, { city: '上海', temperature: 28, condition: '晴' });
    assert.equal(home.calendar.length, 1);
    assert.equal(home.distance.meters, 12800);
    assert.deepEqual(home.critical_alert, {
      id: 'alert-1',
      title: '客厅出现需要确认的情况',
      level: 'critical',
      acknowledged: false,
    });
    assert.equal(JSON.stringify(home).includes('raw_pose_evidence'), false);
    assert.equal(home.care_message.message_id, 'return-home-family-native-1');
    assert.deepEqual(home.care_message.metadata.topics, ['公园夜游', '周末安排']);
    assert.deepEqual(home.care_message.actions, [{ type: 'shared', label: '分享' }]);
    assert.equal(home.articles.length, 1);
    assert.equal(home.articles[0].source_url, 'https://news.example.com/a');

    const globalToken = await fetch(`${baseUrl}/api/v2/app/bootstrap`, {
      headers: { Authorization: `Bearer ${app.appToken}` },
    });
    assert.equal(globalToken.status, 401);
  } finally {
    await new Promise((resolve) => app.server.close(resolve));
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
