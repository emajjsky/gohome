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
    assert.equal(result.classification_only, false);
    assert.equal(result.planned_deletions, 1);
    assert.equal(result.deleted, 0);
    assert.equal(result.cos_orphans.planned, 1);
    assert.equal(result.cos_orphans.deleted, 0);
    assert.equal(result.local_orphans.planned, 1);
    assert.equal(result.local_orphans.deleted, 0);
    assert.equal(expiredAsset.retention_class, undefined);
    assert.equal(expiredAsset.retention_status, undefined);
    assert.equal(saves, 1);
    assert.equal(manager.status().last_run.dry_run, true);
    assert.deepEqual(deletedKeys, []);
    assert.equal(fs.existsSync(localPath), true);
    fs.rmSync(root, { recursive: true, force: true });
});

test("classification-only mode persists retention state without deleting assets or orphans", async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "gohome-media-classification-only-"));
    const mediaDir = path.join(root, "media");
    const localPath = path.join(mediaDir, "expired.jpg");
    const orphanPath = path.join(mediaDir, "orphan.jpg");
    fs.mkdirSync(mediaDir, { recursive: true });
    fs.writeFileSync(localPath, "expired");
    fs.writeFileSync(orphanPath, "orphan");
    const nowMs = Date.parse("2026-08-02T08:00:00.000Z");
    const oldTime = new Date(nowMs - 10 * DAY_MS);
    fs.utimesSync(localPath, oldTime, oldTime);
    fs.utimesSync(orphanPath, oldTime, oldTime);
    const expiredAsset = asset("expired", "expired.jpg", iso(nowMs, 10), {
        storage_provider: "local",
        relative_path: "expired.jpg",
        purpose: "transient_upload",
    });
    let saves = 0;
    const manager = new MediaLifecycleManager({
        mediaDir,
        clock: () => nowMs,
        store: {
            db: { assets: [expiredAsset], events: [], family_memory_media: [], media_upload_intents: [] },
            async save() { saves += 1; },
        },
        cosStorage: { enabled: false },
    });

    const result = await manager.run({ classificationOnly: true });

    assert.equal(result.dry_run, false);
    assert.equal(result.classification_only, true);
    assert.equal(result.planned_deletions, 1);
    assert.equal(result.deleted, 0);
    assert.equal(result.local_orphans.planned, 1);
    assert.equal(result.local_orphans.deleted, 0);
    assert.equal(expiredAsset.retention_class, "transient_upload");
    assert.equal(expiredAsset.retention_status, "active");
    assert.equal(saves, 2);
    assert.equal(fs.existsSync(localPath), true);
    assert.equal(fs.existsSync(orphanPath), true);
    fs.rmSync(root, { recursive: true, force: true });
});

test("media lifecycle bounds physical deletion and processes the oldest data first", async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "gohome-media-bounded-delete-"));
    const mediaDir = path.join(root, "media");
    fs.mkdirSync(mediaDir, { recursive: true });
    const nowMs = Date.parse("2026-08-02T08:00:00.000Z");
    const assets = [12, 11, 10].map((daysAgo, index) => asset(
        `asset-${index + 1}`,
        `assets/asset-${index + 1}.jpg`,
        iso(nowMs, daysAgo),
        {
            storage_provider: "local",
            relative_path: `assets/asset-${index + 1}.jpg`,
            purpose: "transient_upload",
            size: 10,
        },
    ));
    for (const item of assets) {
        const filePath = path.join(mediaDir, item.relative_path);
        fs.mkdirSync(path.dirname(filePath), { recursive: true });
        fs.writeFileSync(filePath, item.id);
    }
    const orphanPaths = [9, 8, 7].map((daysAgo, index) => {
        const filePath = path.join(mediaDir, `orphans/orphan-${index + 1}.jpg`);
        fs.mkdirSync(path.dirname(filePath), { recursive: true });
        fs.writeFileSync(filePath, `orphan-${index + 1}`);
        const oldTime = new Date(nowMs - daysAgo * DAY_MS);
        fs.utimesSync(filePath, oldTime, oldTime);
        return filePath;
    });
    const manager = new MediaLifecycleManager({
        mediaDir,
        clock: () => nowMs,
        env: {
            GOHOME_MEDIA_LIFECYCLE_MAX_ASSETS_PER_RUN: "2",
            GOHOME_MEDIA_LIFECYCLE_MAX_ASSET_BYTES_PER_RUN: "100",
            GOHOME_MEDIA_LIFECYCLE_MAX_ORPHANS_PER_RUN: "1",
            GOHOME_MEDIA_LIFECYCLE_MAX_ORPHAN_BYTES_PER_RUN: "100",
        },
        store: {
            db: { assets, events: [], family_memory_media: [], media_upload_intents: [] },
            async save() {},
        },
        cosStorage: { enabled: false },
    });

    const result = await manager.run();

    assert.equal(result.planned_deletions, 3);
    assert.equal(result.selected_deletions, 2);
    assert.equal(result.limited_deletions, 1);
    assert.equal(result.deleted, 2);
    assert.equal(assets[0].retention_status, "deleted");
    assert.equal(assets[1].retention_status, "deleted");
    assert.equal(assets[2].retention_status, "active");
    assert.equal(result.local_orphans.planned, 3);
    assert.equal(result.local_orphans.selected, 1);
    assert.equal(result.local_orphans.limited, 2);
    assert.equal(result.local_orphans.deleted, 1);
    assert.equal(fs.existsSync(orphanPaths[0]), false);
    assert.equal(fs.existsSync(orphanPaths[1]), true);
    assert.equal(fs.existsSync(orphanPaths[2]), true);
    fs.rmSync(root, { recursive: true, force: true });
});

test("COS orphan failures persist retry state and wait for deterministic backoff", async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "gohome-media-cos-retry-"));
    const mediaDir = path.join(root, "media");
    fs.mkdirSync(mediaDir, { recursive: true });
    const now = { value: Date.parse("2026-08-04T08:00:00.000Z") };
    const lastModified = iso(now.value, 4);
    let deleteCalls = 0;
    const store = {
        db: {
            assets: [],
            events: [],
            family_memory_media: [],
            media_upload_intents: [],
            media_orphans: [],
            scheduler_runs: [],
        },
        async save() {},
    };
    const manager = new MediaLifecycleManager({
        store,
        mediaDir,
        clock: () => now.value,
        logger: { warn() {} },
        cosStorage: {
            enabled: true,
            async listObjects({ prefix }) {
                return prefix === "event-evidence/"
                    ? [{ key: "event-evidence/retry.jpg", size: 40, last_modified: lastModified }]
                    : [];
            },
            async deleteObject() {
                deleteCalls += 1;
                if (deleteCalls === 1) {
                    const error = new Error("temporary service failure");
                    error.code = "ServiceUnavailable";
                    throw error;
                }
            },
        },
    });

    const first = await manager.run();
    const failed = store.db.media_orphans[0];
    assert.equal(first.cos_orphans.failed, 1);
    assert.equal(failed.status, "failed");
    assert.equal(failed.deletion_attempts, 1);
    assert.equal(failed.next_deletion_at, new Date(now.value + 60_000).toISOString());

    now.value += 30_000;
    const deferred = await manager.run();
    assert.equal(deferred.cos_orphans.deferred, 1);
    assert.equal(deferred.cos_orphans.selected, 0);
    assert.equal(deleteCalls, 1);

    now.value += 31_000;
    const retried = await manager.run();
    assert.equal(retried.cos_orphans.deleted, 1);
    assert.equal(store.db.media_orphans[0].status, "deleted");
    assert.equal(store.db.media_orphans[0].deletion_attempts, 2);
    assert.equal(deleteCalls, 2);
    fs.rmSync(root, { recursive: true, force: true });
});

test("local orphan failures retain only relative identity and sanitized errors", async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "gohome-media-local-retry-"));
    const mediaDir = path.join(root, "media");
    const orphanPath = path.join(mediaDir, "event-evidence", "local.jpg");
    fs.mkdirSync(path.dirname(orphanPath), { recursive: true });
    fs.writeFileSync(orphanPath, "orphan");
    const now = { value: Date.parse("2026-08-04T08:00:00.000Z") };
    const oldTime = new Date(now.value - 4 * DAY_MS);
    fs.utimesSync(orphanPath, oldTime, oldTime);
    let deleteCalls = 0;
    const manager = new MediaLifecycleManager({
        mediaDir,
        clock: () => now.value,
        logger: { warn() {} },
        store: {
            db: {
                assets: [],
                events: [],
                family_memory_media: [],
                media_upload_intents: [],
                media_orphans: [],
                scheduler_runs: [],
            },
            async save() {},
        },
        cosStorage: { enabled: false },
        async deleteLocalFile(filePath) {
            deleteCalls += 1;
            if (deleteCalls === 1) {
                const error = new Error("permission denied at /Users/private/media/local.jpg");
                error.code = "EACCES";
                throw error;
            }
            await fs.promises.unlink(filePath);
        },
    });

    const result = await manager.run();
    const state = manager.store.db.media_orphans[0];
    assert.equal(result.local_orphans.failed, 1);
    assert.equal(state.storage_provider, "local");
    assert.equal(state.storage_key, "event-evidence/local.jpg");
    assert.equal(state.storage_key.includes(root), false);
    assert.equal(state.deletion_error.includes("/Users"), false);
    assert.equal(fs.existsSync(orphanPath), true);

    now.value += 59_000;
    const deferred = await manager.run();
    assert.equal(deferred.local_orphans.deferred, 1);
    assert.equal(deleteCalls, 1);

    now.value += 1_000;
    const retried = await manager.run();
    assert.equal(retried.local_orphans.deleted, 1);
    assert.equal(manager.store.db.media_orphans[0].status, "deleted");
    assert.equal(deleteCalls, 2);
    assert.equal(fs.existsSync(orphanPath), false);
    fs.rmSync(root, { recursive: true, force: true });
});

test("orphan state resolves when the physical object disappears before retry", async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "gohome-media-orphan-resolved-"));
    const mediaDir = path.join(root, "media");
    fs.mkdirSync(mediaDir, { recursive: true });
    const now = { value: Date.parse("2026-08-04T08:00:00.000Z") };
    const store = {
        db: {
            assets: [],
            events: [],
            family_memory_media: [],
            media_upload_intents: [],
            media_orphans: [],
            scheduler_runs: [],
        },
        async save() {},
    };
    let visible = true;
    const manager = new MediaLifecycleManager({
        store,
        mediaDir,
        clock: () => now.value,
        logger: { warn() {} },
        cosStorage: {
            enabled: true,
            async listObjects({ prefix }) {
                return visible && prefix === "event-evidence/"
                    ? [{ key: "event-evidence/missing.jpg", size: 10, last_modified: iso(now.value, 4) }]
                    : [];
            },
            async deleteObject() {
                const error = new Error("temporary failure");
                error.code = "ServiceUnavailable";
                throw error;
            },
        },
    });

    await manager.run();
    visible = false;
    now.value += 30_000;
    const result = await manager.run();
    assert.equal(result.cos_orphans.resolved, 1);
    assert.equal(store.db.media_orphans[0].status, "resolved");
    assert.equal(store.db.media_orphans[0].next_deletion_at, null);
    fs.rmSync(root, { recursive: true, force: true });
});

test("media lifecycle run summaries survive manager restart without changing dry-run orphan state", async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "gohome-media-run-audit-"));
    const mediaDir = path.join(root, "media");
    fs.mkdirSync(mediaDir, { recursive: true });
    const nowMs = Date.parse("2026-08-04T08:00:00.000Z");
    const store = {
        db: {
            assets: [],
            events: [],
            family_memory_media: [],
            media_upload_intents: [],
            media_orphans: [],
            scheduler_runs: [],
        },
        async save() {},
    };
    const firstManager = new MediaLifecycleManager({ store, mediaDir, clock: () => nowMs, cosStorage: { enabled: false } });
    const result = await firstManager.run({ dryRun: true });
    const secondManager = new MediaLifecycleManager({ store, mediaDir, clock: () => nowMs, cosStorage: { enabled: false } });

    assert.equal(store.db.scheduler_runs.length, 1);
    assert.equal(store.db.scheduler_runs[0].job_type, "media_lifecycle");
    assert.deepEqual(store.db.media_orphans, []);
    assert.deepEqual(secondManager.status().last_run, result);
    fs.rmSync(root, { recursive: true, force: true });
});

test("media lifecycle protects assets still referenced by product views", async () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "gohome-media-product-reference-"));
    const mediaDir = path.join(root, "media");
    fs.mkdirSync(mediaDir, { recursive: true });
    const nowMs = Date.parse("2026-08-02T08:00:00.000Z");
    const cardAsset = asset("card-image", "care-cards/2026-07-01/card.webp", iso(nowMs, 32), {
        storage_provider: "local",
        relative_path: "care-cards/2026-07-01/card.webp",
        purpose: "care_card_image",
    });
    const avatarAsset = asset("avatar-image", "profiles/avatar.jpg", iso(nowMs, 32), {
        storage_provider: "local",
        relative_path: "profiles/avatar.jpg",
        purpose: "transient_upload",
    });
    const unusedAsset = asset("unused-image", "care-cards/2026-07-01/unused.webp", iso(nowMs, 32), {
        storage_provider: "local",
        relative_path: "care-cards/2026-07-01/unused.webp",
        purpose: "care_card_image",
    });
    const linkedMemoryAsset = asset("linked-memory", "memory-media/linked.jpg", iso(nowMs, 32), {
        storage_provider: "local",
        relative_path: "memory-media/linked.jpg",
        purpose: "family_memory",
    });
    const abandonedMemoryAsset = asset("abandoned-memory", "memory-media/abandoned.jpg", iso(nowMs, 32), {
        storage_provider: "local",
        relative_path: "memory-media/abandoned.jpg",
        purpose: "family_memory",
    });
    for (const item of [cardAsset, avatarAsset, unusedAsset, linkedMemoryAsset, abandonedMemoryAsset]) {
        const filePath = path.join(mediaDir, item.relative_path);
        fs.mkdirSync(path.dirname(filePath), { recursive: true });
        fs.writeFileSync(filePath, item.id);
    }
    const store = {
        db: {
            assets: [cardAsset, avatarAsset, unusedAsset, linkedMemoryAsset, abandonedMemoryAsset],
            events: [],
            family_memory_media: [{ memory_id: "memory", asset_id: "linked-memory" }],
            media_upload_intents: [],
            care_cards: [{ id: "card", image_url: "/media/care-cards/2026-07-01/card.webp?token=short" }],
            users: [{ id: "user", metadata: { avatar_asset_id: "avatar-image" } }],
        },
        async save() {},
    };
    const manager = new MediaLifecycleManager({
        store,
        mediaDir,
        clock: () => nowMs,
        cosStorage: { enabled: false },
    });

    const result = await manager.run({ reconcileOrphans: false });

    assert.equal(cardAsset.retention_status, "active");
    assert.equal(cardAsset.retention_reason, "active_care_card");
    assert.equal(avatarAsset.retention_status, "active");
    assert.equal(avatarAsset.retention_reason, "active_avatar");
    assert.equal(unusedAsset.retention_status, "deleted");
    assert.equal(linkedMemoryAsset.retention_status, "active");
    assert.equal(linkedMemoryAsset.retention_class, "family_memory");
    assert.equal(abandonedMemoryAsset.retention_status, "deleted");
    assert.equal(abandonedMemoryAsset.retention_class, "transient_upload");
    assert.equal(result.protected, 3);
    assert.equal(result.deleted, 2);
    assert.equal(fs.existsSync(path.join(mediaDir, cardAsset.relative_path)), true);
    assert.equal(fs.existsSync(path.join(mediaDir, avatarAsset.relative_path)), true);
    assert.equal(fs.existsSync(path.join(mediaDir, unusedAsset.relative_path)), false);
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
        assert.deepEqual(calls, [{ reconcileOrphans: false, dryRun: false, classificationOnly: false }]);

        const dryRun = await fetch(`${baseUrl}/api/v1/internal/media-lifecycle/run`, {
            method: "POST",
            headers: {
                Authorization: "Bearer media-ops-secret",
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ dry_run: true }),
        });
        assert.equal(dryRun.status, 200);
        assert.deepEqual(calls[1], { reconcileOrphans: true, dryRun: true, classificationOnly: false });
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
        assert.deepEqual(calls, [{ reconcileOrphans: true, dryRun: true, classificationOnly: false }]);

        const deletion = await fetch(`${baseUrl}/api/v1/internal/media-lifecycle/run`, {
            method: "POST",
            headers,
            body: JSON.stringify({ dry_run: false }),
        });
        assert.equal(deletion.status, 409);
        assert.equal(calls.length, 1);

        const classification = await fetch(`${baseUrl}/api/v1/internal/media-lifecycle/run`, {
            method: "POST",
            headers,
            body: JSON.stringify({ classification_only: true }),
        });
        assert.equal(classification.status, 200);
        assert.deepEqual(calls[1], { reconcileOrphans: true, dryRun: false, classificationOnly: true });
    } finally {
        await new Promise((resolve) => app.server.close(resolve));
        fs.rmSync(dataDir, { recursive: true, force: true });
    }
});

test("media lifecycle PostgreSQL migrations expose retention, orphan retry, and event media identity", () => {
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
    const orphanMigration = fs.readFileSync(
        path.join(__dirname, "..", "migrations", "014_media_orphan_cleanup.sql"),
        "utf8",
    );
    for (const column of [
        "storage_provider",
        "storage_key",
        "first_seen_at",
        "last_seen_at",
        "deletion_attempts",
        "deletion_error",
        "next_deletion_at",
        "deleted_at",
        "resolved_at",
    ]) {
        assert.match(orphanMigration, new RegExp(`\\b${column}\\b`));
    }
    const identityMigration = fs.readFileSync(
        path.join(__dirname, "..", "migrations", "015_media_asset_identity.sql"),
        "utf8",
    );
    assert.match(identityMigration, /media_assets_storage_object_unique_idx/);
    assert.match(identityMigration, /media_assets_device_upload_idempotency_unique_idx/);
    assert.match(identityMigration, /metadata\s*->>\s*'device_upload_idempotency_key'/);
    const eventMediaMigration = fs.readFileSync(
        path.join(__dirname, "..", "migrations", "016_event_media_assets.sql"),
        "utf8",
    );
    assert.match(eventMediaMigration, /create table if not exists event_media_assets/);
    assert.match(eventMediaMigration, /unique \(event_id, asset_id\)/);
    assert.match(eventMediaMigration, /where canonical/);
    assert.match(eventMediaMigration, /payload\s*-\s*'evidence_media_assets'/);
});
