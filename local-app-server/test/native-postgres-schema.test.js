const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { promisify } = require('node:util');
const { execFile } = require('node:child_process');
const test = require('node:test');
const { Client } = require('pg');

const execFileAsync = promisify(execFile);
const databaseUrl =
  process.env.GOHOME_DATABASE_URL || process.env.DATABASE_URL || '';
const repoRoot = path.join(__dirname, '..', '..');
const migrationsDir = path.join(repoRoot, 'local-app-server', 'migrations');
const migrationRunner = path.join(repoRoot, 'scripts', 'apply-postgres-migrations.js');

function postgresSslConfig() {
  return process.env.GOHOME_DATABASE_SSL === '1' ||
    process.env.GOHOME_DATABASE_SSL === 'true'
    ? { rejectUnauthorized: false }
    : undefined;
}

function quoteIdentifier(value) {
  return `"${value.replaceAll('"', '""')}"`;
}

function copyNativeMigrations(targetDir) {
  const files = fs
    .readdirSync(migrationsDir)
    .filter((file) => /^(001|002|003|004|005)_.+\.sql$/.test(file))
    .sort();

  assert.deepEqual(
    files.map((file) => file.slice(0, 3)),
    ['001', '002', '003', '004', '005'],
  );

  for (const file of files) {
    fs.copyFileSync(path.join(migrationsDir, file), path.join(targetDir, file));
  }
}

async function runMigrations(targetDir, schemaName) {
  const pgOptions = [
    process.env.PGOPTIONS || '',
    `-c search_path=${schemaName},public`,
  ]
    .filter(Boolean)
    .join(' ');
  const { stdout } = await execFileAsync(
    process.execPath,
    [migrationRunner, '--migrations-dir', targetDir],
    {
      cwd: repoRoot,
      env: {
        ...process.env,
        GOHOME_DATABASE_URL: databaseUrl,
        PGOPTIONS: pgOptions,
      },
      maxBuffer: 1024 * 1024,
    },
  );

  return JSON.parse(stdout);
}

async function constraintDefinitions(client, schemaName, tableName) {
  const result = await client.query(
    `
      select constraint_name, pg_get_constraintdef(pg_constraint.oid) as definition
      from information_schema.table_constraints
      join pg_namespace
        on pg_namespace.nspname = table_constraints.constraint_schema
      join pg_class
        on pg_class.relname = table_constraints.table_name
       and pg_class.relnamespace = pg_namespace.oid
      join pg_constraint
        on pg_constraint.conrelid = pg_class.oid
       and pg_constraint.conname = table_constraints.constraint_name
      where table_constraints.constraint_schema = $1
        and table_constraints.table_name = $2
    `,
    [schemaName, tableName],
  );

  return Object.fromEntries(
    result.rows.map((row) => [row.constraint_name, row.definition]),
  );
}

async function assertCheckViolation(operation, message) {
  await assert.rejects(
    operation,
    (error) => error?.code === '23514',
    message,
  );
}

test(
  'native PostgreSQL schema is idempotent and enforces ownership and catalog checks',
  {
    skip: databaseUrl
      ? false
      : 'GOHOME_DATABASE_URL or DATABASE_URL is not set',
    timeout: 60000,
  },
  async () => {
    const schemaName = `gohome_native_test_${process.pid}_${crypto
      .randomBytes(6)
      .toString('hex')}`;
    const temporaryMigrations = fs.mkdtempSync(
      path.join(os.tmpdir(), 'gohome-native-migrations-'),
    );
    const client = new Client({
      connectionString: databaseUrl,
      ssl: postgresSslConfig(),
    });
    let connected = false;
    let schemaCreated = false;

    try {
      copyNativeMigrations(temporaryMigrations);
      await client.connect();
      connected = true;
      await client.query(`create schema ${quoteIdentifier(schemaName)}`);
      schemaCreated = true;

      const firstRun = await runMigrations(temporaryMigrations, schemaName);
      const secondRun = await runMigrations(temporaryMigrations, schemaName);

      assert.deepEqual(
        firstRun.results.map(({ version, status }) => [version.slice(0, 3), status]),
        [
          ['001', 'applied'],
          ['002', 'applied'],
          ['003', 'applied'],
          ['004', 'applied'],
          ['005', 'applied'],
        ],
      );
      assert.deepEqual(
        secondRun.results.map(({ version, status }) => [version.slice(0, 3), status]),
        [
          ['001', 'skipped'],
          ['002', 'skipped'],
          ['003', 'skipped'],
          ['004', 'skipped'],
          ['005', 'skipped'],
        ],
      );

      await client.query(
        `set search_path to ${quoteIdentifier(schemaName)}, public`,
      );

      const messageConstraints = await constraintDefinitions(
        client,
        schemaName,
        'app_message_actions',
      );
      assert.match(
        messageConstraints.app_message_actions_family_message_fkey,
        /FOREIGN KEY \(family_id, message_id\) REFERENCES app_messages\(family_id, message_id\) ON DELETE CASCADE/,
      );

      const uniqueIndex = await client.query(
        `
          select indexdef
          from pg_indexes
          where schemaname = $1
            and tablename = 'app_messages'
            and indexname = 'app_messages_family_message_idx'
        `,
        [schemaName],
      );
      assert.equal(uniqueIndex.rowCount, 1);
      assert.match(
        uniqueIndex.rows[0].indexdef,
        /UNIQUE INDEX .* \(family_id, message_id\)/,
      );

      const productConstraints = await constraintDefinitions(
        client,
        schemaName,
        'product_catalog',
      );
      assert.match(
        productConstraints.product_catalog_suitability_array_check,
        /jsonb_typeof\(suitability\) = 'array'/,
      );
      assert.match(
        productConstraints.product_catalog_status_check,
        /status = ANY \(ARRAY\['draft'.*'active'.*'disabled'/,
      );
      assert.match(
        productConstraints.product_catalog_active_fields_check,
        /verified_at IS NOT NULL/,
      );

      const productColumns = await client.query(
        `
          select column_name, column_default
          from information_schema.columns
          where table_schema = $1
            and table_name = 'product_catalog'
            and column_name in ('status', 'suitability')
        `,
        [schemaName],
      );
      const defaults = Object.fromEntries(
        productColumns.rows.map((row) => [row.column_name, row.column_default]),
      );
      assert.match(defaults.status, /'draft'/);
      assert.match(defaults.suitability, /'\[\]'/);

      const families = await client.query(
        `insert into families (name) values ('Family A'), ('Family B') returning id`,
      );
      const [familyA, familyB] = families.rows.map((row) => row.id);
      await client.query(
        `
          insert into app_messages (message_id, family_id, idempotency_key)
          values ('native-integration-message', $1, 'native-integration-message')
        `,
        [familyA],
      );
      await assert.rejects(
        client.query(
          `
            insert into app_message_actions (
              family_id,
              message_id,
              action_type,
              idempotency_key
            ) values ($1, 'native-integration-message', 'opened', 'wrong-family')
          `,
          [familyB],
        ),
        (error) => error?.code === '23503',
      );
      await client.query(
        `
          insert into app_message_actions (
            family_id,
            message_id,
            action_type,
            idempotency_key
          ) values ($1, 'native-integration-message', 'opened', 'matching-family')
        `,
        [familyA],
      );

      const draftProduct = await client.query(
        `
          insert into product_catalog (category, name)
          values ('', '')
          returning status, suitability
        `,
      );
      assert.equal(draftProduct.rows[0].status, 'draft');
      assert.deepEqual(draftProduct.rows[0].suitability, []);

      await assertCheckViolation(
        client.query(
          `
            insert into product_catalog (category, name, status)
            values ('care', 'Invalid status', 'pending')
          `,
        ),
        'unsupported product status should be rejected',
      );
      await assertCheckViolation(
        client.query(
          `
            insert into product_catalog (category, name, suitability)
            values ('care', 'Invalid suitability', '{}'::jsonb)
          `,
        ),
        'non-array suitability should be rejected',
      );

      const validProduct = {
        category: 'care',
        brand: 'GoHome',
        name: 'Verified product',
        imageUrl: 'https://cdn.example.com/product.jpg',
        sourceName: 'Example source',
        sourceUrl: 'https://example.com/product',
        verifiedAt: new Date(),
      };
      const activeInsert = `
        insert into product_catalog (
          category,
          brand,
          name,
          image_url,
          source_name,
          source_url,
          status,
          verified_at
        ) values ($1, $2, $3, $4, $5, $6, 'active', $7)
      `;
      const activeValues = (product) => [
        product.category,
        product.brand,
        product.name,
        product.imageUrl,
        product.sourceName,
        product.sourceUrl,
        product.verifiedAt,
      ];

      for (const field of [
        'category',
        'brand',
        'name',
        'imageUrl',
        'sourceName',
        'sourceUrl',
      ]) {
        await assertCheckViolation(
          client.query(
            activeInsert,
            activeValues({ ...validProduct, [field]: ' ' }),
          ),
          `active product should require non-empty ${field}`,
        );
      }
      await assertCheckViolation(
        client.query(
          activeInsert,
          activeValues({
            ...validProduct,
            imageUrl: 'http://cdn.example.com/product.jpg',
          }),
        ),
        'active product image URL should require HTTPS',
      );
      await assertCheckViolation(
        client.query(
          activeInsert,
          activeValues({
            ...validProduct,
            sourceUrl: 'http://example.com/product',
          }),
        ),
        'active product source URL should require HTTPS',
      );
      await assertCheckViolation(
        client.query(
          activeInsert,
          activeValues({ ...validProduct, verifiedAt: null }),
        ),
        'active product should require verified_at',
      );
      await client.query(activeInsert, activeValues(validProduct));
    } finally {
      try {
        if (schemaCreated) {
          await client.query('set search_path to public');
          await client.query(
            `drop schema if exists ${quoteIdentifier(schemaName)} cascade`,
          );
        }
      } finally {
        if (connected) {
          await client.end();
        }
        fs.rmSync(temporaryMigrations, { recursive: true, force: true });
      }
    }
  },
);
