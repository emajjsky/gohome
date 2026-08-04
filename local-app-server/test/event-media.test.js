"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
    canonicalizeEventMedia,
    withoutEventMediaPayload,
} = require("../event-media");
const { buildCloudSeedBundle } = require("../../scripts/export-local-app-db");

test("event media keeps one relation per asset and one canonical asset per role", () => {
    const relations = canonicalizeEventMedia([
        { id: "r1", event_id: "e1", asset_id: "a1", role: "current", canonical: true },
        { id: "r2", event_id: "e1", asset_id: "a2", role: "current", canonical: true },
        { id: "r3", event_id: "e1", asset_id: "a1", role: "before", canonical: true },
        { id: "r4", event_id: "e2", asset_id: "a3", role: "current", canonical: true },
    ]);

    assert.deepEqual(relations.map((relation) => [relation.id, relation.role, relation.canonical]), [
        ["r1", "current", true],
        ["r2", "current", false],
        ["r4", "current", true],
    ]);
});

test("legacy event media payload is removed without mutating the inbound object", () => {
    const input = { evidence_media_assets: [{ asset_id: "a1" }], evidence: { score: 0.9 } };
    const output = withoutEventMediaPayload(input);

    assert.deepEqual(output, { evidence: { score: 0.9 } });
    assert.equal(input.evidence_media_assets.length, 1);
});

test("cloud export normalizes legacy event evidence into the relation table only", () => {
    const timestamp = "2026-08-04T08:00:00.000Z";
    const asset = (id) => ({
        id,
        family_id: "family-1",
        storage_provider: "cos",
        storage_key: `event-evidence/family-1/${id}.jpg`,
        content_type: "image/jpeg",
        size: 100,
        created_at: timestamp,
        updated_at: timestamp,
    });
    const bundle = buildCloudSeedBundle({
        created_at: timestamp,
        updated_at: timestamp,
        assets: [asset("a1"), asset("a2")],
        events: [{
            id: "e1",
            family_id: "family-1",
            idempotency_key: "event:e1",
            payload: {
                evidence: { score: 0.9 },
                evidence_media_assets: [
                    { asset_id: "a1", role: "current" },
                    { asset_id: "a2", role: "current" },
                ],
            },
            occurred_at: timestamp,
            created_at: timestamp,
            updated_at: timestamp,
        }],
    }, { exportedAt: timestamp });

    assert.equal(bundle.tables.events[0].payload.evidence_media_assets, undefined);
    assert.equal(bundle.tables.events[0].payload.evidence.score, 0.9);
    assert.deepEqual(bundle.tables.event_media_assets.map((relation) => relation.canonical), [true, false]);
});
