const assert = require('node:assert/strict');
const test = require('node:test');
const { factSignals, validateCareModelOutput } = require('../care-card-contract');

test('care model can only cite facts issued by the server', () => {
  const signals = factSignals([
    { type: 'visit_interval', text: '距离上次回家已经 12 天。', title: '这个周末，留一点时间回家' },
    { type: 'weather', text: '杭州今天多云，28°C。', title: '多云天，问问晚饭吃什么' },
  ]);
  const accepted = validateCareModelOutput({
    primary_fact_id: 'fact-2',
    supporting_fact_ids: ['fact-1'],
  }, signals);
  assert.deepEqual(accepted.fact_ids, ['fact-2', 'fact-1']);
  assert.equal(accepted.facts[0].text, '杭州今天多云，28°C。');

  assert.equal(validateCareModelOutput({
    primary_fact_id: 'invented-fact',
    supporting_fact_ids: [],
  }, signals), null);
  assert.equal(validateCareModelOutput({
    primary_fact_id: 'fact-1',
    title: '模型试图写入用户文案',
  }, signals), null);
});
