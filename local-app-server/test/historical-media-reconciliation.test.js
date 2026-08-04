"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
    buildHistoricalMediaPlan,
    originalSnapshotBasename,
    stableId,
} = require("../historical-media-reconciliation");

const generatedAt = "2026-08-04T10:00:00.000Z";

function snapshot(eventId, role, snapshotPath, patch = {}) {
    return {
        event_id: eventId,
        family_id: "family-1",
        device_id: "edge-1",
        camera_id: "camera-1",
        edge_event_id: `edge-${eventId}`,
        level: "critical",
        role,
        snapshot_path: snapshotPath,
        snapshot_id: "11",
        captured_at: generatedAt,
        postures: ["lying"],
        ...patch,
    };
}

function file(storageKey, checksum = "a".repeat(64)) {
    return {
        storage_key: storageKey,
        size_bytes: 128,
        source_modified_at: "2026-07-30T08:00:00.000Z",
        checksum_sha256: checksum,
    };
}

test("historical reconciliation replaces collision relations and protects unknown ownership", () => {
    const assets = [
        {
            id: "asset-wrong",
            storage_provider: "local",
            relative_path: "2026-07-30/900-other.jpg",
            snapshot_path: "camera_1/shot.jpg",
        },
        { id: "asset-existing", storage_provider: "cos", storage_key: "event-evidence/before.jpg", snapshot_path: "camera_1/before.jpg" },
        { id: "asset-tracked", relative_path: "tracked.jpg" },
    ];
    const relations = [
        { id: "relation-wrong", event_id: "event-1", asset_id: "asset-wrong", role: "current", canonical: true },
        { id: "relation-existing", event_id: "event-2", asset_id: "asset-existing", role: "before", canonical: true },
    ];
    const plan = buildHistoricalMediaPlan({
        files: [
            file("2026-07-30/613-shot.jpg"),
            file("2026-07-30/614-shot.jpg"),
            file("2026-07-30/615-before.jpg", "b".repeat(64)),
            file("memories/unknown.grid.webp", "c".repeat(64)),
            file("tracked.jpg", "d".repeat(64)),
        ],
        assets,
        relations,
        snapshots: [
            snapshot("event-1", "current", "camera_1/shot.jpg"),
            snapshot("event-2", "before", "camera_1/before.jpg"),
        ],
        orphanStates: [],
        generatedAt,
    });

    assert.deepEqual(plan.summary, {
        files_scanned: 5,
        untracked_candidates: 4,
        recoverable_files: 3,
        protected_files: 1,
        relations_to_create: 3,
        relations_to_remove: 1,
        events_to_update: 1,
    });
    assert.deepEqual(plan.relation_ids_to_remove, ["relation-wrong"]);
    assert.equal(plan.protected_orphans[0].protection_reason, "family_memory_derivative_not_original");
    assert.equal(plan.assets_to_create.every((asset) => asset.id.startsWith("asset-recovered-")), true);
    assert.equal(plan.assets_to_create.every((asset) => asset.metadata.checksum_sha256.length === 64), true);
    assert.equal(plan.assets_to_create.every((asset) => asset.metadata.local_camera_id === "1"), true);
    const currentRelations = plan.relations_to_create.filter((relation) => relation.event_id === "event-1");
    assert.equal(currentRelations.filter((relation) => relation.canonical).length, 1);
    assert.equal(currentRelations.filter((relation) => relation.metadata.duplicate_of_asset_id).length, 1);
    assert.equal(plan.relations_to_create.find((relation) => relation.event_id === "event-2").canonical, false);
    assert.equal(plan.events_to_update[0].media_asset_id, stableId("asset-recovered-", "local\u00002026-07-30/613-shot.jpg"));
    assert.match(plan.plan_hash, /^[a-f0-9]{64}$/);
});

test("conflicting bytes for the same historical snapshot require manual review", () => {
    const plan = buildHistoricalMediaPlan({
        files: [
            file("2026-07-30/613-shot.jpg", "a".repeat(64)),
            file("2026-07-30/614-shot.jpg", "b".repeat(64)),
        ],
        assets: [],
        relations: [],
        snapshots: [snapshot("event-1", "current", "camera_1/shot.jpg")],
        orphanStates: [],
        generatedAt,
    });

    assert.equal(plan.summary.recoverable_files, 0);
    assert.equal(plan.summary.protected_files, 2);
    assert.equal(plan.protected_orphans.every((orphan) => orphan.protection_reason === "snapshot_content_conflict"), true);
});

test("one event snapshot basename with multiple roles is never guessed", () => {
    const plan = buildHistoricalMediaPlan({
        files: [file("2026-07-30/613-shot.jpg")],
        assets: [],
        relations: [],
        snapshots: [
            snapshot("event-1", "before", "camera_1/shot.jpg"),
            snapshot("event-1", "current", "camera_1/shot.jpg"),
        ],
        orphanStates: [],
        generatedAt,
    });

    assert.equal(plan.summary.recoverable_files, 0);
    assert.equal(plan.protected_orphans[0].protection_reason, "ambiguous_event_role");
});

test("legacy numeric prefix parsing is isolated from permanent recovered identity", () => {
    assert.deepEqual(originalSnapshotBasename("2026-07-30/613-shot.jpg"), {
        legacy_asset_id: "613",
        snapshot_basename: "shot.jpg",
    });
    assert.equal(originalSnapshotBasename("memories/photo.jpg"), null);
    assert.notEqual(
        stableId("asset-recovered-", "local\u00002026-07-30/613-shot.jpg"),
        stableId("asset-recovered-", "local\u00002026-07-31/613-shot.jpg"),
    );
});
