const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const sql = fs.readFileSync(path.join(__dirname, '..', 'migrations', '007_family_memories.sql'), 'utf8')
  .toLowerCase()
  .replace(/\s+/g, ' ');

function table(name) {
  const match = sql.match(new RegExp(`create table if not exists ${name} \\((.*?)\\); `));
  assert.ok(match, `${name} table should exist`);
  return match[1];
}

test('family memory migration keeps all records family-owned and cascade-safe', () => {
  assert.match(sql, /(?:^| )begin; /);
  assert.match(sql, / commit;\s*$/);

  const memories = table('family_memories');
  assert.match(memories, /family_id text not null references families\(id\) on delete cascade/);
  assert.match(memories, /author_user_id text not null references users\(id\) on delete restrict/);
  assert.match(memories, /visibility text not null default 'family'/);
  assert.match(memories, /constraint family_memories_people_array_check check \(jsonb_typeof\(people\) = 'array'\)/);

  const media = table('family_memory_media');
  assert.match(media, /memory_id text not null references family_memories\(id\) on delete cascade/);
  assert.match(media, /asset_id text not null references media_assets\(id\) on delete restrict/);
  assert.match(media, /unique \(memory_id, sort_order\)/);

  const comments = table('family_memory_comments');
  assert.match(comments, /memory_id text not null references family_memories\(id\) on delete cascade/);
  assert.match(comments, /char_length\(body\) <= 500/);

  const favorites = table('family_memory_favorites');
  assert.match(favorites, /primary key \(memory_id, user_id\)/);
  assert.match(sql, /family_memories_family_time_idx/);
});
