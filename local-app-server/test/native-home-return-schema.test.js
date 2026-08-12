const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

test('home return migration defines explicit visits and plans without storing network addresses', () => {
  const sql = fs.readFileSync(path.join(__dirname, '..', 'migrations', '018_home_visits_and_return_plans.sql'), 'utf8').toLowerCase();
  assert.match(sql, /create table if not exists home_visits/);
  assert.match(sql, /unique \(family_id, user_id, visit_date\)/);
  assert.match(sql, /verification_method text not null check \(verification_method = 'public_network_match'\)/);
  assert.match(sql, /create table if not exists home_return_plans/);
  assert.match(sql, /unique \(family_id, user_id\)/);
  assert.doesNotMatch(sql, /ip_address|network_fingerprint|public_ip/);
});
