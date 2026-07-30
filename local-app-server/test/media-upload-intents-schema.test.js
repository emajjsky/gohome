const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const sql = fs.readFileSync(
  path.join(__dirname, '..', 'migrations', '009_media_upload_intents.sql'),
  'utf8',
).toLowerCase().replace(/\s+/g, ' ');

test('media upload intents are durable, family-owned, and expiry-indexed', () => {
  assert.match(sql, /(?:^| )begin; /);
  assert.match(sql, / commit;\s*$/);
  assert.match(sql, /create table if not exists media_upload_intents/);
  assert.match(sql, /asset_id text primary key/);
  assert.match(sql, /family_id text not null references families\(id\) on delete cascade/);
  assert.match(sql, /user_id text not null references users\(id\) on delete cascade/);
  assert.match(sql, /object_key text not null unique/);
  assert.match(sql, /object_key like 'memory-media\/%'/);
  assert.match(sql, /expires_at timestamptz not null/);
  assert.match(sql, /media_upload_intents_expiry_idx/);
});
