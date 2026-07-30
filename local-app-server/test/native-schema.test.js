const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const migrationPath = path.join(
  __dirname,
  '..',
  'migrations',
  '005_native_app.sql',
);

function readMigration() {
  assert.ok(
    fs.existsSync(migrationPath),
    'migration 005_native_app.sql should exist',
  );

  return fs
    .readFileSync(migrationPath, 'utf8')
    .toLowerCase()
    .replace(/\s+/g, ' ');
}

function tableDefinition(sql, tableName) {
  const pattern = new RegExp(
    `create table if not exists ${tableName} \\((.*?)\\); `,
  );
  const match = sql.match(pattern);

  assert.ok(match, `${tableName} table should be created`);

  return match[1];
}

test('native app migration defines family-owned message actions, product catalog, and preferences', () => {
  const sql = readMigration();

  assert.match(sql, /(?:^| )begin; /, 'migration should use begin');
  assert.match(sql, / commit;\s*$/, 'migration should end with commit');
  assert.match(
    sql,
    /create unique index if not exists app_messages_family_message_idx on app_messages \(family_id, message_id\)/,
  );

  const messageActions = tableDefinition(sql, 'app_message_actions');
  assert.match(messageActions, /id text primary key default gen_random_uuid\(\)::text/);
  assert.match(messageActions, /family_id text not null references families\(id\) on delete cascade/);
  assert.match(messageActions, /message_id text not null/);
  assert.doesNotMatch(
    messageActions,
    /message_id text not null references app_messages\(message_id\)/,
  );
  assert.match(
    messageActions,
    /constraint app_message_actions_family_message_fkey foreign key \(family_id, message_id\) references app_messages\(family_id, message_id\) on delete cascade/,
  );
  assert.match(messageActions, /user_id text references users\(id\) on delete set null/);
  assert.match(
    messageActions,
    /action_type text not null check \(action_type in \('opened', 'shared', 'contacted', 'snoozed', 'dismissed', 'returned_home'\)\)/,
  );
  assert.match(messageActions, /payload jsonb not null default '\{\}'::jsonb/);
  assert.match(messageActions, /idempotency_key text not null unique/);
  assert.match(messageActions, /created_at timestamptz not null default now\(\)/);

  const productCatalog = tableDefinition(sql, 'product_catalog');
  assert.match(productCatalog, /id text primary key default gen_random_uuid\(\)::text/);
  assert.match(productCatalog, /category text not null/);
  assert.match(productCatalog, /brand text not null default ''/);
  assert.match(productCatalog, /name text not null/);
  assert.match(productCatalog, /summary text not null default ''/);
  assert.match(productCatalog, /image_url text not null default ''/);
  assert.match(productCatalog, /source_name text not null default ''/);
  assert.match(productCatalog, /source_url text not null default ''/);
  assert.match(productCatalog, /suitability jsonb not null default '\[\]'::jsonb/);
  assert.match(productCatalog, /disclosure text not null default ''/);
  assert.match(productCatalog, /status text not null default 'draft'/);
  assert.match(productCatalog, /verified_at timestamptz/);
  assert.match(productCatalog, /created_at timestamptz not null default now\(\)/);
  assert.match(productCatalog, /updated_at timestamptz not null default now\(\)/);
  assert.match(
    productCatalog,
    /constraint product_catalog_suitability_array_check check \(jsonb_typeof\(suitability\) = 'array'\)/,
  );
  assert.match(
    productCatalog,
    /constraint product_catalog_status_check check \(status in \('draft', 'active', 'disabled'\)\)/,
  );
  assert.match(
    productCatalog,
    /constraint product_catalog_active_fields_check check \(\s*status <> 'active' or \(\s*btrim\(category\) <> '' and btrim\(brand\) <> '' and btrim\(name\) <> '' and btrim\(image_url\) <> '' and btrim\(image_url\) ~\* '\^https:\/\/\[\^\[:space:\]\]\+\$' and btrim\(source_name\) <> '' and btrim\(source_url\) <> '' and btrim\(source_url\) ~\* '\^https:\/\/\[\^\[:space:\]\]\+\$' and verified_at is not null\s*\)\s*\)/,
  );

  const preferences = tableDefinition(sql, 'product_preferences');
  assert.match(preferences, /family_id text primary key references families\(id\) on delete cascade/);
  assert.match(preferences, /categories jsonb not null default '\[\]'::jsonb/);
  assert.doesNotMatch(preferences, /category_preferences/);
  assert.match(preferences, /needs jsonb not null default '\[\]'::jsonb/);
  assert.match(preferences, /updated_by text references users\(id\) on delete set null/);
  assert.match(preferences, /updated_at timestamptz not null default now\(\)/);

  assert.match(sql, /create index if not exists app_message_actions_family_time_idx on app_message_actions \(family_id, created_at desc\)/);
  assert.match(sql, /create index if not exists app_message_actions_message_type_idx on app_message_actions \(message_id, action_type, created_at desc\)/);
  assert.match(sql, /create index if not exists product_catalog_status_category_idx on product_catalog \(status, category, verified_at desc\)/);
  assert.match(sql, /create index if not exists product_preferences_updated_at_idx on product_preferences \(updated_at desc\)/);
});
