"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { createCosStorage } = require("../cos-storage");
const { DAY_MS, MediaLifecycleManager } = require("../media-lifecycle");
const { createLocalAppServer } = require("../server");

function iso(nowMs, daysAgo) {
    return new Date(nowMs - daysAgo * DAY_MS).toISOString();
}

function asset(id, key, createdAt, patch = {}) {
    return {
        id,
        storage_provider: "cos",
        storage_key: key,
        content_type: "image/jpeg",
        purpose: "event_evidence",
        size: 128,
        created_at: createdAt,
        updated_at: createdAt,
        ...patch,
    };
}

test("media lifecycle protects user media and unresolved alerts while deleting expired managed evidence", async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "gohome-media-lifecycle-"));
    const mediaDir = path.join(root, "media");
    fs.mkdirSync(mediaDir, { recursive: true });
    const now = { value: Date.parse("2026-08-02T08:00:00.000Z") };
    const deletedKeys = [];
    const failures = new Set(["event-evidence/fail-once.jpg"]);
    const listed = [
        { key: "event-evidence/orphan.jpg", last_modified: iso(now.value, 4), size: 10 },
        { key: "memory-media/pending.jpg", last_modified: iso(now.value, 4), size: 10 },
    ];
    const cosStorage = {
        enabled: true,
        async deleteObject({ key }) {
            if (failures.delete(key)) throw new Error("temporary COS failure");
            deletedKeys.push(key);
        },
        async listObjects({ prefix }) {
            return listed.filter((item) => item.key.startsWith(prefix));
        },
    };
    const db = {
        assets: [
            asset("memory", "memory-media/family/photo.jpg", iso(now.value, 400), {
                purpose: "family_memory",
            }),
            asset("open-critical", "event-evidence/open-critical.jpg", iso(now.value, 400)),
            asset("resolved-critical", "event-evidence/resolved-critical.jpg", iso(now.value, 181)),
            asset("normal-event", "event-evidence/normal.jpg", iso(now.value, 91)),
            asset("verification", "event-evidence/verification.jpg", iso(now.value, 31), {
                purpose: "validation_evidence",
            }),
            asset("fail-once", "event-evidence/fail-once.jpg", iso(now.value, 20), {
                purpose: "transient_upload",
            }),
        ],
        events: [
            {
                id: "event-open",
                media_asset_id: "open-critical",
                level: "critical",
                acknowledged: false,
                resolution: "",
            },
            {
                id: "event-resolved",
                media_asset_id: "resolved-critical",
                level: "critical",
                acknowledged: true,
                resolution: "handled",
            },
            {
                id: "event-normal",
                media_asset_id: "normal-event",
                level: "warning",
                acknowledged: true,
            },
        ],
        family_memory_media: [{ memory_id: "m1", asset_id: "memory" }],
        media_upload_intents: [{ asset_id: "pending", object_key: "memory-media/pending.jpg" }],
    };
    let saves = 0;
    const store = { db, async save() { saves += 1; } };

    const localOrphan = path.join(mediaDir, "orphan-local.jpg");
    fs.writeFileSync(localOrphan, "orphan");
    const oldTime = new Date(now.value - 4 * DAY_MS);
    fs.utimesSync(localOrphan, oldTime, oldTime);

    const manager = new MediaLifecycleManager({
        store,
        cosStorage,
        mediaDir,
        clock: () => now.value,
        logger: { warn() {} },
    });
    const first = await manager.run();

    assert.equal(db.assets.find((item) => item.id === "memory").retention_status, "active");
    assert.equal(db.assets.find((item) => item.id === "memory").retention_class, "family_memory");
    assert.equal(db.assets.find((item) => item.id === "open-critical").retention_status, "active");
    assert.equal(db.assets.find((item) => item.id === "resolved-critical").retention_status, "deleted");
    assert.equal(db.assets.find((item) => item.id === "normal-event").retention_status, "deleted");
    assert.equal(db.assets.find((item) => item.id === "verification").retention_status, "deleted");
    assert.equal(db.assets.find((item) => item.id === "fail-once").retention_status, "failed");
    assert.equal(first.deleted, 3);
    assert.equal(first.failed, 1);
    assert.equal(first.cos_orphans.deleted, 1);
    assert.equal(first.local_orphans.deleted, 1);
    assert.equal(fs.existsSync(localOrphan), false);
    assert.ok(deletedKeys.includes("event-evidence/orphan.jpg"));
    assert.ok(!deletedKeys.includes("memory-media/pending.jpg"));
    assert.ok(!deletedKeys.includes("memory-media/family/photo.jpg"));
    assert.ok(saves >= 1);

    now.value += 61 * 1000;
    const second = await manager.run({ reconcileOrphans: false });
    assert.equal(second.deleted, 1);
    assert.equal(second.failed, 0);
    assert.equal(db.assets.find((item) => item.id === "fail-once").retention_status, "deleted");
    assert.ok(deletedKeys.includes("event-evidence/fail-once.jpg"));

    fs.rmSync(root, { recursive: true, force: true });
});

test("orphan reconciliation keeps COS and local ownership namespaces isolated", async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "gohome-media-provider-ownership-"));
    const mediaDir = path.join(root, "media");
    const sharedKey = "event-evidence/shared.jpg";
    const localPath = path.join(mediaDir, sharedKey);
    fs.mkdirSync(path.dirname(localPath), { recursive: true });
    fs.writeFileSync(localPath, "local orphan");
    const nowMs = Date.parse("2026-08-02T08:00:00.000Z");
    const oldTime = new Date(nowMs - 4 * DAY_MS);
    fs.utimesSync(localPath, oldTime, oldTime);
    const deletedKeys = [];
    const store = {
        db: {
            assets: [asset("cos-owner", sharedKey, iso(nowMs, 1))],
            events: [],
            family_memory_media: [],
            media_upload_intents: [],
        },
        async save() {},
    };
    const manager = new MediaLifecycleManager({
        store,
        mediaDir,
        clock: () => nowMs,
        cosStorage: {
            enabled: true,
            async listObjects() { return []; },
            async deleteObject({ key }) { deletedKeys.push(key); },
        },
    });

    const result = await manager.run();

    assert.equal(result.local_orphans.deleted, 1);
    assert.equal(fs.existsSync(localPath), false);
    assert.deepEqual(deletedKeys, []);
    fs.rmSync(root, { recursive: true, force: true });
});

test("media lifecycle dry run reports due assets and orphans without changing storage state", async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "gohome-media-dry-run-"));
    const mediaDir = path.join(root, "media");
    const localPath = path.join(mediaDir, "local-orphan.jpg");
    fs.mkdirSync(mediaDir, { recursive: true });
    fs.writeFileSync(localPath, "orphan");
    const nowMs = Date.parse("2026-08-02T08:00:00.000Z");
    const oldTime = new Date(nowMs - 4 * DAY_MS);
    fs.utimesSync(localPath, oldTime, oldTime);
    const expiredAsset = asset("expired", "event-evidence/expired.jpg", iso(nowMs, 91));
    const deletedKeys = [];
    let saves = 0;
    const manager = new MediaLifecycleManager({
        mediaDir,
        clock: () => nowMs,
        store: {
            db: { assets: [expiredAsset], events: [], family_memory_media: [], media_upload_intents: [] },
            async save() { saves += 1; },
        },
        cosStorage: {
            enabled: true,
            async listObjects({ prefix }) {
                return prefix === "event-evidence/"
                    ? [{ key: "event-evidence/orphan.jpg", last_modified: iso(nowMs, 4) }]
                    : [];
            },
            async deleteObject({ key }) { deletedKeys.push(key); },
        },
    });

    const result = await manager.run({ dryRun: true });

    assert.equal(result.dry_run, true);
    assert.equal(result.planned_deletions, 1);
    assert.equal(result.deleted, 0);
    assert.equal(result.cos_orphans.planned, 1);
    assert.equal(result.cos_orphans.deleted, 0);
    assert.equal(result.local_orphans.planned, 1);
    assert.equal(result.local_orphans.deleted, 0);
    assert.equal(expiredAsset.retention_class, undefined);
    assert.equal(expiredAsset.retention_status, undefined);
    assert.equal(saves, 0);
    assert.deepEqual(deletedKeys, []);
    assert.equal(fs.existsSync(localPath), true);
    fs.rmSync(root, { recursive: true, force: true });
});

test("COS listing follows continuation markers until the complete inventory is returned", async () => {
    const requests = [];
    const client = {
        async getBucket(request) {
            requests.push(request);
            if (!request.Marker) {
                return {
                    IsTruncated: "true",
                    NextMarker: "page-2",
                    Contents: [{ Key: "event-evidence/first.jpg", Size: "10", LastModified: "2026-08-01T00:00:00.000Z" }],
                };
            }
            return {
                IsTruncated: false,
                Contents: [{ Key: "event-evidence/second.jpg", Size: "20", LastModified: "2026-08-02T00:00:00.000Z" }],
            };
        },
    };
    const storage = createCosStorage({
        enabled: true,
        bucket: "bucket-123",
        region: "ap-shanghai",
        client,
    });

    const objects = await storage.listObjects({ prefix: "event-evidence/" });

    assert.deepEqual(objects.map((item) => item.key), [
        "event-evidence/first.jpg",
        "event-evidence/second.jpg",
    ]);
    assert.deepEqual(requests.map((request) => request.Marker), ["", "page-2"]);
    assert.ok(requests.every((request) => request.Prefix === "event-evidence/" && request.MaxKeys === 1000));
});

function listen(server) {
    return new Promise((resolve, reject) => {
        server.once("error", reject);
        server.listen(0, "127.0.0.1", () => resolve(`http://127.0.0.1:${server.address().port}`));
    });
}

test("media lifecycle operations endpoint requires ops authorization and forwards reconciliation mode", async () => {
    const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "gohome-media-lifecycle-ops-"));
    const calls = [];
    const manager = {
        status() { return { running: false, last_run: null, policies: {} }; },
        async run(options) {
            calls.push(options);
            return { ok: true, running: false, deleted: 0 };
        },
    };
    const app = createLocalAppServer({
        rootDir: path.join(__dirname, "..", ".."),
        dataDir,
        opsToken: "media-ops-secret",
        mediaLifecycleEnabled: false,
        mediaLifecycleDeleteEnabled: true,
        mediaLifecycleManager: manager,
    });
    const baseUrl = await listen(app.server);
    try {
        const denied = await fetch(`${baseUrl}/api/v1/internal/media-lifecycle/run`, { method: "POST" });
        assert.equal(denied.status, 403);
        assert.equal(calls.length, 0);

        const accepted = await fetch(`${baseUrl}/api/v1/internal/media-lifecycle/run`, {
            method: "POST",
            headers: {
                Authorization: "Bearer media-ops-secret",
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ reconcile_orphans: false }),
        });
        assert.equal(accepted.status, 200);
        assert.deepEqual(await accepted.json(), { ok: true, running: false, deleted: 0 });
        assert.deepEqual(calls, [{ reconcileOrphans: false, dryRun: false }]);

        const dryRun = await fetch(`${baseUrl}/api/v1/internal/media-lifecycle/run`, {
            method: "POST",
            headers: {
                Authorization: "Bearer media-ops-secret",
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ dry_run: true }),
        });
        assert.equal(dryRun.status, 200);
        assert.deepEqual(calls[1], { reconcileOrphans: true, dryRun: true });
    } finally {
        await new Promise((resolve) => app.server.close(resolve));
        fs.rmSync(dataDir, { recursive: true, force: true });
    }
});

test("media lifecycle deletion stays locked until production enables it explicitly", async () => {
    const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "gohome-media-lifecycle-lock-"));
    const calls = [];
    const manager = {
        status() { return { running: false, last_run: null, policies: {} }; },
        async run(options) {
            calls.push(options);
            return { ok: true, dry_run: options.dryRun };
        },
    };
    const app = createLocalAppServer({
        rootDir: path.join(__dirname, "..", ".."),
        dataDir,
        opsToken: "media-ops-secret",
        mediaLifecycleEnabled: false,
        mediaLifecycleDeleteEnabled: false,
        mediaLifecycleManager: manager,
    });
    const baseUrl = await listen(app.server);
    const headers = { Authorization: "Bearer media-ops-secret", "Content-Type": "application/json" };
    try {
        const inventory = await fetch(`${baseUrl}/api/v1/internal/media-lifecycle/run`, {
            method: "POST",
            headers,
            body: "{}",
        });
        assert.equal(inventory.status, 200);
        assert.deepEqual(calls, [{ reconcileOrphans: true, dryRun: true }]);

        const deletion = await fetch(`${baseUrl}/api/v1/internal/media-lifecycle/run`, {
            method: "POST",
            headers,
            body: JSON.stringify({ dry_run: false }),
        });
        assert.equal(deletion.status, 409);
        assert.equal(calls.length, 1);
    } finally {
        await new Promise((resolve) => app.server.close(resolve));
        fs.rmSync(dataDir, { recursive: true, force: true });
    }
});

test("media lifecycle PostgreSQL migration exposes queryable retention state", () => {
    const migration = fs.readFileSync(
        path.join(__dirname, "..", "migrations", "013_media_lifecycle.sql"),
        "utf8",
    );
    for (const column of [
        "retention_class",
        "retention_status",
        "retain_until",
        "deletion_attempts",
        "next_deletion_at",
        "deleted_at",
    ]) {
        assert.match(migration, new RegExp(`\\b${column}\\b`));
    }
});
