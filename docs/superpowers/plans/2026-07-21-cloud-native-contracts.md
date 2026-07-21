# Cloud Native Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide account-isolated, row-level PostgreSQL contracts for the native iOS bootstrap, home, messages, actions, and curated product recommendations while preserving edge and browser compatibility.

**Architecture:** Add a focused `/api/v2` router backed by explicit repositories. Keep legacy `/api/v1` and edge routes operational during migration, but remove full-table replacement from the PostgreSQL save path before native mutations are enabled.

**Tech Stack:** Node.js CommonJS, PostgreSQL 16, `pg`, SQL migrations, `node:test`, existing `local-app-server` HTTP server.

---

## File Map

- Create `local-app-server/migrations/005_native_app.sql`: native message actions, product catalog, preferences, and indexes.
- Create `local-app-server/native-api/router.js`: `/api/v2` route dispatch only.
- Create `local-app-server/native-api/repository.js`: repository contract and JSON test implementation.
- Create `local-app-server/native-api/postgres-repository.js`: parameterized row-level PostgreSQL implementation.
- Create `local-app-server/native-api/auth-service.js`: OTP challenge and session policy.
- Create `local-app-server/native-api/view-service.js`: bootstrap/home/message/product view assembly.
- Modify `local-app-server/server.js`: dependency injection and v2 router delegation.
- Modify `local-app-server/postgres-store.js`: row-delta persistence; no whole-table delete.
- Create `local-app-server/test/native-api.test.js`: HTTP contract tests.
- Create `local-app-server/test/postgres-row-delta.test.js`: persistence regression.
- Modify `package.json`: native server test command.

### Task 1: Native Schema

**Files:**
- Create: `local-app-server/migrations/005_native_app.sql`
- Create: `local-app-server/test/native-schema.test.js`
- Modify: `package.json`

- [x] **Step 1: Write the failing schema test**

```js
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");

test("native migration defines action and curated catalog ownership", () => {
  const sql = fs.readFileSync("local-app-server/migrations/005_native_app.sql", "utf8");
  for (const table of ["app_message_actions", "product_catalog", "product_preferences"]) {
    assert.match(sql, new RegExp(`create table if not exists ${table}`, "i"));
  }
  assert.match(sql, /foreign key \(family_id\)|references families\(id\)/i);
});
```

- [x] **Step 2: Run the test and verify failure**

Run: `node --test local-app-server/test/native-schema.test.js`  
Expected: FAIL because `005_native_app.sql` does not exist.

- [x] **Step 3: Add the migration**

Define:

```sql
create table if not exists app_message_actions (
  id text primary key default gen_random_uuid()::text,
  family_id text not null references families(id) on delete cascade,
  message_id text not null references app_messages(message_id) on delete cascade,
  user_id text not null references users(id) on delete cascade,
  action_type text not null check (action_type in ('opened','shared','contacted','snoozed','dismissed','returned_home')),
  action_payload jsonb not null default '{}'::jsonb,
  idempotency_key text not null unique,
  created_at timestamptz not null default now()
);

create table if not exists product_catalog (
  id text primary key default gen_random_uuid()::text,
  category text not null,
  brand text not null,
  name text not null,
  summary text not null default '',
  image_url text not null,
  source_name text not null,
  source_url text not null,
  suitability jsonb not null default '[]'::jsonb,
  disclosure text not null default '',
  status text not null default 'active',
  verified_at timestamptz not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists product_preferences (
  family_id text primary key references families(id) on delete cascade,
  categories jsonb not null default '[]'::jsonb,
  needs jsonb not null default '[]'::jsonb,
  updated_by text references users(id) on delete set null,
  updated_at timestamptz not null default now()
);
```

Add indexes for `(family_id, created_at desc)`, `(status, category)`, and message action lookup.

- [x] **Step 4: Add and run the test command**

Add to `package.json`:

```json
"test:native-server": "node --test local-app-server/test/*.test.js"
```

Run: `npm run test:native-server`  
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add local-app-server/migrations/005_native_app.sql local-app-server/test/native-schema.test.js package.json
git commit -m "feat(server): add native app schema"
```

### Task 2: Repository Contract And Row-Level PostgreSQL

**Files:**
- Create: `local-app-server/native-api/repository.js`
- Create: `local-app-server/native-api/postgres-repository.js`
- Test: `local-app-server/test/native-repository.test.js`

- [x] **Step 1: Write repository isolation tests**

Test two users in different families and assert that `bootstrapForUser`, `messagesForFamily`, and `productsForFamily` never return rows from the other family. Also assert `recordMessageAction` returns the same row for the same idempotency key.

```js
assert.deepEqual((await repo.messagesForFamily("family-a", "user-a")).map(x => x.family_id), ["family-a"]);
await assert.rejects(() => repo.messagesForFamily("family-b", "user-a"), /family access denied/);
assert.equal(first.id, duplicate.id);
```

- [x] **Step 2: Run and verify failure**

Run: `node --test local-app-server/test/native-repository.test.js`  
Expected: FAIL because the repository modules do not exist.

- [x] **Step 3: Implement the repository interface**

Expose exactly these methods:

```js
class NativeRepository {
  bootstrapForUser(userId) {}
  homeForFamily(userId, familyId) {}
  messagesForFamily(userId, familyId, options = {}) {}
  messageForFamily(userId, familyId, messageId) {}
  recordMessageAction(userId, familyId, messageId, action) {}
  productsForFamily(userId, familyId, options = {}) {}
  productById(userId, familyId, productId) {}
  productPreferences(userId, familyId) {}
  updateProductPreferences(userId, familyId, input) {}
}
```

The PostgreSQL implementation must use parameterized statements and an access guard based on `family_members`. It must not read a global active user.

- [x] **Step 4: Run repository tests**

Run: `npm run test:native-server`  
Expected: PASS for JSON contract tests; PostgreSQL integration tests skip only when `GOHOME_DATABASE_URL` is absent.

- [x] **Step 5: Commit**

```bash
git add local-app-server/native-api/repository.js local-app-server/native-api/postgres-repository.js local-app-server/test/native-repository.test.js
git commit -m "feat(server): add account-scoped native repository"
```

### Task 3: Remove Full-Table Replacement

**Files:**
- Modify: `local-app-server/postgres-store.js`
- Modify: `local-app-server/server.js`
- Test: `local-app-server/test/postgres-row-delta.test.js`

- [ ] **Step 1: Add a failing SQL-spy test**

Use a fake pool/client, call `store.save()` after changing one camera, and assert no query matches `delete from users`, `delete from families`, or another unmodified table. Then call `store.deleteRow("cameras", cameraID)` and assert exactly one parameterized camera delete occurs.

```js
assert.equal(queries.some(q => /^delete from users/i.test(q.text)), false);
assert.equal(queries.some(q => /^delete from families/i.test(q.text)), false);
assert.equal(queries.some(q => /insert into cameras/i.test(q.text)), true);
```

- [ ] **Step 2: Run and verify failure**

Run: `node --test local-app-server/test/postgres-row-delta.test.js`  
Expected: FAIL because `replaceAllRows` deletes every table.

- [ ] **Step 3: Implement snapshot-based row deltas**

Maintain the last persisted bundle by table and primary key. Define a primary-key map (`users.id`, `families.id`, `devices.device_id`, and the corresponding declared key for every remaining table). In one transaction, upsert only changed rows with the mapped key, for example `on conflict (id) do update`, and acquire `pg_advisory_xact_lock(hashtext('gohome-app-store'))`. Never infer deletion from a row being absent in the in-memory snapshot, because native repository writes may have occurred in PostgreSQL. Add an explicit parameterized `deleteRow(table, id)` method and migrate existing camera, binding, session, and cleanup deletion routes to call it. Update the in-memory persisted snapshot only after commit.

- [ ] **Step 4: Run persistence and legacy regression**

Run:

```bash
npm run test:native-server
npm run verify:postgres-loop
npm run verify:app-server
```

Expected: all PASS; SQL spy records no complete-table wipe.

- [ ] **Step 5: Commit**

```bash
git add local-app-server/postgres-store.js local-app-server/server.js local-app-server/test/postgres-row-delta.test.js
git commit -m "fix(server): persist postgres changes by row"
```

### Task 4: Production Phone Authentication Policy

**Files:**
- Create: `local-app-server/native-api/auth-service.js`
- Modify: `local-app-server/server.js`
- Test: `local-app-server/test/native-auth.test.js`

- [ ] **Step 1: Write tests for demo and production modes**

Assert production rejects `000000`, challenge requests are rate-limited, challenge hashes expire, and debug mode accepts the configured `GOHOME_DEMO_OTP` only when `GOHOME_AUTH_MODE=demo`.

- [ ] **Step 2: Run and verify failure**

Run: `node --test local-app-server/test/native-auth.test.js`  
Expected: FAIL because the legacy route accepts `000000` unconditionally.

- [ ] **Step 3: Implement provider abstraction**

Define `requestCode(phone)` and `verifyCode(phone, code)` around a `SmsProvider`. Store only `sha256(challengeId + code + serverSecret)`, expiry, attempt count, and consumed timestamp. Return `503 sms provider not configured` in production when no provider exists; never silently fall back to demo OTP.

- [ ] **Step 4: Run auth and onboarding regression**

Run:

```bash
npm run test:native-server
npm run verify:cloud-onboarding
```

Expected: PASS in explicit demo test environment; production-policy test rejects fixed OTP.

- [ ] **Step 5: Commit**

```bash
git add local-app-server/native-api/auth-service.js local-app-server/server.js local-app-server/test/native-auth.test.js
git commit -m "feat(auth): enforce environment-scoped phone verification"
```

### Task 5: Native Bootstrap And Home Endpoints

**Files:**
- Create: `local-app-server/native-api/view-service.js`
- Create: `local-app-server/native-api/router.js`
- Modify: `local-app-server/server.js`
- Test: `local-app-server/test/native-api.test.js`

- [ ] **Step 1: Write failing HTTP contract tests**

Assert `/api/v2/app/bootstrap` returns `user`, `families`, `active_family_id`, `onboarding.next_step`, `unread_count`, and `revision`; `/api/v2/home` returns separate `weather`, `calendar`, `distance`, `critical_alert`, and `articles` fields. Assert articles without HTTPS source URLs are omitted.

- [ ] **Step 2: Run and verify 404**

Run: `node --test local-app-server/test/native-api.test.js`  
Expected: FAIL with HTTP 404.

- [ ] **Step 3: Implement router delegation and views**

Delegate `/api/v2/*` before legacy route matching. Return ETags/revisions and support `If-None-Match`. Bootstrap computes exactly one onboarding next step: `family`, `profile`, `device`, `camera`, or `complete`.

- [ ] **Step 4: Run contract tests**

Run: `npm run test:native-server`  
Expected: PASS with two-account isolation fixtures.

- [ ] **Step 5: Commit**

```bash
git add local-app-server/native-api/view-service.js local-app-server/native-api/router.js local-app-server/server.js local-app-server/test/native-api.test.js
git commit -m "feat(server): expose native bootstrap and home contracts"
```

### Task 6: Return-Home Messages And Actions

**Files:**
- Modify: `local-app-server/native-api/view-service.js`
- Modify: `local-app-server/native-api/router.js`
- Modify: `local-app-server/server.js`
- Test: `local-app-server/test/native-messages.test.js`

- [ ] **Step 1: Write workflow tests**

Create one threshold trigger and assert one idempotent `return_home` message contains `trigger_reason`, 2-3 `topics`, two `message_variants`, and allowed actions. Record `shared`, `snoozed`, and `returned_home`; assert each updates state without claiming WeChat delivery.

- [ ] **Step 2: Run and verify failure**

Run: `node --test local-app-server/test/native-messages.test.js`  
Expected: FAIL because v2 message actions are absent.

- [ ] **Step 3: Implement endpoints**

Implement:

```text
GET  /api/v2/messages?family_id=family-1
GET  /api/v2/messages/message-1?family_id=family-1
POST /api/v2/messages/:id/actions
```

Allow only `opened`, `shared`, `contacted`, `snoozed`, `dismissed`, and `returned_home`. Require an idempotency key. `snoozed` requires a future timestamp; `returned_home` closes the reminder and updates the visit record.

- [ ] **Step 4: Run scheduler and message tests**

Run: `npm run test:native-server && npm run verify:app-server`  
Expected: PASS; legacy safety reminders remain unchanged.

- [ ] **Step 5: Commit**

```bash
git add local-app-server/native-api local-app-server/server.js local-app-server/test/native-messages.test.js
git commit -m "feat(messages): close return-home action workflow"
```

### Task 7: Curated Product Recommendation API

**Files:**
- Create: `local-app-server/native-api/product-policy.js`
- Modify: `local-app-server/native-api/router.js`
- Test: `local-app-server/test/native-products.test.js`

- [ ] **Step 1: Write product policy tests**

Reject non-HTTPS links, stale verification timestamps, missing source/brand/image, and categories matching medicine, supplement, medical device, or diagnosis. Verify a household safety light with a real source passes.

- [ ] **Step 2: Run and verify failure**

Run: `node --test local-app-server/test/native-products.test.js`  
Expected: FAIL because policy and endpoints are absent.

- [ ] **Step 3: Implement product policy and endpoints**

Add `GET /api/v2/products`, `GET /api/v2/products/:id`, and preference GET/PUT. Responses expose no cart, checkout, order, payment, or inventory fields. Recommendation reasons use only explicitly selected preference categories/needs.

- [ ] **Step 4: Run all cloud gates**

Run:

```bash
npm run db:migrate
npm run test:native-server
npm run verify:app-server
npm run verify:cloud-onboarding
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add local-app-server/native-api/product-policy.js local-app-server/native-api/router.js local-app-server/test/native-products.test.js
git commit -m "feat(discover): add curated product contracts"
```
