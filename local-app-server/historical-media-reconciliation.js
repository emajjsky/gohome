"use strict";

const crypto = require("crypto");
const path = require("path");

const { eventMediaRole } = require("./event-media");

function text(value) {
    return value === null || value === undefined ? "" : String(value);
}

function basename(value) {
    return path.posix.basename(text(value).replace(/\\/g, "/"));
}

function originalSnapshotBasename(fileName) {
    const name = basename(fileName);
    const match = name.match(/^([0-9]+)-(.+)$/);
    return match ? { legacy_asset_id: match[1], snapshot_basename: match[2] } : null;
}

function stableId(prefix, value) {
    return `${prefix}${crypto.createHash("sha256").update(value).digest("hex")}`;
}

function contentType(fileName) {
    const extension = path.extname(fileName).toLowerCase();
    if (extension === ".png") return "image/png";
    if (extension === ".webp") return "image/webp";
    if (extension === ".heic" || extension === ".heif") return "image/heic";
    if (extension === ".mp4") return "video/mp4";
    if (extension === ".mov") return "video/quicktime";
    return "image/jpeg";
}

function timestamp(value) {
    const parsed = Date.parse(value || "");
    return Number.isFinite(parsed) ? parsed : 0;
}

function assetSnapshotBasename(asset) {
    const direct = basename(asset?.snapshot_path);
    if (direct) return direct;
    const parsed = originalSnapshotBasename(asset?.relative_path || asset?.storage_key || asset?.file_name);
    return parsed?.snapshot_basename || basename(asset?.file_name);
}

function roleCandidateOrder(role, left, right) {
    const timeDelta = timestamp(left.captured_at) - timestamp(right.captured_at);
    if (timeDelta) return role === "before" ? timeDelta : -timeDelta;
    return left.storage_key.localeCompare(right.storage_key);
}

function protectionReason(file) {
    const key = text(file.storage_key).toLowerCase();
    if (key.includes("/care-card") || key.startsWith("care-card")) return "care_card_ownership_not_reconciled";
    if (/\.grid\.(webp|jpe?g|png)$/.test(key)) return "family_memory_derivative_not_original";
    if (key.includes("/memories/") || key.startsWith("memories/")) return "family_memory_ownership_not_reconciled";
    return "ownership_not_reconciled";
}

function buildHistoricalMediaPlan({ files, assets, relations, snapshots, orphanStates, generatedAt }) {
    const trackedKeys = new Set((assets || []).map((asset) => (
        text(asset.relative_path || asset.storage_key).replace(/^\/+/, "")
    )).filter(Boolean));
    const assetsById = new Map((assets || []).map((asset) => [text(asset.id), asset]));
    const orphanByKey = new Map((orphanStates || []).map((orphan) => [text(orphan.storage_key), orphan]));
    const referencesByBasename = new Map();
    for (const snapshot of snapshots || []) {
        const snapshotBasename = basename(snapshot.snapshot_path);
        if (!snapshotBasename || !snapshot.event_id) continue;
        const reference = {
            event_id: text(snapshot.event_id),
            family_id: text(snapshot.family_id) || null,
            device_id: text(snapshot.device_id) || null,
            camera_id: text(snapshot.camera_id) || null,
            edge_event_id: text(snapshot.edge_event_id),
            level: text(snapshot.level || "warning"),
            role: eventMediaRole(snapshot.role),
            snapshot_path: text(snapshot.snapshot_path),
            snapshot_basename: snapshotBasename,
            snapshot_id: text(snapshot.snapshot_id) || null,
            captured_at: text(snapshot.captured_at || snapshot.occurred_at) || null,
            postures: Array.isArray(snapshot.postures) ? snapshot.postures.map(String).slice(0, 8) : [],
        };
        const rows = referencesByBasename.get(snapshotBasename) || [];
        if (!rows.some((row) => row.event_id === reference.event_id && row.role === reference.role)) rows.push(reference);
        referencesByBasename.set(snapshotBasename, rows);
    }

    const candidates = (files || [])
        .filter((file) => !trackedKeys.has(text(file.storage_key)))
        .map((file) => ({
            storage_key: text(file.storage_key),
            size_bytes: Number(file.size_bytes || 0),
            source_modified_at: text(file.source_modified_at),
            checksum_sha256: text(file.checksum_sha256),
            ...originalSnapshotBasename(file.storage_key),
        }))
        .sort((left, right) => left.storage_key.localeCompare(right.storage_key));
    const mapped = [];
    const protectedFiles = [];
    for (const file of candidates) {
        const references = file.snapshot_basename ? referencesByBasename.get(file.snapshot_basename) || [] : [];
        const eventIds = new Set(references.map((reference) => reference.event_id));
        const eventRoles = new Set(references.map((reference) => `${reference.event_id}\u0000${reference.role}`));
        if (eventIds.size !== 1 || eventRoles.size !== 1) {
            protectedFiles.push({
                ...file,
                protection_reason: eventIds.size > 1
                    ? "ambiguous_event_ownership"
                    : (eventRoles.size > 1 ? "ambiguous_event_role" : protectionReason(file)),
                candidate_event_ids: [...eventIds].sort(),
            });
            continue;
        }
        const reference = [...references].sort((left, right) => (
            left.role.localeCompare(right.role) || text(left.captured_at).localeCompare(text(right.captured_at))
        ))[0];
        mapped.push({ ...file, ...reference });
    }

    const descriptorGroups = new Map();
    for (const item of mapped) {
        const key = `${item.event_id}\u0000${item.role}\u0000${item.snapshot_basename}`;
        const rows = descriptorGroups.get(key) || [];
        rows.push(item);
        descriptorGroups.set(key, rows);
    }
    const recoverable = [];
    for (const rows of descriptorGroups.values()) {
        const checksums = new Set(rows.map((row) => row.checksum_sha256).filter(Boolean));
        if (checksums.size > 1 || checksums.size === 0) {
            for (const row of rows) {
                protectedFiles.push({ ...row, protection_reason: "snapshot_content_conflict", candidate_event_ids: [row.event_id] });
            }
            continue;
        }
        recoverable.push(...rows);
    }

    const relationRows = relations || [];
    const roleGroups = new Map();
    for (const item of recoverable) {
        const key = `${item.event_id}\u0000${item.role}`;
        const rows = roleGroups.get(key) || [];
        rows.push(item);
        roleGroups.set(key, rows);
    }
    const assetsToCreate = [];
    const relationsToCreate = [];
    const relationIdsToRemove = new Set();
    const eventsToUpdate = [];
    for (const [groupKey, rows] of roleGroups) {
        const [eventId, role] = groupKey.split("\u0000");
        const expectedBasenames = new Set(rows.map((row) => row.snapshot_basename));
        const existing = relationRows.filter((relation) => (
            text(relation.event_id) === eventId && eventMediaRole(relation.role) === role
        ));
        const matchingExisting = existing.filter((relation) => (
            expectedBasenames.has(assetSnapshotBasename(assetsById.get(text(relation.asset_id))))
        ));
        for (const relation of existing) {
            if (!matchingExisting.includes(relation)) relationIdsToRemove.add(text(relation.id));
        }
        rows.sort((left, right) => roleCandidateOrder(role, left, right));
        const existingCanonical = matchingExisting.find((relation) => relation.canonical !== false);
        const canonicalAssetId = text(existingCanonical?.asset_id || matchingExisting[0]?.asset_id)
            || stableId("asset-recovered-", `local\u0000${rows[0].storage_key}`);
        for (const row of rows) {
            const assetId = stableId("asset-recovered-", `local\u0000${row.storage_key}`);
            const exactDuplicates = rows.filter((candidate) => (
                candidate.snapshot_basename === row.snapshot_basename
                && candidate.checksum_sha256 === row.checksum_sha256
            ));
            const duplicateLeader = exactDuplicates
                .sort((left, right) => left.storage_key.localeCompare(right.storage_key))[0];
            assetsToCreate.push({
                id: assetId,
                family_id: row.family_id,
                device_id: row.device_id,
                camera_id: row.camera_id,
                file_name: basename(row.storage_key),
                content_type: contentType(row.storage_key),
                snapshot_path: row.snapshot_path,
                relative_path: row.storage_key,
                storage_provider: "local",
                storage_key: row.storage_key,
                edge_event_id: row.edge_event_id,
                size_bytes: row.size_bytes,
                metadata: {
                    purpose: "event_evidence_recovered",
                    checksum_sha256: row.checksum_sha256,
                    recovered_from_historical_identity_collision: true,
                    reconciliation_version: "historical-media-v1",
                    original_numeric_asset_id: row.legacy_asset_id,
                    evidence_frame_role: role,
                    captured_at: row.captured_at,
                    snapshot_id: row.snapshot_id,
                },
                created_at: row.source_modified_at || generatedAt,
                updated_at: generatedAt,
            });
            const canonical = assetId === canonicalAssetId;
            relationsToCreate.push({
                id: stableId("event-media-recovered-", `${eventId}\u0000${assetId}`),
                event_id: eventId,
                asset_id: assetId,
                role,
                canonical,
                captured_at: row.captured_at,
                snapshot_id: row.snapshot_id,
                postures: row.postures,
                metadata: {
                    reconciliation_version: "historical-media-v1",
                    checksum_sha256: row.checksum_sha256,
                    duplicate_of_asset_id: duplicateLeader.storage_key === row.storage_key ? null : canonicalAssetId,
                },
                created_at: row.source_modified_at || generatedAt,
                updated_at: generatedAt,
            });
        }
        if (role === "current" && canonicalAssetId.startsWith("asset-recovered-")) {
            eventsToUpdate.push({ event_id: eventId, media_asset_id: canonicalAssetId });
        }
    }

    const protectedAuditRows = protectedFiles.map((file) => {
        const previous = orphanByKey.get(file.storage_key);
        return {
            storage_provider: "local",
            storage_key: file.storage_key,
            size_bytes: file.size_bytes,
            source_modified_at: file.source_modified_at,
            first_seen_at: previous?.first_seen_at || generatedAt,
            last_seen_at: generatedAt,
            status: "protected",
            protection_reason: file.protection_reason,
            metadata: {
                reconciliation_version: "historical-media-v1",
                checksum_sha256: file.checksum_sha256,
                legacy_asset_id: file.legacy_asset_id || null,
                snapshot_basename: file.snapshot_basename || null,
                candidate_event_ids: file.candidate_event_ids || [],
            },
            deletion_attempts: 0,
            deletion_error: "",
            next_deletion_at: null,
            deleted_at: null,
            resolved_at: null,
            created_at: previous?.created_at || generatedAt,
            updated_at: generatedAt,
        };
    });
    const summary = {
        files_scanned: (files || []).length,
        untracked_candidates: candidates.length,
        recoverable_files: assetsToCreate.length,
        protected_files: protectedAuditRows.length,
        relations_to_create: relationsToCreate.length,
        relations_to_remove: relationIdsToRemove.size,
        events_to_update: eventsToUpdate.length,
    };
    const plan = {
        schema_version: "historical-media-reconciliation-v1",
        generated_at: generatedAt,
        summary,
        assets_to_create: assetsToCreate,
        relations_to_create: relationsToCreate,
        relation_ids_to_remove: [...relationIdsToRemove].sort(),
        events_to_update: eventsToUpdate,
        protected_orphans: protectedAuditRows,
    };
    plan.plan_hash = crypto.createHash("sha256").update(JSON.stringify(plan)).digest("hex");
    return plan;
}

module.exports = {
    buildHistoricalMediaPlan,
    originalSnapshotBasename,
    stableId,
};
