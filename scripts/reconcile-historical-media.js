#!/usr/bin/env node
"use strict";

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const { Pool } = require("pg");

const { buildHistoricalMediaPlan } = require("../local-app-server/historical-media-reconciliation");
const { listLocalFiles } = require("../local-app-server/media-lifecycle");

function parseArgs(argv) {
    const options = {
        apply: false,
        mediaRoot: process.env.GOHOME_MEDIA_ROOT || "/var/lib/gohome/app-server/media",
        output: "",
        planFile: "",
        expectedHash: "",
    };
    for (let index = 0; index < argv.length; index += 1) {
        const argument = argv[index];
        if (argument === "--apply") options.apply = true;
        else if (argument === "--media-root") options.mediaRoot = argv[++index];
        else if (argument === "--out") options.output = argv[++index];
        else if (argument === "--plan") options.planFile = argv[++index];
        else if (argument === "--plan-hash") options.expectedHash = argv[++index];
        else throw new Error(`unknown argument: ${argument}`);
    }
    if (options.apply && (!options.planFile || !options.expectedHash)) {
        throw new Error("--apply requires --plan and --plan-hash");
    }
    return options;
}

function sha256File(filePath) {
    return new Promise((resolve, reject) => {
        const hash = crypto.createHash("sha256");
        const stream = fs.createReadStream(filePath);
        stream.on("error", reject);
        stream.on("data", (chunk) => hash.update(chunk));
        stream.on("end", () => resolve(hash.digest("hex")));
    });
}

async function loadInputs(client, mediaRoot) {
    const assetsResult = await client.query("select * from media_assets where retention_status <> 'deleted'");
    const relationsResult = await client.query("select * from event_media_assets");
    const snapshotsResult = await client.query(`
            select
                event.id as event_id,
                event.family_id,
                event.device_id,
                event.camera_id,
                event.edge_event_id,
                event.level,
                event.occurred_at,
                snapshot.value->>'role' as role,
                snapshot.value->>'snapshot_path' as snapshot_path,
                snapshot.value->>'snapshot_id' as snapshot_id,
                coalesce(snapshot.value->>'observed_at', snapshot.value->>'captured_at') as captured_at,
                case when jsonb_typeof(snapshot.value->'postures') = 'array'
                     then snapshot.value->'postures' else '[]'::jsonb end as postures
            from events as event
            cross join lateral jsonb_array_elements(
                case when jsonb_typeof(event.payload->'temporal_evidence_bundle'->'snapshots') = 'array'
                     then event.payload->'temporal_evidence_bundle'->'snapshots' else '[]'::jsonb end
            ) as snapshot(value)
            where coalesce(snapshot.value->>'snapshot_path', '') <> ''
        `);
    const orphanResult = await client.query("select * from media_orphan_cleanup where storage_provider = 'local'");
    const trackedKeys = new Set(assetsResult.rows.map((asset) => (
        String(asset.relative_path || asset.storage_key || "").replace(/^\/+/, "")
    )).filter(Boolean));
    const files = await listLocalFiles(mediaRoot);
    const fileRows = [];
    for (const file of files) {
        const row = {
            storage_key: file.key,
            size_bytes: file.size,
            source_modified_at: new Date(Math.trunc(file.last_modified_ms)).toISOString(),
            checksum_sha256: "",
        };
        if (!trackedKeys.has(file.key)) row.checksum_sha256 = await sha256File(file.path);
        fileRows.push(row);
    }
    return {
        files: fileRows,
        assets: assetsResult.rows,
        relations: relationsResult.rows,
        snapshots: snapshotsResult.rows,
        orphanStates: orphanResult.rows,
    };
}

function verifyPlanHash(plan, expectedHash) {
    const suppliedHash = String(plan.plan_hash || "");
    const withoutHash = { ...plan };
    delete withoutHash.plan_hash;
    const calculated = crypto.createHash("sha256").update(JSON.stringify(withoutHash)).digest("hex");
    if (!suppliedHash || suppliedHash !== calculated || suppliedHash !== expectedHash) {
        throw new Error("historical media plan hash mismatch");
    }
}

async function applyPlan(client, plan, mediaRoot) {
    await client.query("begin isolation level serializable");
    try {
        await client.query("select pg_advisory_xact_lock(hashtext('gohome-historical-media-reconciliation'))");
        await client.query("select pg_advisory_xact_lock(hashtext('gohome-app-store'))");
        await client.query("select pg_advisory_xact_lock(hashtext('gohome-media-lifecycle'))");
        const currentInputs = await loadInputs(client, mediaRoot);
        const currentPlan = buildHistoricalMediaPlan({ ...currentInputs, generatedAt: plan.generated_at });
        if (currentPlan.plan_hash !== plan.plan_hash) throw new Error("historical media state changed after preview");
        for (const asset of plan.assets_to_create) {
            await client.query(`
                insert into media_assets (
                    id, family_id, device_id, camera_id, file_name, content_type, snapshot_path,
                    relative_path, storage_provider, storage_key, edge_event_id, size_bytes, metadata,
                    retention_class, retention_status, retention_reason, created_at, updated_at
                ) values (
                    $1, $2, $3, $4, $5, $6, $7,
                    $8, $9, $10, $11, $12, $13::jsonb,
                    '', 'active', 'historical_event_relation', $14, $15
                )
            `, [
                asset.id, asset.family_id, asset.device_id, asset.camera_id, asset.file_name,
                asset.content_type, asset.snapshot_path, asset.relative_path, asset.storage_provider,
                asset.storage_key, asset.edge_event_id, asset.size_bytes, JSON.stringify(asset.metadata),
                asset.created_at, asset.updated_at,
            ]);
        }
        if (plan.relation_ids_to_remove.length) {
            await client.query("delete from event_media_assets where id = any($1::text[])", [plan.relation_ids_to_remove]);
        }
        for (const relation of plan.relations_to_create) {
            await client.query(`
                insert into event_media_assets (
                    id, event_id, asset_id, role, canonical, captured_at, snapshot_id,
                    postures, metadata, created_at, updated_at
                ) values ($1, $2, $3, $4, false, $5, $6, $7::jsonb, $8::jsonb, $9, $10)
            `, [
                relation.id, relation.event_id, relation.asset_id, relation.role, relation.captured_at,
                relation.snapshot_id, JSON.stringify(relation.postures), JSON.stringify(relation.metadata),
                relation.created_at, relation.updated_at,
            ]);
        }
        for (const relation of plan.relations_to_create.filter((item) => item.canonical)) {
            await client.query("update event_media_assets set canonical = true, updated_at = $2 where id = $1", [
                relation.id, plan.generated_at,
            ]);
        }
        for (const update of plan.events_to_update) {
            await client.query("update events set media_asset_id = $2, updated_at = $3 where id = $1", [
                update.event_id, update.media_asset_id, plan.generated_at,
            ]);
        }
        const auditRows = [
            ...plan.assets_to_create.map((asset) => ({
                storage_provider: "local",
                storage_key: asset.storage_key,
                size_bytes: asset.size_bytes,
                source_modified_at: asset.created_at,
                first_seen_at: plan.generated_at,
                last_seen_at: plan.generated_at,
                status: "resolved",
                protection_reason: "",
                metadata: {
                    reconciliation_version: "historical-media-v1",
                    resolution: "recovered_event_relation",
                    asset_id: asset.id,
                    checksum_sha256: asset.metadata.checksum_sha256,
                },
                resolved_at: plan.generated_at,
                created_at: plan.generated_at,
                updated_at: plan.generated_at,
            })),
            ...plan.protected_orphans,
        ];
        for (const audit of auditRows) {
            await client.query(`
                insert into media_orphan_cleanup (
                    storage_provider, storage_key, size_bytes, source_modified_at, first_seen_at,
                    last_seen_at, status, protection_reason, metadata, deletion_attempts,
                    deletion_error, next_deletion_at, deleted_at, resolved_at, created_at, updated_at
                ) values (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8, $9::jsonb, 0,
                    '', null, null, $10, $11, $12
                )
                on conflict (storage_provider, storage_key) do update set
                    size_bytes = excluded.size_bytes,
                    source_modified_at = excluded.source_modified_at,
                    last_seen_at = excluded.last_seen_at,
                    status = excluded.status,
                    protection_reason = excluded.protection_reason,
                    metadata = excluded.metadata,
                    deletion_attempts = 0,
                    deletion_error = '',
                    next_deletion_at = null,
                    deleted_at = null,
                    resolved_at = excluded.resolved_at,
                    updated_at = excluded.updated_at
            `, [
                audit.storage_provider, audit.storage_key, audit.size_bytes, audit.source_modified_at,
                audit.first_seen_at, audit.last_seen_at, audit.status, audit.protection_reason,
                JSON.stringify(audit.metadata || {}), audit.resolved_at || null,
                audit.created_at, audit.updated_at,
            ]);
        }
        await client.query(`
            insert into scheduler_runs (
                id, family_id, job_type, status, scope, result, error_message,
                started_at, finished_at, created_at, updated_at
            ) values (
                $1, null, 'historical_media_reconciliation', 'succeeded', $2::jsonb, $3::jsonb, '',
                $4, $4, $4, $4
            )
        `, [
            crypto.randomUUID(),
            JSON.stringify({ plan_hash: plan.plan_hash, schema_version: plan.schema_version }),
            JSON.stringify(plan.summary),
            plan.generated_at,
        ]);
        await client.query("commit");
    } catch (error) {
        await client.query("rollback");
        throw error;
    }
}

async function main() {
    const options = parseArgs(process.argv.slice(2));
    const databaseUrl = process.env.GOHOME_DATABASE_URL || process.env.DATABASE_URL;
    if (!databaseUrl) throw new Error("GOHOME_DATABASE_URL or DATABASE_URL is required");
    const pool = new Pool({ connectionString: databaseUrl });
    const client = await pool.connect();
    try {
        if (options.apply) {
            const approved = JSON.parse(fs.readFileSync(path.resolve(options.planFile), "utf8"));
            verifyPlanHash(approved, options.expectedHash);
            await applyPlan(client, approved, path.resolve(options.mediaRoot));
            process.stdout.write(`${JSON.stringify({ ok: true, applied: true, plan_hash: approved.plan_hash, summary: approved.summary }, null, 2)}\n`);
            return;
        }
        const inputs = await loadInputs(client, path.resolve(options.mediaRoot));
        const plan = buildHistoricalMediaPlan({ ...inputs, generatedAt: new Date().toISOString() });
        const output = `${JSON.stringify(plan, null, 2)}\n`;
        if (options.output) fs.writeFileSync(path.resolve(options.output), output, { mode: 0o600 });
        process.stdout.write(`${JSON.stringify({ ok: true, applied: false, plan_hash: plan.plan_hash, summary: plan.summary, output: options.output || null }, null, 2)}\n`);
    } finally {
        client.release();
        await pool.end();
    }
}

if (require.main === module) {
    main().catch((error) => {
        console.error(error.message || error);
        process.exit(1);
    });
}

module.exports = {
    applyPlan,
    loadInputs,
    parseArgs,
    verifyPlanHash,
};
